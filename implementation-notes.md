# hypermnesic — implementation notes (Phase 0)

Running log of decisions, deviations from the plan, and open questions. The
authoritative plan lives in the gbrain-brain vault at
`projects/hypermnesic/docs/plans/2026-06-01-001-feat-hypermnesic-phase0-kernel-plan.md`.

## Conventions

- Python ≥3.11, `uv` for deps, `ruff` (line-length 100), `pytest`
  (`--import-mode=importlib`). CLI tooling mirrors the vault convention:
  standalone `main()` + `argparse` + `--json` (`ensure_ascii=False`).
- Permissive primitives only. The U1 license gate
  (`scripts/license_scan.py`) fails on any AGPL/GPL/SSPL transitive dep.
- gbrain-brain is read **only** — corpus + parity baseline. Never written; its
  `.gitignore` / tracked files are never mutated (KTD8).

## U1 — scaffold (in progress)

- Repo created at `<home>/dev/hypermnesic`, `git init -b main`.
- Deps declared: `sqlite-vec`, `openai`, `mcp`, `ruamel.yaml`; dev:
  `pytest`, `ruff`, `pip-licenses`.
- `LICENSE`: proprietary/private placeholder. Plan allows no public LICENSE
  while private; an internal notice is added for clarity. Public terms TBD
  pre-release (Open Questions).
- License gate: `scripts/license_scan.py` denies AGPL/GPL/SSPL; LGPL reported
  informationally (not in the deny set per the plan). Prefers `pip-licenses`,
  falls back to `importlib.metadata`.

### Direct dependency licenses (recorded per U1 acceptance criterion)

| Package | Version | License |
|---|---|---|
| sqlite-vec | 0.1.9 | MIT + Apache-2.0 |
| openai | 2.38.0 | Apache-2.0 |
| mcp | 1.27.2 | MIT |
| ruamel.yaml | 0.19.1 | MIT |
| pytest | 9.0.3 | MIT |
| ruff | 0.15.15 | MIT |
| pip-licenses | 5.5.5 | MIT |

Full resolved tree: 46 packages, **0 AGPL/GPL/SSPL**, 0 LGPL (G2 PASS).

### Resolved blockers (U1)

- **OPENAI_API_KEY**: operator populated `<home>/dev/hypermnesic/.env`
  (verified non-empty, `sk-` prefix, 164 chars; value never echoed). `.env` is
  gitignored. Key blocker cleared for U2/U5/U6 live gates.

## U2 — read-only index core (done, live-verified)

- `config.py` pins `text-embedding-3-large` @ 1536 in one place;
  `assert_embedder_agrees` fails fast on a dim mismatch. Key read from env/.env
  only, never echoed/persisted.
- `embed.py`: `dimensions=1536` sent explicitly; `smoke_embed_or_die` fails loud
  on missing/invalid key (never zero-vectors). Live smoke embed confirmed the
  key is actually *read* by the SDK.
- `ingest.py`: walks `*.md`, strips frontmatter, chunks to ≤4000 chars.
  **Bug found + fixed on first full index:** a single >8192-token block
  overflowed the embedding API (`input[118]`); `_split_oversized` now hard-splits
  oversized blocks (regression test added).
- `index.py`: sqlite-vec `vec0(... float[1536])` + FTS5 (`unicode61
  remove_diacritics 2`) + `meta` checkpoint slot. KNN uses `MATCH ... k = ?`
  (tested invariant, KTD3). State dir 0700, db 0600.
- **Corpus written read-only via an EXTERNAL state dir** (`build_index(...,
  state_dir=...)`): gbrain-brain itself is never written — not even a gitignored
  dir or a `.git/info/exclude` entry. The in-repo `.hypermnesic/` default (with
  `ensure_ignored` via `.git/info/exclude`, never `.gitignore`) is reserved for
  U6 portability targets.
