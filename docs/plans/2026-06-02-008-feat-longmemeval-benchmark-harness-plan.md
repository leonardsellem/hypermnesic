---
title: "feat: LongMemEval V1 head-to-head benchmark harness"
type: feat
status: completed
date: 2026-06-02
origin: docs/brainstorms/2026-06-02-longmemeval-benchmark-protocol-requirements.md
deepened: 2026-06-02
---

# feat: LongMemEval V1 head-to-head benchmark harness

## Summary

Build a reproducible LongMemEval V1 benchmark harness under `harness/longmemeval/` that ingests
conversation sessions verbatim as markdown, indexes them with the shipped read path, and reports
Hypermnesic head-to-head with the SOTA memory systems. Delivered in two phases: **Phase 1** is the
cheap, embeddings-only diagnostic (session- and turn-level retrieval recall) plus the full
materializer, manifest, gitignore policy, and offline CI smoke test; **Phase 2** is the
budget-gated end-to-end QA headline run — **both** a GPT-4.1 and a GPT-4o reader column under the
canonical `gpt-4o-2024-08-06` judge, so the published number carries an apples-to-apples anchor —
finalizing a `PARITY_VERDICT`-style verdict doc with per-row reader/judge/dataset-version attribution.

---

## Problem Frame

There is no defensible, reproducible answer to "how does Hypermnesic compare to Mem0 / Zep / OMEGA on
LongMemEval?" — the existing `harness/PARITY_VERDICT.md` is a private parity-vs-gbrain retrieval
number, not an end-to-end QA number on a public board. The brainstorm (see origin) resolved the
product shape; this plan resolves the implementation, and adds a sequencing decision: spend the cheap
retrieval diagnostic *first* to learn where Hypermnesic breaks on conversational memory before paying
for the headline QA run. Full motivation and the comparability rationale live in the origin doc.

---

## Requirements

Carried from origin (`docs/brainstorms/2026-06-02-longmemeval-benchmark-protocol-requirements.md`):

- R1. LongMemEval V1 `_s` headline (end-to-end QA), reported aggregate + per-ability.
- R2. Verdict doc states the comparability envelope explicitly.
- R3. `_m` is a defined scale tier, not v1 headline; V2 is a future tier.
- R4. Raw verbatim session→markdown ingestion; no summarization/fact-extraction.
- R5. Deterministic, committed session→markdown mapping (byte-reproducible corpus).
- R6. Temporal metadata (session dates/order) survives ingestion.
- R7. Two tracks: end-to-end QA + retrieval-only diagnostic.
- R8. LongMemEval autoeval grading; abstention scored as its own ability, never dropped.
- R9. Single comparison table: aggregate + per-ability + retrieval recall vs SOTA rows.
- R10. **[Overridden — see Key Technical Decisions]** Headline reader was GPT-4o in origin; this plan
  runs **both a GPT-4.1 and a GPT-4o reader column** (GPT-4.1 lead, GPT-4o the apples-to-apples anchor),
  published together. `gpt-4.1-mini` is the cheap dev/CI reader.
- R21. **[Plan-local]** The verdict doc must attribute **reader model, judge model, and dataset release
  (original vs cleaned-2025-09)** for every cited SOTA row, and decompose the ~11-pt reader-vs-judge swing,
  so no reader mistakes the GPT-4.1-reader / GPT-4o-judge cell for the GPT-4.1-graded 95.4 row.
- R11. Judge is GPT-4o (`gpt-4o-2024-08-06`), the canonical LongMemEval judge.
- R12. Embedding stays the production config (text-embedding-3-large @ 1536); no benchmark-only embed.
- R13. Published deliverable = verdict doc (à la `harness/PARITY_VERDICT.md`) + re-runnable harness.
- R14. Reproducibility manifest pins dataset hash, model snapshots, retrieval params, prompts, seed.
- R15. Large generated artifacts gitignored; only aggregate/per-ability results + manifest committed.
- R16. A third party with an OpenAI key can reproduce the number from harness + manifest alone.
- R17. Headline runs the full `_s` set (no sampling); record an estimated per-run cost.
- R18. Pinned CI smoke subset (spans 5 abilities), always labeled non-headline.
- R19. Retrieval/fusion params frozen before the headline run; no tune-to-pass; changes recorded.
- R20. Embed-quiescence verified before scoring; degraded runs voided, not reported.

**Origin flows:** F1 (end-to-end QA run), F2 (retrieval-only diagnostic run), F3 (critic re-run from manifest).
**Origin acceptance examples:** AE1 (abstention scored as own ability), AE2 (degraded run voided), AE3 (non-headline reader — e.g. gpt-4.1-mini, or the deferred GPT-4o column — in a separate labeled column), AE4 (smoke subset labeled non-headline).

---

## Scope Boundaries

- LongMemEval V2 (multimodal, LAFS metric) — future tier (origin R3).
- BEAM, MemoryAgentBench, Letta board — future tiers; LoCoMo is the designated next benchmark.
- Distilled / write-kernel (`commit_note`) ingestion track — deferred until the write path un-gates.
- Tuning Hypermnesic's retrieval to chase a score (origin R19).
- Any change to the engine read path (`src/hypermnesic/`) — the harness consumes it as shipped.

### Deferred to Follow-Up Work

