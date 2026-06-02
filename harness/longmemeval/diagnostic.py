"""U4 — retrieval diagnostic scorer (session + turn level).

Computes the official LongMemEval retrieval metrics over both granularities,
aggregate and per-ability:

- ``recall_all@k`` — 1.0 iff **every** gold unit is in the top-k, else 0.0 (the
  headline retrieval metric; strictly distinct from the parity harness's
  fractional ``recall_at_k``).
- ``ndcg_any@k`` — binary-relevance NDCG (ideal-DCG normalized).
- ``recall_any@k`` — 1.0 iff **at least one** gold unit is in the top-k; reported
  for the **date-sensitive** abilities (knowledge-update, temporal-reasoning),
  beside the gold-set-size distribution, so a low ``recall_all`` there reads as
  date-blind ranking / metric strictness rather than a genuine memory miss (the
  engine does no date-aware retrieval ranking).

Session level reports @5/@10; turn level adds @50. The 30 ``_abs`` instances are
excluded from retrieval scoring (matching official ``run_retrieval.py``). A run
whose retrieval degraded to lexical-only is **voided**, not scored (R20/AE2).
The result is a structured dict with an explicit ``verdict``/``void`` field,
mirroring ``harness/parity_harness.py``; only aggregate/per-ability numbers are
ever committed (R15).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from longmemeval.adapter import RetrievalRun
from longmemeval.materialize import turn_to_session

SESSION_KS = (5, 10)
TURN_KS = (5, 10, 50)

# Abilities whose answer depends on session date/order. Hypermnesic's search()
# does no recency/date weighting, so under strict recall_all these can score low
# for ranking/metric reasons, not memory reasons — hence the recall_any companion.
DATE_SENSITIVE_TYPES = {"knowledge-update", "temporal-reasoning"}


# --- metrics ----------------------------------------------------------------
def recall_all_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """1.0 iff every gold unit appears in the top-k ranking, else 0.0."""
    if not gold:
        return 0.0
    return 1.0 if set(gold) <= set(ranked[:k]) else 0.0


def recall_any_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """1.0 iff at least one gold unit appears in the top-k ranking, else 0.0."""
    if not gold:
        return 0.0
    return 1.0 if set(ranked[:k]) & set(gold) else 0.0


def ndcg_any_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """Binary-relevance NDCG@k (each gold unit has relevance 1)."""
    gold = set(gold)
    if not gold:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, u in enumerate(ranked[:k]) if u in gold)
    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg else 0.0


def _normalize_type(qt: str) -> str:
    return qt.strip().lower().replace("_", "-")


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# --- aggregation ------------------------------------------------------------
def _rankings(results, gran: str) -> list[tuple[list[str], set[str]]]:
    """(ranking, gold) pairs for scorable instances at one granularity (gold
    non-empty — instances with no gold for this granularity are not scorable)."""
    pairs = []
    for r in results:
        hr = getattr(r, gran)
        if hr.gold_units:
            pairs.append((hr.ranked_units, set(hr.gold_units)))
    return pairs


def _aggregate(results, gran: str, ks: tuple[int, ...]) -> dict:
    pairs = _rankings(results, gran)
    out: dict = {"n": len(pairs)}
    for k in ks:
        out[f"recall_all@{k}"] = _mean([recall_all_at_k(r, g, k) for r, g in pairs])
        out[f"ndcg_any@{k}"] = _mean([ndcg_any_at_k(r, g, k) for r, g in pairs])
    return out


def _aggregate_any(results, gran: str, ks: tuple[int, ...]) -> dict:
    pairs = _rankings(results, gran)
    return {f"recall_any@{k}": _mean([recall_any_at_k(r, g, k) for r, g in pairs])
            for k in ks}


def _aggregate_turn_derived_session(results, ks: tuple[int, ...]) -> dict:
    """Session recall computed by mapping the per-turn ranking back to sessions
    (turn_to_session), scored against the session-level gold — localizes whether
    the evidence is reachable at all when the session ranking misses it."""
    pairs = []
    for r in results:
        if not r.session.gold_units:
            continue
        derived: list[str] = []
        seen: set[str] = set()
        for tid in r.turn.ranked_units:
            sid = turn_to_session(tid)
            if sid not in seen:
                seen.add(sid)
                derived.append(sid)
        pairs.append((derived, set(r.session.gold_units)))
    out: dict = {"n": len(pairs)}
    for k in ks:
        out[f"recall_all@{k}"] = _mean([recall_all_at_k(r, g, k) for r, g in pairs])
        out[f"ndcg_any@{k}"] = _mean([ndcg_any_at_k(r, g, k) for r, g in pairs])
    return out


def _gold_size_distribution(results, gran: str) -> dict:
    sizes = [len(getattr(r, gran).gold_units) for r in results
             if getattr(r, gran).gold_units]
    if not sizes:
        return {"min": 0, "max": 0, "mean": 0, "values": []}
    return {"min": min(sizes), "max": max(sizes),
            "mean": round(sum(sizes) / len(sizes), 3), "values": sorted(sizes)}


def score_diagnostic(run: RetrievalRun) -> dict:
    """Score a retrieval run into the committed diagnostic result dict.

    A void run (embeddings degraded to lexical-only) reports no numbers (R20/AE2).
    """
    if run.void:
        return {"track": "retrieval-diagnostic", "verdict": "void", "void": True,
                "note": "retrieval degraded to lexical-only; run voided, not scored (R20)."}

    scored = [r for r in run.results if not r.instance.is_abstention]
    n_abs = sum(1 for r in run.results if r.instance.is_abstention)

    by_type: dict[str, list] = defaultdict(list)
    for r in scored:
        by_type[_normalize_type(r.instance.question_type)].append(r)

    per_ability: dict[str, dict] = {}
    for qt, group in sorted(by_type.items()):
        entry = {
            "n": len(group),
            "date_sensitive": qt in DATE_SENSITIVE_TYPES,
            "session": _aggregate(group, "session", SESSION_KS),
            "turn": _aggregate(group, "turn", TURN_KS),
        }
        if qt in DATE_SENSITIVE_TYPES:
            entry["recall_any"] = {
                "session": _aggregate_any(group, "session", SESSION_KS),
                "turn": _aggregate_any(group, "turn", TURN_KS),
            }
            entry["gold_set_size"] = _gold_size_distribution(group, "session")
        per_ability[qt] = entry

    return {
        "track": "retrieval-diagnostic",
        "verdict": "reported",
        "void": False,
        "n_instances": len(scored),
        "n_excluded_abstention": n_abs,
        "session_ks": list(SESSION_KS),
        "turn_ks": list(TURN_KS),
        "session": _aggregate(scored, "session", SESSION_KS),
        "turn": _aggregate(scored, "turn", TURN_KS),
        "turn_derived_session": _aggregate_turn_derived_session(scored, SESSION_KS),
        "per_ability": per_ability,
    }


# --- F2 live run entry ------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """F2 — the retrieval-only diagnostic run (cheap, embeddings-only).

    Loads the pinned dataset, materializes + retrieves every instance with the
    production embedder (content-hash-cached), and scores. Embed-quiescence is
    verified before scoring (``smoke_embed_or_die``); a degraded run voids.
    """
    ap = argparse.ArgumentParser(description="LongMemEval retrieval diagnostic (F2)")
    ap.add_argument("--dataset", required=True, help="path to longmemeval_s_cleaned.json")
    ap.add_argument("--work-dir", default="harness/longmemeval/corpus")
    ap.add_argument("--out", default=None, help="write the result JSON here")
    ap.add_argument("--cache", default="harness/longmemeval/.embed_cache.sqlite")
    ap.add_argument("--limit", type=int, default=None, help="dev: cap instances (non-headline)")
    args = ap.parse_args(argv)

    from hypermnesic import embed
    from longmemeval import adapter, materialize

    embed.smoke_embed_or_die()  # verify embed-quiescence is achievable before scoring (R20)
    instances = materialize.load_dataset(Path(args.dataset))
    if args.limit:
        instances = instances[:args.limit]
    store = adapter.SqliteEmbeddingCache(Path(args.cache))
    embedder = adapter.CachingEmbedder(embed.OpenAIEmbedder(), store=store)
    run = adapter.retrieve_instances(instances, Path(args.work_dir), embedder)
    store.close()
    result = score_diagnostic(run)
    result["limited_to"] = args.limit  # non-None ⇒ a dev/non-headline subset
    blob = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(blob + "\n", encoding="utf-8")
        print(f"wrote diagnostic result → {args.out}")
    else:
        print(blob)
    return 0 if not result["void"] else 1


if __name__ == "__main__":
    sys.exit(main())
