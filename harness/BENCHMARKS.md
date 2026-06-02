# Hypermnesic on LongMemEval V1 — Benchmark Verdict

**Status: Phase 1 retrieval diagnostic — RUN (2026-06-02, full `_s`; numbers below).
Phase 2 — end-to-end QA headline (GPT-4.1 + GPT-4o columns): pending (gated).**

This document is the public-facing verdict for Hypermnesic on **LongMemEval V1**,
in the integrity style of [`PARITY_VERDICT.md`](PARITY_VERDICT.md): it records
methodology, the **comparability envelope**, and **aggregate / per-ability**
numbers only — never per-instance corpus data (R15) — and it carries a corrections
log and a no-tune-to-pass commitment. The re-runnable harness lives under
[`harness/longmemeval/`](longmemeval/); the pinned reproducibility manifest is
[`harness/longmemeval/manifest.json`](longmemeval/manifest.json).

The numbers themselves are produced by running the harness (below); the tables here
are seeded with the exact columns each run fills, marked **— (pending run)** until
the run is executed and its aggregate transcribed.

---

## What this number is, and is not (comparability envelope)

> **The single most important section.** A LongMemEval score is only meaningful
> next to the *reader model*, the *judge model*, and the *dataset release* that
> produced it. Cells that differ on any of these three axes are **not** directly
> comparable, and the field's headline numbers differ on all three.

| | Comparable to | **Not** comparable to |
|---|---|---|
| **Benchmark** | LongMemEval **V1**, `_s` variant (~115k tokens, ~40 sessions) | LongMemEval **V2** (multimodal, LAFS metric) |
| **Judge** | rows graded by **`gpt-4o-2024-08-06`** (the canonical judge) | rows graded by a **GPT-4.1 judge** (more lenient — see below) |
| **Dataset** | the **cleaned-2025-09** release | rows reported on the **original** release (flagged per row) |
| **Ingestion** | **raw verbatim** RAG-style ingestion | distilled / fact-extraction systems' best rows |

### Per-row attribution of the cited SOTA (R21)

