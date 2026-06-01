# U5 Parity Verdict — PROVISIONAL (2026-06-01)

**Verdict: `fail` (provisional) — does NOT gate Phase 1.**

This verdict is **provisional** by construction: the relevance labels are
**agent-proposed known-item labels**, not human-judged (KTD6 requires human
review before this can gate Phase 1). The frozen query set, the gbrain baseline,
and the per-query results are **corpus-derived private data and are not
committed** — they are generated locally by the harness tools and gitignored.
This document records only the methodology and aggregate (non-identifying)
metrics.

## Setup

- **Query set** (`harness/queries.frozen.jsonl`, gitignored): 32 known-item
  queries (18 French, 14 English), built deterministically by
  `build_query_set.py`. Each query targets one real corpus doc; that doc (and
  its equivalence class — see below) is the label.
- **gbrain baseline** (gitignored): top-10 docs/query from the homelab
  `gbrain search` (`capture_gbrain_baseline.py`).
- **Rerank level (KTD5):** **un-reranked, verified.** `gbrain search` output is
  byte-identical with `search.reranker.enabled` true vs false — `search` does
  not apply the ZeroEntropy reranker (the `query`/RAG path does). So the baseline
  is at the un-reranked level **without** any lasting change to the shared
  service (the global setting was toggled and restored+verified; net-zero).
- **Equivalence-class scoring:** all metrics are computed in equivalence-class
  space (`corpus_equivalence.py`): a corpus mirrors the same document at multiple
  paths and stores meeting/source copies of one event, so a query's answer is a
  *class* and finding any member counts. This is applied symmetrically to both
  sides and removes duplicate-copy artifacts by construction.
- **Embed-quiescence:** the full corpus index was complete; no query degraded to
  lexical-only, so the run is scored, not voided.

## Result (aggregate, class-space)

| Metric | hypermnesic | gbrain (un-reranked) | Δ |
|---|---|---|---|
| recall@10 (all) | **0.906** | 0.781 | **+0.125** |
| MRR (all) | 0.459 | **0.521** | −0.063 |
| recall@10 (French) | **0.889** | 0.667 | **+0.222** |
| MRR (French) | **0.416** | 0.311 | **+0.105** |

**Catastrophic French misses: 0.**

## Reading

- On the gate's core question — **can the permissive index match gbrain's French
  recall?** — the answer is **yes, it exceeds it**: French recall@10 +0.222 and
  French MRR +0.105, with zero catastrophic French misses.
- hypermnesic also wins overall recall@10 (+0.125).
- The provisional `fail` is driven by **aggregate MRR** (−0.063, beyond the
  near-tie band): on **English title-derived known-item queries**, gbrain's exact
  lexical match tends to rank the target at position 1, while hypermnesic's
  hybrid (dense+lexical) fusion sometimes ranks a semantically-adjacent sibling
  first. This is partly a **methodology artifact** — known-item queries derived
  from document titles over-reward exact lexical matching; natural-language
  queries would favor the hybrid more.
- No tuning was done to chase a PASS; the MRR gap is reported as a real signal.

## Earlier iteration (recorded)

A first scoring pass used single-label known-item labels and raw-path metrics.
It produced 2 "catastrophic French misses" that were **duplicate-content
labeling artifacts**: the corpus mirrors documents at two path prefixes and
stores `meetings/` + `sources/` copies of one event, so the single labeled path
was crowded out by its own duplicates / found as a different copy. Two fixes
resolved this on principle (not by gaming): (1) **retrieval-time near-duplicate
collapse** in `retrieve.search` (also a genuine UX win — users don't want a
half-duplicate result list), and (2) **equivalence-class scoring** for both
sides. After both, catastrophic misses → 0.

## Required before this can gate Phase 1 (operator)

1. **Human-review the labels** (KTD6) and prefer **natural-language queries**
   over title-derived ones, so MRR is not biased toward exact lexical matching.
2. Re-run; record the human-reviewed verdict as the actual gate.

The Phase-1 gate is U5-passes (human-reviewed) **and** the pre-U7 threat model.
Neither a provisional fail nor a no-decision abandons the build (KTD11) — it
drives label/query refinement (and, if it held under real labels, an MRR/fusion
look).
