"""U10 — rename/move as a one-surface atomic op (no resurrection, no orphan)."""

from __future__ import annotations

import subprocess

import pytest

from hypermnesic import audit_log as al
from hypermnesic import commit_note as cn
from hypermnesic import index as ix
from hypermnesic import serialize


def _log(tmp_path):
    return al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test-node")


def _finds(idx, term, path):
    return any(idx.get_chunk(c)["path"] == path for c, _ in idx.lexical_search(term, k=10))


def test_git_mv_rekeys_index_no_resurrection(make_corpus, fake_embedder, tmp_path):
    # Covers AE3 — the rename-orphan-resurrection scar.
    repo = make_corpus({"old-slug.md": "# Old\n\nalpha RENAMEWORD content.\n"})
    idx = ix.build_index(repo, fake_embedder)
    assert "old-slug.md" in idx.all_paths()
    r = cn.rename_note(repo, "old-slug.md", "new-slug.md", idx=idx, log=_log(tmp_path))
    assert r.new_sha and "new-slug.md" in idx.all_paths()
    assert "old-slug.md" not in idx.all_paths()        # no orphan left behind
    assert _finds(idx, "RENAMEWORD", "new-slug.md")
    assert not _finds(idx, "RENAMEWORD", "old-slug.md")
    # a subsequent catch-up (replica) must NOT resurrect the old slug
    ix.catch_up(idx, repo)
    assert "old-slug.md" not in idx.all_paths()
    assert not (repo / "old-slug.md").exists()
    idx.close()


def test_rename_with_content_edit(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"a.md": "# A\n\noriginalword alpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cn.rename_note(repo, "a.md", "b.md", body="# A\n\nUPDATEDword beta.\n",
                   idx=idx, log=_log(tmp_path))
    assert "b.md" in idx.all_paths() and "a.md" not in idx.all_paths()
    assert _finds(idx, "UPDATEDword", "b.md")
    assert not _finds(idx, "originalword", "b.md")     # new content re-indexed
    idx.close()


def test_case_only_rename(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"Foo.md": "# Foo\n\ncasewordx body.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cn.rename_note(repo, "Foo.md", "foo.md", idx=idx, log=_log(tmp_path))
    assert "foo.md" in idx.all_paths() and "Foo.md" not in idx.all_paths()
    idx.close()


def test_rename_to_protected_path_refused(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"a.md": "# A\n\nbody.\n"})
    idx = ix.build_index(repo, fake_embedder)
    with pytest.raises(serialize.WriteGuardError):
        cn.rename_note(repo, "a.md", "CLAUDE.md", idx=idx, log=_log(tmp_path))
    assert (repo / "a.md").exists() and not (repo / "CLAUDE.md").exists()
    idx.close()


def test_rename_preserves_embeddings(make_corpus, fake_embedder, tmp_path):
    # pure move (no content change) re-keys WITHOUT dropping dense vectors
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    n_vecs_before = idx.conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
    cn.rename_note(repo, "a.md", "b.md", idx=idx, log=_log(tmp_path))
    n_vecs_after = idx.conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
    assert n_vecs_after == n_vecs_before               # vectors preserved (re-key, not re-embed)
    idx.close()


def test_rename_dry_run_previews_without_moving(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    r = cn.rename_note(repo, "a.md", "b.md", idx=idx, log=_log(tmp_path), dry_run=True)
    assert r.dry_run is True and "a.md" in r.diff and "b.md" in r.diff
    assert (repo / "a.md").exists() and not (repo / "b.md").exists()   # no move
    assert subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip() == head
    assert "a.md" in idx.all_paths() and "b.md" not in idx.all_paths()
    idx.close()


def _head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
