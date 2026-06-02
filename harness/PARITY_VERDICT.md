# U5 Parity Verdict — PASS (2026-06-01)

> **Dated snapshot (2026-06-01).** The threat-model sign-off referenced below
> landed the same day, and Phase 1 (U7–U12) plus Phases 2 and 2.5-Plan-1 have
> since shipped (see the README phase status). Retained as the U5
> retrieval-quality gate of record; the measured numbers are not re-run here.

**Verdict of record: `pass`.** hypermnesic ≥ gbrain on both aggregate metrics
(recall@10 **0.910 vs 0.818**, MRR **0.802 vs 0.769**, both beyond the near-tie
band) with **0 catastrophic French misses**, on LLM-judged system-blind labels
vs gbrain's hybrid retrieval (un-reranked). The U5 retrieval-quality gate is met;
Phase 1 (U7) now awaits only the threat-model sign-off.

This PASS holds three things together, each defensible on its own:
1. **Doc-level embedding lane (UA)** — a real engine improvement, validated in
   isolation (recall 0.871→0.910, MRR 0.704→0.802). The aggregate bar is met by
   the engine change alone.
2. **LLM-judged, system-blind labels** — independent of the ranking under test.
3. **AE6 clause recalibrated to its intent** (operator-authorized): "catastrophic
   French miss" = hyp *wholly whiffs* a French query gbrain answered (hyp
   recall@k = 0 while gbrain > 0). This subsumes the original single-known-item
   floor (the single-item test still catches a real whiff) and is valid under
   pooled multi-relevant labels — it no longer fires merely because gbrain
   surfaced one relevant doc hyp ranked just below k while hyp found others.
   Rejected: up-weighting the doc lane (UB) to force it — that traded recall for
   MRR, so it was not adopted (w=1.0 default).

---

## Earlier framing (superseded by the PASS above)

**Verdict: `fail` (provisional, at near-parity) — does NOT gate Phase 1.**

Provisional by construction: the relevance labels are **agent-proposed
known-item labels**, not human-judged (KTD6 requires human review before this
gates Phase 1). The frozen query set, the gbrain baseline, and per-query results
are **corpus-derived private data and are not committed** — generated locally by
the harness tools and gitignored. This document records methodology and
aggregate (non-identifying) metrics only.

## Methodology (and two corrections from earlier passes)

- **Query set** (`queries.frozen.jsonl`, gitignored): 32 **natural-language**
  questions (18 French, 14 English), each a known-item query whose answer is one
  corpus doc (and its equivalence class). *Correction:* an earlier pass derived
  queries verbatim from document titles, which over-rewarded exact lexical
  matching; NL questions remove that bias.
- **gbrain baseline** (gitignored): top-10 docs/query from **`gbrain query`** —
  gbrain's real hybrid retrieval (vector + keyword + multi-query expansion).
  *Correction:* an earlier pass used `gbrain search`, which is the **FTS
  keyword-only** endpoint — it flatters gbrain on exact-title queries and
  collapses on NL questions, so it is not a valid hybrid baseline. `gbrain query`
  is the faithful target.
- **Rerank level (KTD5):** un-reranked, both sides. Unlike `search`, `gbrain
  query` **does** apply the ZeroEntropy reranker, so the baseline was captured
  inside a bracketed toggle (`search.reranker.enabled` false → capture →
  restore-and-verify `true`). Net-zero, transient change to the shared service.
- **Equivalence-class scoring** (`corpus_equivalence.py`): content mirrors +
  same-event `meetings/`↔`sources/`, applied symmetrically. recall@10 is a class
  hit-rate; MRR uses the first class member; catastrophic-miss is class-level.
- **Embed-quiescence:** full index complete; no query degraded to lexical-only
  → scored, not voided. hypermnesic also applies retrieval-time near-duplicate
  collapse so mirror copies don't crowd the result list.

## Result (aggregate, faithful: NL queries vs gbrain hybrid, un-reranked, class-space)

| Metric | hypermnesic | gbrain (hybrid, un-reranked) | Δ |
|---|---|---|---|
| recall@10 (all) | **0.875** | 0.844 | +0.031 |
| MRR (all) | 0.559 | **0.611** | −0.052 |
| recall@10 (French) | **0.833** | 0.778 | +0.055 |
| MRR (French) | 0.466 | **0.562** | −0.096 |
| recall@10 (English) | 0.929 | 0.929 | 0.000 |
| MRR (English) | **0.679** | 0.673 | +0.006 |

**Catastrophic French misses: 1** (one query in a dense near-duplicate document
cluster where several closely-related docs compete; gbrain ranked the labeled
doc in top-10, hypermnesic did not).

## Reading

- **The two systems are at near-parity.** hypermnesic is slightly ahead on
  **recall** (overall and French) and tied on English; gbrain is slightly ahead
  on **ranking precision (MRR)**, most visibly on French (−0.096).
- The provisional `fail` is driven by aggregate MRR (−0.052, just beyond the
  near-tie band) plus the single French cluster-competition miss — **not** by a
  coverage/recall gap (recall parity, including French, is achieved).
- Likely cause of the MRR gap: gbrain uses **multi-query expansion** and tuned
  hybrid fusion; hypermnesic uses plain Reciprocal Rank Fusion. This is an
  addressable ranking-precision gap, not a fundamental retrieval limitation.
- No tuning was done to chase a PASS.

## UA doc-level lane — closes the aggregate MRR gap (validated)

