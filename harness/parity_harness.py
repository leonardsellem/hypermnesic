#!/usr/bin/env python3
"""U5 — French/English retrieval-parity harness (the Phase-0 quality gate).

Scores hypermnesic against a **frozen gbrain baseline** on a frozen query set and
emits the R5 verdict: ``pass`` / ``fail`` / ``no_decision`` / ``void``.

Design (per the plan):
- Metrics: recall@10 and MRR, both sides scored against **human-judged**,
  gbrain-independent relevance labels (KTD6) — so "≥ gbrain" is not tautological.
- Both sides un-reranked (equalize DOWN, KTD5); the gbrain side is a frozen
  fixture captured once, not the live shared service per run.
- Pass bar: hypermnesic ≥ gbrain on aggregate recall@10 **and** MRR (outside a
  near-tie band) **and** no catastrophic French miss (a known-relevant doc that
  is top-10 for the gbrain baseline but outside hypermnesic's top-10 — AE6).
- A near-tie aggregate delta → ``no_decision``; **no_decision counts as
  not-passing** for the Phase-1 gate.
- Run only at **embed-quiescence**; if any query degraded to lexical-only
  (embedding unavailable) the whole run is **voided**, not scored FAIL.

One command, ``--json`` (``ensure_ascii=False``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hypermnesic import retrieve

DEFAULT_K = 10
DEFAULT_BAND = 0.02  # near-tie / no-decision half-width on the aggregate delta


# --- io ------------------------------------------------------------------
def load_queries(path: Path) -> list[dict]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def load_baseline(path: Path) -> dict[str, list[str]]:
    base = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            row = json.loads(line)
            base[row["id"]] = row["top10"]
    return base


# --- metrics -------------------------------------------------------------
def doc_ranking(hits, k: int) -> list[str]:
    """Ordered unique doc paths from chunk hits, truncated to k docs."""
    seen, out = set(), []
    for h in hits:
        if h.path not in seen:
            seen.add(h.path)
            out.append(h.path)
        if len(out) >= k:
            break
    return out


def rank_to_classes(paths: list[str], canon: dict[str, str] | None, k: int) -> list[str]:
    """Map a ranked path list to ordered unique equivalence-class ids, top-k.

    All metrics are computed in class space (not raw paths): a corpus mirrors the
    same doc at multiple paths and stores meeting/source copies of one event, so
    a query's "answer" is a *class*, and finding any member counts. This makes
    the comparison symmetric and kills the duplicate-copy artifacts (q07/q13/q15)
    by construction. With ``canon=None`` a class id is just the path.
    """
    seen, out = set(), []
    for p in paths:
        cid = (canon or {}).get(p, p)
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        if len(out) >= k:
            break
    return out


def recall_at_k(ranked: list[str], relevant: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    topk = set(ranked[:k])
    return len(topk & set(relevant)) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: list[str]) -> float:
    rel = set(relevant)
    for i, p in enumerate(ranked, start=1):
        if p in rel:
            return 1.0 / i
    return 0.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# --- core ----------------------------------------------------------------
def run_parity(idx, embedder, queries: list[dict], baseline: dict[str, list[str]],
               *, k: int = DEFAULT_K, band: float = DEFAULT_BAND,
               canon: dict[str, str] | None = None,
               expand: int = 0, expander=None) -> dict:
    """All metrics are computed in equivalence-CLASS space (see rank_to_classes).

    A query's answer is a class; finding any member counts. recall@k is therefore
    a class hit-rate, MRR uses the first class member, and the catastrophic-miss
    check compares classes — so a content mirror or meeting/source copy found by
    one side but not the exact path the other ranked is NOT a spurious miss.
    """
    per_query = []
    any_degraded = False
    catastrophic = []

    def canon_of(p):
        return (canon or {}).get(p, p)

    for q in queries:
        res = retrieve.search(idx, q["query"], embedder=embedder, k=max(k, 50),
                              expand=expand, expander=expander)
        if res.degraded:
            any_degraded = True
        hyp_cls = rank_to_classes(doc_ranking(res.hits, 50), canon, k)
        gb_cls = rank_to_classes(baseline.get(q["id"], []), canon, k)
        rel_cls = sorted({canon_of(p) for p in q.get("relevant", [])})
        rec = {
            "id": q["id"], "lang": q.get("lang", "en"),
            "hyp_recall": recall_at_k(hyp_cls, rel_cls, k),
            "hyp_mrr": reciprocal_rank(hyp_cls, rel_cls),
            "gbrain_recall": recall_at_k(gb_cls, rel_cls, k),
            "gbrain_mrr": reciprocal_rank(gb_cls, rel_cls),
            "degraded": res.degraded,
        }
        # AE6 catastrophic French miss, in class space: a relevant class top-k for
        # gbrain but for which hypermnesic found NO member in its top-k.
        if rec["lang"] == "fr":
            missed = [c for c in (set(rel_cls) & set(gb_cls[:k])) if c not in set(hyp_cls[:k])]
            if missed:
                catastrophic.append({"id": q["id"], "missed_classes": sorted(missed)})
        per_query.append(rec)

    agg = {
        "hyp_recall": _mean([r["hyp_recall"] for r in per_query]),
        "hyp_mrr": _mean([r["hyp_mrr"] for r in per_query]),
        "gbrain_recall": _mean([r["gbrain_recall"] for r in per_query]),
        "gbrain_mrr": _mean([r["gbrain_mrr"] for r in per_query]),
    }
    d_recall = agg["hyp_recall"] - agg["gbrain_recall"]
    d_mrr = agg["hyp_mrr"] - agg["gbrain_mrr"]

    verdict = _verdict(d_recall, d_mrr, band, bool(catastrophic), any_degraded)
    return {
        "k": k, "band": band, "n_queries": len(queries),
        "n_french": sum(1 for q in queries if q.get("lang") == "fr"),
        "aggregate": agg,
        "delta_recall": d_recall, "delta_mrr": d_mrr,
        "catastrophic_french_miss": catastrophic,
        "any_query_degraded_lexical_only": any_degraded,
        "verdict": verdict,
        "passes_phase1_gate": verdict == "pass",
        "per_query": per_query,
    }


def _verdict(d_recall: float, d_mrr: float, band: float,
             catastrophic: bool, degraded: bool) -> str:
    if degraded:
        return "void"  # embedding unavailable on ≥1 query — not a real FAIL
    if catastrophic:
        return "fail"
    if d_recall <= -band or d_mrr <= -band:
        return "fail"            # clearly below gbrain on a metric
    if d_recall >= band and d_mrr >= band:
        return "pass"            # clearly ≥ gbrain on both
    return "no_decision"          # within the near-tie band → not-passing


# --- cli -----------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="hypermnesic French/English parity harness")
    p.add_argument("--index-db", required=True)
    p.add_argument("--queries", required=True, help="harness/queries.frozen.jsonl")
    p.add_argument("--baseline", required=True, help="frozen gbrain baseline jsonl")
    p.add_argument("--corpus", default=None,
                   help="corpus path; enables equivalence-class scoring (content mirrors + "
                        "same-event meeting/source) for both sides")
    p.add_argument("--k", type=int, default=DEFAULT_K)
    p.add_argument("--band", type=float, default=DEFAULT_BAND)
    p.add_argument("--expand", type=int, default=0,
                   help="multi-query expansion variants per query (0 = off)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    from hypermnesic import embed, index
    embed.smoke_embed_or_die()  # ensure embed-quiescence is achievable, fail loud otherwise
    canon = None
    if args.corpus:
        import corpus_equivalence
        classes = corpus_equivalence.equivalence_classes(Path(args.corpus))
        canon = {p: members[0] for p, members in classes.items()}  # canonical = first member
    expander = None
    if args.expand:
        from hypermnesic import expand as expand_mod
        expander = expand_mod.OpenAIExpander()
    idx = index.Index(Path(args.index_db))
    embedder = embed.OpenAIEmbedder()
    result = run_parity(idx, embedder, load_queries(args.queries),
                        load_baseline(args.baseline), k=args.k, band=args.band,
                        canon=canon, expand=args.expand, expander=expander)
    idx.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"verdict={result['verdict']}  Δrecall@{args.k}={result['delta_recall']:+.4f}  "
              f"Δmrr={result['delta_mrr']:+.4f}  "
              f"catastrophic_fr={len(result['catastrophic_french_miss'])}  "
              f"degraded={result['any_query_degraded_lexical_only']}")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