- **Phase 2 GPT-4.1 headline execution**: gated on the Phase 1 diagnostic result + an explicit
  per-run budget sign-off. The *code* for Phase 2 lands in this plan (U7–U9); the *paid 500-Q run*
  is deliberately not triggered as part of landing the plan.
- **`_m` scale-tier run** (retrieval-only): same harness, larger haystacks; run after `_s`.
- **GPT-4.1-*judge* column** (the cell directly comparable to GPT-4.1-graded vendor rows like 95.4):
  out of scope — a non-`gpt-4o-2024-08-06` judge is rejected by the official aggregator (R11). (The GPT-4o
  *reader* column is **in scope** now — Phase 2 publishes both reader columns.)

---

## Context & Research

### Relevant Code and Patterns

- `harness/parity_harness.py` — the metrics + four-state verdict template. Reuse `doc_ranking(hits, k)`,
  `recall_at_k`, `reciprocal_rank`, `rank_to_classes`, the `_verdict` ladder (`pass`/`fail`/`no_decision`/`void`,
  `DEFAULT_BAND=0.02`), and the `smoke_embed_or_die()` gate. Result-dict + `--json` conventions.
- `harness/portability_probe.py` — the per-haystack **build + retrieve** pattern (`probe_repo`):
  materialize a throwaway repo → `index.build_index(repo, embedder)` → `retrieve.search(...)` → check
  `res.degraded`. This is the closest analog to one LongMemEval haystack.
- `harness/judge_labels.py` — pluggable judge backends (`OpenAIJudge` lazy-keyed client; `CodexJudge`
  no-API-key lane) and deterministic source-blind shuffling. Reuse the **backend shape** for the reader
  and judge; do **not** reuse its retrieval-relevance prompt for QA grading.
- `src/hypermnesic/index.py` — `build_index(repo, embedder, *, rebuild=True, state_dir=None)`;
  `state_dir=` keeps index state outside the corpus. `Index.stats()`, `chunks_for_path`, `all_paths`.
- `src/hypermnesic/retrieve.py` — `search(idx, query, embedder=None, *, k=10, ...) -> SearchResult`;
  `Hit(chunk_id, path, heading, text, score, channels, recency)`; `SearchResult.degraded`;
  `collapse_duplicates=True` near-dup collapse (keep symmetric with scoring).
- `src/hypermnesic/embed.py` / `config.py` — `OpenAIEmbedder` (dimensions=1536 enforced),
  `smoke_embed_or_die`, `config.EMBED_MODEL`/`EMBED_DIM`, `config.get_api_key()` (env/`.env`, never logged).
- `src/hypermnesic/expand.py` — `OpenAIExpander` (`chat.completions.create`, lazy keyed client) — the
  exact shape to copy for `Reader` and `Judge`.
- `tests/conftest.py` — `FakeEmbedder` (deterministic), `make_corpus(files, git=True)`; `harness/` is on
  `sys.path` so harness modules import by stem. `tests/test_parity_harness.py`, `test_portability_probe.py`,
  `test_judge_labels.py` show offline mocking (build a real index over a fake embedder; inject fake judge).
- `.github/workflows/ci.yml` — single `lint-test-license` job (`ruff` → `pytest` → `license_scan.py`).
- `.gitignore` — existing corpus-derived data policy (`harness/*.frozen.jsonl`, `harness/results/`,
  `*.db`, `.hypermnesic/`); extend it for the new harness.

### Institutional Learnings

- `harness/PARITY_VERDICT.md` — the verdict-doc template and integrity discipline: record corrections,
  methodology, aggregate/non-identifying metrics only; embed-quiescence void; no tune-to-pass. Mirror it.
- `docs/solutions/design-patterns/surgical-scalar-set-frontmatter-byte-preservation.md` — only tangential
  (write-path frontmatter), but its "don't reflow bytes you didn't touch" mindset applies to making the
  materialized corpus deterministic (R5).

### External References

LongMemEval V1 official source (`github.com/xiaowu0162/LongMemEval`), confirmed against the actual
eval scripts:

- **Dataset**: HF `xiaowu0162/longmemeval-cleaned` (2025-09 cleaned release), **MIT licensed**, 500
  instances per split. Direct `resolve/main/longmemeval_s_cleaned.json` URL. `_s` ≈115k tokens / ~40
  sessions; `_oracle` carries `question`/`answer`/`question_type` for all IDs (the QA reference file).
- **Instance schema**: `question_id` (trailing `_abs` ⇒ abstention), `question_type` (6 values),
  `question`, `answer`, `question_date`, `haystack_session_ids`, `haystack_dates`, `haystack_sessions`
  (list of sessions, each a list of `{role, content}` turns; evidence turns carry `has_answer: true`),
  `answer_session_ids` (session-level gold).
- **Gold encoding**: session id contains substring `answer` ⇒ evidence session; turn-level gold =
  `has_answer:true` user turns. Retrieval eval **excludes** the 30 `_abs` instances.
- **QA autoeval** (`evaluate_qa.py`): judge `gpt-4o-2024-08-06`, `temperature=0`, `max_tokens=10`,
  label = `'yes' in response.lower()`; **5 per-`question_type` prompt templates** (default,
  temporal off-by-one tolerance, knowledge-update "latest wins", preference rubric, abstention).
  `print_qa_metrics.py` **hard-asserts** the judge string `gpt-4o-2024-08-06` and reports Overall
  (micro), **Task-averaged** (macro over 6 buckets, abstention excluded), Abstention (30 instances).
