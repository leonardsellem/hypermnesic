# Plan — Close the retrieval MRR gap (representation parity with gbrain)

**Status: DONE — gate met.** UA (doc-level embedding lane) closed the gap: vs
gbrain, recall@10 +0.092 and MRR +0.033 (0.704→0.802) on LLM-judged labels; 0
catastrophic French misses; U5 verdict = PASS. UB (doc-lane up-weighting) was
measured and rejected (traded recall for MRR). UC (LLM summaries) not needed.
See `harness/PARITY_VERDICT.md`.

**Repo:** hypermnesic · **Gate this unblocks:** U5 parity
(strict R5: hyp ≥ gbrain on recall@10 **and** MRR). Phase 1 (U7) remains gated on
this **and** the threat-model sign-off.

## Problem

Across three independent labelings (agent-title, NL-agent, LLM-judged), the
result is stable: hypermnesic is **≥ gbrain on recall@10 (incl. French)** but
**~0.05–0.07 behind on MRR** (ranking the exact relevant doc #1, most visibly in
French). Query-side levers were measured and **do not** close it: lexical
OR-of-terms hurt (reverted); multi-query expansion was neutral.

**Root cause (diagnosis): representation, not query handling.** gbrain embeds a
*compiled/summarized* per-page representation (`chunk_source: compiled_truth`) +
tuned hybrid fusion; hypermnesic embeds raw markdown paragraph chunks. A
mid-paragraph chunk embedding aligns worse with an "about this document" NL query
than a whole-doc/summary embedding, so the right doc lands at rank 2–3 instead of
1 → lower MRR with unchanged recall.

## Approach — cheap-first, measured (don't over-build)

Each unit is gated by re-running the **existing LLM-judge parity harness**
(`judge_labels.py` → `parity_harness.py`, class-space). Keep what moves MRR
without hurting recall; stop as soon as the strict bar is met. No tuning to chase
a PASS — principled changes, measured both ways.

### UA — doc-level embedding lane (cheap, deterministic, no LLM)
- **Idea:** add ONE embedding per *document* alongside the per-chunk vectors,
  built from a doc-level "surface" (title + section headings + lead paragraph,
  bounded to the model's token limit). This is a deterministic proxy for gbrain's
  compiled summary; it captures what a doc is *about*, which is what NL queries
  ask.
- **Index:** new `vec_docs(doc_id, embedding float[1536])` + a `docs(path)` table;
  `build_index` computes + embeds the doc surface per file. ~3.5k extra embeds
  (cheap). Schema is additive; `vec_chunks`/FTS unchanged. SHA checkpoint covers it.
- **Retrieve:** add a doc-level dense channel; a doc-level hit contributes RRF
  mass to that doc. Fuse {lexical, chunk-dense, doc-dense}.
- **Test (TDD):** `vec_docs` declared `float[1536]`; one row per indexed doc;
  doc-surface excludes frontmatter; a doc whose *summary* (not any single chunk)
  matches a query ranks that doc into the top via the doc lane (fixture).
- **Gate:** re-run LLM-judge parity. Measure ΔMRR, Δrecall. Keep iff MRR improves
  and recall does not regress.

### UB — fusion weighting (only if UA insufficient)
- Weighted RRF over the three channels (e.g. emphasize doc-dense for ranking).
  Pick weights on principle (semantic "about" queries → doc lane), **not** by
  grid-searching the eval. Re-gate.

### UC — LLM-compiled summaries (escalation, only if UA+UB insufficient)
- Replace the deterministic doc surface with an **LLM-compiled summary** per doc,
  generated via **`codex exec` (ChatGPT Pro, no API key)** — matching gbrain's
  compiled_truth more closely. Heavy (~3.5k codex calls, batched/incremental;
  cache by content hash so it only runs on changed docs). Embed the summary as
  the doc lane. Re-gate.

## Gates (all must hold)

- [G-MRR] LLM-judge parity: hyp MRR ≥ gbrain (within the near-tie band) **and**
  recall@10 not regressed (still ≥ gbrain), French included.
- [G-TEST] `uv run pytest` green; new schema/retrieve covered TDD.
- [G-RUFF] `ruff check` clean.
- [G-READONLY] gbrain-brain never written (external state dir); eval data + any
  generated summaries stay gitignored; repo stays private + private-term-free.
- [G-COST] No OpenAI API key for any LLM *generation* (summaries via Codex);
  embeddings remain the pinned index model.

## Out of scope / constraints

- Still **no Phase 1 (U7+) write kernel** — this only clears the U5 gate.
- Reranking stays out of the core (KTD5) — this is first-stage representation, not
  a reranker.
- Index stays a disposable projection (rebuildable; SHA-checkpointed).

## Done when

G-MRR passes on the LLM-judged labels (recall maintained, MRR ≥ gbrain), all gates
green, verdict recorded in `harness/PARITY_VERDICT.md`. Then the U5 gate is met;
Phase 1 still awaits the threat-model sign-off.
