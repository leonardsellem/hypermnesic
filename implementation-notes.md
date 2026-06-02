# hypermnesic — implementation notes (running log: Phase 0 → 2.5)

Running log of decisions, deviations from the plan, and open questions, in ship
order. The Phase-0 kernel plan lives in the gbrain-brain vault at
`projects/hypermnesic/docs/plans/2026-06-01-001-feat-hypermnesic-phase0-kernel-plan.md`;
the Phase-1 → 2.5 plans live in-repo under `docs/plans/`.

> **Provenance.** The Phase 0 and Phase 1 entries below are first-hand live-gate
> notes. The **Phase 2** and **Phase 2.5** sections were reconstructed from the
> merged plans (`docs/plans/…-005/006/007-…`) and PR history (#1/#2/#3/#5) during a
> 2026-06-02 documentation pass — accurate to what shipped, but not a live-gate
> log like the sections above them.

## Conventions

- Python ≥3.11, `uv` for deps, `ruff` (line-length 100), `pytest`
  (`--import-mode=importlib`). CLI tooling mirrors the vault convention:
  standalone `main()` + `argparse` + `--json` (`ensure_ascii=False`).
- Permissive primitives only. The U1 license gate
  (`scripts/license_scan.py`) fails on any AGPL/GPL/SSPL transitive dep.
- gbrain-brain is read **only** — corpus + parity baseline. Never written; its
  `.gitignore` / tracked files are never mutated (KTD8).

## U1 — scaffold (in progress)

- Repo created at `/home/ubuntu/dev/hypermnesic`, `git init -b main`.
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

Full resolved tree at U1: 46 packages (base + dev only, before the Phase-2 `sidecar`
extra), **0 AGPL/GPL/SSPL**, 0 LGPL (G2 PASS).

#### Obsidian companion devDeps (Phase 2.5 Plan 2, U35/U38)

The committed plugin now builds via esbuild. Direct devDeps are all permissive
(license-gate-clean — no AGPL/GPL/SSPL across the resolved `node_modules` tree):

| Package | License |
|---|---|
| obsidian | MIT |
| esbuild | MIT |
| typescript | Apache-2.0 |
| builtin-modules | MIT |
| @types/node | MIT |
| @codemirror/state | MIT |
| @codemirror/view | MIT |

`@codemirror/*` are added only so `tsc` resolves the CM6 imports for the optional
inline marker (U38); esbuild marks them (and `obsidian`/`electron`) external, so
they are never bundled — Obsidian provides them at runtime.

### Resolved blockers (U1)

- **OPENAI_API_KEY**: operator populated `/home/ubuntu/dev/hypermnesic/.env`
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

## U5 GATE: PASS (gate of record)

UA doc-level embedding lane + LLM-judged system-blind labels + AE6 clause
recalibrated to intent (operator-authorized): hyp ≥ gbrain on recall@10
(0.910 vs 0.818) AND MRR (0.802 vs 0.769), 0 catastrophic French misses →
**U5 retrieval-quality gate PASSES**. Phase 1 (U7) now gated only on the
pre-U7 threat-model sign-off (`docs/threat-model-commit-note.md`).
UB doc-lane up-weighting measured + rejected (traded recall for MRR; w=1.0
default). Full record: `harness/PARITY_VERDICT.md`.

## Phase 1 — write kernel (in progress; dev against temp repos only)

Threat model signed off 2026-06-01; U5 gate PASS. Built in dependency order:

- **U8 frontmatter gate** (`frontmatter_gate.py`): diff-or-die. ruamel RT (indent
  matched to vault 2-space style) + a guard that aborts on any unrequested key
  change. Scalar dates/`_`-props/order preserved; non-canonical docs abort (safe).
- **U11 audit log** (`audit_log.py`): append-only JSONL, summaries-only
  (truncated), server-set actor (Tailscale node id / sentinel; caller ignored),
  reconciler back-fills unlogged commits.
- **U7 commit_note** (`commit_note.py`): guard → gate → write → git stage+commit →
  `idx.upsert_lexical` (embeddings async, AE5) → audit append → return diff.
  Idempotent on content; gate abort = no partial effect.
  **Deviation:** commits per note (durable unit = a real commit, recoverable via
  reconciler + U9 checkpoint), vs the plan's "git stage" wording. git is the only
  sync layer, so a commit per write is the natural git-native unit.
- **U12 guard** (`serialize.py`): rule-based protected-path denylist + within-repo
  + allowlist. Multi-writer **serialization (worktree/path-scoped locks) is the
  remaining half of U12** — follow-up.
- **Remaining Phase-1 units:** U9 (index = pure projection of git tree + SHA
  checkpoint catch-up + working-tree overlay), U10 (rename/move one-surface),
  U12 serialization. No live gbrain-brain write / cron repoint without explicit
  per-action go-ahead (sign-off proviso).

## Phase 1 COMPLETE (U7–U12) — write kernel (temp-repo dev only)

- **U9** index = pure git-tree projection: `catch_up` delta-replays from the SHA
  checkpoint (committed-tree read), `apply_working_tree_overlay` for the dirty
  authoring host (no checkpoint advance). `remove_path`/`all_paths` added.
- **U10** rename one-surface: `rename_note` = git mv + `index.rekey_path` (UPDATE
  path in place — preserves embeddings, no tombstone, no resurrection).
- **U12** serialization: `serialize.FileLock` (flock), `index_write_lock`
  (single-indexer KTD9), `path_lock` (narrow), `preflight` (dirty-tree +
  head-drift). Wired into build_index/catch_up/commit_note/rename_note so all
  index writers are single-writer-safe. **Follow-up:** broad-reindex worktree
  isolation (the lock already gives correctness; worktree isolation would let a
  broad reindex run without blocking narrow writers).
- All Phase-1 units TDD'd against TEMP repos. No live gbrain-brain write / cron
  repoint performed (sign-off proviso) — awaits explicit per-action go-ahead.

## Phase-0/1 follow-ups COMPLETE (U13–U16) — plan 003

- **U13 async embed-stale** (`index.embed_stale`, `hypermnesic embed`): fills only
  missing vec_chunks + backfills the doc lane for commit_note pages; idempotent;
  closes the AE5 dense lag.
- **U14 worktree-isolated reindex** (`index.reindex_isolated`, `reindex --isolated`):
  build lock-free in a worktree, atomic `os.replace` swap under a ms lock; narrow
  writers never block; non-git fallback to in-place rebuild.
- **U15 dry-run** (`commit_note`/`rename_note` `dry_run=True`): guard + gate run,
  zero side effects; preview-only `commit-note` CLI.
- **U16 dogfood preview** (`harness/dogfood_commit_note.py`): structured read-only
  "safe to cut over?" report; never writes (safe against the live vault).
- **Still deferred + gated:** the LIVE cron cutover (actual writes to gbrain-brain)
  — needs per-action go-ahead after reviewing a U16 report. Then Phase 2.

## Real-vault gate+guard audit (read-only; harness/gate_audit.py)

Ran against gbrain-brain (3,111 md, read-only — corpus untouched):

- **Gate abort rate: 11.1%** (298/2,698 editable docs). A no-op field-set would
  churn an untouched key on ~1 in 9 docs — concentrated on **list/sequence fields**
  whose original indent differs from the gate's configured style (`snapshot_tags`
  on Readwise `.raw/` snapshots; `aliases`/`tags`/`evidence_sources` on company
  pages). The gate ABORTS (safe — no silent churn), but this is real edit friction.
  **Follow-up (pre-heavy-live-use): tune the gate's ruamel list-style preservation**
  (per-doc indent detection, or preserve flow/block style) to cut the abort rate.
  2 docs have unparseable YAML (would error on any edit) — operator hygiene.