- **Live full index:** 27,451 chunks / 3,518 docs, checkpoint = HEAD
  `42f6ac5`. Corpus verified untouched (clean tree, no `.hypermnesic/`, no
  exclude edit). Known queries return sensible pages; rebuild is deterministic.

## U3 — hybrid retrieval + build_context (done, live-verified)

- `retrieve.py`: RRF fusion of FTS5 + sqlite-vec; **optional** rerank stage
  (KTD5, default off); graceful lexical-only degradation flagged
  `dense_used=False` so U5 can VOID (not FAIL) a degraded run.
- `graph.py`: body-`[[wikilink]]` edges only (frontmatter relations excluded for
  free — ingest already stripped frontmatter). `build_context` BFS over in+out
  edges, cycle-safe, depth-bounded. Live: 3,518 nodes; `build_context` from
  `gbrain.md` returns 53 linked pages.

## U4 — read-only MCP server (code done; G5 live check pending)

- `mcp_server.py`: FastMCP, streamable-http, binds a specific Tailscale IP
  (refuses `0.0.0.0`/`::` at construction — KTD10). Exactly two tools (`search`,
  `build_context`), both `readOnlyHint=True`; **no write tool exists** (structural
  read-only). Dense degrades gracefully; lexical+graph always answer.

## U5 — parity harness (code + offline tests done; live verdict blocked)

- `harness/parity_harness.py`: recall@10 + MRR, both sides scored vs
  human-judged labels (KTD6); verdict pass/fail/no_decision/void; near-tie band;
  catastrophic-French-miss (AE6); voids on any lexical-only-degraded query.
  One command, `--json`. 6 offline fixture tests pass (AE6, aggregate, near-tie,
  determinism, void, metric helpers).
- **The live verdict (G6) is blocked on operator-owned inputs** — see below.

## U6 — zero-infra portability probe (done, live G7 PASS)

- `harness/portability_probe.py` + `hypermnesic init`. Grades builds/answers/
  zero-setup/tracked-unchanged; requires both a coding and a markdown target.
- **Live G7:** markdown target (vault slice, 140 chunks) and coding target
  (fresh clone of hypermnesic, 14 chunks — only 2 `.md`, code/binary skipped, no
  crash) both PASS. Independent check: both targets' tracked files UNCHANGED,
  `git status` empty; only the `.hypermnesic/` state dir added, ignored via
  `.git/info/exclude` (never `.gitignore`). 6 offline fixture tests pass.

## U5 — parity verdict: PROVISIONAL `fail` (operator decisions applied)

Operator chose **agent best-effort (provisional) query set** + **authorize the
reranker toggle** for the baseline.

- **Query set** `harness/queries.frozen.jsonl`: 32 known-item queries (18 FR /
  14 EN), built deterministically by `build_query_set.py` (sha256 seed; excludes
  `sources/` ID-title noise; per-dir diversity cap). Labels are AGENT-proposed →
  verdict is provisional, not the Phase-1 gate (KTD6).
- **gbrain baseline** `harness/gbrain_baseline.frozen.jsonl`: top-10 docs/query
  from homelab `gbrain search` (`capture_gbrain_baseline.py`), slugs resolved to
  actual case-correct paths.
- **Reranker toggle finding (KTD5):** `gbrain search` output is **byte-identical
  with `search.reranker.enabled` true vs false** — `search` does not apply the
  ZeroEntropy reranker (the `query`/RAG path does). So the baseline is
  un-reranked **without** a lasting shared-service change. The global setting was
  toggled false→true→**restored to `true` and verified** (net-zero; transient
  maintenance, not mirrored to gbrain-brain since this goal keeps the corpus
  read-only and the net state is unchanged).
- **Verdict (class-space, current):** PROVISIONAL **`fail`**, 0 catastrophic
  French misses. hypermnesic wins recall@10 (all 0.906 vs 0.781; French 0.889 vs
  0.667) and **French MRR** (0.416 vs 0.311); trails on **aggregate MRR** (0.459
  vs 0.521) — driven by English *title-derived* known-item queries where exact
  lexical match ranks #1. No tuning to chase a PASS. Full analysis +
  operator follow-ups in `harness/PARITY_VERDICT.md`.

