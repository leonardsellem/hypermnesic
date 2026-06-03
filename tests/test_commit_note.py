"""U7 — commit_note: the single write primitive (against temp git repos)."""

from __future__ import annotations

import subprocess

import pytest

from hypermnesic import audit_log as al
from hypermnesic import commit_note as cn
from hypermnesic import frontmatter_gate as fg
from hypermnesic import index as index_mod
from hypermnesic import serialize


def _git(repo, *a):
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
    return r.stdout.strip()


_DOC_NONCANON = "---\nstatus:    active\ncreated: 2026-05-02\n---\nbody\n"
_DOC_FM = "---\ntitle: N\nstatus: active\ncreated: 2026-05-02\n---\nbody\n"


def _setup(make_corpus, fake_embedder, tmp_path, files=None):
    repo = make_corpus(files or {"seed.md": "# Seed\n\nseed body.\n"})
    idx = index_mod.build_index(repo, fake_embedder)
    log = al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test-node")
    return repo, idx, log


def test_new_note_writes_commits_extracts_logs_returns_diff(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    r = cn.commit_note(repo, "notes/new.md",
                       body="# New\n\nA brand new note about widgets.\n",
                       summary="add new note", idx=idx, log=log)
    assert r.created and r.new_sha and "widgets" in r.diff
    assert (repo / "notes/new.md").exists()
    assert _git(repo, "status", "--porcelain") == ""        # committed, clean tree
    # findable LEXICALLY immediately (no embedding ran) — AE5
    hits = idx.lexical_search("widgets", k=5)
    assert any(idx.get_chunk(c)["path"] == "notes/new.md" for c, _ in hits)
    # logged with the resulting sha, summary only, server-set actor
    e = log.entries()[-1]
    assert e["path"] == "notes/new.md" and e["new_sha"] == r.new_sha
    assert e["actor"] == "tailnet:test-node" and e["verb"] == "create"
    idx.close()


def test_idempotent_noop_on_identical_content(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    cn.commit_note(repo, "notes/x.md", body="# X\n\nbody.\n", idx=idx, log=log)
    n = len(log.entries())
    head = _git(repo, "rev-parse", "HEAD")
    r2 = cn.commit_note(repo, "notes/x.md", body="# X\n\nbody.\n", idx=idx, log=log)
    assert r2.noop is True
    assert len(log.entries()) == n                          # no new log entry
    assert _git(repo, "rev-parse", "HEAD") == head          # no new commit
    idx.close()


def test_gate_abort_prevents_all_effects(make_corpus, fake_embedder, tmp_path):
    # non-canonical YAML → editing one field would reflow another → gate aborts;
    # NO file write, NO commit, NO log entry (no partial effect).
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path,
                            files={"doc.md": _DOC_NONCANON})
    before = (repo / "doc.md").read_text()
    head = _git(repo, "rev-parse", "HEAD")
    n = len(log.entries())
    with pytest.raises(fg.FrontmatterDriftError):
        cn.commit_note(repo, "doc.md", set_fields={"newkey": "x"}, idx=idx, log=log)
    assert (repo / "doc.md").read_text() == before          # file untouched
    assert _git(repo, "rev-parse", "HEAD") == head          # no commit
    assert len(log.entries()) == n                          # no log entry
    idx.close()


def test_protected_path_refused(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(serialize.WriteGuardError):
        cn.commit_note(repo, "CLAUDE.md", body="# pwned\n", idx=idx, log=log)
    assert not (repo / "CLAUDE.md").exists()
    assert _git(repo, "rev-parse", "HEAD") == head          # nothing committed
    idx.close()


def test_crash_recovery_reconciler_backfills(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    log.append("commit_note", "seed.md", None, _git(repo, "rev-parse", "HEAD"), "seed")
    # commit_note with NO log → the commit lands but the log append never happened
    r = cn.commit_note(repo, "notes/c.md", body="# C\n\nbody about crash.\n", idx=idx, log=None)
    assert r.new_sha
    assert log.reconcile(repo) == 1                          # back-fills the unlogged commit
    assert log.entries()[-1]["new_sha"] == r.new_sha
    idx.close()


def test_dry_run_has_no_side_effects(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    n_log = len(log.entries())
    n_paths = len(idx.all_paths())
    r = cn.commit_note(repo, "notes/preview.md", body="# P\n\nPREVIEWWORD body.\n",
                       summary="preview", idx=idx, log=log, dry_run=True)
    assert r.dry_run is True and "PREVIEWWORD" in r.diff and r.new_sha is None
    assert not (repo / "notes/preview.md").exists()         # no file written
    assert _git(repo, "rev-parse", "HEAD") == head          # no commit
    assert len(log.entries()) == n_log                      # no log entry
    assert len(idx.all_paths()) == n_paths                  # index untouched
    idx.close()


def test_dry_run_gate_still_aborts(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path, files={"doc.md": _DOC_NONCANON})
    with pytest.raises(fg.FrontmatterDriftError):
        cn.commit_note(repo, "doc.md", set_fields={"newkey": "x"},
                       idx=idx, log=log, dry_run=True)
    idx.close()


def test_dry_run_guard_still_refuses_protected(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    with pytest.raises(serialize.WriteGuardError):
        cn.commit_note(repo, "CLAUDE.md", body="# x\n", dry_run=True)
    idx.close()


def test_frontmatter_edit_preserves_scalar_date(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path,
                            files={"n.md": _DOC_FM})
    r = cn.commit_note(repo, "n.md", set_fields={"status": "done"}, summary="close",
                       idx=idx, log=log)
    text = (repo / "n.md").read_text()
    assert "status: done" in text and "created: 2026-05-02" in text
    assert "2026-05-02T" not in text
    assert not r.created and r.new_sha
    idx.close()


# --- U11: shared-origin/main coordination (fetch+ff+preflight+push, retry) -----

def _runq(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True,
                          check=True)


def _with_remote(repo, tmp_path):
    """Wire a bare `origin` and push `main`, so commit_note's coordination engages."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)],
                   check=True, capture_output=True)
    _runq(repo, "remote", "add", "origin", str(bare))
    _runq(repo, "push", "-u", "origin", "main")
    return bare


def _other_clone(bare, tmp_path):
    """A second checkout of the bare = 'another committer' (the gbrain fleet / Mac)."""
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(bare), str(other)], check=True, capture_output=True)
    _runq(other, "config", "user.email", "o@o.o")
    _runq(other, "config", "user.name", "other")
    return other


def _advance_origin(other, rel, body, msg="foreign"):
    (other / rel).parent.mkdir(parents=True, exist_ok=True)
    (other / rel).write_text(body, encoding="utf-8")
    _runq(other, "add", "-A")
    _runq(other, "commit", "-q", "-m", msg)
    _runq(other, "push", "origin", "main")


def test_coord_write_lands_on_origin_main(make_corpus, fake_embedder, tmp_path):
    # Covers AE4 (happy): fetch + fast-forward + commit + push; the test origin/main
    # carries the commit afterward (never a local-only commit that wedges --ff-only).
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    _with_remote(repo, tmp_path)
    r = cn.commit_note(repo, "sources/canary.md", body="# C\n\nWIDGET body.\n",
                       summary="canary", idx=idx, log=log, allowlist=["sources/"])
    assert r.new_sha and not r.noop
    assert _git(repo, "rev-parse", "origin/main") == r.new_sha   # reached the shared remote
    assert log.entries()[-1]["new_sha"] == r.new_sha             # audited the pushed sha
    idx.close()


def test_coord_aborts_on_remote_drift(make_corpus, fake_embedder, tmp_path):
    # Covers AE4 (error): the remote advanced under our base-read → fetch+ff exposes the
    # drift, preflight(expected_head) aborts; clean tree, no partial commit, no audit.
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    bare = _with_remote(repo, tmp_path)
    other = _other_clone(bare, tmp_path)
    _advance_origin(other, "sources/foreign.md", "# F\n\nforeign.\n")   # origin moves ahead
    n = len(log.entries())
    with pytest.raises(serialize.HeadDriftError):
        cn.commit_note(repo, "sources/mine.md", body="# M\n\nmine.\n",
                       idx=idx, log=log, allowlist=["sources/"])
    assert _git(repo, "status", "--porcelain") == ""             # tree clean (ff'd, no partial)
    assert not (repo / "sources/mine.md").exists()               # our write never landed
    assert len(log.entries()) == n                               # no audit entry
    idx.close()


def test_coord_nonff_exhaustion_aborts_clean(make_corpus, fake_embedder, tmp_path, monkeypatch):
    # Edge: remote diverged non-ff at push time with a CONFLICTING change → bounded
    # retry cannot converge → abort cleanly, leaving NO local-ahead commit.
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    bare = _with_remote(repo, tmp_path)
    other = _other_clone(bare, tmp_path)
    _advance_origin(other, "sources/canary.md", "# Foreign\n\nDIFFERENT body.\n")
    # neutralize the pre-commit ff so we commit on a stale base and hit the push race
    monkeypatch.setattr(cn, "_fetch_and_ff", lambda *a, **k: None)
    monkeypatch.setattr(cn, "_PUSH_MAX_ATTEMPTS", 2)
    n = len(log.entries())
    with pytest.raises(cn.GitCoordinationError):
        cn.commit_note(repo, "sources/canary.md", body="# Mine\n\nMINE body.\n",
                       idx=idx, log=log, allowlist=["sources/"])
    assert _git(repo, "rev-parse", "HEAD") == _git(repo, "rev-parse", "origin/main")  # not ahead
    assert _git(repo, "status", "--porcelain") == ""
    assert len(log.entries()) == n                               # no audit on a non-landed write
    idx.close()


def test_coord_push_rejected_raises_refusal_no_audit(make_corpus, fake_embedder, tmp_path):
    # Error path: a push that fails for a non-ff reason (here a rejecting remote hook,
    # standing in for auth/network) surfaces as a raised refusal — never a silent
    # success — and drops the local-ahead commit (no --ff-only wedge), no audit.
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    bare = _with_remote(repo, tmp_path)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    origin_before = _git(repo, "rev-parse", "origin/main")
    n = len(log.entries())
    with pytest.raises(cn.GitCoordinationError):
        cn.commit_note(repo, "sources/x.md", body="# X\n\nbody.\n",
                       idx=idx, log=log, allowlist=["sources/"])
    assert _git(repo, "rev-parse", "HEAD") == origin_before      # local-ahead commit dropped
    assert _git(repo, "status", "--porcelain") == ""
    assert len(log.entries()) == n                               # no silent-success audit entry
    idx.close()


def test_coord_two_sequential_writes_both_land(make_corpus, fake_embedder, tmp_path):
    # Integration: two coordinated writes serialize and BOTH reach origin/main — the
    # second fetch+ff incorporates the first's push (neither clobbers the other).
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    _with_remote(repo, tmp_path)
    r1 = cn.commit_note(repo, "sources/a.md", body="# A\n\nAAA.\n",
                        idx=idx, log=log, allowlist=["sources/"])
    r2 = cn.commit_note(repo, "sources/b.md", body="# B\n\nBBB.\n",
                        idx=idx, log=log, allowlist=["sources/"])
    assert r1.new_sha and r2.new_sha and not r1.noop and not r2.noop
    assert (repo / "sources/a.md").exists() and (repo / "sources/b.md").exists()
    assert _git(repo, "rev-parse", "origin/main") == r2.new_sha  # b on top of a, both pushed
    idx.close()


def test_local_only_repo_still_commits_without_remote(make_corpus, fake_embedder, tmp_path):
    # No remote (the portable / single-host case) → no fetch/push; commit_note behaves
    # exactly as before. Guards the coexistence change against breaking solo use.
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    assert _git(repo, "remote") == ""                            # no origin
    r = cn.commit_note(repo, "sources/solo.md", body="# S\n\nbody.\n",
                       idx=idx, log=log, allowlist=["sources/"])
    assert r.new_sha and not r.noop and (repo / "sources/solo.md").exists()
    idx.close()


def test_commit_note_is_path_scoped_no_sweep_of_foreign_staged(make_corpus, fake_embedder,
                                                               tmp_path):
    # Coexistence: another committer has work STAGED in the shared index when commit_note
    # runs. commit_note must commit ONLY its own note — never sweep the foreign staged
    # change into its commit (which a no-pathspec `git commit` would, then push it).
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    (repo / "sources").mkdir(exist_ok=True)
    (repo / "sources/foreign.md").write_text("# foreign\n\nFOREIGNWORD staged elsewhere.\n",
                                             encoding="utf-8")
    _git(repo, "add", "--", "sources/foreign.md")               # a fleet committer staged this
    r = cn.commit_note(repo, "sources/mine.md", body="# Mine\n\nMINEWORD body.\n",
                       summary="mine", idx=idx, log=log, allowlist=["sources/"])
    assert r.new_sha and not r.noop
    committed = _git(repo, "show", "--name-only", "--format=", r.new_sha).split()
    assert committed == ["sources/mine.md"]                     # ONLY the note — no sweep
    assert "sources/foreign.md" in _git(repo, "diff", "--cached", "--name-only")  # still staged
    idx.close()


def test_commit_note_noop_detection_ignores_foreign_staged(make_corpus, fake_embedder, tmp_path):
    # An idempotent edit while foreign changes are staged is still a no-op for OUR path
    # (the path-scoped staged check must not be confused by the foreign staged change).
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    cn.commit_note(repo, "sources/x.md", body="# X\n\nbody.\n", idx=idx, log=log,
                   allowlist=["sources/"])
    (repo / "sources/foreign.md").write_text("# f\n\nstaged.\n", encoding="utf-8")
    _git(repo, "add", "--", "sources/foreign.md")
    head = _git(repo, "rev-parse", "HEAD")
    r2 = cn.commit_note(repo, "sources/x.md", body="# X\n\nbody.\n", idx=idx, log=log,
                        allowlist=["sources/"])               # identical content → no-op
    assert r2.noop is True
    assert _git(repo, "rev-parse", "HEAD") == head             # no commit despite foreign staged
    idx.close()
