---
date: 2026-06-02
topic: longmemeval-benchmark-protocol
---

# LongMemEval Head-to-Head Benchmark Protocol

## Summary

A reproducible benchmark protocol and committed harness that reports Hypermnesic's
**LongMemEval V1** score head-to-head with the SOTA memory systems (Mem0, OMEGA, Zep,
etc.). Conversation sessions are ingested **raw and verbatim** as markdown, retrieved
with the shipped read path, answered by a pinned **GPT-4o reader**, and graded by the
mandated **GPT-4o judge** — published as a `PARITY_VERDICT`-style verdict doc plus a
pinned reproducibility manifest so the number can be independently re-run.

---

## Problem Frame

Hypermnesic has a strong internal benchmark culture — `harness/PARITY_VERDICT.md`
measures recall@10 / MRR against a frozen gbrain baseline with LLM-judged, system-blind
labels and a documented refusal to tune-to-pass. But that number is **private,
corpus-derived, and parity-vs-one-baseline**. It cannot be placed on the public memory
leaderboards (LongMemEval, LoCoMo, BEAM) that prospective users and peers actually use
to compare Mem0 / Zep / OMEGA / Letta, because (a) those boards score **end-to-end QA
accuracy**, not retrieval recall, and (b) Hypermnesic has no committed pipeline that
ingests a conversational dataset and answers its questions.

The cost of that gap: when someone asks "how does Hypermnesic compare to Mem0?", there
is no defensible, reproducible answer. And in a field where "benchmark skepticism is
high" — vendors routinely dispute each other's numbers over judge reliability,
retrieval-only-vs-end-to-end conflation, and un-auditable runs — a number that can't be
reproduced is worth little even when it's favorable.

**Comparability envelope** — the number this protocol produces is comparable to:

| Comparable to | NOT comparable to |
|---|---|
| LongMemEval **V1**, `_s` variant | LongMemEval **V2** (multimodal, LAFS metric) |
| **GPT-4o reader**, GPT-4o judge | rows using a different reader/judge |
| **Raw retrieval-augmented** ingestion (RAG-style) | distilled fact-extraction systems' best rows |

---

## Key Flows

- F1. **End-to-end QA run (headline)**
  - **Trigger:** operator runs the headline benchmark
  - **Actors:** ingestion adapter, read-path index, retriever, GPT-4o reader, GPT-4o judge
  - **Steps:** materialize the corpus from the pinned dataset → build the index → for each
    question, retrieve top-k context → reader answers within a fixed token budget → judge
    emits the autoeval correct/incorrect label → aggregate overall and per-ability
  - **Outcome:** a verdict-doc metrics table comparable to the cited SOTA rows
  - **Covered by:** R1, R4, R7, R8, R10, R11, R17

- F2. **Retrieval-only diagnostic run**
  - **Trigger:** operator runs the diagnostic track (cheap, no reader/judge)
  - **Actors:** ingestion adapter, index, retriever
  - **Steps:** same corpus/index → for each question, retrieve → score recall@k at the
    turn and session level against the dataset's gold evidence
  - **Outcome:** recall numbers that localize any end-to-end gap to retrieval vs reader
  - **Covered by:** R7, R9

- F3. **Critic re-run from manifest**
  - **Trigger:** a third party wants to reproduce the published number
  - **Actors:** external operator with an OpenAI key
  - **Steps:** clone the harness → read the manifest → fetch the pinned dataset by hash →
    run with the pinned models/params → compare against the published headline
  - **Outcome:** the headline is reproduced (or refuted) without help from the authors
  - **Covered by:** R13, R14, R16

---

## Requirements

**Benchmark target & comparability**
- R1. The protocol targets **LongMemEval V1** as the anchor; the published headline is
  **end-to-end QA accuracy on the `_s` variant** (~115k tokens, ~40 sessions), reported
  both aggregate and per the 5 V1 abilities (information extraction, multi-session
  reasoning, knowledge updates, temporal reasoning, abstention).
- R2. The verdict doc must state explicitly which published leaderboard rows the
  Hypermnesic number **is** comparable to and which it **is not** (per the comparability
  envelope above), so a reader cannot mistake it for a V2/LAFS or distilled-system number.
- R3. The `_m` variant (~500 sessions) is a defined **scale tier** the protocol supports
  running but is **not** part of the v1 headline; V2 is recorded as a future tier
  contingent on multimodal/trajectory ingestion Hypermnesic does not have today.

