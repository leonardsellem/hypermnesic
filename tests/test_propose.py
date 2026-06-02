"""U18 — review-gated proposal/PR queue (the foundation). [R11/R10/F5/KD7/#12]

Spec-as-tests: the trust-critical behaviours are "never auto-merges" and
"never a silent write". Every proposal write passes the diff-or-die gate on the
branch-commit path (AE3 re-proven), multi-file proposals are atomic, the path
scope is an explicit allowlist, slugs are sanitised, and a cold-start PR flood is
bounded by a global proposal budget.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from hypermnesic import audit_log as al
from hypermnesic import frontmatter_gate as fg
from hypermnesic import index as index_mod
from hypermnesic import propose as pr
from hypermnesic import serialize


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


def _branches(repo) -> list[str]:
    out = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return out.splitlines()


# A canonical curated note (surgical scalar-set holds → clean single-field edit).
_TOPIC = ("---\ntitle: Topic\nstatus: draft\ncreated: 2026-05-01\n---\n"
          "# Topic\n\nbody about alpha.\n")
# Non-canonical YAML: setting/adding a field reflows an untouched key → gate aborts.
_NONCANON = "---\nstatus:    active\ncreated: 2026-05-02\n---\nbody about beta.\n"
# A note with a block list — AE3: editing one scalar must leave the list bytes intact.
_AE3 = ("---\ntitle: N\nstatus: active\ncreated: 2026-05-02\ntags:\n"
        "    - one\n    - two\n---\nAE3 body text.\n")


def _env(make_corpus, fake_embedder, tmp_path, files):
    repo = make_corpus(files)
    idx = index_mod.build_index(repo, fake_embedder)
    log = al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test")
    calls = []

    def fake_gh(*, title, body, branch, base):
        calls.append({"title": title, "body": body, "branch": branch, "base": base})
        return "https://github.com/o/r/pull/7"

    return repo, idx, log, calls, fake_gh


# --- slug sanitisation (security) ---------------------------------------------

def test_safe_slug_neutralises_traversal_metachars_and_leading_dash():
    s = pr.safe_slug("--rm -rf; weird/../Name!! danger")
    assert ".." not in s
    assert not s.startswith("-")
    assert not s.startswith("/")
    assert all(c.isalnum() or c in "-_/" for c in s)
    assert 0 < len(s) <= 60


def test_safe_slug_falls_back_for_empty_input():
    s = pr.safe_slug("!!!")
    assert s and all(c.isalnum() or c in "-_/" for c in s)


# --- F5: a single-file proposal -----------------------------------------------

def test_single_file_proposal_branch_pr_body_head_unchanged(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/topic.md": _TOPIC})
    head_before = _git(repo, "rev-parse", "HEAD")

    res = pr.propose(
        repo, [pr.Change(path="notes/topic.md", set_fields={"status": "active"})],
        slug="promote-topic", summary="promote topic to active",
        why="status drifted from reality", source="notes/topic.md",
        allowlist=["notes/"], idx=idx, log=log, gh_create=fake_gh)

    assert res.branch == "hypermnesic/proposals/promote-topic"
    assert res.files == ["notes/topic.md"]
    assert res.pr_url.endswith("/pull/7") and res.pr_skipped is False
    # the working branch HEAD is untouched — never auto-merged
    assert _git(repo, "rev-parse", "HEAD") == head_before
    assert "status: draft" in _git(repo, "show", "HEAD:notes/topic.md")
    # the change lives only on the proposal branch
    assert "status: active" in _git(repo, "show", f"{res.branch}:notes/topic.md")
    # PR body carries what / why / source
    body = calls[0]["body"]
    assert "promote topic to active" in body
    assert "status drifted from reality" in body
    assert "notes/topic.md" in body
    idx.close()


# --- diff-or-die holds through the proposal path ------------------------------

def test_unrequested_drift_aborts_no_branch_no_pr_no_audit(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/n.md": _NONCANON})
    with pytest.raises(fg.FrontmatterDriftError):
        pr.propose(repo, [pr.Change(path="notes/n.md", set_fields={"newkey": "x"})],
                   slug="bad", summary="s", allowlist=["notes/"], log=log, gh_create=fake_gh)
    assert "hypermnesic/proposals/bad" not in _branches(repo)
    assert calls == []
    assert log.entries() == []
    idx.close()


def test_protected_path_refused_before_any_branch(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/topic.md": _TOPIC})
    with pytest.raises(serialize.WriteGuardError):
        pr.propose(repo, [pr.Change(path="CLAUDE.md", body="# pwned\n")],
                   slug="p", summary="s", allowlist=["notes/"], log=log, gh_create=fake_gh)
    assert "hypermnesic/proposals/p" not in _branches(repo)
    assert calls == [] and log.entries() == []
    idx.close()


# --- zone tiers: immutable free-append vs curated propose ---------------------

def test_free_append_fast_path_vs_curated_propose(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/topic.md": _TOPIC})

    # new file in an immutable free-append zone → fast path (commit, no branch/PR)
    res1 = pr.propose(repo, [pr.Change(path="sources/cap-1.md", body="raw capture\n")],
                      slug="cap", summary="capture", allowlist=["sources/"],
                      idx=idx, log=log, gh_create=fake_gh)
    assert res1.fast_path is True and res1.branch is None
    assert (repo / "sources/cap-1.md").exists()
    assert "hypermnesic/proposals/cap" not in _branches(repo)
    assert calls == []

    # curated edit → propose→approve path (branch + PR)
    res2 = pr.propose(repo, [pr.Change(path="notes/topic.md", set_fields={"status": "active"})],
                      slug="edit-topic", summary="edit", allowlist=["notes/"],
                      idx=idx, log=log, gh_create=fake_gh)
    assert res2.fast_path is False
    assert res2.branch == "hypermnesic/proposals/edit-topic"
    idx.close()


def test_path_scope_allowlist_and_no_curated_via_fast_path(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/topic.md": _TOPIC})
    # curated path outside the declared allowlist → rejected
    with pytest.raises(serialize.WriteGuardError):
        pr.propose(repo, [pr.Change(path="notes/topic.md", set_fields={"status": "active"})],
                   slug="x", summary="s", allowlist=["other/"], log=log, gh_create=fake_gh)
    # a curated (non-immutable) path never takes the free-append fast path
    res = pr.propose(repo, [pr.Change(path="notes/topic.md", set_fields={"status": "active"})],
                     slug="y", summary="s", allowlist=["notes/"], log=log, gh_create=fake_gh)
    assert res.fast_path is False
    idx.close()


# --- multi-file atomicity -----------------------------------------------------

def test_multi_file_atomicity_aborts_whole_proposal(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(make_corpus, fake_embedder, tmp_path, {
        "notes/a.md": _TOPIC,
        "notes/b.md": _NONCANON,   # file 2: gate aborts
        "notes/c.md": "# C\n\nplain.\n",
    })
    changes = [
        pr.Change(path="notes/a.md", set_fields={"status": "active"}),
        pr.Change(path="notes/b.md", set_fields={"newkey": "x"}),
        pr.Change(path="notes/c.md", body="# C\n\nrewritten.\n"),
    ]
    with pytest.raises(fg.FrontmatterDriftError):
        pr.propose(repo, changes, slug="multi", summary="s",
                   allowlist=["notes/"], log=log, gh_create=fake_gh)
    assert "hypermnesic/proposals/multi" not in _branches(repo)
    assert "status: active" not in _git(repo, "show", "HEAD:notes/a.md")
    assert calls == [] and log.entries() == []
    idx.close()


# --- idempotency --------------------------------------------------------------

def test_idempotent_reproposing_identical_is_noop(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/topic.md": _TOPIC})
    kw = dict(slug="iso", summary="promote", allowlist=["notes/"], log=log, gh_create=fake_gh)
    change = [pr.Change(path="notes/topic.md", set_fields={"status": "active"})]
    pr.propose(repo, change, **kw)
    res2 = pr.propose(repo, change, **kw)
    assert res2.noop is True
    assert len(calls) == 1                                   # no duplicate PR
    assert _branches(repo).count("hypermnesic/proposals/iso") == 1
    idx.close()


# --- gh unavailable → branch+diff local; later run resumes the PR -------------

def test_gh_unavailable_skips_pr_then_resumes(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/topic.md": _TOPIC})
    change = [pr.Change(path="notes/topic.md", set_fields={"status": "active"})]

    res1 = pr.propose(repo, change, slug="rz", summary="promote",
                      allowlist=["notes/"], log=log, gh_create=None)  # gh unavailable
    assert res1.pr_skipped is True and res1.pr_url is None
    assert res1.branch == "hypermnesic/proposals/rz"
    assert "status: active" in _git(repo, "show", f"{res1.branch}:notes/topic.md")
    assert calls == []

    res2 = pr.propose(repo, change, slug="rz", summary="promote",
                      allowlist=["notes/"], log=log, gh_create=fake_gh)  # gh now available
    assert res2.pr_skipped is False and res2.pr_url.endswith("/pull/7")
    assert len(calls) == 1                                   # PR created on resume
    assert _branches(repo).count("hypermnesic/proposals/rz") == 1  # no second branch
    idx.close()


# --- AE3 re-proven on the branch-commit path ----------------------------------

def test_ae3_byte_preservation_on_branch_commit(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/ae3.md": _AE3})
    res = pr.propose(repo, [pr.Change(path="notes/ae3.md", set_fields={"status": "done"})],
                     slug="ae3", summary="close", allowlist=["notes/"], log=log, gh_create=fake_gh)
    branch_text = _git(repo, "show", f"{res.branch}:notes/ae3.md") + "\n"  # git strips trailing nl
    expected = _AE3.replace("status: active", "status: done")
    assert branch_text == expected
    idx.close()


# --- audit: server-set actor, summary only ------------------------------------

def test_audit_records_proposal_summary_only(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/topic.md": _TOPIC})
    pr.propose(repo, [pr.Change(path="notes/topic.md", set_fields={"status": "active"})],
               slug="aud", summary="promote topic", allowlist=["notes/"], log=log,
               gh_create=fake_gh)
    e = log.entries()[-1]
    assert e["verb"] == "propose"
    assert e["actor"] == "tailnet:test"                      # server-set
    assert e["summary"] == "promote topic"
    assert "body about alpha" not in json.dumps(e)           # no page body leaks
    idx.close()


# --- global proposal budget (R-1 cold-start flood) ----------------------------

def test_proposal_budget_bounds_branch_creation(make_corpus, fake_embedder, tmp_path):
    repo, idx, log, calls, fake_gh = _env(
        make_corpus, fake_embedder, tmp_path, {"notes/a.md": _TOPIC, "notes/c.md": "# C\n\nx.\n"})
    budget = pr.ProposalBudget(tmp_path / "budget.json", max_per_cycle=1)
    pr.propose(repo, [pr.Change(path="notes/a.md", set_fields={"status": "active"})],
               slug="b1", summary="s", allowlist=["notes/"], log=log, budget=budget,
               gh_create=fake_gh)
    with pytest.raises(pr.BudgetExceededError):
        pr.propose(repo, [pr.Change(path="notes/c.md", body="# C\n\nedited.\n")],
                   slug="b2", summary="s", allowlist=["notes/"], log=log, budget=budget,
                   gh_create=fake_gh)
    assert "hypermnesic/proposals/b2" not in _branches(repo)
    idx.close()