- **Guard: 0 true false-positives** — ordinary notes (people/companies/projects/
  concepts/memory) are writable; CLAUDE.md→AGENTS.md symlink correctly refused.
  **Gap found + fixed:** `skills/` (vault-local agent skills, governance) was
  writable — added `skills` to the protected-dir denylist.

## U17 gate surgical scalar-set — abort rate 11.1% -> 0.0% (plan 004)

The diff-or-die gate now does a **surgical line edit** for scalar field-sets
(`_surgical_set` in frontmatter_gate): replace only the target key's inline value
on its own line, leaving every other byte identical — so untouched block lists
can't reflow. Falls back to the ruamel round-trip only for structural edits
(add/delete/list/block value, or a commented/multi-line key); `assert_only_changed`
still guards the result (diff-or-die unchanged). Re-running the read-only vault
audit: **abort rate 11.1% -> 0.0%** across 2,698 editable docs (2 unparseable-YAML
docs remain = operator hygiene). The write kernel is now practically usable for
field edits on the real vault. Live cutover still gated on per-action go-ahead.

## Phase 2 — the human/product surface (U18–U25, plan 005; PR #1)

Turns the kernel into the human surface: review-gated proposals, the H1–H6
experience axis, and multi-format coverage — all under the trust floor of
no-surprise-rewrite maintenance. Built **foundation-first** (the proposal queue
before every proposal-emitting feature). The Obsidian surface ships **Hybrid**:
generated markdown + native **Bases** (Phase 2a, zero plugin code) plus a thin
desktop companion (Phase 2b).

