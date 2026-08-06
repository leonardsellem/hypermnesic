"""U14 — worktree-isolated broad reindex: complete, atomic, non-blocking."""

from __future__ import annotations

import subprocess

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