- **Retrieval eval**: headline `recall_all@k` (all gold in top-k) + `ndcg_any@k`; session level @5/@10,
  turn level adds @50; turn→session derivation by stripping the turn suffix.
- **Reader conventions** (`run_generation.py`): `con` (chain-of-note) reading method, `history_format=json`,
  chunks re-sorted ascending by date, `has_answer` stripped, `Current Date = question_date`, token budget
  = `model_max_length − gen_length − 1000`, tiktoken `o200k_base` for GPT-4o/4.1. GPT-4.1 = 1M context
  ⇒ `_s` fits untruncated. Reader/judge choice moves the headline ~11 pts (OMEGA 95.4 GPT-4.1 vs 84.2 GPT-4o).

---

## Key Technical Decisions

- **Phased: diagnostic-first, headline gated.** Phase 1 (U1–U6) is embeddings-only and runnable now;
  Phase 2 (U7–U9) lands the code but the paid 500-Q GPT-4.1 run is gated on the diagnostic + budget.
  Rationale: the cheap diagnostic is the highest-value-per-dollar signal and should drive feature work.
- **Dual reader columns (GPT-4.1 lead + GPT-4o anchor), published together.** Overrides origin R10's
  single GPT-4o reader: GPT-4.1 (`gpt-4.1-2025-04-14`, 1M context → `_s` untruncated) is the lead column,
  and GPT-4o (`gpt-4o-2024-08-06` reader) runs in the **same** Phase 2 pass as the apples-to-apples anchor
  (marginal cost = one extra reader pass; retrieval + judge are shared). Rationale: reader choice alone is
  worth ~11 pts (OMEGA 95.4 on GPT-4.1 vs 84.2 on GPT-4o), so publishing GPT-4.1 *alone* next to
  GPT-4o-graded SOTA rows would be apples-to-oranges and forfeit the credibility the brainstorm prized.
- **Judge stays `gpt-4o-2024-08-06` (both columns).** The official aggregator hard-asserts this snapshot.
  Critically, the vendor 93–96% rows (e.g. OMEGA 95.4) were graded with a **GPT-4.1 judge**, more lenient
  than `gpt-4o-2024-08-06` — so our GPT-4.1-reader / GPT-4o-judge cell is **not** the 95.4 row and is
  expected to land below it on judge strictness alone. The verdict says so (R21) and does not claim "in the
  93–96% column" without the caveat. A GPT-4.1-judge column is out of scope (non-official); the
  GPT-4o-judge rows (full-context ≈60, Zep ≈71, OMEGA-on-GPT-4o ≈84.2) are the truly comparable anchors.
- **Dataset version is a comparability axis.** We pin `longmemeval-cleaned` (2025-09); several cited SOTA
  rows were reported on the **original** release. The verdict envelope carries a cleaned-vs-original column
  and flags any cited row whose release differs (R21).
- **No date-aware retrieval ranking → report `recall_any` beside `recall_all` for date-sensitive abilities.**
  Hypermnesic's `search()` does no recency/date weighting, but knowledge-update ("latest-fact-wins") and
  temporal-reasoning need the newest session surfaced. Under strict `recall_all@k` those abilities can
  score ~0 for ranking/metric reasons, not memory reasons — so U4 also reports `recall_any@k` + the
  gold-set-size distribution for them, and the verdict states the gap localizes to retrieval ordering, not
  the reader. This keeps the "diagnostic localizes the gap" claim honest.
- **Per-haystack isolation.** One index per instance: build over that instance's sessions with
  `state_dir` outside the corpus, retrieve, discard. Mirrors `portability_probe`. (Embeddings dominate
  diagnostic cost — cache by content hash to make re-runs cheap; see Open Questions.)
- **Two materialization granularities.** Per-session markdown for the QA corpus (preserves conversational
  context); per-user-turn markdown for the turn-level diagnostic corpus. Both embeddings-only.
- **Gold reconstruction** from `answer_session_ids` (session) + `has_answer:true` user turns (turn),
  excluding `_abs` for retrieval — matching `run_retrieval.py`. Keep scoring dedup symmetric with
  `retrieve.search(collapse_duplicates=True)`.
- **Headline metric = task-averaged (macro, 6 buckets)**; also report Overall (micro) + Abstention
  (30) separately — matching `print_qa_metrics.py`.
- **Reading method `con`, `history_format=json`**, date-ascending context, `has_answer` stripped,
  `Current Date=question_date`, token budget `model_max − gen − 1000`, tiktoken `o200k_base` — official
  defaults for comparability.
- **Dataset referenced by content hash + downloader, not committed.** MIT permits committing, but size
  (~3 GB across splits) + contamination argue against it; commit the deterministic mapping + manifest (R15).
- **Reuse the four-state verdict + `smoke_embed_or_die` void gate** for both tracks (R20).

---

## Open Questions

### Resolved During Planning

- Exact autoeval prompts + judge invocation (R8/R11): the 5 per-`question_type` templates and
  `gpt-4o-2024-08-06`/temp 0/max_tokens 10/`'yes' in` rule — from official `evaluate_qa.py`.
