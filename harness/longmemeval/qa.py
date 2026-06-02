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

from longmemeval import batch
from longmemeval import manifest as mf
from longmemeval.adapter import Embedder, retrieve_for_corpus, safe_name
from longmemeval.judge import Judge
from longmemeval.materialize import (
    Instance,
    materialize_sessions,
    normalize_question_type,
    session_units,
)
from longmemeval.reader import Reader, RetrievedUnit


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
    # None (not 0.0) when there are no scorable buckets, so an all-abstention or
    # empty column is not misread as a genuine 0% headline.
    task_averaged = _mean(list(per_ability.values())) if per_ability else None
    abstention = _mean([1.0 if a.correct else 0.0 for a in abst]) if abst else None
    # Surface partial-evaluation: a reader/judge outage scores graded-False answers
    # that silently depress task_averaged. Counts let the caller see (and discount
    # or re-run) a column that was only partially evaluated rather than trusting it.
    reader_errors = sum(1 for a in answers if a.reader_error)
    judge_errors = sum(1 for a in answers if a.judge_error)

    return {
        "overall": overall,                  # micro over all
        "task_averaged": task_averaged,      # macro over buckets, abstention excluded
        "abstention": abstention,            # over the _abs instances
        "headline_metric": "task_averaged",
        "n": len(answers),
        "n_abstention": len(abst),
        "per_ability": per_ability,
        "reader_errors": reader_errors,
        "judge_errors": judge_errors,
    }


def _context(ranked_unit_ids: list[str], units_map: dict[str, tuple[str, str]],
             k: int) -> list[RetrievedUnit]:
    ctx = []
    for uid in ranked_unit_ids[:k]:
        if uid in units_map:
            date, text = units_map[uid]
            ctx.append(RetrievedUnit(unit_id=uid, date=date, text=text))
    return ctx


def _void_result(mode: str) -> dict:
    return {"track": "qa-headline", "verdict": "void", "void": True, "mode": mode,
            "note": "retrieval degraded to lexical-only; headline voided (R20)."}


def _retrieve_phase(instances: list[Instance], work_dir: Path, embedder: Embedder,
                    k: int):
    """Retrieve top-k session context per instance, once, shared across columns.

    Returns the list of ``(instance, ranked_unit_ids, units_map)`` or ``None`` if any
    corpus degraded (void gate, R20). Retrieval uses the **frozen production**
    ``candidate_k`` (R19) so the top-k the reader sees mirrors the shipped read path.
    """
    work_dir = Path(work_dir)
    retrievals = []
    for inst in instances:
        base = work_dir / safe_name(inst.question_id)
        sessions_m = materialize_sessions(inst, base / "sessions")
        sres = retrieve_for_corpus(sessions_m, inst.question, embedder,
                                   state_dir=base / "state_sessions",
                                   search_depth=mf.RETRIEVAL_CANDIDATE_K)
        if sres.degraded:
            return None
        retrievals.append((inst, sres.ranked_units, session_units(inst)))
    return retrievals


def _qa_answer(inst: Instance, reader: Reader, ra, jr) -> QAAnswer:
    return QAAnswer(instance_id=inst.question_id,
                    question_type=normalize_question_type(inst.question_type),
                    is_abstention=inst.is_abstention, correct=jr.correct,
                    reader_model=reader.model, reader_error=ra.error, judge_error=jr.error)


def run_qa(instances: list[Instance], work_dir: Path, embedder: Embedder,
           readers: list[Reader], judge: Judge, *, headline: bool,
           k: int = mf.RETRIEVAL_K) -> dict:
    """Run F1 (sync API) for one or more reader columns under a shared judge.

    Retrieval is done once and shared; each reader column then reads + is graded.
    A degraded retrieval voids the run.
    """
    retrievals = _retrieve_phase(instances, work_dir, embedder, k)
    if retrievals is None:
        return _void_result("sync")

    columns: dict[str, dict] = {}
    for reader in readers:
        answers: list[QAAnswer] = []
        for inst, ranked, units_map in retrievals:
            ctx = _context(ranked, units_map, k)
            ra = reader.answer(inst.question, inst.question_date, ctx)
            jr = judge.grade(question=inst.question, answer=inst.answer,
                             response=ra.answer, question_type=inst.question_type,
                             is_abstention=inst.is_abstention)
            answers.append(_qa_answer(inst, reader, ra, jr))
        columns[reader.model] = score_column(answers)

    return {"track": "qa-headline", "verdict": "reported", "void": False,
            "headline": bool(headline), "judge_model": judge.model, "k": k,
            "mode": "sync", "columns": columns}