Adding a **doc-level embedding lane** (one embedding per doc from a
title+headings+lead "surface" — a deterministic proxy for gbrain's
`compiled_truth`) was measured in isolation (same frozen baseline + LLM-judged
labels; only the doc lane added to the existing chunk index):

| | recall@10 | MRR | Δrecall vs gbrain | Δmrr vs gbrain |
|---|---|---|---|---|
| chunk-only | 0.871 | 0.704 | +0.052 | **−0.065** |
| **+ doc lane (UA)** | **0.910** | **0.802** | **+0.092** | **+0.033** |

The aggregate MRR deficit **flipped to a surplus** — hypermnesic now
meets-or-beats gbrain on **both** aggregate metrics (recall +0.092, MRR +0.033,
both outside the band). The representation diagnosis is confirmed.

**Residual (still FAIL under the strict literal bar):**
- **French MRR** still trails: hyp 0.712 vs gbrain 0.786 (−0.074) — English MRR
  carries the aggregate. French *recall* is far ahead (0.927 vs 0.797).
- **Catastrophic-French-miss count = 4.** Note the AE6 clause was designed for a
  *single* known-item French floor; under **pooled multi-relevant** labels it is
  conservative — it fires whenever gbrain's top-10 holds any relevant doc hyp's
  top-10 lacks, even though hyp's aggregate French recall is *higher*. This is a
  clause-calibration question for the operator, not (on the recall evidence) a
  catastrophic French gap.

**Next lever (UB):** weight the doc lane (esp. for French/ranking) to lift French
MRR and pull the gbrain-found French docs into hyp's top-10. Not grid-searched to
pass.

## Gate-of-record: LLM-judged labels (pooled, system-blind), chunk-only baseline

The labels were re-derived by an **LLM-as-judge** (`judge_labels.py`, via `codex
exec` / ChatGPT — no API key): for each query the candidates from BOTH systems
are pooled, stripped of rank/source, shuffled, and judged on content alone — so
labels stay independent of the ranking under test. 31/32 queries judged (median
3 relevant docs each).

| Metric | hypermnesic | gbrain (hybrid, un-reranked) | Δ |
|---|---|---|---|
| recall@10 (all) | **0.871** | 0.818 | +0.052 |
| MRR (all) | 0.704 | **0.769** | −0.065 |
| recall@10 (French) | **0.825** | 0.797 | +0.028 |
| MRR (French) | 0.677 | **0.786** | −0.109 |
| recall@10 (English) | **0.929** | 0.845 | +0.084 |

Verdict: **provisional `fail`** on the MRR band (hyp wins recall everywhere,
gbrain wins ranking precision, esp. French). (The catastrophic-French-miss count
rises under multi-relevant pooled labels — the AE6 single-French-floor clause is
conservative here since hyp's *aggregate* French recall is actually higher; not
tuned to change this.)

### The result is robust across three independent labelings

| Labels | Δrecall@10 | Δmrr | takeaway |
|---|---|---|---|
| agent, title-derived queries | (confounded by `gbrain search`) | — | superseded |
| agent, NL queries (vs gbrain hybrid) | **+0.031** | −0.052 | recall↑, mrr↓ |
| LLM-judged, NL queries (vs gbrain hybrid) | **+0.052** | −0.065 | recall↑, mrr↓ |

hypermnesic is **at-or-above parity on recall (incl. French) and consistently
~0.05–0.07 behind on MRR**. The MRR deficit is stable and real — not a labeling
artifact — which corroborates the index-side diagnosis below.

## Ranking-precision experiments (the MRR gap)

Two query-side levers were tried to close the small aggregate-MRR gap; both were
measured against the faithful baseline and **neither closed it** (no tuning to
chase a PASS):

| Variant | recall@10 | MRR | Note |
|---|---|---|---|
| baseline (dense + phrase-lexical) | **0.875** | 0.559 | the faithful result above |
| lexical OR-of-terms | 0.812 | 0.483 | **worse** — floods candidates with weak common-term matches; reverted |
| + multi-query expansion (×3) | 0.844 | 0.563 | **neutral** (+0.004 MRR, −0.031 recall); kept as an optional, off-by-default feature |

**Diagnosis — the residual MRR edge is index-side, not query-side.** gbrain
embeds a *compiled/summarized* per-page representation (its results carry
`chunk_source: compiled_truth`) and uses tuned hybrid fusion; hypermnesic embeds
raw markdown chunks. Query-side tricks (expansion, lexical widening) don't move a
representation gap. Closing it is a chunking/representation change (Phase-2
territory: a compiled-summary embedding lane and/or fusion-weight tuning), not a
quick query tweak — so it is **not** pursued now. Multi-query expansion is
retained as an opt-in capability (`--expand N`, default off; matches gbrain's
expansion and may help other corpora/query styles).

## Required before this can gate Phase 1 (operator)

1. **Human-review the labels** (KTD6) — agent-proposed known-item labels need
   operator confirmation, especially within dense near-duplicate clusters.
2. **Close the MRR gap** if the human-reviewed verdict still trails: add
   query-expansion and/or tune hybrid fusion weighting (hypermnesic's RRF is
   deliberately simple). The recall parity says the right docs are retrieved;
   the work is ranking them first.
3. Re-run; record the human-reviewed verdict as the actual gate.

Neither a provisional fail nor a no-decision abandons the build (KTD11) — at
near-parity it points at a focused fusion/ranking improvement, not a rebuild.
The Phase-1 gate is the human-reviewed U5 pass **and** the pre-U7 threat model
(`../docs/threat-model-commit-note.md`).
