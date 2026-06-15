# Benchmark chart — transcribed data + attribution

The numbers in [`benchmark-longmemeval.svg`](benchmark-longmemeval.svg) are transcribed
verbatim from [`harness/BENCHMARKS.md`](../../harness/BENCHMARKS.md), the single source of
truth (re-verified against primary sources 2026-06-02). If BENCHMARKS.md changes, update
the SVG **and** this file in the same PR (doc-no-drift).

## Comparable axis — judge = `gpt-4o-2024-08-06` (the canonical judge)

LongMemEval V1, `_s` variant. Overall (micro) accuracy %.

| System | Overall | Reader | Judge | Release |
|---|---|---|---|---|
| hypermnesic — lead | **88.6** | GPT-4.1 (`gpt-4.1-2025-04-14`) | `gpt-4o-2024-08-06` | cleaned-2025-09 |
| Mastra Observational Memory | 84.2 | GPT-4o | `gpt-4o` | original |
| hypermnesic — anchor | **83.2** | GPT-4o (`gpt-4o-2024-08-06`) | `gpt-4o-2024-08-06` | cleaned-2025-09 |
| Zep | 71.2 | GPT-4o | `gpt-4o` | original |
| Full context (no memory) | 60.2 | GPT-4o | `gpt-4o` | original |

The chart's purple bars are hypermnesic; grey bars are the comparable GPT-4o-judge anchors.

## NOT directly comparable — GPT-4.1 judge (more lenient)

Shown in the chart's separated, dashed zone only to scope the judge axis. A GPT-4.1
*judge* is more lenient than `gpt-4o-2024-08-06`, so these are **not** the same
measurement as the bars above (AE3).

| System | Overall | Judge |
|---|---|---|
| OMEGA (headline) | 95.4 | GPT-4.1 |
| Mastra (OMEGA leaderboard) | 94.9 | GPT-4.1 |

## Sources (re-verified 2026-06-02, per BENCHMARKS.md)

- Zep arXiv 2501.13956 — full-context 60.2, Zep 71.2 (GPT-4o reader + GPT-4o judge).
- Mastra research page — Observational Memory 84.2 (GPT-4o reader + GPT-4o judge).
- OMEGA leaderboard (`omegamax.co/benchmarks`) — OMEGA 95.4 / Mastra 94.9 (GPT-4.1 judge).
- hypermnesic — `harness/BENCHMARKS.md` Phase 2 headline (88.6 / 83.2, both `gpt-4o-2024-08-06` judge).
