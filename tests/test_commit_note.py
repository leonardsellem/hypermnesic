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
        cn.commit_note(repo, "doc.md", set_fields={"created": "2026-05-03"}, idx=idx, log=log)
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
