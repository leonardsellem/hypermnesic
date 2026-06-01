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
