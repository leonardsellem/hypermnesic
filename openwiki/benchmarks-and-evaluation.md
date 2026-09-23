---
type: Reference
title: Benchmarks and Evaluation
description: How retrieval quality is measured and reported — the LongMemEval harness, its pinned manifest, the reader/judge/release comparability envelope, and why a benchmark score is not a product-readiness proof.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-ea70eb6c045047448e446296
    resource: repo://.gitignore
  - id: openwiki-source-7e2faff78811ec16a74aaa48
    resource: repo://harness/BENCHMARKS.md
  - id: openwiki-source-4307528c8fbee2107480aa74
    resource: repo://harness/corpus_equivalence.py
  - id: openwiki-source-1a863cad5946181fc4252610
    resource: repo://harness/longmemeval/adapter.py
  - id: openwiki-source-2dbe2d4818c5e221f6498e81
    resource: repo://harness/longmemeval/diagnostic.py
  - id: openwiki-source-b913a7bba2cf6b5b2d9a8819
    resource: repo://harness/longmemeval/judge.py
  - id: openwiki-source-149fc9f6914593e10569b53c
    resource: repo://harness/longmemeval/manifest.json
  - id: openwiki-source-8e3e9627c7024a05744124d6
    resource: repo://harness/longmemeval/manifest.py
  - id: openwiki-source-3a03bc87b74be2ba7d50d34a
    resource: repo://harness/longmemeval/materialize.py
  - id: openwiki-source-6ec0e16fd1f74a3810a08e51
    resource: repo://harness/longmemeval/qa.py
  - id: openwiki-source-41f901f9f19f630d69b443e1
    resource: repo://harness/parity_harness.py
  - id: openwiki-source-67d6bfc4b44aab1dcbded940
    resource: repo://harness/PARITY_VERDICT.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-6fc73e7c1f9cf3f50dfc9013
    resource: repo://scripts/product_smoke.py
  - id: openwiki-source-98204273e659be738502eb9c
    resource: repo://tests/test_corpus_equivalence.py
  - id: openwiki-source-d4e05c43ba8428d5802e4843
    resource: repo://tests/test_longmemeval_harness.py
  - id: openwiki-source-4b5767396e93e2f3f348638c
    resource: repo://tests/test_parity_harness.py
  - id: openwiki-source-8510c80127b69aeef6921fdd
    resource: repo://tests/test_product_remote_smoke.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Benchmarks and Evaluation

Retrieval quality is measured by a re-runnable harness under `harness/`, not by assertion.
The discipline of this page is inherited from the harness itself: a number is meaningless
without the exact conditions that produced it, so no score appears here without its reader
model, its judge model, and its dataset release.

## The comparability envelope

> A LongMemEval score is only comparable to another score that shares **three** axes:
> the reader model, the judge model, and the dataset release. The field's published
> headline numbers differ on all three.

| Axis | This harness measures | Not comparable to |
|---|---|---|
| Benchmark | LongMemEval **V1**, `_s` variant | LongMemEval V2 (multimodal, different metric) |
| Judge | `gpt-4o-2024-08-06` — the canonical judge | rows graded by a GPT-4.1 judge, which is more lenient |
| Dataset release | `cleaned-2025-09`, pinned by content hash | rows reported on the original release |
| Ingestion | raw verbatim, RAG-style | distilled / fact-extraction systems' best rows |

The judge axis matters most in practice. Leaderboard rows in the 93–96% range are graded
by a GPT-4.1 judge; this harness pins `gpt-4o-2024-08-06` because the official aggregator
hard-asserts that snapshot. A GPT-4.1-judged column is deliberately out of scope, and the
resulting gap to those rows is **judge leniency, not memory quality**. Cited external
anchors are attributed per row by reader · judge · release, and that discipline has already
caught one real error: an ~84-point GPT-4o-judge figure attributed in planning to one
system actually belongs to another, which publishes no GPT-4o-judge row at all. The
correction is recorded in the log rather than quietly fixed.

## The two phases

**Phase 1 — retrieval diagnostic.** Embeddings only, no reader or judge spend. Each
instance's sessions are materialized to markdown **verbatim** — no summarization or fact
extraction between the dataset and the index — at two granularities, per-session and
per-user-turn. The session date is written into the note *body* so it survives frontmatter
stripping into the index. The mapping is deterministic: the same instance yields
byte-identical files.

Each instance gets its **own isolated index**, built with a state directory outside the
corpus and discarded afterwards, using the production embedding configuration unchanged.
The harness consumes the shipped read path; no engine source is modified for benchmarking.
Metrics are the official ones — `recall_all@k` and `ndcg_any@k` — and the abstention
instances are excluded from retrieval scoring, matching the official runner.