**Ingestion adapter (raw verbatim)**
- R4. Sessions are ingested **verbatim as markdown** into a throwaway repo and indexed
  with the shipped read path; **no LLM summarization or fact-extraction** step sits
  between the dataset and the index.
- R5. The session→markdown mapping must be **deterministic and committed**, so the
  materialized corpus is reproducible from the pinned dataset (same input → same files).
- R6. Temporal metadata the benchmark depends on (session dates and ordering, needed for
  temporal-reasoning and knowledge-update questions) must survive ingestion and be
  available to retrieval and the reader.

**Scoring tracks & metrics**
- R7. Two tracks are reported: (a) **end-to-end QA accuracy** (headline) and (b) a
  **retrieval-only diagnostic** track (recall@k at turn and session level, per
  LongMemEval's retrieval eval), so a QA gap is attributable to retrieval vs reader.
- R8. End-to-end answers are graded by the **LongMemEval autoeval procedure** (GPT-4o
  judge → correct/incorrect label); **abstention** questions are scored per the
  benchmark's abstention handling and reported as their own ability, never silently dropped.
- R9. Results are published as a single comparison table: aggregate accuracy, per-ability
  accuracy, and the retrieval-track recall numbers, alongside the cited SOTA systems.

**Models & pinning**
- R10. The **headline reader is GPT-4o** (dated snapshot pinned). GPT-4o-mini is supported
  as a cheap dev/CI reader and, if reported, lives in a **clearly-labeled separate column**.
- R11. The **judge is GPT-4o** (dated snapshot pinned), matching LongMemEval's mandated judge.
- R12. The embedding model stays Hypermnesic's **production** config (text-embedding-3-large
  @ 1536 dims); the benchmark must not introduce a benchmark-only embedding configuration.

**Reproducibility & published artifact**
- R13. The published deliverable is a **verdict document** analogous to
  `harness/PARITY_VERDICT.md` plus a **re-runnable harness** committed under `harness/`,
  recording methodology and aggregate/per-ability metrics.
- R14. A **reproducibility manifest** pins everything needed to reproduce the number:
  dataset version + content hash, embedding/reader/judge model snapshots, retrieval params
  (k, fusion weights, doc/chunk lanes), prompt templates, and a run seed.
- R15. Large generated artifacts (materialized corpus, per-question outputs, judge
  transcripts) are **gitignored** following the existing parity-harness data policy; only
  non-identifying aggregate/per-ability results and the manifest are committed.
- R16. A third party with an OpenAI key must be able to **reproduce the headline number
  from the committed harness + manifest alone** (the F3 critic re-run path).

**Run economics & CI**
- R17. The headline runs the **full** LongMemEval V1 `_s` question set — sampling is not
  headline-eligible because it breaks comparability — and the protocol records an
  **estimated per-run cost**.
- R18. A small, **pinned smoke subset** (a handful of questions spanning all 5 abilities)
  runs cheaply in CI for regression detection and is **always labeled non-headline**.

**Integrity / anti-gaming**
- R19. Retrieval/fusion params are **frozen before** the headline run; no per-corpus tuning
  to chase a score, and any param change is recorded in the verdict doc (carrying over the
  `PARITY_VERDICT` discipline).
- R20. **Embed-quiescence is verified before scoring** (no question degraded to
  lexical-only because embeddings lagged), mirroring the parity harness; degraded runs are
  **voided, not reported**.

---

## Acceptance Examples

- AE1. **Covers R8.** Given an abstention question whose answer is not derivable from the
  history, when the reader correctly abstains, the autoeval labels it correct and it counts
  in the **abstention** ability — not folded into another category or dropped.
- AE2. **Covers R20.** Given embeddings still lagging for some sessions at query time, when
  a run is executed, the run is **voided** (not scored), because the results would be
  lexical-only and non-comparable.
- AE3. **Covers R2, R10.** Given a GPT-4o-mini run, when results are published, they appear
  in a separate labeled column and are **not** compared against GPT-4o-reader SOTA rows.
- AE4. **Covers R18.** Given the CI smoke subset, when it runs, its output is labeled
  non-headline and is **never** substituted for the full-set number in the verdict doc.

---

## Success Criteria

- A reader can compare Hypermnesic's LongMemEval V1 `_s` number **directly** against the
  cited SOTA systems and trust it, because the methodology is pinned and the run reproduces.
- A third party with an OpenAI key reproduces the headline from the committed harness +
  manifest within run-cost, landing on the same aggregate within judge variance.