- Gold-evidence → retrieval-unit mapping (R7): `answer_session_ids` + `has_answer` per the `answer`
  substring convention; `_abs` excluded.
- Dataset license/redistribution (R5/R15): MIT — reference by hash + downloader, don't commit corpus.
- Session→markdown granularity (R4/R6): per-session for QA, per-user-turn for the turn diagnostic;
  session date in the body (frontmatter is stripped from the indexed body by `ingest.strip_frontmatter`).
- Harness organization (origin deferred): a `harness/longmemeval/` subpackage (importable by stem since
  `harness/` is on `sys.path`).

### Deferred to Implementation

- Confirm GPT-4.1 uses `o200k_base` and the exact `model_max_length`/snapshot pricing at run time (U7).
- The dollar budget ceiling for the Phase 2 `_s` headline (now covering **both** reader columns) and
  whether to also fund `_m` — **user decision before Phase 2 execution**, not before landing the plan.
  (Phase-1 embedding cost is no longer open: U1 records a ceiling, U3 ships the cache.)

---

## Output Structure

    harness/longmemeval/
      __init__.py
      manifest.py          # U1: pins (dataset hash, models, params, prompts, seed) + downloader
      materialize.py       # U2: instance -> per-session and per-turn markdown; gold reconstruction
      adapter.py           # U3: per-haystack build_index + retrieve; embed-quiescence void gate
      diagnostic.py        # U4: session/turn recall_all@k + ndcg_any@k scorer (+ per-ability)
      reader.py            # U7: reader — GPT-4.1 + GPT-4o columns (con method, token budget, tiktoken) [Phase 2]
      judge.py             # U8: LongMemEval autoeval judge (gpt-4o-2024-08-06, per-type prompts) [Phase 2]
      qa.py                # U9: end-to-end QA runner + task-averaged scorer [Phase 2]
      smoke.example.jsonl  # U5: synthetic non-headline subset spanning the 5 abilities (committed)
    harness/BENCHMARKS.md  # U6/U9: verdict doc (diagnostic first, headline appended) [committed]
    tests/test_longmemeval_harness.py   # U5: offline tests + CI smoke

(Generated, gitignored: `harness/longmemeval/corpus/`, `harness/longmemeval/results/`,
`harness/longmemeval/*.frozen.jsonl`, downloaded dataset JSON.)

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation
> specification. The implementing agent should treat it as context, not code to reproduce.*

```mermaid
flowchart TD
  DS[LongMemEval _s JSON\npinned by hash] --> MAT[materialize.py]
  MAT -->|per-session md| CS[(per-haystack corpus)]
  MAT -->|per-turn md| CT[(per-turn corpus)]
  MAT -->|gold: answer_session_ids + has_answer| GOLD[gold sets]
  CS --> IDX[adapter.py: build_index + retrieve\nstate_dir outside corpus]
  CT --> IDX
  IDX -->|res.degraded?| VOID{embed-quiescent?}
  VOID -- no --> V[VOID run]
  VOID -- yes --> RANK[ranked hits]
  RANK --> DIAG[diagnostic.py\nrecall_all@5,10 / ndcg_any / turn@50]
  GOLD --> DIAG
  DIAG --> VD[BENCHMARKS.md\nPhase 1 diagnostic]
  RANK -. Phase 2 gated .-> RD[reader.py: GPT-4.1 + GPT-4o columns\ncon, token budget]
  RD --> JG[judge.py gpt-4o-2024-08-06\nshared judge, per-type prompts]
  JG --> QA[qa.py: task-avg + overall + abstention\nper reader column]
  QA --> VD
```

---

## Implementation Units

### U1. Dataset acquisition + reproducibility manifest

**Goal:** Pin and fetch the LongMemEval `_s` dataset deterministically, and establish the manifest that
makes the F3 critic re-run turnkey.

**Requirements:** R5, R14, R15, R16; F3

**Dependencies:** None

**Files:**
- Create: `harness/longmemeval/__init__.py`, `harness/longmemeval/manifest.py`
- Modify: `.gitignore` (ignore downloaded dataset + `harness/longmemeval/corpus/` + `results/` + `*.frozen.jsonl`)
- Test: `tests/test_longmemeval_harness.py`

**Approach:**
- Downloader uses stdlib `urllib` + `hashlib` (no new dependency) against the HF `resolve/main`
  `longmemeval_s_cleaned.json` URL; verify SHA-256 against a pinned constant; fail loud on mismatch.
- Manifest is a serializable structure pinning: dataset URL + content hash + release tag, embedding
  model/dim (from `config`), reader snapshot, judge snapshot, retrieval params (k, fusion weights, lanes),
  prompt-template version, and a run seed. Manifest is committed; the dataset JSON is not.
- The OpenAI key must never enter the manifest or any committed output (U2 credential discipline).
- Record an estimated **Phase-1 embedding-cost ceiling** in the manifest before any run: approximate token
  volume (500 instances × ~40 sessions, across both the per-session and per-turn corpora) ×
  text-embedding-3-large pricing. Phase 1 is "cheap, runnable now" only once this estimate is written down
  and acknowledged — a recorded ceiling, not an assumption (pairs with the U3 embedding cache).

