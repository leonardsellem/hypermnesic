"""U9 — end-to-end QA runner + scorer + verdict finalization [Phase 2].

Orchestrates the F1 headline run: per instance, **retrieve once** (shared across
reader columns) → **reader** (U7) → **judge** (U8), for **both** the GPT-4.1 lead
and the GPT-4o anchor reader columns under the **shared** ``gpt-4o-2024-08-06``
judge — only the reader pass repeats; retrieval and judge are reused. Embed-
quiescence gates the run (void if degraded, R20). The headline runs the full
500-Q `_s` set with no sampling (R17).

Scoring matches the official ``print_qa_metrics.py``, **per reader column**:

- **Overall** — micro accuracy over all instances.
- **Task-averaged** — macro over the question_type buckets, **abstention
  excluded** — the headline metric.
- **Abstention** — accuracy over the ``_abs`` instances, reported separately
  (never folded into the buckets).

**The paid 500-Q run is a deliberate, gated step** (this unit's Execution note):
the code and offline tests land now; ``main`` refuses to spend without an explicit
``--confirm-paid-run`` flag, and the headline is triggered only after the Phase 1
diagnostic is reviewed and a budget — covering both reader passes — is signed off.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from longmemeval import manifest as mf
from longmemeval.adapter import retrieve_for_corpus
from longmemeval.judge import Judge
from longmemeval.materialize import materialize_sessions, session_units
from longmemeval.reader import RetrievedUnit


@dataclass
class QAAnswer:
    instance_id: str
    question_type: str          # normalized question_type bucket
    is_abstention: bool
    correct: bool
    reader_model: str
    reader_error: str | None = None
    judge_error: str | None = None


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _normalize_type(qt: str) -> str:
    return (qt or "").strip().lower().replace("_", "-")


def score_column(answers: list[QAAnswer]) -> dict:
    """Official three numbers for one reader column (print_qa_metrics.py)."""
    overall = _mean([1.0 if a.correct else 0.0 for a in answers])
    non_abs = [a for a in answers if not a.is_abstention]
    abst = [a for a in answers if a.is_abstention]

    by_type: dict[str, list[QAAnswer]] = defaultdict(list)
    for a in non_abs:
        by_type[a.question_type].append(a)
    per_ability = {qt: _mean([1.0 if a.correct else 0.0 for a in group])
                   for qt, group in sorted(by_type.items())}
    task_averaged = _mean(list(per_ability.values()))
    abstention = _mean([1.0 if a.correct else 0.0 for a in abst]) if abst else None

    return {
        "overall": overall,                  # micro over all
        "task_averaged": task_averaged,      # macro over buckets, abstention excluded
        "abstention": abstention,            # over the _abs instances
        "headline_metric": "task_averaged",
        "n": len(answers),
        "n_abstention": len(abst),
        "per_ability": per_ability,
    }


def _context(ranked_unit_ids: list[str], units_map: dict[str, tuple[str, str]],
             k: int) -> list[RetrievedUnit]:
    ctx = []
    for uid in ranked_unit_ids[:k]:
        if uid in units_map:
            date, text = units_map[uid]
            ctx.append(RetrievedUnit(unit_id=uid, date=date, text=text))
    return ctx


def run_qa(instances, work_dir, embedder, readers, judge, *, headline: bool,
           k: int = mf.RETRIEVAL_K) -> dict:
    """Run F1 for one or more reader columns under a shared judge.

    Retrieval (per-session corpus, top-k) is done once per instance and shared;
    each reader column then reads + is graded. A degraded retrieval voids the run.
    """
    work_dir = Path(work_dir)
    # phase 1: retrieve top-k session context per instance (void gate, R20)
    retrievals = []
    for inst in instances:
        base = work_dir / _safe(inst.question_id)
        sessions_m = materialize_sessions(inst, base / "sessions")
        sres = retrieve_for_corpus(sessions_m, inst.question, embedder,
                                   state_dir=base / "state_sessions")
        if sres.degraded:
            return {"track": "qa-headline", "verdict": "void", "void": True,
                    "note": "retrieval degraded to lexical-only; headline voided (R20)."}
        retrievals.append((inst, sres.ranked_units, session_units(inst)))

    # phase 2: per reader column (shared retrieval + judge); only the reader repeats
    columns: dict[str, dict] = {}
    for reader in readers:
        answers: list[QAAnswer] = []
        for inst, ranked, units_map in retrievals:
            ctx = _context(ranked, units_map, k)
            ra = reader.answer(inst.question, inst.question_date, ctx)
            jr = judge.grade(question=inst.question, answer=inst.answer,
                             response=ra.answer, question_type=inst.question_type,
                             is_abstention=inst.is_abstention)
            answers.append(QAAnswer(
                instance_id=inst.question_id,
                question_type=_normalize_type(inst.question_type),
                is_abstention=inst.is_abstention, correct=jr.correct,
                reader_model=reader.model, reader_error=ra.error, judge_error=jr.error))
        columns[reader.model] = score_column(answers)

    return {
        "track": "qa-headline",
        "verdict": "reported",
        "void": False,
        "headline": bool(headline),
        "judge_model": judge.model,
        "k": k,
        "columns": columns,
    }


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "-" for c in name)[:80] or "x"


# --- F1 live (GATED) run entry ----------------------------------------------
_CEILING = mf.default_manifest().phase1_embedding_cost_ceiling_usd
_GATE_MESSAGE = (
    "LongMemEval QA headline is a GATED, paid run (R17: full 500-Q `_s`, no "
    "sampling, both reader columns under the shared gpt-4o-2024-08-06 judge).\n"
    "It is triggered only AFTER the Phase 1 diagnostic is reviewed and a budget "
    "covering both reader passes is signed off.\n"
    f"Estimated Phase-1 embedding ceiling: ${_CEILING} "
    "(reader/judge cost recorded at run time).\n"
    "Re-run with --confirm-paid-run once the budget is approved."
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LongMemEval end-to-end QA headline (F1, GATED)")
    ap.add_argument("--dataset", help="path to longmemeval_s_cleaned.json")
    ap.add_argument("--out", default=None, help="write the result JSON here")
    ap.add_argument("--work-dir", default="harness/longmemeval/corpus")
    ap.add_argument("--cache", default="harness/longmemeval/.embed_cache.sqlite")
    ap.add_argument("--readers", nargs="+",
                    default=[mf.READER_LEAD, mf.READER_ANCHOR],
                    help="reader model columns (default: GPT-4.1 lead + GPT-4o anchor)")
    ap.add_argument("--limit", type=int, default=None, help="dev: cap instances (non-headline)")
    ap.add_argument("--confirm-paid-run", action="store_true",
                    help="required: acknowledge this spends real budget")
    args = ap.parse_args(argv)

    if not args.confirm_paid_run:
        print(_GATE_MESSAGE)
        return 2  # refuse to spend without explicit confirmation
    if not args.dataset:
        ap.error("--dataset is required for a confirmed run")

    from hypermnesic import embed
    from longmemeval import adapter, materialize, reader

    embed.smoke_embed_or_die()  # verify embed-quiescence before scoring (R20)
    instances = materialize.load_dataset(Path(args.dataset))
    if args.limit:
        instances = instances[:args.limit]
    store = adapter.SqliteEmbeddingCache(Path(args.cache))
    embedder = adapter.CachingEmbedder(embed.OpenAIEmbedder(), store=store)
    readers = [reader.Reader(m) for m in args.readers]
    judge = Judge()
    headline = args.limit is None and set(args.readers) == {mf.READER_LEAD, mf.READER_ANCHOR}
    result = run_qa(instances, Path(args.work_dir), embedder, readers, judge, headline=headline)
    store.close()
    blob = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(blob + "\n", encoding="utf-8")
        print(f"wrote QA headline result → {args.out}")
    else:
        print(blob)
    return 0 if not result["void"] else 1


if __name__ == "__main__":
    sys.exit(main())
