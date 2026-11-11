"""U13 — async embed-stale pass: fill dense vectors that lag lexical (AE5)."""

from __future__ import annotations

import subprocess

import pytest

from hypermnesic import audit_log as al
from hypermnesic import commit_note as cn
from hypermnesic import embed as embed_mod
from hypermnesic import index as ix
from hypermnesic import ingest


class CountingEmbedder:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.model = wrapped.model
        self.dim = wrapped.dim
        self.texts: list[str] = []
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        self.texts.extend(texts)
        return self.wrapped.embed(texts)


class ThrottledEmbedder:
    """Dim-correct double that answers 429 above ``limit`` inputs.

    Reproduces the reported org behaviour: a 128-chunk request is rejected as
    ``rate_limited`` while a smaller request succeeds.
    """

    def __init__(self, wrapped, limit: int):
        self.wrapped = wrapped
        self.model = wrapped.model
        self.dim = wrapped.dim
        self.limit = limit
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if len(texts) > self.limit:
            raise embed_mod.EmbeddingError("429 insufficient_quota", reason="rate_limited")
        return self.wrapped.embed(texts)


def _commit_file(repo, rel, body, msg="edit"):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)


def _log(tmp_path):
    return al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test")


def _vec_count(idx):
    return idx.conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]


def _dense_finds(idx, fake_embedder, text, path):
    qvec = fake_embedder.embed([text])[0]
    return any(idx.get_chunk(cid)["path"] == path for cid, _ in idx.dense_search(qvec, k=10))