**Patterns to follow:** `harness/capture_gbrain_baseline.py` (frozen-fixture discipline), `.gitignore`
existing corpus-data policy.

**Test scenarios:**
- Happy path: a manifest round-trips (build → serialize → parse) with all required pins present.
- Edge case: hash mismatch on a tampered/short download raises and does not write a corpus.
- `Covers AE-adjacent:` manifest never contains the API key (assert key string absent from output).

**Verification:** `manifest.py` produces a complete, committed manifest; the dataset is fetched and
hash-verified locally; `git status` shows no dataset JSON or corpus staged.

---

### U2. Deterministic session→markdown materializer + gold reconstruction

**Goal:** Turn each instance into a byte-reproducible markdown corpus (two granularities) and reconstruct
the session- and turn-level gold sets.

**Requirements:** R4, R5, R6; F2

**Dependencies:** U1

**Files:**
- Create: `harness/longmemeval/materialize.py`
- Test: `tests/test_longmemeval_harness.py`

**Approach:**
- Per instance, write one markdown file per session (QA corpus) AND one per user turn (turn-diagnostic
  corpus). File body carries `Session Date: <haystack_date>` and the turns in plain `**user:** … /
  **assistant:** …` form — in the body (not frontmatter), since `ingest.strip_frontmatter` removes
  frontmatter from the indexed body and the reader needs the date inline.
- Verbatim content only — no summarization/fact-extraction (R4). Deterministic file naming + ordering so
  the same instance yields byte-identical files (R5).
- Reconstruct gold: session-level from `answer_session_ids`; turn-level from `has_answer:true` user
  turns; record per-instance `question_type` and `_abs` flag. Map each materialized file path back to its
  session/turn id for scoring.

**Patterns to follow:** `tests/conftest.py::make_corpus` (write + git init), `harness/build_query_set.py`
(JSONL row conventions, `relevant`/`relevant_primary` keys).

**Test scenarios:**
- Happy path: a 3-session instance with one evidence session yields the expected per-session and per-turn
  files and a correct session/turn gold set.
- Edge case: re-materializing the same instance produces byte-identical files (determinism, R5).
- Edge case: session date is present in the file body and survives indexing (not only in frontmatter, R6).
- `Covers AE1.` an `_abs` instance is flagged abstention and carries no retrieval gold.

**Verification:** materialized corpus is deterministic; gold sets match the `answer` substring +
`has_answer` convention from official `run_retrieval.py`.

---

### U3. Per-haystack index + retrieval adapter

**Goal:** Build an isolated index per instance and return ranked hits, with the embed-quiescence void gate.

**Requirements:** R12, R19, R20; F2

**Dependencies:** U2

**Files:**
- Create: `harness/longmemeval/adapter.py`
- Test: `tests/test_longmemeval_harness.py`

**Approach:**
- For one instance: `index.build_index(corpus_dir, embedder, state_dir=<outside corpus>)` then
  `retrieve.search(idx, question, embedder=embedder, k=…)`; close/discard. Run once over the per-session
  corpus and once over the per-turn corpus.
- Call `embed.smoke_embed_or_die()` before any scoring; if any query's `SearchResult.degraded` is true,
  mark the whole run `void` (R20/AE2) — never score a lexical-only degraded run.
- Use the production embedding config unchanged (R12); freeze k + fusion weights + lanes and record them
  in the manifest (R19). Keep near-dup handling symmetric with `collapse_duplicates=True`.
- Include a **content-hash embedding cache** (keyed by chunk text + model + dim) in this unit's scope —
  not conditional — so per-haystack isolation does not re-embed shared content on every run and the F3
  critic re-run stays within the U1 cost ceiling.

**Patterns to follow:** `harness/portability_probe.py::probe_repo`, `harness/parity_harness.py`
(`smoke_embed_or_die`, `res.degraded` → void).

**Test scenarios:**
- Happy path: building over a small fake corpus and retrieving returns `Hit`s mapped to session/turn ids.
- Integration: per-haystack isolation — one instance's index does not leak docs from another.
- `Covers AE2.` a degraded embedder (raises `EmbeddingError`) yields a `void` run, not a score.
- Edge case: index `state_dir` lives outside the corpus; the corpus tree is unmodified after a build.
- Integration: a re-run hits the content-hash embedding cache (no duplicate embed calls for unchanged chunks).

**Verification:** ranked hits map cleanly to gold ids; degraded path voids; no engine `src/` changes.

---

### U4. Retrieval diagnostic scorer (session + turn level)

**Goal:** Compute the official retrieval metrics for both granularities, aggregate + per-ability.

**Requirements:** R7, R9, R20; F2

**Dependencies:** U3

**Files:**
- Create: `harness/longmemeval/diagnostic.py`
- Test: `tests/test_longmemeval_harness.py`

**Approach:**
- Reuse `parity_harness.doc_ranking` to collapse hits → ranked session/turn ids; add `recall_all@k`
  (all gold in top-k → 1.0 else 0.0) and `ndcg_any@k` (binary relevance, ideal-DCG normalized) — the
  official headline metrics, distinct from parity's fractional `recall_at_k`.
