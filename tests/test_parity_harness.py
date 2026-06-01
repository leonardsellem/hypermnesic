"""U5 — parity harness logic, on a controlled fixture (offline)."""

from __future__ import annotations

import parity_harness as ph

from hypermnesic import embed as embed_mod
from hypermnesic import index

CORPUS = {
    "doca.md": "# A\n\nunique_alpha unique_alpha content about homelab\n",
    "docb.md": "# B\n\nunique_beta unique_beta content about retrieval\n",
    "docc.md": "# C\n\nunique_gamma content about cooking\n",
}


def _idx(make_corpus, fake_embedder):
    repo = make_corpus(CORPUS)
    return index.build_index(repo, fake_embedder)


def test_aggregate_metrics_and_pass(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    queries = [{"id": "q1", "lang": "en", "query": "unique_alpha", "relevant": ["doca.md"]}]
    baseline = {"q1": ["docc.md"]}  # gbrain misses → hypermnesic strictly better
    r = ph.run_parity(idx, fake_embedder, queries, baseline, k=1)
    assert r["aggregate"]["hyp_recall"] == 1.0
    assert r["aggregate"]["gbrain_recall"] == 0.0
    assert r["delta_recall"] > r["band"]
    assert r["verdict"] == "pass"
    assert r["passes_phase1_gate"] is True
    idx.close()


def test_catastrophic_french_miss_fails(make_corpus, fake_embedder):
    # Covers AE6 (single known-item): hyp wholly misses the one relevant FR doc
    # that gbrain found → hyp recall 0, gbrain recall >0 → catastrophic → FAIL.
    idx = _idx(make_corpus, fake_embedder)
    queries = [{"id": "q1", "lang": "fr", "query": "unique_alpha", "relevant": ["docb.md"]}]
    baseline = {"q1": ["docb.md", "doca.md"]}
    r = ph.run_parity(idx, fake_embedder, queries, baseline, k=1)
    assert r["catastrophic_french_miss"]
    assert r["verdict"] == "fail"
    assert r["passes_phase1_gate"] is False
    idx.close()


def test_catastrophic_not_fired_when_hyp_recalls_some(make_corpus, fake_embedder):
    # Recalibrated AE6 for pooled multi-relevant labels: hyp finds A relevant doc
    # (recall>0) but not the specific one gbrain also had → NOT catastrophic
    # (only a per-doc ranking difference, not a whiffed query).
    idx = _idx(make_corpus, fake_embedder)
    # relevant = {doca (hyp finds via lexical), docb (gbrain has, hyp misses at k=1)}
    queries = [{"id": "q1", "lang": "fr", "query": "unique_alpha",
                "relevant": ["doca.md", "docb.md"]}]
    baseline = {"q1": ["docb.md", "doca.md"]}
    r = ph.run_parity(idx, fake_embedder, queries, baseline, k=1)
    # hyp top-1 = doca (relevant) → hyp recall>0 → not catastrophic
    assert r["catastrophic_french_miss"] == []
    idx.close()


def test_near_tie_band_is_no_decision(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    queries = [{"id": "q1", "lang": "en", "query": "unique_alpha", "relevant": ["doca.md"]}]
    baseline = {"q1": ["doca.md"]}  # gbrain identical → Δ≈0 → no decision
    r = ph.run_parity(idx, fake_embedder, queries, baseline, k=1)
    assert r["delta_recall"] == 0.0
    assert r["verdict"] == "no_decision"
    assert r["passes_phase1_gate"] is False
    idx.close()


def test_deterministic_same_verdict(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    queries = [{"id": "q1", "lang": "en", "query": "unique_alpha", "relevant": ["doca.md"]}]
    baseline = {"q1": ["docc.md"]}
    r1 = ph.run_parity(idx, fake_embedder, queries, baseline, k=1)
    r2 = ph.run_parity(idx, fake_embedder, queries, baseline, k=1)
    assert r1["verdict"] == r2["verdict"]
    assert r1["aggregate"] == r2["aggregate"]
    idx.close()


def test_degraded_run_is_voided(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)

    class Down:
        dim = fake_embedder.dim

        def embed(self, texts):
            raise embed_mod.EmbeddingError("API down")

    queries = [{"id": "q1", "lang": "en", "query": "unique_alpha", "relevant": ["doca.md"]}]
    baseline = {"q1": ["docc.md"]}
    r = ph.run_parity(idx, Down(), queries, baseline, k=1)
    assert r["any_query_degraded_lexical_only"] is True
    assert r["verdict"] == "void"          # voided, not a false FAIL
    assert r["passes_phase1_gate"] is False
    idx.close()


def test_metric_helpers():
    assert ph.recall_at_k(["a", "b", "c"], ["b", "z"], 10) == 0.5
    assert ph.reciprocal_rank(["a", "b", "c"], ["b"]) == 0.5
    assert ph.reciprocal_rank(["a", "b"], ["z"]) == 0.0
    assert ph.doc_ranking(
        [type("H", (), {"path": "a.md"}), type("H", (), {"path": "a.md"}),
         type("H", (), {"path": "b.md"})], 10) == ["a.md", "b.md"]
