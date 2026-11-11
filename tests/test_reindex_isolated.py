"""U14 — worktree-isolated broad reindex: complete, atomic, non-blocking."""

from __future__ import annotations

import os
import subprocess
import threading

import pytest

from hypermnesic import commit_note as cn
from hypermnesic import index as ix
from hypermnesic import ingest, serialize


def _commit(repo, msg="c"):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)


def test_reindex_produces_complete_index(make_corpus, fake_embedder):
    files = {f"n{i}.md": f"# N{i}\n\nbody about topic{i}.\n" for i in range(5)}
    repo = make_corpus(files)
    ix.build_index(repo, fake_embedder).close()
    res = ix.reindex_isolated(repo, fake_embedder)
    assert res["status"] == "reindexed"
    idx = ix.Index(ix.state_dir_for(repo) / "index.db")
    assert len(idx.all_paths()) == 5
    assert idx.conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] >= 5
    idx.close()


def test_reindex_picks_up_new_commits_atomically(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    ix.build_index(repo, fake_embedder).close()
    (repo / "b.md").write_text("# B\n\nNEWDOC beta.\n", encoding="utf-8")
    _commit(repo, "add b")
    ix.reindex_isolated(repo, fake_embedder)
    idx = ix.Index(ix.state_dir_for(repo) / "index.db")
    assert "b.md" in idx.all_paths()                       # new commit reflected
    assert any(idx.get_chunk(c)["path"] == "b.md"
               for c, _ in idx.lexical_search("NEWDOC", k=5))
    idx.close()


def test_build_phase_does_not_hold_live_lock(make_corpus, fake_embedder):
    # The long build must NOT hold the live index lock — a concurrent writer's
    # work (modeled here by the embedder probing the live lock) stays unblocked.
    repo = make_corpus({"a.md": "# A\n\nalpha.\n", "b.md": "# B\n\nbeta.\n"})
    ix.build_index(repo, fake_embedder).close()
    live_lock_path = ix.state_dir_for(repo) / "index.lock"
    probed = {"n": 0}

    class LockProbeEmbedder:
        dim = fake_embedder.dim

        def embed(self, texts):
            # if reindex held the live lock during build, this acquire would raise
            serialize.FileLock(live_lock_path).acquire().release()
            probed["n"] += 1
            return fake_embedder.embed(texts)

    res = ix.reindex_isolated(repo, LockProbeEmbedder())
    assert res["status"] == "reindexed" and probed["n"] > 0  # build ran, live lock was free
    idx = ix.Index(ix.state_dir_for(repo) / "index.db")
    assert len(idx.all_paths()) == 2
    idx.close()


def test_worktree_cleaned_up_and_tracked_files_unchanged(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    ix.build_index(repo, fake_embedder).close()
    before = subprocess.run(["git", "-C", str(repo), "ls-files", "-s"],
                            capture_output=True, text=True).stdout
    ix.reindex_isolated(repo, fake_embedder)
    after = subprocess.run(["git", "-C", str(repo), "ls-files", "-s"],
                           capture_output=True, text=True).stdout
    assert before == after                                 # tracked files unchanged
    wts = subprocess.run(["git", "-C", str(repo), "worktree", "list"],
                         capture_output=True, text=True).stdout
    assert "reindex" not in wts                             # no leftover worktree
    assert not (ix.state_dir_for(repo) / ".reindex-build").exists()
    assert "" == subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                capture_output=True, text=True).stdout.strip()


def test_fallback_when_not_a_git_repo(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"}, git=False)   # no git
    res = ix.reindex_isolated(repo, fake_embedder)
    assert res["status"] == "fallback-inplace"
    idx = ix.Index(ix.state_dir_for(repo) / "index.db")
    assert "a.md" in idx.all_paths()                            # still produced an index
    idx.close()


# --- the swap must not strand a long-lived holder (LS-2539) ---------------
# The MCP servers open the index once at boot. `os.replace` unlinks the inode
# under them: reads then serve a frozen snapshot and writes fail with
# "attempt to write a readonly database".


def test_long_lived_index_can_still_write_after_swap(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    ix.build_index(repo, fake_embedder).close()

    live = ix.Index(ix.state_dir_for(repo) / "index.db")     # the server's handle
    try:
        ix.reindex_isolated(repo, fake_embedder)
        live.upsert_lexical("a.md",
                            ingest.chunks_for_text("a.md", "# A\n\nalpha rewritten.\n"))
    finally:
        live.close()


def test_long_lived_index_sees_new_docs_after_swap(make_corpus, fake_embedder):
    """The silent half: a stale read looks perfectly healthy."""
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    ix.build_index(repo, fake_embedder).close()

    live = ix.Index(ix.state_dir_for(repo) / "index.db")
    try:
        (repo / "b.md").write_text("# B\n\nNEWDOC beta.\n", encoding="utf-8")
        _commit(repo, "add b")
        ix.reindex_isolated(repo, fake_embedder)
        assert "b.md" in live.all_paths()
    finally:
        live.close()


def test_missing_db_file_does_not_trigger_a_reopen(make_corpus, fake_embedder):
    """An in-flight rebuild must not make us reopen onto nothing."""
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    ix.build_index(repo, fake_embedder).close()

    db = ix.state_dir_for(repo) / "index.db"
    live = ix.Index(db)
    try:
        db.unlink()
        assert "a.md" in live.all_paths()                    # served from the open inode
    finally:
        live.close()


# --- LS-4075 R3: one dense-maintenance mutex around every provider-fill path ---

class _Counting:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.model = wrapped.model
        self.dim = wrapped.dim
        self.sizes: list[int] = []
        self.texts: list[str] = []

    def embed(self, texts):
        self.sizes.append(len(texts))
        self.texts.extend(texts)
        return self.wrapped.embed(texts)


def test_dense_mutex_excludes_full_build_but_not_narrow_writes(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha original.\n"})
    ix.build_index(repo, fake_embedder).close()
    live = ix.Index(ix.state_dir_for(repo) / "index.db")
    started, release = threading.Event(), threading.Event()
    results: list[dict] = []

    class GatedEmbedder:
        model = fake_embedder.model
        dim = fake_embedder.dim

        def __init__(self):
            self.calls = 0

        def embed(self, texts):
            self.calls += 1
            started.set()                       # build is paused after its first request
            assert release.wait(30)
            return fake_embedder.embed(texts)

    gated = GatedEmbedder()
    worker = threading.Thread(
        target=lambda: results.append(ix.reindex_isolated(repo, gated)))
    worker.start()
    try:
        assert started.wait(30), "isolated build never started"
        counting = _Counting(fake_embedder)
        with pytest.raises(serialize.LockBusyError):
            ix.embed_stale(live, repo, counting)
        assert counting.texts == []             # opposing fill made zero paid calls

        # Narrow writes are NOT blocked by the long build (index.lock stays free).
        cn.commit_note(repo, "notes/live.md", body="# Live\n\nLIVEMARKER body.\n", idx=live)
        assert any(live.get_chunk(c)["path"] == "notes/live.md"
                   for c, _ in live.lexical_search("LIVEMARKER", k=5))
    finally:
        release.set()
        worker.join(30)

    assert not worker.is_alive()
    assert results and results[0]["status"] == "reindexed"
    live.close()


def test_dense_mutex_held_blocks_reindex_before_any_build(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    ix.build_index(repo, fake_embedder).close()
    state = ix.state_dir_for(repo)
    before = os.stat(state / "index.db").st_ino

    held = serialize.dense_maintenance_lock(state).acquire()
    try:
        with pytest.raises(serialize.LockBusyError):
            ix.reindex_isolated(repo, _Counting(fake_embedder))
    finally:
        held.release()

    assert not (state / ".reindex-build").exists()      # no build started
    assert os.stat(state / "index.db").st_ino == before  # live index untouched


def test_public_dense_entrypoints_defer_under_maintenance(
        make_corpus, fake_embedder, monkeypatch, capsys):
    from hypermnesic import cli, embed, local_proof

    repo = make_corpus({"a.md": "# A\n\nalpha retrieval marker question answered here.\n"})
    ix.build_index(repo, fake_embedder).close()
    (repo / "b.md").write_text("# B\n\nbeta retrieval marker question answered here.\n",
                               encoding="utf-8")
    _commit(repo, "add b")                               # a real dense delta is pending
    state = ix.state_dir_for(repo)
    counting = _Counting(fake_embedder)
    monkeypatch.setattr(embed, "OpenAIEmbedder", lambda **kw: counting)

    held = serialize.dense_maintenance_lock(state).acquire()
    try:
        with pytest.raises(serialize.LockBusyError):     # direct build_index
            ix.build_index(repo, counting)

        idx = ix.Index(state / "index.db")
        try:
            with pytest.raises(serialize.LockBusyError):  # embed_stale
                ix.embed_stale(idx, repo, counting)
        finally:
            idx.close()

        idx = ix.Index(state / "index.db")
        try:
            catchup = ix.catch_up(idx, repo, embedder=counting)   # local_proof path
        finally:
            idx.close()
        assert catchup["status"] == "lock_busy"

        for argv in (["init", str(repo)], ["index", str(repo)], ["reindex", str(repo)]):
            assert cli.main(argv) == 1
            assert "maintenance" in capsys.readouterr().err.lower()
        assert counting.sizes == []                      # former startup probes: zero calls

        result = local_proof.run_local_proof(repo=repo, query="alpha retrieval",
                                             embedder=counting)
        assert result.index_info["catchup_status"] == "lock_busy"
        assert counting.sizes == [1]                     # query embedding only, no bulk fill
    finally:
        held.release()