- Report session-level `recall_all@{5,10}` + `ndcg_any@{5,10}`; turn-level same plus `@50`. Exclude the
  30 `_abs` instances from retrieval scoring. Break results out per the 5 abilities.
- For the **date-sensitive abilities (knowledge-update, temporal-reasoning)**, additionally report
  `recall_any@k` and the gold-set-size distribution, so a low `recall_all` is attributable to
  metric-strictness / date-blind ranking vs a genuine miss (the engine does no date-aware ranking).
- Emit a structured result dict + `--json` with an explicit `verdict`/`void` field, matching the parity
  harness shape; commit only aggregate/per-ability numbers (R15).

**Patterns to follow:** `harness/parity_harness.py` (metric fns, result-dict shape, `_verdict` states),
`harness/corpus_equivalence.py` (symmetric dedup if duplicate sessions appear).

**Test scenarios:**
- Happy path: a hand-built ranking with known gold yields the expected `recall_all@k` and `ndcg_any@k`.
- Edge case: `recall_all` is 0 when only some gold docs are in top-k (distinct from `recall_any`).
- Edge case: `_abs` instances are excluded from retrieval aggregates.
- Edge case: turn→session derivation matches when computed from the per-turn ranking.
- Edge case: knowledge-update/temporal instances report both `recall_any@k` and `recall_all@k` plus gold-set size.

**Verification:** numbers match the official `recall_all`/`ndcg_any` definitions on a worked example;
per-ability breakdown sums correctly.

---

### U5. Offline tests + CI smoke subset

**Goal:** Exercise the whole Phase 1 pipeline offline and add a pinned, non-headline CI smoke subset.

**Requirements:** R18; AE1, AE2, AE4

**Dependencies:** U2, U3, U4

**Files:**
- Create: `tests/test_longmemeval_harness.py`, `harness/longmemeval/smoke.example.jsonl`
- Modify: (no CI change needed — existing `pytest` job picks it up)
- Test: (this unit *is* the tests)

**Approach:**
- Build a tiny synthetic set of instances spanning all 5 abilities (incl. one `_abs`) as
  `smoke.example.jsonl` (committed, synthetic — never real corpus data).
- Use `FakeEmbedder` + `make_corpus` and inject fake reader/judge callables; no network/API calls.
- Assert: diagnostic result-dict shape, the void path (AE2), abstention handled as its own ability (AE1),
  and the smoke subset labeled non-headline and never substituted for the full number (AE4).

**Patterns to follow:** `tests/test_parity_harness.py`, `tests/test_portability_probe.py`,
`tests/test_judge_labels.py` (offline injection patterns).

**Test scenarios:**
- `Covers AE4.` smoke-subset output carries a non-headline label and is excluded from any headline field.
- `Covers AE1.` abstention instance scored in the abstention bucket, not folded elsewhere.
- `Covers AE2.` degraded embedder → void.
- Happy path: full Phase-1 pipeline runs end-to-end on the synthetic set with `FakeEmbedder`.

**Verification:** `uv run pytest` passes offline with no key; `ruff` + `license_scan` stay green.

---

### U6. Diagnostic results write-up (verdict-doc scaffold)

**Goal:** Publish the Phase 1 retrieval diagnostic as the seed of the committed verdict doc.

**Requirements:** R2, R9, R13, R15, R21

**Dependencies:** U4

**Files:**
- Create: `harness/BENCHMARKS.md`
- Test: none — documentation artifact (`Test expectation: none — committed prose/results doc`)

**Approach:**
- Seed `harness/BENCHMARKS.md` in the `PARITY_VERDICT.md` style: methodology, the **comparability
  envelope** table, the retrieval diagnostic results table (session + turn level, per-ability), a manifest
  reference, and a contamination disclosure. Aggregate/non-identifying numbers only (R15).
- The comparability envelope (R2, R21) must attribute **reader model, judge model, and dataset release
  (original vs cleaned-2025-09)** per cited SOTA row; decompose the ~11-pt reader-vs-judge swing; state
  that our GPT-4.1-reader / `gpt-4o-2024-08-06`-judge cell is **not** the GPT-4.1-graded 95.4 row and is
  expected below it on judge strictness; and name the truly-comparable GPT-4o-judge anchors (full-context
  ≈60, Zep ≈71, OMEGA-on-GPT-4o ≈84.2).
- Document that the engine does **no date-aware retrieval ranking**, so any knowledge-update /
  temporal-reasoning gap localizes to retrieval ordering, not the reader (report `recall_any` beside
  `recall_all` for those abilities, per U4).
- Leave a clearly-marked "Phase 2 — end-to-end QA headline (GPT-4.1 + GPT-4o columns): pending" placeholder for U9.

**Patterns to follow:** `harness/PARITY_VERDICT.md` (structure, honesty discipline, corrections log).

**Test scenarios:** none — non-behavioral documentation unit.

**Verification:** the doc states the comparability envelope explicitly and references the manifest; no
per-instance corpus data is committed.

---

### U7. GPT-4.1 reader [Phase 2]

**Goal:** Answer each question from retrieved context with the pinned readers (GPT-4.1 lead + GPT-4o
anchor), matching official reading conventions.

**Requirements:** R10 (dual reader columns), R17, R21; F1; AE3

**Dependencies:** U3