## U5/U6 follow-up — dedup, class-space scoring, privacy

- **#1 retrieval near-duplicate collapse** (`retrieve.search`, default on):
  drops hits whose chunk text is byte-identical to a higher-ranked hit. A real
  UX win (corpora mirror docs at two paths) + fixes the earlier q07 artifact.
- **#2 equivalence-class scoring** (`corpus_equivalence.py`): content mirrors +
  same-event `meetings/`↔`sources/` (date+slug, hex-suffix stripped; date kept so
  recurring-title meetings don't merge). Labels expand to the class; the harness
  scores both sides in class space. Earlier single-label/raw-path run had 2
  "catastrophic French misses" that were duplicate-copy artifacts → now 0.
- **Privacy (repo will go public):** the frozen query set, gbrain baseline, and
  per-query results are **corpus-derived private data → gitignored, never
  committed**. The repo ships generic tooling + `queries.example.jsonl`
  (synthetic). All test fixtures use fictional names/slugs. The earlier commit
  with real corpus data was purged (old repo deleted + recreated from clean
  history; old SHA 404s).

## Pre-U7 threat model (gate artifact)

- `docs/threat-model-commit-note.md`: the mandatory Phase-1 gate artifact. 10
  attack vectors (protected-path escalation, ingested-content prompt injection,
  frontmatter churn, actor spoofing, log leak, path traversal, gitignore side
  effects, concurrent-writer corruption, credential exposure, crash recovery)
  mapped to U8/U11/U12, with accepted risks + a Phase-1 entry checklist. Needs
  operator sign-off before U7.

## Faithful parity (NL queries vs gbrain HYBRID, un-reranked) — supersedes earlier

- **Two corrections to the methodology:** (1) queries are now **natural-language
  questions**, not verbatim titles (titles over-rewarded exact lexical match);
  (2) the baseline is **`gbrain query`** (real hybrid: vector+keyword+expansion),
  not `gbrain search` (FTS keyword-only — flatters gbrain on titles, collapses on
  NL). `query` *does* rerank, so the baseline was captured inside a bracketed
  reranker toggle (false→capture→restore+verify `true`).
- **Result (provisional, near-parity):** hyp recall@10 0.875 vs gbrain 0.844
  (French 0.833 vs 0.778 — hyp ahead on recall incl. French); MRR 0.559 vs 0.611
  (French 0.466 vs 0.562 — gbrain ahead on ranking precision). 1 French
  catastrophic miss in a dense near-duplicate cluster. Verdict **`fail`** on the
  MRR band, but the systems are essentially **at parity** — recall parity is
  achieved; the gap is ranking precision, plausibly gbrain's multi-query
  expansion vs hyp's plain RRF. Addressable via fusion/expansion, not a rebuild.
  Full sanitized verdict: `harness/PARITY_VERDICT.md`.

## LLM-as-judge label automation (Codex / ChatGPT Pro)

- `judge_labels.py`: pooled, **system-blind** LLM-as-judge labeling (candidates
  from both systems, rank/source stripped, shuffled, judged on content). Default
  judge = `CodexJudge` (`codex exec --json`, ChatGPT login — **no OpenAI API key**
  for judging; embeddings for pooling are the pinned index model). `label_review.py`
  remains for manual checkbox review.
- **Gate-of-record (LLM-judged):** provisional FAIL at near-parity — hyp recall@10
  0.871 vs 0.818 (wins, incl. French), MRR 0.704 vs 0.769 (gbrain wins, French MRR
  0.677 vs 0.786). Robust across 3 labelings: recall parity-or-better, consistent
  ~0.05–0.07 MRR deficit. Confirms the MRR gap is index-side (compiled-truth
  representation), a Phase-2 item — not a labeling artifact or a query-side fix.