- **U18 review-gated proposal/PR queue** (`propose.py`) [R10/R11/F5/#12]: a
  `propose()` primitive that lands narrow, path-scoped, gate-checked diffs on
  `hypermnesic/proposals/*` branches and surfaces them as GitHub PRs the owner
  approves — never auto-merged. The foundation every other proposal-emitting
  feature depends on.
- **U19 multi-format sidecars** (`sidecar.py`) [R13/#10]: content-addressed
  extract-to-markdown for PDF/DOCX/XLSX/PPTX/PNG, routed Docling (MIT) ↔
  MarkItDown (MIT), hash-gated so re-extraction is skipped when the source is
  unchanged.
- **U20 thinking-mode** (`think.py`) [R7/H1/KD2]: an observable, **no-write**
  reasoning boundary — a read-only `think` surface distinct from the write path.
- **U21 salience + spaced-review digest** (`salience.py`) [R6/H4/F3/KTD2]:
  salience scoring and a spaced-review digest for resurfacing.
- **U22 connection / serendipity proposals** (`connect.py`) [R6/H3/F3/AE4/KTD3]:
  surfaces non-obvious links as review-gated connection proposals.
- **U23 always-organized navigation surface** (`nav_surface.py`) [R6/H5/F3/AE4]:
  generated MOCs / dashboards + native Obsidian **Bases** (Phase 2a).
- **U24 frictionless capture → deferred triage** (`capture.py`) [R6/H6/F5]: land
  raw text in `sources/` with zero ceremony; triaged later in thinking-mode.
- **U25 Obsidian companion** (`obsidian-plugin/`) [R6/H2/KD2]: a thin, read-only,
  desktop plugin for retrieval-while-writing (Phase 2b) — debounced `search` /
  `build_context` against the tailnet MCP, with a "you may be reinventing [[X]]"
  warning. Read-only by construction (hard `callTool` allowlist + a static
  read-only test).

Deferred to Phase 3: the authenticated gateway (R4/KD4), full LLM
knowledge-graph extraction (#7), schema-as-data (#14), progressive activation (#15).

## Phase 2.5 (Plan 1) — engine convergence, git-first write tool, role-aware installer (U26–U34, plan 006; PRs #2/#3)

Plan 1 of 2. Makes the index converge automatically on the read path, gives
agents a git-first write tool over MCP, and ships a role-aware installer so the
master/client/single topology is deployable. The Obsidian companion redesign that
consumes the recency signal is **Plan 2** (plan 007, shipped — PR #5; see below).

- **U26 bounded embed budget + convergence tunables** [FR-R31]: `embed_stale`
  gains a `budget` cap so first-read latency is bounded; analytical callers pass
  `None` (unbounded). Progress is idempotent/resumable across reads.
- **U27 `converge()` primitive** (`converge.py`) [FR-R24..R35]: one shared
  read-path step — debounce check, host-aware staleness, `catch_up`, the bounded
  embed slice, a non-blocking indexer lock (skip if held — reads never stall on a
  writer), an oversized-delta guard (signals a manual reindex, never
  auto-reindexes), and graceful lexical-only degradation when the embedder is down.
- **U28 wire convergence into read entrypoints** [FR-R24/R41/R34]: every MCP read
  tool and CLI read converges first; adds the `retrieve` CLI command.
- **U29 per-Hit write-recency** (`retrieve.py`) [FR-R42]: each `Hit` carries
  `recency` — epoch seconds of the most recent commit touching its path
  (`git_commit_recency`), `None` when untracked. A **raw timestamp**, not a
  pre-decayed score; the consumer derives its own forgetting curve.
- **U30 full convergence for salience + connections** [FR-R39/R40]: the
  analytical surfaces force a complete convergence before scoring, so
  `note_vectors()` never runs on a half-embedded corpus; adds a
  `coverage_complete` flag.
- **U31 git-first `commit_note` MCP write tool** (`commit_note.py`,
  `mcp_server.py`) [DEP-R5/R6/R8]: the write tool over MCP, reusing the
  diff-or-die gate, protected-path guard, allowlist, and audit log unchanged.
  Registered as `WRITE_TOOL_NAMES = {commit_note}`, separate from
  `READ_TOOL_NAMES = {search, build_context, think}`, and exposed **only on a
  write-enabled master** — read-only clients never receive it.
- **U32 single-JSON serve** (`mcp_server.py`) [DEP-R15]: `build_server(…,
  json_response=True)` (default) returns one buffered JSON response (non-SSE), so
  Obsidian's `requestUrl` works without SSE.
- **U33 opt-in install-hooks + converge command** (`install.py`, `cli.py`)
  [FR-R36/R37/R38]: an idempotent managed-block post-merge hook that pre-warms
  convergence after a pull; plus the `converge` CLI command.
- **U34 role-aware installer** (`install.py`) [DEP-R1..R4/R9/R11]: `hypermnesic
  install --role={single|master|client}`. Master = systemd **or** Docker service
  + convergence hook + role config; client = config-only, emits/patches
  `mcpServers.hypermnesic = {type: streamable-http, url}` (no engine, no index);
  single = localhost. Tailnet membership is the MVP auth boundary; OAuth deferred.

**Review-fix follow-ups (PR #3):** index non-ASCII git paths + guard `git show`
failures (`converge.py`); batch write-recency into one `git log` pass
(`retrieve.py`, perf); `digest_proposal` forces full convergence before scoring
(`salience.py`); surface the convergence manual-reindex / degraded signal in the
read-tool responses (`mcp_server.py`); installer fails loud before provisioning +
hardened hook/client/strip (`install.py`); test fixtures use a CGNAT
documentation IP range instead of a real homelab Tailscale IP.

## Phase 2.5 (Plan 2) — Obsidian companion redesign (U35–U41, plan 007; PR #5)

Plan 2 of 2. Rebuilds the U25 single-file companion into a calm, modular,
strictly read-only recall surface that consumes the shipped engine contract
(per-`Hit` recency, the `think` read tool, the `manual_reindex_recommended`
signal, single-JSON serve). The plugin is now bundled with esbuild from
`main.ts` + `src/` (devDeps logged in the U1/Plan-2 dep table above); `obsidian`
and the CM6 packages are marked external. Built phase-by-phase:

- **U35 build scaffolding + lifecycle hygiene** (Phase A): `package.json`,
  `esbuild.config.mjs`, `tsconfig.json`, `.gitignore`, `styles.css`. Fixes the
  old `onunload` leaf-detach violation; registrations auto-clean.
- **U36/U37 shared retrieval core + forgetting-curve ranking** (Phase B):
  `src/core.ts` — one `RetrievalCore` behind the hard read-only allowlist
  `READ_ONLY_TOOLS = {search, build_context, think}`, with a capability probe
  (`hasThink`, `hitsCarryRecency`) so the plugin lights up or degrades against any
  engine version. `src/ranking.ts` — forgetting-curve ranking: relevance ×
  staleness from the engine `recency` (epoch seconds) with a local note-mtime
  fallback; `recencyHalfLifeDays` (30) and `stalenessWeight` (0.35) tunables.
- **U38–U40 calm surfaces + thinking-mode + reinvention nudge** (Phase C):
  `src/surfaces/{statusbar,gutter,render}.ts` — a calm-primary status-bar that
  expands to a popover, an opt-in sidebar (`openSidebarOnLoad` off), and an
  optional CM6 inline gutter marker (`showGutter` off by default, R-3).
  `src/thinking.ts` — thinking-mode (related notes + Socratic questions +
  tensions, visible `wrote: false` badge) and selection-recall. `src/nudge.ts` —
  an interrogable reinvention nudge that expands to the matched snippet + a
  one-hop context peek; per-note mute is view-only (plugin-local, never edits the
  note).
- **U41 trust / state machine, accessibility, settings, compliance** (Phase D):
  `src/state.ts` — one `RecallState` machine (idle / loading / results / stale /
  offline / degraded / reindex / error; a failed refresh after a prior success
  becomes "stale — as of HH:MM"). `src/settings.ts` — MCP URL **empty by default**
  (opt-in off-device send; placeholder `http://<tailscale-host>:8848/mcp`), pause
  interval, result count, reinvention threshold, per-surface toggles. Trust shown
  not asserted (read-only · tailnet · no-text-retained posture, allowlist
  surfaced); accessibility (`aria-live`, keyboard nav, never color-as-sole-signal);
  Obsidian compliance (no leaf-detach on unload, `registerEditorExtension`,
  sentence-case settings, safe DOM). The protocol-handler OAuth seam (PKCE) is
  left as a seam, not implemented.

Privacy: the default MCP URL is empty (`src/types.ts`), so a manual install
transmits nothing off-device until configured; a provisioned `--role=client`
install (Plan 1 U34) pre-fills the endpoint. The read-only guarantee stays
statically verified by `tests/test_obsidian_plugin.py`.
