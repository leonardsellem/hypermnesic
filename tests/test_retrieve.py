"""U3 — hybrid retrieval (RRF fusion), optional rerank, graceful degradation."""

from __future__ import annotations

from hypermnesic import embed as embed_mod
from hypermnesic import index, retrieve

NOTE_FR = """# Parité du rappel en français

La recherche dense doit égaler gbrain sur le rappel français. L'embedding
utilise text-embedding-3-large à 1536 dimensions.
"""
NOTE_EN = """# Hetzner homelab migration

We migrated the homelab from OVH to Hetzner and bound the MCP server to the
Tailscale interface address.
"""
NOTE_OTHER = "# Cooking\n\nA recipe for pancakes with flour and eggs.\n"


def _idx(make_corpus, fake_embedder):
    repo = make_corpus({"fr.md": NOTE_FR, "en.md": NOTE_EN, "other.md": NOTE_OTHER})
    return index.build_index(repo, fake_embedder)


def test_english_proper_noun_query(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    res = retrieve.search(idx, "Hetzner", embedder=fake_embedder, k=3)
    assert res.hits
    assert res.hits[0].path == "en.md"
    assert res.dense_used is True
    idx.close()


def test_french_query(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    res = retrieve.search(idx, "rappel français parité", embedder=fake_embedder, k=3)
    assert any(h.path == "fr.md" for h in res.hits)
    idx.close()


def test_graceful_degradation_when_embedding_down(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)

    class DownEmbedder:
        dim = fake_embedder.dim

        def embed(self, texts):
            raise embed_mod.EmbeddingError("API down")

    res = retrieve.search(idx, "Hetzner", embedder=DownEmbedder(), k=3)
    assert res.dense_used is False
    assert res.degraded is True          # harness must VOID, not FAIL
    assert res.lexical_used is True
    assert any(h.path == "en.md" for h in res.hits)  # lexical still answers
    idx.close()


def test_collapses_exact_content_duplicates(make_corpus, fake_embedder):
    # Mirror-flooding: the same content at two paths must not consume two result
    # slots — collapse to the highest-ranked representative so distinct docs
    # surface. (Synthetic fixture; no real corpus content.)
    mirror_body = "# Widget brief\n\nalpha widget assembly brief content here.\n"
    repo = make_corpus({
        "docs/briefs/x.md": mirror_body,
        "projects/teamspace/docs/briefs/x.md": mirror_body,   # exact mirror of the above
        "docs/distinct.md": "# Widget distinct\n\nalpha widget a distinct document.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    res = retrieve.search(idx, "alpha widget", embedder=fake_embedder, k=10)
    paths = [h.path for h in res.hits]
    mirror_hits = [p for p in paths if p.endswith("briefs/x.md")]
    assert len(mirror_hits) == 1, f"mirror not collapsed: {paths}"
    # collapse is opt-out
    res_raw = retrieve.search(idx, "alpha widget", embedder=fake_embedder, k=10,
                              collapse_duplicates=False)
    raw_mirror = [p for p in (h.path for h in res_raw.hits) if p.endswith("briefs/x.md")]
    assert len(raw_mirror) == 2
    idx.close()


def test_expansion_fuses_variant_results(make_corpus, fake_embedder):
    # Multi-query expansion: a variant query surfaces docs the original misses.
    # (With the deterministic embedder, a variant equal to a doc's text retrieves
    # that doc at distance 0 — exercises the fan-out + RRF fusion mechanics.)
    repo = make_corpus({
        "a.md": "# A\n\nalpha alpha alpha topic one.\n",
        "b.md": "# B\n\nbeta beta beta topic two.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    calls = []

    def expander(query, n):
        calls.append((query, n))
        return ["beta beta beta topic two."]  # variant == b.md chunk text

    res = retrieve.search(idx, "alpha", embedder=fake_embedder, k=5,
                          expand=1, expander=expander)
    assert calls and calls[0][1] == 1
    assert any(h.path == "b.md" for h in res.hits)  # surfaced via the variant
    idx.close()


def test_expansion_graceful_on_expander_failure(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha alpha alpha.\n"})
    idx = index.build_index(repo, fake_embedder)

    def bad_expander(query, n):
        raise RuntimeError("LLM unavailable")

    res = retrieve.search(idx, "alpha", embedder=fake_embedder, k=5,
                          expand=2, expander=bad_expander)
    assert res.hits and res.dense_used is True  # no crash; behaves as expand=0
    idx.close()


def test_doc_lane_lifts_doc_by_surface(make_corpus, fake_embedder):
    # A doc whose SURFACE (title) matches the query but whose body chunks don't
    # should be lifted by the doc lane. (Deterministic embedder: query == the
    # doc's surface → doc-lane returns it at distance 0.)
    from hypermnesic import index as index_mod
    from hypermnesic import ingest
    note = "# zeta unique surface marker\n\nbody discusses unrelated omega omega.\n"
    repo = make_corpus({"target.md": note, "other.md": "# Other\n\nomega omega omega.\n"})
    idx = index_mod.build_index(repo, fake_embedder)
    surface = ingest.doc_surface(note, "target.md")
    res = retrieve.search(idx, surface, embedder=fake_embedder, k=5)
    target = [h for h in res.hits if h.path == "target.md"]
    assert target and "doc" in target[0].channels   # surfaced via the doc lane
    # turning the doc lane off must not credit the doc lane
    res_off = retrieve.search(idx, surface, embedder=fake_embedder, k=5, use_doc_lane=False)
    assert all("doc" not in h.channels for h in res_off.hits)
    idx.close()


def test_rerank_changes_order_not_membership(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    base = retrieve.search(idx, "homelab français Hetzner recipe", embedder=fake_embedder, k=3)
    assert len(base.hits) >= 2

    def reverse_rerank(query, hits):
        return list(reversed(hits))

    rer = retrieve.search(idx, "homelab français Hetzner recipe", embedder=fake_embedder,
                          k=3, rerank=reverse_rerank)
    assert {h.chunk_id for h in base.hits} == {h.chunk_id for h in rer.hits}  # membership
    assert [h.chunk_id for h in base.hits] != [h.chunk_id for h in rer.hits]  # order
    idx.close()