def run_qa_batch(instances: list[Instance], work_dir: Path, embedder: Embedder,
                 readers: list[Reader], judge: Judge, *, headline: bool, client,
                 k: int = mf.RETRIEVAL_K, **batch_kw) -> dict:
    """Run F1 via the OpenAI **Batch API** (50% cheaper). Two stages: one reader
    batch across all (column × instance), then one judge batch over the reader
    answers. Retrieval + scoring are identical to ``run_qa``; only the LLM
    transport differs. ``client`` is an OpenAI-like client; ``batch_kw`` is passed
    to ``batch.submit_and_collect`` (``poll_interval``, ``timeout``, ``sleep``,
    ``log``)."""
    retrievals = _retrieve_phase(instances, work_dir, embedder, k)
    if retrievals is None:
        return _void_result("batch")

    # stage 1: one reader batch over every (column, instance)
    reader_reqs, rmeta = [], {}
    for reader in readers:
        for inst, ranked, units_map in retrievals:
            body, truncated, used = reader.request_body(
                inst.question, inst.question_date, _context(ranked, units_map, k))
            cid = f"r-{len(reader_reqs)}"
            reader_reqs.append({"custom_id": cid, "method": "POST",
                                "url": "/v1/chat/completions", "body": body})
            rmeta[cid] = (reader, inst, truncated, used)
    reader_out = batch.submit_and_collect(client, reader_reqs, **batch_kw)
    answers = {cid: meta[0].answer_from_content(
                   reader_out.get(cid, {}).get("content"),
                   truncated=meta[2], units_used=meta[3],
                   error=reader_out.get(cid, {"error": "missing batch result"}).get("error"))
               for cid, meta in rmeta.items()}

    # stage 2: one judge batch over the reader answers (each column graded separately)
    judge_reqs, jmeta = [], {}
    for cid, (reader, inst, _t, _u) in rmeta.items():
        ra = answers[cid]
        body, kind = judge.request_body(question=inst.question, answer=inst.answer,
                                        response=ra.answer, question_type=inst.question_type,
                                        is_abstention=inst.is_abstention)
        jcid = f"j-{len(judge_reqs)}"
        judge_reqs.append({"custom_id": jcid, "method": "POST",
                           "url": "/v1/chat/completions", "body": body})
        jmeta[jcid] = (reader, inst, kind, ra)
    judge_out = batch.submit_and_collect(client, judge_reqs, **batch_kw)

    # score per column
    by_col: dict[str, list[QAAnswer]] = {r.model: [] for r in readers}
    for jcid, (reader, inst, kind, ra) in jmeta.items():
        res = judge_out.get(jcid, {"content": None, "error": "missing batch result"})
        jr = judge.grade_from_content(res.get("content"), kind=kind, error=res.get("error"))
        by_col[reader.model].append(_qa_answer(inst, reader, ra, jr))
    columns = {model: score_column(ans) for model, ans in by_col.items()}

    return {"track": "qa-headline", "verdict": "reported", "void": False,
            "headline": bool(headline), "judge_model": judge.model, "k": k,
            "mode": "batch", "columns": columns}


# --- F1 live (GATED) run entry ----------------------------------------------
def _gate_message() -> str:
    """The gate text shown when a paid run is attempted without confirmation.
    Built lazily so importing this module never evaluates the manifest/config."""
    ceiling = mf.default_manifest().phase1_embedding_cost_ceiling_usd
    return (
        "LongMemEval QA headline is a GATED, paid run (R17: full 500-Q `_s`, no "
        "sampling, both reader columns under the shared gpt-4o-2024-08-06 judge).\n"
        "It is triggered only AFTER the Phase 1 diagnostic is reviewed and a budget "
        "covering both reader passes is signed off.\n"
        f"Estimated Phase-1 embedding ceiling: ${ceiling} "
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
    ap.add_argument("--batch", action="store_true",
                    help="route reader+judge through the OpenAI Batch API (50%% cheaper)")
    ap.add_argument("--poll-interval", type=float, default=30.0,
                    help="batch poll interval in seconds (--batch only)")
    ap.add_argument("--confirm-paid-run", action="store_true",
                    help="required: acknowledge this spends real budget")
    args = ap.parse_args(argv)

    if not args.confirm_paid_run:
        print(_gate_message())
        return 2  # refuse to spend without explicit confirmation
    if not args.dataset:
        ap.error("--dataset is required for a confirmed run")

    from hypermnesic import config, embed
    from longmemeval import adapter, materialize, reader

    embed.smoke_embed_or_die()  # verify embed-quiescence before scoring (R20)
    instances = materialize.load_dataset(Path(args.dataset))
    if args.limit:
        instances = instances[:args.limit]
    headline = args.limit is None and set(args.readers) == {mf.READER_LEAD, mf.READER_ANCHOR}
    with adapter.SqliteEmbeddingCache(Path(args.cache)) as store:  # always closed
        embedder = adapter.CachingEmbedder(embed.OpenAIEmbedder(), store=store)
        readers = [reader.Reader(m) for m in args.readers]
        if args.batch:
            from openai import OpenAI
            client = OpenAI(api_key=config.get_api_key())
            result = run_qa_batch(instances, Path(args.work_dir), embedder, readers,
                                  Judge(), headline=headline, client=client,
                                  poll_interval=args.poll_interval,
                                  log=lambda m: print(m, flush=True))  # live, not buffered
        else:
            result = run_qa(instances, Path(args.work_dir), embedder, readers, Judge(),
                            headline=headline)
    blob = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(blob + "\n", encoding="utf-8")
        print(f"wrote QA headline result → {args.out}")
    else:
        print(blob)
    return 0 if not result["void"] else 1


if __name__ == "__main__":
    sys.exit(main())
