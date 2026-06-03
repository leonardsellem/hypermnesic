"""U12 guard — protected-path denylist + within-repo + allowlist."""

from __future__ import annotations

import subprocess

import pytest

from hypermnesic import serialize


@pytest.mark.parametrize("bad", [
    ".git/config",
    "CLAUDE.md",
    "AGENTS.md",
    "projects/x/AGENTS.md",                 # nested instruction file
    ".github/workflows/ci.yml",             # foreign repo's CI
    ".obsidian/workspace.json",
    "scripts/evil.py",
    "skills/my-skill/SKILL.md",             # vault-local agent skills are governance
    "bin/run",
    ".gitignore",
    "views/projects.yml",
    ".hypermnesic/index.db",
])
def test_protected_paths_refused(make_corpus, bad):
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    with pytest.raises(serialize.WriteGuardError):
        serialize.check(repo, bad)


@pytest.mark.parametrize("ok", [
    "notes/new-note.md",
    "concepts/idea.md",
    "projects/x/notes/thing.md",
])
def test_writable_paths_allowed(make_corpus, ok):
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    assert serialize.check(repo, ok) == ok


def test_traversal_and_absolute_refused(make_corpus):
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    with pytest.raises(serialize.WriteGuardError):
        serialize.check(repo, "../../etc/passwd")
    with pytest.raises(serialize.WriteGuardError):
        serialize.check(repo, "/etc/passwd")


def test_allowlist_enforced(make_corpus):
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    assert serialize.check(repo, "notes/a.md", allowlist=["notes/"]) == "notes/a.md"
    with pytest.raises(serialize.WriteGuardError):
        serialize.check(repo, "concepts/a.md", allowlist=["notes/"])


def test_rule_generalizes_to_unseen_repo(make_corpus):
    # the denylist is a RULE, not a fixed gbrain list — holds for any repo
    repo = make_corpus({"README.md": "# r\n\nx\n"})
    for bad in ("CLAUDE.md", ".github/workflows/x.yml", "deep/nested/AGENTS.md"):
        with pytest.raises(serialize.WriteGuardError):
            serialize.check(repo, bad)


# --- U1: the extracted writable_reason predicate (single-sourced from check) ---
# The folder-discovery tool (U2/U3) classifies a folder by probing a file UNDER it
# with this predicate, so discovery can never disagree with what commit_note accepts.
# check() now wraps this predicate; these pin the predicate independently.


@pytest.mark.parametrize("ok", [
    "notes/a.md",
    "projects/x/y.md",          # blocklist permits the operator's content folders today
    "people/bob.md",
    "meetings/2026/standup.md",
])
def test_writable_reason_writable_classes_are_none(ok):
    assert serialize.writable_reason(ok, allowlist=None) is None


def test_writable_reason_protected_classes_return_reason():
    # top-level protected dir, instruction file, and the NESTED-protected parity case
    assert "skills/" in serialize.writable_reason("skills/s.md", allowlist=None)
    assert serialize.writable_reason("skills/s.md", allowlist=None) is not None
    assert "instruction" in serialize.writable_reason("notes/AGENTS.md", allowlist=None).lower()
    # nested protected — projects/scripts/ is refused even though projects/ is writable:
    # this is the parity-lie guard (commit_note refuses projects/scripts/n.md too)
    nested = serialize.writable_reason("projects/scripts/n.md", allowlist=None)
    assert nested is not None and "scripts/" in nested


def test_writable_reason_pins_blocklist_governance_baseline():
    # DOCUMENTED BASELINE for the U6 governance-fence decision: in blocklist mode
    # (allowlist=None) protected_reason does NOT refuse these governance/CI/non-.md
    # classes — they are writable at the predicate level today. The 4-prefix allowlist
    # only blocked them by exclusion (the server coercion). The U6 delta decides whether
    # to add a positive content-surface fence; this asserts the pre-decision baseline.
    for governance in ("Dockerfile", "Makefile", "node_modules/x.md", ".gitlab-ci.yml",
                       ".pre-commit-config.yaml", "uv.lock"):
        assert serialize.writable_reason(governance, allowlist=None) is None, governance


def test_writable_reason_allowlist_mode():
    assert serialize.writable_reason("notes/a.md", allowlist=["notes/"]) is None
    outside = serialize.writable_reason("concepts/a.md", allowlist=["notes/"])
    assert outside == "not in writable allowlist"
    # protected-path refusal precedes the allowlist check (a protected dir inside an
    # allowed prefix is still refused, with the protected reason — not the allowlist one)
    assert "protected dir" in serialize.writable_reason("notes/.github/ci.yml",
                                                        allowlist=["notes/"])


def test_check_wraps_writable_reason_behavior_preserving(make_corpus):
    # check() raises iff writable_reason is non-None, preserving its two distinct messages.
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    assert serialize.check(repo, "notes/a.md") == "notes/a.md"          # writable → returns path
    with pytest.raises(serialize.WriteGuardError, match="protected path"):
        serialize.check(repo, "skills/s.md")                            # protected message kept
    with pytest.raises(serialize.WriteGuardError, match="not in writable allowlist"):
        serialize.check(repo, "concepts/a.md", allowlist=["notes/"])    # allowlist message kept


# --- serialization (single-indexer lock, path locks, preflight) ---

def test_index_write_lock_serializes(tmp_path):
    a = serialize.index_write_lock(tmp_path).acquire()
    with pytest.raises(serialize.LockBusyError):
        serialize.index_write_lock(tmp_path).acquire()   # second holder blocked
    a.release()
    b = serialize.index_write_lock(tmp_path).acquire()   # free again after release
    b.release()


def test_path_locks_are_independent(tmp_path):
    la = serialize.path_lock(tmp_path, "notes/a.md").acquire()
    lb = serialize.path_lock(tmp_path, "notes/b.md").acquire()   # different path → ok
    with pytest.raises(serialize.LockBusyError):
        serialize.path_lock(tmp_path, "notes/a.md").acquire()    # same path → busy
    la.release()
    lb.release()


def test_concurrent_broad_writer_blocked(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nbody.\n"})
    held = serialize.index_write_lock(repo).acquire()    # simulate another indexer
    try:
        with pytest.raises(serialize.LockBusyError):
            __import__("hypermnesic.index", fromlist=["build_index"]).build_index(
                repo, fake_embedder)
    finally:
        held.release()


def test_preflight_clean_ok_dirty_raises(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nbody.\n"})
    head = serialize.preflight(repo, require_clean=True)
    assert head
    (repo / "a.md").write_text("# A\n\nDIRTY uncommitted.\n", encoding="utf-8")
    with pytest.raises(serialize.DirtyTreeError):
        serialize.preflight(repo, require_clean=True)


def test_preflight_head_drift_raises(make_corpus):
    repo = make_corpus({"a.md": "# A\n\nbody.\n"})
    old = serialize.preflight(repo)
    (repo / "b.md").write_text("# B\n\nx\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "drift"],
                   check=True, capture_output=True)
    with pytest.raises(serialize.HeadDriftError):
        serialize.preflight(repo, expected_head=old)
