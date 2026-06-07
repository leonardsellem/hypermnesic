"""U13 — async embed-stale pass: fill dense vectors that lag lexical (AE5)."""

from __future__ import annotations

from hypermnesic import audit_log as al
from hypermnesic import commit_note as cn
from hypermnesic import index as ix
from hypermnesic import ingest


class CountingEmbedder:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.model = wrapped.model
        self.dim = wrapped.dim
        self.texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return self.wrapped.embed(texts)


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
    (repo / "a.md").write_text("# A changed\n\nalpha updated surface.\n", encoding="utf-8")
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
    (repo / "a.md").write_text("# A changed\n\nalpha updated.\n", encoding="utf-8")
    idx.upsert_lexical(
        "a.md",
        ingest.chunks_for_text("a.md", "# A changed\n\nalpha updated.\n"),
    )
    (repo / "b.md").write_text("# B changed\n\nbeta updated.\n", encoding="utf-8")
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