**Files:**
- Create: `harness/longmemeval/reader.py`
- Modify: `pyproject.toml` (add `tiktoken` under a new `bench` optional-dependency group — MIT, keeps
  `license_scan` green)
- Test: `tests/test_longmemeval_harness.py`

**Approach:**
- `Reader` modeled on `expand.OpenAIExpander`/`judge_labels.OpenAIJudge`: lazy keyed client, pinned model,
  `temperature=0`, graceful failure, injectable for tests. The model is a parameter so the **same reader
  runs both headline columns** — `gpt-4.1-2025-04-14` (lead) and `gpt-4o-2024-08-06` (apples-to-apples
  anchor) — plus `gpt-4.1-mini` as the cheap dev/CI reader. Every column is labeled with its reader model
  (AE3); the GPT-4.1 and GPT-4o columns publish together under the shared judge.
- Reading method `con` (extract-then-reason), `history_format=json`, retrieved units re-sorted ascending
  by date, `has_answer` stripped, `Current Date = question_date`. Token budget `model_max − gen − 1000`
  via tiktoken `o200k_base`; GPT-4.1's 1M context means `_s` fits untruncated.

**Patterns to follow:** `src/hypermnesic/expand.py`, `harness/judge_labels.py::OpenAIJudge`.

**Test scenarios:**
- Happy path (injected fake client): the reader assembles date-sorted, `has_answer`-stripped context with
  the correct `Current Date` and returns an answer string.
- `Covers AE3.` each reader column (gpt-4.1, gpt-4o, gpt-4.1-mini) is tagged with its own model label; the dev/mini run is non-headline.
- Edge case: context within budget is not truncated; over-budget context is truncated by tiktoken count.

**Verification:** offline test with a fake client reproduces the `con`/json/date-sorted prompt shape;
`license_scan` passes with `tiktoken` added.

---

### U8. LongMemEval autoeval judge [Phase 2]

**Goal:** Grade reader answers with the canonical judge and the official per-type prompts.

**Requirements:** R8, R11; F1; AE1

**Dependencies:** U2

**Files:**
- Create: `harness/longmemeval/judge.py`
- Test: `tests/test_longmemeval_harness.py`

**Approach:**
- `Judge` on the `OpenAIJudge` shape, pinned `gpt-4o-2024-08-06`, `temperature=0`, `max_tokens=10`,
  label = `'yes' in response.lower()`. Select among the **5 verbatim per-`question_type` templates**
  (default; temporal off-by-one; knowledge-update latest-wins; preference rubric; abstention) by
  `question_type` + `_abs`.
- Reuse the `CodexJudge` no-API-key lane only for cheap dev iteration; the headline must use the keyed
  `gpt-4o-2024-08-06` judge (R11).

**Patterns to follow:** `harness/judge_labels.py` (backend shape, robust parsing, graceful failure).

**Test scenarios:**
- Happy path (injected fake): the correct per-type prompt is selected for each `question_type`.
- `Covers AE1.` abstention picks the abstention prompt and grades "correctly refused" as correct.
- Edge case: knowledge-update grades the updated answer as correct even when the old one is restated.
- Edge case: label parsing is case-insensitive and robust to extra text.

**Verification:** prompt selection matches official `get_anscheck_prompt()`; judge model string is exactly
`gpt-4o-2024-08-06` (so an official aggregator would accept it).

---

### U9. End-to-end QA runner + scorer + verdict finalization [Phase 2]

**Goal:** Run the full `_s` headline for both reader columns under the shared judge, compute the official
metrics, and finalize the verdict doc with full comparability attribution.

**Requirements:** R1, R2, R8, R9, R13, R16, R17, R19, R20, R21; F1, F3

**Dependencies:** U4, U6, U7, U8

**Files:**
- Create: `harness/longmemeval/qa.py`
- Modify: `harness/BENCHMARKS.md` (append the headline results + critic re-run instructions)
- Test: `tests/test_longmemeval_harness.py`

**Approach:**
- Orchestrate F1: per instance, retrieve (U3) → reader (U7) → judge (U8), for **both** the GPT-4.1 and
  GPT-4o reader columns under the shared `gpt-4o-2024-08-06` judge (retrieval + judge are reused across
  columns; only the reader pass repeats). Gate on embed-quiescence (void if degraded, R20). Run the full
  500-Q `_s` set — no sampling (R17); log the actual per-run cost per column.
- Score per `print_qa_metrics.py`: **Overall** (micro), **Task-averaged** (macro over the 6 `question_type`
  buckets, abstention excluded) as the headline, **Abstention** (30) separately; per-ability breakdown —
  for each reader column.
