# Hypermnesic on LongMemEval V1 — Benchmark Verdict

**Status: Phase 1 scaffold (retrieval diagnostic harness landed; numbers pending the
F2 run). Phase 2 — end-to-end QA headline (GPT-4.1 + GPT-4o columns): pending.**

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

Embeddings-only; no reader/judge spend. Produced by the F2 run below over the full
`_s` set; the smoke subset ([`smoke.example.jsonl`](longmemeval/smoke.example.jsonl))
is **non-headline** and is never substituted here (AE4).

### Aggregate (full `_s`, 470 retrieval-scored instances; 30 `_abs` excluded)

| Granularity | recall_all@5 | recall_all@10 | ndcg_any@5 | ndcg_any@10 | recall_all@50 | ndcg_any@50 |
|---|---|---|---|---|---|---|
| Session | — | — | — | — | n/a | n/a |
| Turn | — | — | — | — | — | — |

*— (pending F2 run).*

### Per-ability (full `_s`)

| Ability (`question_type`) | n | session recall_all@10 | turn recall_all@10 | turn recall_all@50 | also reports |
|---|---|---|---|---|---|
| single-session-user | — | — | — | — | |
| single-session-assistant | — | — | — | — | |
| single-session-preference | — | — | — | — | |
| multi-session | — | — | — | — | |
| knowledge-update | — | — | — | — | `recall_any@k` + gold-set size (date-sensitive) |
| temporal-reasoning | — | — | — | — | `recall_any@k` + gold-set size (date-sensitive) |

*— (pending F2 run). The `turn_derived_session` block (session recall computed from
the turn ranking) is also reported, to localize reachability when the session ranking
misses.*

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

# 3. Phase 2 — end-to-end QA headline (gated; both reader columns; shared judge).
PYTHONPATH=harness uv run python harness/longmemeval/qa.py \
  --dataset harness/longmemeval/longmemeval_s_cleaned.json \
  --out harness/longmemeval/results/qa.json
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

- *(none yet — Phase 1 harness landed; diagnostic + headline runs pending.)*

---

## Sources & references

- Harness: [`harness/longmemeval/`](longmemeval/); manifest:
  [`manifest.json`](longmemeval/manifest.json); offline tests:
  `tests/test_longmemeval_harness.py`.
- LongMemEval: `github.com/xiaowu0162/LongMemEval`; dataset
  `xiaowu0162/longmemeval-cleaned` (HF, MIT); paper arXiv 2410.10813.
- Reader/judge comparability: the Zep and OMEGA LongMemEval reports (reader/judge/release
  attribution above to be re-verified against these at publication).