def test_commit_note_page_becomes_dense_findable_after_embed(make_corpus, fake_embedder, tmp_path):
    # Covers AE5: a commit_note write is lexical-only; embed_stale closes the dense lag.
    repo = make_corpus({"seed.md": "# Seed\n\nseed body.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cn.commit_note(repo, "notes/n.md", body="# N\n\nZZUNIQUE dense marker content.\n",
                   idx=idx, log=_log(tmp_path))
    # lexical finds it, dense does NOT yet (no vectors for the new chunks)
    assert any(idx.get_chunk(c)["path"] == "notes/n.md"
               for c, _ in idx.lexical_search("ZZUNIQUE", k=5))
    assert not _dense_finds(idx, fake_embedder, "ZZUNIQUE dense marker content.", "notes/n.md")
    res = ix.embed_stale(idx, repo, fake_embedder)
    assert res["chunks_embedded"] >= 1
    assert _dense_finds(idx, fake_embedder, "ZZUNIQUE dense marker content.", "notes/n.md")
    idx.close()


def test_embed_stale_idempotent(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"seed.md": "# Seed\n\nseed body.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cn.commit_note(repo, "notes/n.md", body="# N\n\nbody one.\n", idx=idx, log=_log(tmp_path))
    ix.embed_stale(idx, repo, fake_embedder)
    n = _vec_count(idx)
    res2 = ix.embed_stale(idx, repo, fake_embedder)        # nothing stale now
    assert res2["chunks_embedded"] == 0 and res2["docs_embedded"] == 0
    assert _vec_count(idx) == n                            # no re-embedding
    idx.close()


def test_embed_stale_only_embeds_missing(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"seed.md": "# Seed\n\nseed body.\n"})
    idx = ix.build_index(repo, fake_embedder)              # seed already fully embedded
    before = _vec_count(idx)
    cn.commit_note(repo, "notes/a.md", body="# A\n\naaa.\n", idx=idx, log=_log(tmp_path))
    cn.commit_note(repo, "notes/b.md", body="# B\n\nbbb.\n", idx=idx, log=_log(tmp_path))
    stale = len(idx.stale_chunk_ids())
    res = ix.embed_stale(idx, repo, fake_embedder)
    assert res["chunks_embedded"] == stale                # exactly the stale chunks
    assert _vec_count(idx) == before + stale              # seed not re-embedded
    idx.close()


def test_embed_stale_backfills_doc_lane(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"seed.md": "# Seed\n\nseed body.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cn.commit_note(repo, "notes/n.md", body="# N\n\nbody.\n", idx=idx, log=_log(tmp_path))
    assert "notes/n.md" in idx.paths_missing_doc_vector()  # commit_note didn't build doc lane
    ix.embed_stale(idx, repo, fake_embedder)
    assert "notes/n.md" not in idx.paths_missing_doc_vector()
    idx.close()


def test_embed_stale_refreshes_only_invalidated_doc_surface(make_corpus, fake_embedder):
    repo = make_corpus({
        "a.md": "# A\n\nalpha original.\n",
        "b.md": "# B\n\nbeta unchanged.\n",
    })
    idx = ix.build_index(repo, fake_embedder)
    _commit_file(repo, "a.md", "# A changed\n\nalpha updated surface.\n", "edit a")
    idx.upsert_lexical(
        "a.md",
        ingest.chunks_for_text("a.md", "# A changed\n\nalpha updated surface.\n"),
    )

    assert idx.paths_missing_doc_vector() == ["a.md"]
    counting = CountingEmbedder(fake_embedder)
    res = ix.embed_stale(idx, repo, counting)

    assert res["docs_embedded"] == 1
    assert idx.paths_missing_doc_vector() == []
    assert any("alpha updated surface" in text for text in counting.texts)
    assert not any("beta unchanged" in text for text in counting.texts)
    res2 = ix.embed_stale(idx, repo, counting)
    assert res2["chunks_embedded"] == 0 and res2["docs_embedded"] == 0
    idx.close()


def test_embed_stale_budget_resumes_multiple_invalidated_doc_surfaces(
        make_corpus, fake_embedder):
    repo = make_corpus({
        "a.md": "# A\n\nalpha original.\n",
        "b.md": "# B\n\nbeta original.\n",
    })
    idx = ix.build_index(repo, fake_embedder)
    _commit_file(repo, "a.md", "# A changed\n\nalpha updated.\n", "edit a")
    idx.upsert_lexical(
        "a.md",
        ingest.chunks_for_text("a.md", "# A changed\n\nalpha updated.\n"),
    )
    _commit_file(repo, "b.md", "# B changed\n\nbeta updated.\n", "edit b")
    idx.upsert_lexical(
        "b.md",
        ingest.chunks_for_text("b.md", "# B changed\n\nbeta updated.\n"),
    )

    assert idx.paths_missing_doc_vector() == ["a.md", "b.md"]
    first = ix.embed_stale(idx, repo, fake_embedder, budget=1)
    assert first["docs_embedded"] == 1
    assert len(idx.paths_missing_doc_vector()) == 1
    second = ix.embed_stale(idx, repo, fake_embedder, budget=1)
    assert second["docs_embedded"] == 1
    assert idx.paths_missing_doc_vector() == []
    third = ix.embed_stale(idx, repo, fake_embedder, budget=1)
    assert third["docs_embedded"] == 0
    idx.close()


# --- R1/R2/R5: adaptive batch on a rate-limited drain ------------------------

def _stale_index(make_corpus, fake_embedder, *, n_docs: int = 70, n_stale: int = 65):
    """A built index with exactly ``n_stale`` chunk vectors removed."""
    files = {f"doc{i:02d}.md": f"# Doc {i}\n\nmarker{i} body text.\n" for i in range(n_docs)}
    repo = make_corpus(files)
    idx = ix.build_index(repo, fake_embedder)
    ids = [r[0] for r in idx.conn.execute(
        "SELECT chunk_id FROM chunks ORDER BY chunk_id LIMIT ?", (n_stale,))]
    idx.conn.executemany("DELETE FROM vec_chunks WHERE chunk_id=?", [(i,) for i in ids])
    idx.conn.commit()
    return repo, idx


def test_embed_stale_halves_batch_on_rate_limit(make_corpus, fake_embedder, monkeypatch):
    monkeypatch.setattr(ix, "_RATE_LIMIT_BACKOFF_SECONDS", (0, 0, 0))
    repo, idx = _stale_index(make_corpus, fake_embedder)
    total_chunks = idx.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    assert len(idx.stale_chunk_ids()) == 65
    limiter = ThrottledEmbedder(fake_embedder, limit=32)   # 128/64 fail, 32 wins

    res = ix.embed_stale(idx, repo, limiter)

    assert res["chunks_embedded"] == 65
    assert res["effective_batch"] == 32
    assert res["rate_limit_retries"] == 2                  # 128 → 64 → 32
    assert res["stale_left"] == 0
    assert _vec_count(idx) == total_chunks                 # every chunk has a vector
    assert limiter.calls == 5                              # 65, 64, then 32/32/1
    second = ix.embed_stale(idx, repo, limiter)            # idempotent: nothing stale
    assert second["chunks_embedded"] == 0
    idx.close()


def test_embed_stale_short_backlog_single_request(make_corpus, fake_embedder, monkeypatch):
    monkeypatch.setattr(ix, "_RATE_LIMIT_BACKOFF_SECONDS", (0, 0, 0))
    repo, idx = _stale_index(make_corpus, fake_embedder, n_docs=6, n_stale=5)
    counting = CountingEmbedder(fake_embedder)

    res = ix.embed_stale(idx, repo, counting)

    assert counting.calls == 1                             # one request for the whole backlog
    assert len(counting.texts) == 5
    assert res["chunks_embedded"] == 5
    assert res["effective_batch"] == 128                   # no 429 → configured batch
    assert res["rate_limit_retries"] == 0
    idx.close()


def test_embed_stale_fails_at_one_chunk_floor(make_corpus, fake_embedder, monkeypatch):
    monkeypatch.setattr(ix, "_RATE_LIMIT_BACKOFF_SECONDS", (0, 0, 0))
    repo, idx = _stale_index(make_corpus, fake_embedder, n_docs=6, n_stale=5)
    before = _vec_count(idx)
    limiter = ThrottledEmbedder(fake_embedder, limit=0)    # every size answers 429

    with pytest.raises(embed_mod.EmbeddingError) as excinfo:
        ix.embed_stale(idx, repo, limiter)

    assert excinfo.value.reason == "rate_limited"
    assert _vec_count(idx) == before                       # no partial/zero vectors written
    assert limiter.calls <= 8                              # the ladder terminates, no spin
    idx.close()


# --- LS-4075 R2: per-lane budget, honest report, durable per-success commits ---

class RecordingEmbedder:
    """Dim-correct double that records every request size and text."""

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


class _FailAfterFirst:
    """First subrequest succeeds; every later request answers an unrecovered 429."""

    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.model = wrapped.model
        self.dim = wrapped.dim
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        if self.calls > 1:
            raise embed_mod.EmbeddingError("429 rate limited", reason="rate_limited")
        return self.wrapped.embed(texts)


def _stale_both_lanes(make_corpus, fake_embedder, *, n_docs=70, n_stale_chunks=65,
                      docs_missing=0):
    """Built index with dropped chunk vectors and/or dropped doc vectors."""
    files = {f"doc{i:02d}.md": f"# Doc {i}\n\nmarker{i} body text.\n" for i in range(n_docs)}
    repo = make_corpus(files)
    idx = ix.build_index(repo, fake_embedder)
    ids = [r[0] for r in idx.conn.execute(
        "SELECT chunk_id FROM chunks ORDER BY chunk_id LIMIT ?", (n_stale_chunks,))]
    idx.conn.executemany("DELETE FROM vec_chunks WHERE chunk_id=?", [(i,) for i in ids])
    idx.conn.commit()
    if docs_missing:
        paths = [r[0] for r in idx.conn.execute(
            "SELECT path FROM docs ORDER BY path LIMIT ?", (docs_missing,))]
        idx.conn.executemany(
            "DELETE FROM vec_docs WHERE doc_id=(SELECT doc_id FROM docs WHERE path=?)",
            [(p,) for p in paths])
        idx.conn.commit()
    return repo, idx


def test_budget_both_lanes_resume_and_report(make_corpus, fake_embedder):
    repo, idx = _stale_both_lanes(make_corpus, fake_embedder, n_docs=70,
                                  n_stale_chunks=65, docs_missing=70)
    recording = RecordingEmbedder(fake_embedder)

    first = ix.embed_stale(idx, repo, recording, batch=32, budget=32)

    assert first["status"] == "budget_partial"
    assert first["chunks_embedded"] == 32
    assert first["docs_embedded"] == 32
    assert first["effective_batch"] == 32
    assert first["rate_limit_retries"] == 0
    assert first["stale_left"] == 33
    assert first["docs_stale_left"] == 38
    assert first["account_state"] == "unverified"
    assert first["provider_code"] is None and first["provider_type"] is None
    assert max(recording.sizes) <= 32                      # per-lane budget caps requests

    second = ix.embed_stale(idx, repo, recording, batch=32, budget=32)
    assert (second["chunks_embedded"], second["docs_embedded"]) == (32, 32)
    assert (second["stale_left"], second["docs_stale_left"]) == (1, 6)
    assert second["status"] == "budget_partial"

    third = ix.embed_stale(idx, repo, recording, batch=32, budget=32)
    assert (third["chunks_embedded"], third["docs_embedded"]) == (1, 6)
    assert (third["stale_left"], third["docs_stale_left"]) == (0, 0)
    assert third["status"] == "complete"

    fourth = ix.embed_stale(idx, repo, recording, batch=32, budget=32)
    assert fourth["status"] == "noop"
    assert fourth["chunks_embedded"] == 0 and fourth["docs_embedded"] == 0
    assert max(recording.sizes) <= 32
    idx.close()


def test_budget_doc_only_backlog_is_capped(make_corpus, fake_embedder):
    repo, idx = _stale_both_lanes(make_corpus, fake_embedder, n_docs=70,
                                  n_stale_chunks=0, docs_missing=70)
    recording = RecordingEmbedder(fake_embedder)

    res = ix.embed_stale(idx, repo, recording, batch=32, budget=32)

    assert res["chunks_embedded"] == 0
    assert res["docs_embedded"] == 32
    assert res["stale_left"] == 0
    assert res["docs_stale_left"] == 38
    assert res["status"] == "budget_partial"
    assert max(recording.sizes) <= 32
    idx.close()


@pytest.mark.parametrize("lane", ["chunks", "docs"])
def test_successful_subrequest_then_floor_failure_resumes_without_replay(
        lane, make_corpus, fake_embedder, monkeypatch):
    monkeypatch.setattr(ix, "_RATE_LIMIT_BACKOFF_SECONDS", (0, 0, 0))
    if lane == "chunks":
        repo, idx = _stale_both_lanes(make_corpus, fake_embedder, n_docs=5,
                                      n_stale_chunks=5)
        committed_texts = [r[0] for r in idx.conn.execute(
            "SELECT text FROM chunks WHERE chunk_id IN "
            "(SELECT chunk_id FROM chunks WHERE chunk_id NOT IN "
            "(SELECT chunk_id FROM vec_chunks) ORDER BY chunk_id LIMIT 2)"
        )]
    else:
        repo, idx = _stale_both_lanes(make_corpus, fake_embedder, n_docs=5,
                                      n_stale_chunks=0, docs_missing=5)
        committed_texts = [ix._doc_surface_for_projection(repo, p) for p in
                           idx.paths_missing_doc_vector()[:2]]
        assert all(committed_texts)

    failing = _FailAfterFirst(fake_embedder)
    with pytest.raises(embed_mod.EmbeddingError) as excinfo:
        ix.embed_stale(idx, repo, failing, batch=2)

    progress = excinfo.value.progress
    if lane == "chunks":
        assert progress["chunks_embedded"] == 2 and progress["docs_embedded"] == 0
        assert progress["stale_left"] == 3
    else:
        assert progress["chunks_embedded"] == 0 and progress["docs_embedded"] == 2
        assert progress["docs_stale_left"] == 3
    assert progress["effective_batch"] == 1
    assert progress["rate_limit_retries"] == 1
    assert progress["account_state"] == "unverified"

    # The successful subrequest's vectors are durable…
    if lane == "chunks":
        assert _vec_count(idx) == 2
    else:
        assert len(idx.paths_missing_doc_vector()) == 3

    # …and a resumed tick never re-requests them.
    resumed = RecordingEmbedder(fake_embedder)
    res = ix.embed_stale(idx, repo, resumed, batch=2)
    assert res["stale_left"] == 0 and res["docs_stale_left"] == 0
    assert not any(text in resumed.texts for text in committed_texts if text)
    idx.close()


def test_recovered_429_metadata_survives_success(make_corpus, fake_embedder, monkeypatch):
    monkeypatch.setattr(ix, "_RATE_LIMIT_BACKOFF_SECONDS", (0, 0, 0))
    repo, idx = _stale_both_lanes(make_corpus, fake_embedder, n_docs=4, n_stale_chunks=3)

    class OnceCoded429:
        model = fake_embedder.model
        dim = fake_embedder.dim

        def __init__(self):
            self.calls = 0

        def embed(self, texts):
            self.calls += 1
            if self.calls == 1:
                raise embed_mod.EmbeddingError(
                    "429 rate limited", reason="rate_limited",
                    provider_code="insufficient_quota",
                    provider_type="insufficient_quota")
            return fake_embedder.embed(texts)

    res = ix.embed_stale(idx, repo, OnceCoded429(), batch=2)

    assert res["status"] == "complete"
    assert res["rate_limit_retries"] == 1
    assert res["stale_left"] == 0 and res["docs_stale_left"] == 0
    # The recovered failure's sanitized metadata survives the success report…
    assert res["provider_code"] == "insufficient_quota"
    assert res["provider_type"] == "insufficient_quota"
    # …and is still reported, never verified as an account/billing state.
    assert res["account_state"] == "unverified"
    idx.close()