- The verdict doc makes the **comparability envelope explicit** — no reader mistakes the
  number for a V2/LAFS or distilled-system result.
- `ce-plan` can implement the harness **without inventing methodology**: ingestion method,
  tracks, metrics, models, pinning, and integrity rules are all specified here.

---

## Scope Boundaries

- **LongMemEval V2** (multimodal web-agent trajectories, LAFS metric) — future tier; needs
  multimodal ingestion Hypermnesic lacks.
- **BEAM** (1M–10M tokens) — future scale tier; cost-prohibitive on text-embedding-3-large
  for v1.
- **MemoryAgentBench** — needs the gated write / continual-learning path; deferred until
  the write path ships.
- **Letta Leaderboard** — a different end-to-end agent harness; out of v1.
- **LoCoMo** — the designated **next** benchmark after LongMemEval, not part of v1.
- **Distilled / write-kernel (`commit_note`) ingestion track** — deferred until the write
  path un-gates; would later be a second, clearly-flagged column, not a replacement for the
  raw headline.
- **Tuning Hypermnesic's retrieval to maximize the score** — explicitly rejected (R19).
- **Building and running the harness / paying for the run** — this document is the protocol
  *design*; implementation and execution are the `ce-plan` / `ce-work` handoff.

---

## Key Decisions

- **Head-to-head framing → match V1's published protocol exactly** (reader, judge, metric,
  variant) so the number is directly comparable, rather than inventing a Hypermnesic-native
  scoring scheme.
- **V1 over V2** — V2 is a different benchmark (multimodal, LAFS, near-empty board); the
  cited SOTA numbers (Mem0 93–94%, OMEGA 95.4%) are V1.
- **Raw verbatim ingestion** — least-confounded, ships today, isolates the memory layer
  from a distiller; aligns with the brief's finding that raw + good retrieval is competitive.
- **GPT-4o headline reader** — apples-to-apples with the 93–95% rows, accepting higher run
  cost; GPT-4o-mini retained for cheap iteration in a separate column.
- **Reproducibility-as-the-artifact** — commit the adapter + manifest + verdict doc; the
  re-runnable number is the credibility, not the score itself.
- **Retain a retrieval-only diagnostic track** — localizes any QA gap to retrieval vs
  reader, is cheap, and matches the existing harness culture.
- **No-tune-to-pass** — carried over verbatim from `harness/PARITY_VERDICT.md`.

---

## Dependencies / Assumptions

- OpenAI API access and **budget** for a full `_s` run with a GPT-4o reader + GPT-4o judge
  (real-dollar cost; estimate to be recorded per R17).
- The **LongMemEval V1 dataset** (`_s` / `_m` / `_oracle`) is publicly downloadable and
  content-hashable for pinning. *(Assumption — verify exact license/redistribution terms
  during planning; affects the R15 gitignore policy.)*
- text-embedding-3-large @ 1536 remains the production embedding config (R12).
- The **shipped read path** (`index` / `init` / `retrieve`) is sufficient for raw-verbatim
  ingestion; the **write path stays gated** and is not needed for v1.
- Per-haystack isolation (one throwaway repo/index per question's history) is feasible with
  the existing index. *(Verify during planning.)*

---

## Outstanding Questions

### Resolve Before Planning

- *(None — the product-level decisions are settled. The items below are technical or
  research questions better answered during planning.)*

### Deferred to Planning

- [Affects R4][Technical] Session→markdown granularity: one file per session vs per-turn,
  and how to encode roles + timestamps so temporal/knowledge-update questions stay answerable.
- [Affects R7][Technical] Mapping LongMemEval's gold "evidence sessions" to Hypermnesic's
  retrieval units for the recall@k diagnostic (turn vs session vs chunk granularity).
- [Affects R1, R8][Needs research] The exact LongMemEval V1 autoeval prompt and judge
  invocation, to match the published procedure faithfully.
- [Affects R17][User decision] Dollar budget ceiling for the full `_s` headline run, and
  whether to also fund the `_m` scale tier and/or the GPT-4o-mini column. *(Confirm before
  execution, not before planning.)*
- [Affects R14][Technical] Manifest format and where retrieval params/prompts are pinned so
  the F3 critic re-run is turnkey.
- [Affects R13][Technical] How the new harness scripts are organized under `harness/`
  alongside the existing parity harness.
- [Affects R5, R15][Needs research] LongMemEval dataset license/redistribution terms — may
  the materialized corpus be committed, or only referenced by hash?