- Freeze retrieval/fusion params before the run; record any deviation (R19). Append to `harness/BENCHMARKS.md`
  the headline table (**both** reader columns) beside the diagnostic, the per-row-attributed comparability
  envelope + reader-vs-judge swing decomposition (R21), and the F3 critic re-run steps (download by hash →
  run with the manifest's pinned models/params).

**Execution note:** This unit's paid 500-Q run is gated on the Phase 1 diagnostic + an explicit budget
sign-off; land and test the code offline first, then trigger the run deliberately.

**Patterns to follow:** `harness/parity_harness.py` (runner + verdict + `--json`), `harness/PARITY_VERDICT.md`.

**Test scenarios:**
- Happy path (injected fake reader+judge): task-averaged macro, Overall micro, and Abstention are computed
  correctly on a synthetic set with known labels.
- Edge case: task-averaged excludes abstention; abstention reported with its count.
- Happy path: both reader columns are scored and reported under the shared judge with distinct model labels.
- `Covers AE2.` a degraded run voids the headline rather than reporting a number.
- Integration: a full offline run wires materialize → index → retrieve → reader → judge → verdict.

**Verification:** offline run reproduces the official three numbers on a worked example; verdict doc
states the comparability envelope and turnkey critic re-run; the paid run remains a deliberate, gated step.

---

## System-Wide Impact

- **Interaction graph:** new code is confined to `harness/longmemeval/`, `tests/`, `harness/BENCHMARKS.md`,
  plus `.gitignore` and a `pyproject.toml` `bench` extra. The engine read path (`src/hypermnesic/`) is
  consumed as shipped — no engine changes.
- **Error propagation:** embedding/retrieval failures surface as a `void` run (never a silent score);
  reader/judge failures fail loud or degrade gracefully per the existing judge pattern.
- **State lifecycle risks:** per-haystack indexes use a `state_dir` outside the corpus and are discarded;
  no leakage across instances; no mutation of any committed tree.
- **API surface parity:** none — this adds harness tooling, not engine API.
- **Integration coverage:** the offline pipeline test (U5) proves materialize→index→retrieve→score wiring
  that mocks alone wouldn't.
- **Unchanged invariants:** embedding config (text-embedding-3-large @ 1536, R12); engine never mutates the
  target repo; credential discipline (key never written to output).

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Embedding cost of 500 per-haystack `_s` builds is larger than "cheap" implies | U1 records a Phase-1 cost ceiling before running; U3 ships a content-hash embedding cache (in scope, not conditional); embeddings still ≪ reader/judge cost |
| GPT-4.1 snapshot drift / availability / pricing | Pin `gpt-4.1-2025-04-14` in the manifest; record cost at run time; reader is injectable |
| Dataset contamination (public on HF) | Disclosure note in `harness/BENCHMARKS.md`; pin the cleaned-2025-09 release by hash |
| Reader nondeterminism (~1 pt at temp 0) | Report within "judge variance"; manifest enables exact re-run |
| Headline misread as the 95.4 row (reader/judge/dataset mismatch) | Publish GPT-4.1 + GPT-4o columns together under the shared judge; attribute reader/judge/dataset-release per SOTA row; decompose the ~11-pt swing; name the GPT-4o-judge anchors (R21) |
| Date-blind ranking depresses knowledge-update/temporal under `recall_all` | U4 also reports `recall_any@k` + gold-set-size for those abilities; verdict states the gap is retrieval-ordering, not reader |
| `license_scan` regression from `tiktoken` | `tiktoken` is MIT; confined to a `bench` extra; CI gate verifies |
| Mis-reporting `recall_any` as `recall_all`, or micro as task-averaged | U4/U9 implement the official definitions; tests assert them on worked examples |

---

## Phased Delivery

### Phase 1 — Diagnostic harness (embeddings-only; cost ceiling recorded first)
- U1 → U2 → U3 → U4 → U5 → U6. Produces the committed harness, manifest, offline CI smoke, and the
  seeded `harness/BENCHMARKS.md` with session- and turn-level retrieval diagnostics. No reader/judge spend,
  but the embedding cost (500 per-haystack builds, both corpora) is real — U1 records an estimated cost
  ceiling and U3 ships the content-hash embedding cache, so "cheap" is quantified, not assumed.

### Phase 2 — Gated end-to-end QA headline (GPT-4.1 + GPT-4o columns)
- U7 → U8 → U9. Lands the reader, judge, and QA runner with offline tests. The paid full `_s` run scores
  **both** reader columns under the shared `gpt-4o-2024-08-06` judge, and is triggered only after the
  Phase 1 diagnostic is reviewed and a budget (covering both reader passes) is signed off. A
  comparability-framing check — per-row reader/judge/dataset attribution present (R21) — is part of that
  sign-off.

---

## Documentation / Operational Notes

- `harness/BENCHMARKS.md` is the public-facing artifact; keep it in the `PARITY_VERDICT.md` honesty style
  (record corrections, no tune-to-pass, aggregate-only numbers).
- Operational: the Phase 2 run needs `OPENAI_API_KEY` and a budget; it is a manual, deliberate step, not
  part of CI. CI runs only the offline smoke (U5).

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-02-longmemeval-benchmark-protocol-requirements.md](docs/brainstorms/2026-06-02-longmemeval-benchmark-protocol-requirements.md)
- Related code: `harness/parity_harness.py`, `harness/portability_probe.py`, `harness/judge_labels.py`,
  `harness/PARITY_VERDICT.md`, `src/hypermnesic/index.py`, `src/hypermnesic/retrieve.py`,
  `src/hypermnesic/embed.py`, `src/hypermnesic/expand.py`, `tests/conftest.py`
- External: LongMemEval (`github.com/xiaowu0162/LongMemEval`), dataset `xiaowu0162/longmemeval-cleaned`
  (HF, MIT), paper arXiv 2410.10813; Zep and OMEGA LongMemEval reports (reader/judge comparability).
