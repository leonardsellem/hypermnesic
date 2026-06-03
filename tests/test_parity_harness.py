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


# --- U6: entity-resolution parity (content-distill's `search→slug` pattern) -----------
import subprocess  # noqa: E402

from hypermnesic import graph as _graph  # noqa: E402


def _commit(repo, rel, body, msg="add"):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg], check=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.t",
                        "PATH": __import__("os").environ["PATH"]})


def _entity_corpus():
    return {"infrastructure/hetzner.md": "# Hetzner\n\nthe homelab box.\n",
            "people/alice.md": "# Alice\n\na person.\n"}


def test_resolve_parity_passes_at_parity_with_no_false_wikilink(make_corpus, fake_embedder):
    # AE4 happy path: hypermnesic resolves the entity-resolution set to the correct existing page
    # (exact path + unambiguous stem) and an absent entity resolves to None (no false wikilink),
    # at >= gbrain. resolution_ok gates U7.
    repo = make_corpus(_entity_corpus())
    g = _graph.Graph.from_index(index.build_index(repo, fake_embedder))
    cases = [
        {"name": "infrastructure/hetzner", "expected": "infrastructure/hetzner"},  # exact path
        {"name": "alice", "expected": "people/alice"},                       # unambiguous stem
        {"name": "nonexistent-entity", "expected": None},                    # no page → None
    ]
    # frozen gbrain baseline: it INVENTED a target for the absent entity (a false wikilink)
    gbrain = {"infrastructure/hetzner": "infrastructure/hetzner", "alice": "people/alice",
              "nonexistent-entity": "people/alice"}
    r = ph.resolve_parity(g, cases, gbrain_resolved=gbrain)
    assert r["hyp_accuracy"] == 1.0 and r["false_positives"] == 0
    assert r["hyp_accuracy"] >= r["gbrain_accuracy"]
    assert r["resolution_ok"] is True


def test_resolve_parity_regression_blocks_cutover(make_corpus, fake_embedder):
    # Error path: hypermnesic misses an entity gbrain resolved → hyp accuracy < gbrain → not safe.
    repo = make_corpus(_entity_corpus())
    g = _graph.Graph.from_index(index.build_index(repo, fake_embedder))
    cases = [{"name": "alice", "expected": "people/alice"},
             {"name": "totally-unknown", "expected": "people/bob"}]  # neither layer can hit this
    gbrain = {"alice": "people/alice", "totally-unknown": "people/bob"}  # gbrain "had" bob
    r = ph.resolve_parity(g, cases, gbrain_resolved=gbrain)
    assert r["hyp_accuracy"] < r["gbrain_accuracy"]
    assert r["resolution_ok"] is False


def test_freshness_recall_without_gbrain_index_step(make_corpus, fake_embedder):
    # AE1 integration: a just-committed content-distill delta is recall-able via read-time
    # convergence + retrieve, with NO gbrain sync/extract/embed (the no-index-step U7 bets on).
    repo = make_corpus({"sources/seed.md": "# Seed\n\nseed.\n"})
    idx = index.build_index(repo, fake_embedder)
    _commit(repo, "sources/fresh.md", "# Fresh\n\nuniquefreshmark distilled content.\n", "distill")
    r = ph.freshness_recall(repo, idx, fake_embedder,
                            query="uniquefreshmark", expected_path="sources/fresh.md")
    assert r["recall_able"] is True and r["oversized_delta"] is False


def test_safe_to_cut_over_requires_all_three_signals():
    ok_retrieval = {"verdict": "pass"}
    ok_resolve = {"resolution_ok": True}
    ok_fresh = {"recall_able": True}
    assert ph.safe_to_cut_over(ok_retrieval, ok_resolve, ok_fresh)["safe_to_cut_over"] is True
    # any one signal failing blocks the cutover, with a reason
    bad = ph.safe_to_cut_over({"verdict": "no_decision"}, ok_resolve, ok_fresh)
    assert bad["safe_to_cut_over"] is False and bad["blocking_reasons"]
    assert ph.safe_to_cut_over(ok_retrieval, {"resolution_ok": False}, ok_fresh)[
        "safe_to_cut_over"] is False
    assert ph.safe_to_cut_over(ok_retrieval, ok_resolve, {"recall_able": False})[
        "safe_to_cut_over"] is False
