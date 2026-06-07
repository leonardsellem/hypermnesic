"""U2 — read-only index core: embed + sqlite-vec + FTS5 + SHA checkpoint.

Covers the plan's U2 test scenarios. Index mechanics use the offline
``FakeEmbedder``; the live OpenAI path is exercised by the smoke embed only.
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from hypermnesic import config, embed, index

NOTE_A = """---
title: Hetzner migration
created: 2026-05-01
---
# Hetzner migration

We moved the homelab from OVH to Hetzner. See [[homelab/network]] for topology.
The Tailscale interface binds the MCP server.
"""

NOTE_B = """---
title: Parité du rappel en français
created: 2026-05-02
---
# Parité du rappel en français

La recherche dense doit égaler gbrain sur le français. L'embedding est
text-embedding-3-large à 1536 dimensions.
"""


# --- dim / startup invariants (KTD2) -------------------------------------

def test_embed_dim_is_1536():
    assert config.EMBED_DIM == 1536
    assert config.EMBED_MODEL == "text-embedding-3-large"


def test_model_dim_mismatch_fails_fast(fake_embedder):
    class Wrong:
        model = "text-embedding-3-large"
        dim = 512
    with pytest.raises(config.ConfigError):
        config.assert_embedder_agrees(Wrong())
    config.assert_embedder_agrees(fake_embedder)  # 1536 → ok


def test_vec_table_declared_1536(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": NOTE_A})
    idx = index.build_index(repo, fake_embedder)
    sql = idx.conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='vec_chunks'"
    ).fetchone()[0]
    assert "float[1536]" in sql
    idx.close()


# --- KNN query shape (KTD3) ----------------------------------------------

def test_knn_query_shape_uses_match_and_k():
    assert "MATCH" in index.Index.KNN_SQL
    assert re.search(r"\bk\s*=\s*\?", index.Index.KNN_SQL)
    assert "vec_distance" not in index.Index.KNN_SQL  # never brute-force ORDER BY


# --- happy path: dense + lexical ------------------------------------------

def test_index_produces_dense_and_lexical_entries(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": NOTE_A, "b.md": NOTE_B})
    idx = index.build_index(repo, fake_embedder)
    # dense: a chunk is its own nearest neighbour under the deterministic embedder
    chunks = idx.all_chunks()
    assert chunks, "expected indexed chunks"
    target = chunks[0]
    qvec = fake_embedder.embed([target["text"]])[0]
    dense = idx.dense_search(qvec, k=3)
    assert dense[0][0] == target["chunk_id"]
    # lexical: a proper noun returns the right page
    lex = idx.lexical_search("Hetzner", k=5)
    assert any(idx.get_chunk(cid)["path"].endswith("a.md") for cid, _ in lex)
    idx.close()


# --- rebuild reproducibility (Covers AE4) ---------------------------------

def test_rebuild_from_same_commit_is_identical(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": NOTE_A, "b.md": NOTE_B})
    idx1 = index.build_index(repo, fake_embedder)
    qvec = fake_embedder.embed(["recherche dense français"])[0]
    before = [cid for cid, _ in idx1.dense_search(qvec, k=5)]
    sha1 = idx1.get_checkpoint()
    idx1.close()
    idx2 = index.build_index(repo, fake_embedder, rebuild=True)
    after = [cid for cid, _ in idx2.dense_search(qvec, k=5)]
    assert idx2.get_checkpoint() == sha1
    assert before == after
    idx2.close()


def test_checkpoint_records_head_sha(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": NOTE_A})
    idx = index.build_index(repo, fake_embedder)
    cp = idx.get_checkpoint()
    assert cp and re.fullmatch(r"[0-9a-f]{40}", cp)
    idx.close()


# --- .gitignore byte-stability (KTD8) -------------------------------------

def test_gitignore_byte_identical_after_index(make_corpus, fake_embedder):
    gi = "node_modules/\n*.log\n"
    repo = make_corpus({"a.md": NOTE_A}, gitignore=gi)
    before = (repo / ".gitignore").read_bytes()
    index.build_index(repo, fake_embedder).close()
    after = (repo / ".gitignore").read_bytes()
    assert before == after
    # the engine ignores its state dir via .git/info/exclude, not .gitignore
    exclude = (repo / ".git" / "info" / "exclude").read_text()
    assert ".hypermnesic/" in exclude


# --- credential discipline -------------------------------------------------

def test_smoke_embed_fails_loud_on_missing_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config, "_DOTENV_PATHS", [tmp_path / "nope.env"])
    with pytest.raises(embed.EmbeddingError) as ei:
        embed.smoke_embed_or_die()
    assert "OPENAI_API_KEY" in str(ei.value)


def test_openai_key_never_in_index_or_output(make_corpus, fake_embedder, monkeypatch):
    sentinel = "sk-SENTINEL-must-not-leak-0123456789"
    monkeypatch.setenv("OPENAI_API_KEY", sentinel)
    repo = make_corpus({"a.md": NOTE_A, "b.md": NOTE_B})
    idx = index.build_index(repo, fake_embedder)
    stats = idx.stats()
    idx.close()
    raw = (index.state_dir_for(repo) / "index.db").read_bytes()
    assert sentinel.encode() not in raw
    assert sentinel not in repr(stats)


def test_index_file_permissions_are_0600(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": NOTE_A})
    idx = index.build_index(repo, fake_embedder)
    idx.close()
    db = index.state_dir_for(repo) / "index.db"
    assert oct((db.stat().st_mode) & 0o777) == oct(0o600)


# --- edge cases (no crash) -------------------------------------------------

def test_empty_repo_does_not_crash(make_corpus, fake_embedder):
    repo = make_corpus({"readme.txt": "not markdown"})
    idx = index.build_index(repo, fake_embedder)
    assert idx.all_chunks() == []
    assert idx.lexical_search("anything", k=5) == []
    idx.close()


def test_frontmatter_only_file_does_not_crash(make_corpus, fake_embedder):
    repo = make_corpus({"empty.md": "---\ntitle: x\ncreated: 2026-05-01\n---\n"})
    idx = index.build_index(repo, fake_embedder)
    idx.close()  # must not raise


def test_non_utf8_bytes_do_not_crash(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"a.md": NOTE_A})
    (repo / "bad.md").write_bytes(b"# T\n\xff\xfe not utf-8 \x80\x81 body\n")
    idx = index.build_index(repo, fake_embedder)
    idx.close()  # must not raise


def test_lexical_phrase_match_exact_terms(make_corpus, fake_embedder):
    # Lexical is precise phrase matching (exact/proper-noun queries); free-form
    # NL recall is the dense channel's job (measured: OR-of-terms floods + hurts).
    repo = make_corpus({
        "doc.md": "# Topic\n\nThe widget assembly throughput improved after retooling.\n",
        "other.md": "# Other\n\nUnrelated cooking recipe content.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    rows = idx.lexical_search("widget assembly throughput", k=5)
    paths = {idx.get_chunk(cid)["path"] for cid, _ in rows}
    assert "doc.md" in paths
    idx.close()


def test_oversized_block_is_split_under_limit(make_corpus, fake_embedder):
    # a single 60k-char paragraph (no blank lines) must split into bounded
    # chunks — the input[118] 8192-token overflow on the first full index.
    from hypermnesic import ingest
    giant = "# Big\n\n" + ("token " * 12000)  # ~72k chars, one block
    repo = make_corpus({"big.md": giant})
    chunks = list(ingest.iter_chunks(repo))
    assert len(chunks) > 1
    assert all(len(c.text) <= ingest.MAX_CHARS for c in chunks)
    index.build_index(repo, fake_embedder).close()  # must not raise


def test_doc_surface_is_title_headings_lead():
    from hypermnesic import ingest
    raw = ("---\ntitle: Hetzner Migration\n---\n"
           "# Heading One\n\nThe lead paragraph about the migration.\n\n"
           "## Subsection\n\nmore body.\n")
    s = ingest.doc_surface(raw, "x.md")
    assert "Hetzner Migration" in s and "Subsection" in s
    assert "lead paragraph" in s
    assert "title:" not in s  # frontmatter excluded


def test_doc_lane_table_and_one_row_per_doc(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": NOTE_A, "b.md": NOTE_B})
    idx = index.build_index(repo, fake_embedder)
    sql = idx.conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='vec_docs'").fetchone()[0]
    assert "float[1536]" in sql
    n_docs = idx.conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    assert n_docs == 2
    n_vecs = idx.conn.execute("SELECT COUNT(*) FROM vec_docs").fetchone()[0]
    assert n_vecs == 2
    idx.close()


def test_upsert_lexical_invalidates_existing_doc_vector_but_preserves_doc_row(
        make_corpus, fake_embedder):
    # Incremental replay of a changed file must make the doc surface stale again
    # without deleting the stable docs row; embed_stale will backfill vec_docs.
    from hypermnesic import ingest

    repo = make_corpus({"a.md": NOTE_A})
    idx = index.build_index(repo, fake_embedder)
    doc_id = idx.conn.execute(
        "SELECT doc_id FROM docs WHERE path=?", ("a.md",)
    ).fetchone()[0]
    assert idx.conn.execute(
        "SELECT COUNT(*) FROM vec_docs WHERE doc_id=?", (doc_id,)
    ).fetchone()[0] == 1

    idx.upsert_lexical(
        "a.md",
        ingest.chunks_for_text("a.md", "# Changed\n\nNew doc-surface lead.\n"),
    )

    assert idx.conn.execute(
        "SELECT doc_id FROM docs WHERE path=?", ("a.md",)
    ).fetchone()[0] == doc_id
    assert idx.conn.execute(
        "SELECT COUNT(*) FROM vec_docs WHERE doc_id=?", (doc_id,)
    ).fetchone()[0] == 0
    assert "a.md" in idx.paths_missing_doc_vector()
    idx.close()


def test_doc_dense_search_returns_paths(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": NOTE_A, "b.md": NOTE_B})
    idx = index.build_index(repo, fake_embedder)
    # query the doc surface of b → b is its own nearest neighbour at the doc lane
    from hypermnesic import ingest
    surface = ingest.doc_surface(NOTE_B, "b.md")
    qvec = fake_embedder.embed([surface])[0]
    docs = idx.doc_dense_search(qvec, k=2)
    assert docs[0][0] == "b.md"
    idx.close()


def test_chunks_for_path(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": NOTE_A})
    idx = index.build_index(repo, fake_embedder)
    cids = idx.chunks_for_path("a.md")
    assert cids and all(idx.get_chunk(c)["path"] == "a.md" for c in cids)
    idx.close()


def test_sqlite_vec_loads():
    conn = sqlite3.connect(":memory:")
    index._load_vec(conn)
    v = conn.execute("SELECT vec_version()").fetchone()[0]
    assert isinstance(v, str)
    conn.close()


# --- U26: bounded embed_stale budget + convergence tunables ----------------

def _stale_index(make_corpus, fake_embedder, n: int):
    """A fully-embedded seed index plus ``n`` lexical-only (vector-less) chunks.

    ``upsert_lexical`` on phantom paths is the cheap way to manufacture the AE5
    lexical-ahead-of-dense gap without git commits or embedding work — exactly the
    state a bounded convergence embed must drain in slices."""
    from hypermnesic import ingest
    repo = make_corpus({"seed.md": "# Seed\n\nseed body.\n"})
    idx = index.build_index(repo, fake_embedder)        # seed fully embedded
    for i in range(n):
        rel = f"notes/n{i}.md"
        idx.upsert_lexical(rel, ingest.chunks_for_text(rel, f"# N{i}\n\nbody {i}.\n"))
    return repo, idx


def test_embed_stale_budget_caps_and_resumes_without_duplicates(make_corpus, fake_embedder):
    repo, idx = _stale_index(make_corpus, fake_embedder, 300)
    assert len(idx.stale_chunk_ids()) == 300
    r1 = index.embed_stale(idx, repo, fake_embedder, budget=128)
    assert r1["chunks_embedded"] == 128
    assert len(idx.stale_chunk_ids()) == 172
    r2 = index.embed_stale(idx, repo, fake_embedder, budget=128)
    assert r2["chunks_embedded"] == 128
    assert len(idx.stale_chunk_ids()) == 44
    r3 = index.embed_stale(idx, repo, fake_embedder, budget=128)
    assert r3["chunks_embedded"] == 44
    assert idx.stale_chunk_ids() == []                  # drained
    # no duplicate vectors: one vec row per chunk (300 notes + the seed chunk)
    n_chunks = idx.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    n_vecs = idx.conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
    assert n_vecs == n_chunks
    idx.close()


def test_embed_stale_budget_none_embeds_all_in_one_pass(make_corpus, fake_embedder):
    repo, idx = _stale_index(make_corpus, fake_embedder, 200)
    assert len(idx.stale_chunk_ids()) == 200
    res = index.embed_stale(idx, repo, fake_embedder, budget=None)   # unbounded (today's behavior)
    assert res["chunks_embedded"] == 200
    assert idx.stale_chunk_ids() == []
    idx.close()


def test_embed_stale_budget_idempotent_on_clean(make_corpus, fake_embedder):
    repo, idx = _stale_index(make_corpus, fake_embedder, 10)
    index.embed_stale(idx, repo, fake_embedder, budget=128)          # drains all 10
    res = index.embed_stale(idx, repo, fake_embedder, budget=128)    # nothing stale now
    assert res["chunks_embedded"] == 0 and res["docs_embedded"] == 0
    idx.close()


def test_embed_stale_budget_on_clean_index_is_zero(make_corpus, fake_embedder):
    repo = make_corpus({"seed.md": "# Seed\n\nseed body.\n"})
    idx = index.build_index(repo, fake_embedder)        # nothing stale
    res = index.embed_stale(idx, repo, fake_embedder, budget=64)
    assert res["chunks_embedded"] == 0 and res["docs_embedded"] == 0
    idx.close()


def test_converge_tunables_are_defined_and_sane():
    assert isinstance(config.CONVERGE_EMBED_BUDGET, int) and config.CONVERGE_EMBED_BUDGET > 0
    assert config.CONVERGE_DEBOUNCE_SECONDS >= 0
    assert isinstance(config.CONVERGE_MAX_DELTA_FILES, int) and config.CONVERGE_MAX_DELTA_FILES > 0