**Phase 2 — end-to-end QA.** Retrieval feeds a reader, and the canonical judge grades the
answer using the official per-question-type prompt templates, including the rule that for a
knowledge-update question the *latest* value is correct and restating the superseded one is
wrong, and that an abstention instance is correct only if the model actually abstains. The
headline metric is task-averaged accuracy, macro-averaged over the six question-type
buckets, reported beside the micro overall and the abstention bucket.

Phase 2 is **gated**: the runner refuses to spend without an explicit paid-run confirmation
flag, printing the gate and a cost estimate instead.

## Honest reporting rules baked into the harness

- **Frozen parameters, no tune-to-pass.** `k`, the fusion weights, the lanes, and near-dup
  collapse are frozen at manifest values *before* any run. Any parameter change goes in the
  corrections log.
- **The embed-quiescence void.** A smoke embedding runs before scoring; if any query
  degraded to lexical-only because embeddings were unavailable, the **entire run is voided
  rather than scored**. A degraded run is non-comparable — it is not a failing score, and it
  never becomes one by accident.
- **`recall_any` beside `recall_all` where ordering is the real variable.** The engine
  applies no date-aware ranking. For abilities that need the newest session surfaced, the
  diagnostic also reports `recall_any@k` and the gold-set-size distribution, so a
  sub-unity `recall_all` localizes to *retrieval ordering* rather than being misread as
  missing coverage. On the session level `recall_any@10` reaches 1.000 for those abilities —
  at least one gold session is always retrieved — which is precisely the claim the
  end-to-end phase then leans on.
- **Aggregates only.** Per-instance corpus data, per-question outputs, the materialized
  corpus, and the embedding cache are all gitignored. Only the manifest, a synthetic smoke
  subset, and aggregate/per-ability tables are committed.
- **A corrections log in the open.** Every methodology correction, parameter change, killed
  and resumed run, and failed batch attempt is written down, including a first Phase-2
  attempt that failed provider validation at zero cost and the regression test added
  afterwards.
- **Contamination disclosed.** The dataset is public, so reader pre-training may have seen
  it. That is stated rather than hidden, and it is part of why the retrieval diagnostic —
  unaffected by reader pre-training — is treated as the higher-confidence signal.

## Reproducibility

Everything needed to reproduce a number is pinned in `harness/longmemeval/manifest.json`:
the dataset URL, its SHA-256, the release label and variant, the embedding model and
dimension, the judge model, the reader models, the frozen retrieval parameters, the prompt
template version, the seed, and the cost assumptions. A re-download is verified strictly
against the hash and fails loud on mismatch, writing nothing on a divergent download.

The paid reader path needs the `bench` extra, which is separate from the default and `dev`
installs. CI runs **only** the offline smoke test for the harness and never a paid run.

## What the benchmark does not prove

LongMemEval measures retrieval quality. It says nothing about whether setup works, whether
consent and scopes behave, whether memory control does what it claims, whether the plugin
hook is observable, or whether a remote client can actually connect. Those are gated
separately by the local product smoke script, offline remote-contract tests, the
remote-client smoke checklist, and the product-readiness checklist. A benchmark score is
never accepted as a substitute for that evidence — see
[Testing and Release Gates](testing-and-release-gates.md).

## The other harnesses

**Retrieval parity** (`harness/parity_harness.py`) scores this engine against a frozen
baseline captured once as a fixture, on a frozen query set, using human-judged relevance
labels that are independent of either system — so "at least as good as the baseline" is not
tautological. Both sides are compared un-reranked. A pass requires winning on both aggregate
`recall@10` and MRR outside a near-tie band **and** no catastrophic miss where a
known-relevant document is top-10 for the baseline but outside this engine's top-10. A
near-tie returns `no_decision`, and `no_decision` counts as not passing. As with LongMemEval,
a run that degraded to lexical-only is voided rather than scored.

The same module computes a composite cut-over verdict that a test enforces, combining
retrieval parity with two further signals: entity resolution — whose critical safety
property is **never a false wikilink**, so a miss returning nothing is acceptable where a
wrong link is not — and index freshness, that a just-committed delta is recall-able through
read-time convergence alone, with an oversized delta surfaced as a manual-reindex signal
rather than silently dropped. See [Read-Time Convergence](read-time-convergence.md).

**Corpus equivalence** (`harness/corpus_equivalence.py`) exists so parity scoring is fair.
It recognizes two narrow notions of "the same document": an exact content mirror, where the
frontmatter-stripped body is identical at two paths, and a same-event representation, where
a note and its source transcript share a date-and-slug stem after a trailing source-id
suffix is stripped. The date is deliberately kept in the key, so two different events that
merely share a title are never merged.