Every cited leaderboard row is attributed by **reader · judge · dataset release**,
so no reader mistakes our GPT-4.1-reader / GPT-4o-judge cell for a GPT-4.1-*graded*
vendor row. (Exact figures and release per row are re-verified against primary
sources when the headline is published in U9; the values below are the planning
sources' figures and are marked accordingly.)

| Row | Reported | Reader | **Judge** | Dataset release | Directly comparable to… |
|---|---|---|---|---|---|
| **Hypermnesic — lead** | *(pending)* | GPT-4.1 (`gpt-4.1-2025-04-14`) | **`gpt-4o-2024-08-06`** | cleaned-2025-09 | *this is us* |
| **Hypermnesic — anchor** | *(pending)* | GPT-4o (`gpt-4o-2024-08-06`) | **`gpt-4o-2024-08-06`** | cleaned-2025-09 | *this is us* |
| OMEGA (headline) | ~95.4 | GPT-4.1 | **GPT-4.1 (lenient)** | original† | ❌ different judge — **not** our cell |
| OMEGA (GPT-4o-judge) | ~84.2 | GPT-4o | **`gpt-4o`** | original† | ✅ our **anchor** (mind the release) |
| Zep | ~71 | GPT-4o | **`gpt-4o`** | original† | ✅ our anchor (mind the release) |
| Full-context baseline | ~60 | GPT-4o | **`gpt-4o`** | — | ✅ our anchor |
| Mem0 | ~93–94 | GPT-4.1† | **GPT-4.1†** | original† | ❌ unless judge/release match |

† *to re-verify against the primary source at publication (U9).*

### The ~11-point reader-vs-judge swing — decomposed

Reader and judge choice **each** move the headline materially; conflating them is
the field's most common comparability error:

- **Reader axis (~11 pts).** The same system scores **~95.4 with a GPT-4.1 reader**
  vs **~84.2 with a GPT-4o reader** (OMEGA). That is why this harness publishes
  **both** reader columns — a GPT-4.1 column alone, set beside GPT-4o-graded SOTA
  rows, would be apples-to-oranges and forfeit the credibility the protocol prizes.
- **Judge axis.** The vendor 93–96% rows were graded with a **GPT-4.1 judge**, which
  is **more lenient** than `gpt-4o-2024-08-06`. Our judge is the canonical
  `gpt-4o-2024-08-06` (the official aggregator hard-asserts this snapshot, R11).

**Consequence (stated plainly):** our **GPT-4.1-reader / `gpt-4o-2024-08-06`-judge**
cell is **not** the GPT-4.1-*graded* 95.4 row, and is **expected to land below it on
judge strictness alone** — independent of memory quality. We do not claim to be "in
the 93–96% column." The **truly comparable anchors** are the GPT-4o-*judge* rows:
**full-context ≈60, Zep ≈71, OMEGA-on-GPT-4o ≈84.2**. A GPT-4.1-*judge* column is
deliberately **out of scope** — a non-`gpt-4o-2024-08-06` judge is rejected by the
official aggregator.

---

## Methodology

- **Ingestion (raw verbatim, R4).** Each instance's sessions are materialized to
  markdown **verbatim** — no summarization or fact-extraction between the dataset
  and the index. Two granularities: **per-session** (the QA corpus) and
  **per-user-turn rounds** (the turn diagnostic corpus). The session date is written
  **in the body** (`Session Date: …`) so it survives `ingest.strip_frontmatter` into
  the index (R6). The session→markdown mapping is **deterministic** — the same
  instance yields byte-identical files (R5).
- **Index + retrieval (shipped read path, R12).** One **isolated index per instance**
  (`build_index` with a `state_dir` outside the corpus → `retrieve.search` → discard),
  using the **production embedding config unchanged** (`text-embedding-3-large` @ 1536).
  No engine `src/` change — the harness consumes the read path as shipped.
- **Gold reconstruction.** Session-level gold = `answer_session_ids`; turn-level gold
  = the rounds carrying `has_answer: true`. The **30 `_abs` (abstention) instances are
  excluded from retrieval scoring**, matching the official `run_retrieval.py`.
- **Retrieval metrics (official).** `recall_all@k` (all gold in top-k → 1.0 else 0.0)
  and `ndcg_any@k` (binary relevance, ideal-DCG normalized). Session level @5/@10; turn
  level adds @50. These are **distinct** from the parity harness's fractional
  `recall_at_k`.
- **Frozen params, no tune-to-pass (R19).** `k`, fusion weights `(lexical, dense, doc)`,
  lanes, and near-dup collapse are frozen at the manifest values **before** any run;
  the diagnostic retrieves a deep candidate list purely to *measure* recall at multiple
  cutoffs — that measurement depth is not a tuned fusion parameter. Any param change is
  recorded in the corrections log.
- **Embed-quiescence void (R20/AE2).** `smoke_embed_or_die` runs before scoring; if any
  query degraded to lexical-only (embedding unavailable), the **whole run is voided**,
  never scored — a degraded run is non-comparable, not a FAIL.
- **No date-aware ranking — `recall_any` beside `recall_all` for date-sensitive abilities.**
  Hypermnesic's `search()` applies **no recency/date weighting**. For **knowledge-update**
  and **temporal-reasoning**, which need the newest session surfaced, the diagnostic also
  reports `recall_any@k` and the **gold-set-size distribution**, so a low `recall_all`
  there localizes to **retrieval ordering** (a known, addressable ranking gap), not to a
  memory or reader failure. This keeps the "diagnostic localizes the gap" claim honest.

---

## Phase 1 — retrieval diagnostic (session + turn level)

Embeddings-only; no reader/judge spend. **Run 2026-06-02** over the **full `_s` set**
(headline-eligible, no sampling, R17); embed-quiescent (not voided); production embed
config (`text-embedding-3-large` @ 1536); frozen retrieval params (`k`=10, fusion
weights `(1,1,1)`, doc lane on, near-dup collapse on) measured to a depth of 200 so
@50 is reportable. The smoke subset
([`smoke.example.jsonl`](longmemeval/smoke.example.jsonl)) is **non-headline** and is
never substituted here (AE4).

### Aggregate (full `_s`, 470 retrieval-scored instances; 30 `_abs` excluded)

| Granularity | recall_all@5 | recall_all@10 | ndcg_any@5 | ndcg_any@10 | recall_all@50 | ndcg_any@50 |
|---|---|---|---|---|---|---|
| Session | 0.821 | **0.949** | 0.809 | 0.840 | n/a | n/a |
| Turn | 0.313 | 0.515 | 0.351 | 0.424 | **0.915** | 0.510 |
| Turn → session (derived) | 0.634 | 0.855 | — | — | n/a | n/a |

**Reading.** Session-level retrieval is strong — for **94.9%** of instances *every* gold
session is in the top-10 (`recall_all@10`). Turn-level is the harder, finer granularity
(getting *all* gold rounds in the top-10 is 51.5%, but by @50 it reaches 91.5%) — the
evidence is reachable; ranking all of a multi-round gold set into a shallow cutoff is
what's hard. The `turn → session` row maps the per-turn ranking back to sessions
(`turn_to_session`): 0.855 @10, slightly below the direct session ranking, i.e. the
finer corpus is a bit noisier for session recovery.

### Per-ability (full `_s`)

| Ability (`question_type`) | n | session recall_all@10 | turn recall_all@10 | turn recall_all@50 | session ndcg_any@10 |
|---|---|---|---|---|---|
| single-session-assistant | 56 | 1.000 | 0.911 | 1.000 | 0.915 |
| single-session-user | 64 | 0.969 | 0.625 | 0.984 | 0.725 |
| single-session-preference | 30 | 0.967 | 0.567 | 0.867 | 0.732 |
| knowledge-update | 72 | 0.958 | 0.431 | 0.861 | 0.836 |
| multi-session | 121 | 0.950 | 0.430 | 0.917 | 0.904 |
| temporal-reasoning | 127 | 0.906 | 0.402 | 0.882 | 0.832 |

### Date-sensitive abilities — `recall_any` beside `recall_all` (the honest localization)

The engine does **no date-aware ranking**, so for knowledge-update ("latest wins") and
temporal-reasoning ("which came first"), strict `recall_all` can understate memory
quality when the gold set spans several sessions. Reporting `recall_any` (≥1 gold
retrieved) beside the gold-set-size distribution localizes the gap:

| Ability | session recall_all@10 | session **recall_any@10** | turn recall_any@10 | gold-set size (min/mean/max) |
|---|---|---|---|---|
| knowledge-update | 0.958 | **1.000** | 0.722 | 2 / 2.0 / 2 |
| temporal-reasoning | 0.906 | **1.000** | 0.701 | 1 / 2.2 / 6 |

**`recall_any@10` is 1.000 at the session level for both** — at least one gold session is
*always* in the top-10. So the sub-unity `recall_all` (0.958, 0.906) is **not** a memory
miss: it is the multi-gold ordering gap (temporal sets run up to 6 sessions) that a
date-aware ranker would close. The diagnostic localizes the gap to retrieval *ordering*,
not retrieval *coverage* or the reader — which is exactly the claim Phase 2 will lean on.

---

## Phase 2 — end-to-end QA headline (GPT-4.1 + GPT-4o columns)

**Pending.** The reader (U7), judge (U8), and QA runner (U9) land with offline tests
in this harness; the **paid full 500-Q `_s` run is a deliberate, gated step** — it is
triggered only after the Phase 1 diagnostic is reviewed and a budget (covering **both**
reader passes under the shared `gpt-4o-2024-08-06` judge) is signed off. The headline
metric is **task-averaged accuracy** (macro over the 6 `question_type` buckets,
abstention excluded), reported beside **Overall** (micro) and **Abstention** (30),
**per reader column** — matching the official `print_qa_metrics.py`.

| Reader column | Judge | Overall (micro) | Task-averaged (macro, headline) | Abstention (30) |
|---|---|---|---|---|
| GPT-4.1 (`gpt-4.1-2025-04-14`) — lead | `gpt-4o-2024-08-06` | — | — | — |
| GPT-4o (`gpt-4o-2024-08-06`) — anchor | `gpt-4o-2024-08-06` | — | — | — |

*— (pending the gated Phase 2 run).*

---

## Reproducing this (the F2 / F3 paths)

Everything needed is pinned in [`manifest.json`](longmemeval/manifest.json) (dataset
URL + content hash + release, embedding/reader/judge snapshots, frozen retrieval
params, prompt-template version, seed). A third party with an OpenAI key reproduces
the number from the committed harness + manifest alone (R16, flow F3):

```bash
# 1. Fetch the pinned dataset by hash (fails loud on mismatch; nothing written on a
#    divergent download). Pin DATASET_SHA256 in manifest.py on first acquisition.
uv run python -c "from longmemeval import manifest as m; \
  m.download_dataset('harness/longmemeval/longmemeval_s_cleaned.json', \
  expected_sha256=m.DATASET_SHA256)"

# 2. Phase 1 — retrieval diagnostic (F2; embeddings-only; content-hash cached).
PYTHONPATH=harness uv run python harness/longmemeval/diagnostic.py \
  --dataset harness/longmemeval/longmemeval_s_cleaned.json \
  --out harness/longmemeval/results/diagnostic.json

# 3. Phase 2 — end-to-end QA headline (GATED; both reader columns; shared judge).
#    --confirm-paid-run is required; without it the runner prints the gate + cost
#    estimate and refuses to spend (R17, this unit's Execution note).
PYTHONPATH=harness uv run python harness/longmemeval/qa.py \
  --dataset harness/longmemeval/longmemeval_s_cleaned.json \
  --out harness/longmemeval/results/qa.json \
  --confirm-paid-run
```

CI runs **only** the offline smoke (`tests/test_longmemeval_harness.py`), never a paid
run. The downloaded dataset, materialized corpus, per-question outputs, and the embed
cache are **gitignored**; only the manifest, the synthetic smoke subset, and the
aggregate/per-ability numbers in this doc are committed (R15).

### Estimated cost

- **Phase 1 (embeddings-only):** ceiling **≈ $15** (≈115M tokens across both corpora at
  `text-embedding-3-large` list price; see `cost_assumptions` in the manifest). The
  content-hash embedding cache makes re-runs and the F3 critic re-run far cheaper.
- **Phase 2 (reader + judge):** recorded at run time per column; the dollar budget is a
  user decision before the gated run.

---

## Contamination disclosure

The LongMemEval dataset is **public on Hugging Face** (`xiaowu0162/longmemeval-cleaned`,
MIT). A model's pre-training may have seen it, which can inflate end-to-end QA. We pin
the **cleaned-2025-09** release by content hash and disclose this so the number is read
with the appropriate caveat; the **retrieval diagnostic** (Phase 1) is unaffected by
reader pre-training, which is part of why it is the higher-confidence signal.

---

## Corrections log

The integrity discipline of `PARITY_VERDICT.md`: every methodology correction or param
change is recorded here, in the open.

- **2026-06-02 — dataset pinned.** Acquired the `longmemeval-cleaned` (2025-09) `_s`
  release and pinned its SHA-256 (`d6f21ea9…c3a442`, 500 instances, 277,383,467 bytes)
  in `manifest.py`/`manifest.json`. A re-download is now verified strictly against this
  hash. Schema confirmed against the harness: 6 `question_type` buckets
  (single-session-user 70, single-session-assistant 56, single-session-preference 30,
  multi-session 133, knowledge-update 78, temporal-reasoning 133) + 30 abstention. The
  Phase-1 pipeline (materialize → index → retrieve → score) was verified to run
  end-to-end on real instances offline (FakeEmbedder); the diagnostic + headline runs
  themselves remain pending an API key + budget.
- **2026-06-02 — Phase 1 retrieval diagnostic run (full `_s`).** Ran F2 over all 500
  instances (470 retrieval-scored, 30 `_abs` excluded) with the production embedder;
  embed-quiescent (`verdict: reported`, not voided). Per-ability counts are
  non-abstention, so they sum to 470 (the 30 abstention instances fall across the
  buckets). The run was killed by unrelated concurrent box activity at 448/500 and
  resumed for free from the content-hash embedding cache (no re-embed of the done
  instances) — no tuning, no param change between the two segments. Numbers committed
  are aggregate/per-ability only (R15); per-instance outputs + the embed cache stay
  gitignored.

---

## Sources & references

- Harness: [`harness/longmemeval/`](longmemeval/); manifest:
  [`manifest.json`](longmemeval/manifest.json); offline tests:
  `tests/test_longmemeval_harness.py`.
- LongMemEval: `github.com/xiaowu0162/LongMemEval`; dataset
  `xiaowu0162/longmemeval-cleaned` (HF, MIT); paper arXiv 2410.10813.
- Reader/judge comparability: the Zep and OMEGA LongMemEval reports (reader/judge/release
  attribution above to be re-verified against these at publication).
