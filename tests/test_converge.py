"""U27 — the converge() primitive: host-aware catch-up + bounded dense fill.

Read-time convergence (KTD1/KTD2): one shared step that brings the index up to
HEAD and closes a bounded dense slice, lock-safe and never full-reindexing. The
lock-skip, oversized-delta, degraded, and authoring-host overlay paths are the
spec (test-first). Uses the offline FakeEmbedder + git-backed make_corpus.
"""

from __future__ import annotations

import subprocess

from hypermnesic import config, converge, serialize
from hypermnesic import embed as embed_mod
from hypermnesic import index as ix


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


def _commit_file(repo, rel, body, msg="add"):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)


def _dense_finds(idx, fake_embedder, text, path):
    qvec = fake_embedder.embed([text])[0]
    return any(idx.get_chunk(c)["path"] == path for c, _ in idx.dense_search(qvec, k=10))


class _DownEmbedder:
    """Dim-correct but the API is unreachable — drives the degraded path."""
    dim = config.EMBED_DIM

    def embed(self, texts):
        raise embed_mod.EmbeddingError("API down")


# --- debounce ---------------------------------------------------------------

def test_debounce_returns_early_without_relocking(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)            # HEAD == checkpoint
    first = converge.converge(repo, idx, fake_embedder)  # default debounce
    assert first.status == "converged"
    second = converge.converge(repo, idx, fake_embedder)  # immediately again
    assert second.status == "debounced"
    assert second.replayed == 0 and second.chunks_embedded == 0
    idx.close()


# --- happy path: catch_up + bounded embed, checkpoint advances --------------

def test_catch_up_replays_committed_files_then_embeds(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    for i in range(3):
        _commit_file(repo, f"n{i}.md", f"# N{i}\n\nFRESHMARKER body {i}.\n", f"add n{i}")
    head = _git(repo, "rev-parse", "HEAD")
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0)
    assert res.status == "converged"
    assert res.replayed == 3 and res.checkpoint_advanced
    assert idx.get_checkpoint() == head                  # caught up to HEAD
    # lexical fresh immediately, and the bounded embed made them dense-findable
    assert any(idx.get_chunk(c)["path"] == "n0.md"
               for c, _ in idx.lexical_search("FRESHMARKER", k=10))
    assert res.chunks_embedded >= 3
    assert _dense_finds(idx, fake_embedder, "FRESHMARKER body 0.", "n0.md")
    assert not res.degraded
    idx.close()


# --- KTD2: lock held by another holder → skip, serve current ----------------

def test_lock_held_skips_convergence_index_unchanged(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cp_before = idx.get_checkpoint()
    _commit_file(repo, "b.md", "# B\n\nLOCKMARKER beta.\n", "add b")  # real work pending
    held = serialize.index_write_lock(repo).acquire()    # another holder owns the lock
    try:
        res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0)
    finally:
        held.release()
    assert res.status == "lock_busy"
    assert idx.get_checkpoint() == cp_before             # checkpoint NOT advanced
    assert "b.md" not in idx.all_paths()                 # index left as-is
    idx.close()


# --- FR-R33: oversized delta → manual-reindex signal, no unbounded replay ---

def test_oversized_delta_signals_manual_reindex_no_replay(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cp_before = idx.get_checkpoint()
    for i in range(4):
        _commit_file(repo, f"big{i}.md", f"# Big{i}\n\nbody {i}.\n", f"big {i}")
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0, max_delta_files=2)
    assert res.status == "oversized_delta"
    assert res.manual_reindex_recommended and res.replayed == 0
    assert idx.get_checkpoint() == cp_before             # no inline replay; left as-is
    assert "big0.md" not in idx.all_paths()
    idx.close()


# --- FR-R34: embedder failure → lexical catch-up completes, degraded --------

def test_embedder_failure_completes_lexical_and_advances_checkpoint(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    _commit_file(repo, "c.md", "# C\n\nDEGRADEDMARKER gamma.\n", "add c")
    head = _git(repo, "rev-parse", "HEAD")
    res = converge.converge(repo, idx, _DownEmbedder(), debounce_seconds=0)
    assert res.degraded is True
    assert res.replayed == 1 and res.checkpoint_advanced
    assert idx.get_checkpoint() == head                  # lexical/graph caught up
    # findable lexically despite the dead embedder
    assert any(idx.get_chunk(c)["path"] == "c.md"
               for c, _ in idx.lexical_search("DEGRADEDMARKER", k=10))
    # no zero-vectors written: c.md's chunks remain stale (absent from vec_chunks)
    c_cids = set(idx.chunks_for_path("c.md"))
    assert c_cids and c_cids.issubset(set(idx.stale_chunk_ids()))
    idx.close()


def test_none_embedder_is_degraded_not_an_error(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    _commit_file(repo, "d.md", "# D\n\ndelta.\n", "add d")
    res = converge.converge(repo, idx, None, debounce_seconds=0)
    assert res.degraded is True and res.replayed == 1 and res.checkpoint_advanced
    idx.close()


# --- FR-R29/R35: authoring-host overlay vs replica projection ---------------

def test_authoring_host_overlay_indexes_uncommitted_without_advancing_checkpoint(
        make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cp = idx.get_checkpoint()
    (repo / "draft.md").write_text("# Draft\n\nOVERLAYMARKER in progress.\n", encoding="utf-8")
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0, authoring_host=True)
    assert res.status == "converged"
    assert "draft.md" in res.overlay_paths
    assert any(idx.get_chunk(c)["path"] == "draft.md"
               for c, _ in idx.lexical_search("OVERLAYMARKER", k=10))
    assert idx.get_checkpoint() == cp                    # overlay never advances checkpoint
    idx.close()


def test_replica_does_not_index_uncommitted_files(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    (repo / "draft.md").write_text("# Draft\n\nUNCOMMITTEDMARKER body.\n", encoding="utf-8")
    converge.converge(repo, idx, fake_embedder, debounce_seconds=0, authoring_host=False)
    assert "draft.md" not in idx.all_paths()             # replica projects committed SHAs only
    idx.close()


# --- FR-R32: convergence never triggers a full reindex ----------------------

def test_converge_never_calls_reindex_isolated(make_corpus, fake_embedder, monkeypatch):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    _commit_file(repo, "e.md", "# E\n\nepsilon.\n", "add e")

    def _boom(*a, **k):
        raise AssertionError("convergence must never call reindex_isolated (OOM scar, FR-R32)")

    monkeypatch.setattr(ix, "reindex_isolated", _boom)
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0)
    assert res.status == "converged" and res.replayed == 1   # caught up without a full reindex
    idx.close()
