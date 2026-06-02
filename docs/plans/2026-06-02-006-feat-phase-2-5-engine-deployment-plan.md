---
title: "feat: Phase 2.5 (Plan 1 of 2) — Engine convergence, git-first write tool, and the role-aware installer"
type: feat
status: completed
created: 2026-06-02
origin:
  - "docs/brainstorms/2026-06-02-phase-2-5-fresh-recall-requirements.md (engine half)"
  - "docs/brainstorms/2026-06-02-deployment-topology-write-model-requirements.md"
tags: [hypermnesic, phase2.5, convergence, mcp, write-path, installer, deployment]
---

# feat: Phase 2.5 (Plan 1 of 2) — Engine convergence, git-first write tool, and the role-aware installer

**Target repo:** `hypermnesic` (this repo, repo root). All `**Files:**` paths are repo-relative. This is **Plan 1 of 2** for Phase 2.5. The Obsidian companion redesign and its plugin-side Obsidian-compliance work are **Plan 2** and are out of scope here (the engine-side single-JSON response, R15, is in this plan because it is a `serve` change). Builds on the Phase-1 kernel (U1–U17) and the Phase-2 surface plan (U18–U25). New units continue from **U26**.

---

## Summary

Make the index converge automatically on the read path, give agents a git-first write tool over MCP, and ship a role-aware installer so the master/client/single topology is actually deployable. Reads (`search`/`build_context`/`think` + CLI) first catch the index up to `HEAD` and close a bounded slice of the dense lag before serving; agents write through a gated `commit_note` MCP tool that commits to git on the master (single write target, index stays a rebuildable projection); and `hypermnesic install --role={single|master|client}` provisions each role end-to-end (systemd **or** Docker for the always-on master, MCP-client config for the client, localhost for single). Convergence never triggers a full reindex, degrades to lexical when embeddings are down, and the write tool reuses the existing gate/guard/audit under the MVP tailnet auth boundary.

---

## Problem Frame

The kernel made the index a disposable projection of the git tree and the write path a single `commit_note` primitive, but three gaps block the Phase-2.5 "fresh recall" experience:

- **Nothing re-captures modifications automatically.** `embed_stale` exists but is only invoked by `hypermnesic embed`; there is no file-watcher, hook, or scheduler (verified absent). Dense vectors lag every write until a manual pass, and `Index.note_vectors()` (behind salience/connections) silently computes on a half-embedded corpus.
- **Agents have no write path that preserves the single-write-target thesis.** The operator wants gbrain-like "just call a tool" ergonomics. The only safe form is git-first (`commit_note` over MCP) — a DB-first write would break the index-as-projection invariant (a `reindex` would delete un-materialized writes) and re-import gbrain's reconcile-cron pain.
- **The split deployment (Mac client, homelab master) is unspecified and uninstallable.** There is no role model and no way to stand up an always-on master service; `serve` exists but nothing provisions it.

This plan closes all three on the engine side. The human-facing companion that consumes the recency signal and the freshness it produces is Plan 2.

---

## Requirements

Traced to the two origin docs. The engine half of the fresh-recall doc (its R24–R42) and the deployment doc (its R1–R15) land here; the companion surfaces (fresh-recall R1–R23) and plugin-side compliance (deployment R16–R20) are Plan 2.

| ID (origin) | Requirement | Advanced by |
|---|---|---|
| FR-R24/R25/R26 | Reads converge first: catch_up + bounded embed, debounced | U27, U28 |
| FR-R27 | Convergence takes the indexer lock non-blocking; skip if held | U27 |
| FR-R29/R30 | Host-aware: replica HEAD-vs-checkpoint; authoring-host overlay refresh | U27 |
| FR-R31 | Bounded embed budget per convergence | U26, U27 |
| FR-R32 | Never auto-trigger `reindex_isolated` | U27 |
| FR-R33 | Oversized-delta guard (signal manual reindex) | U27 |
| FR-R34 | Graceful dense degradation (lexical-only when embedder down) | U27, U28 |
| FR-R35 | Convergence on a serve host writes only the `.hypermnesic/` projection | U27 |
| FR-R36/R37/R38 | Opt-in `install-hooks` post-merge accelerator | U33 |
| FR-R39/R40 | Salience/connections force full convergence; coverage flag | U30 |
| FR-R41 | Plugin reads are served by convergence (engine side) | U28 |
| FR-R42 | Per-result recency field on `Hit` (engine produces) | U29 |
| FR-R28 | Write path stays lexical-only inline (`commit_note` unchanged) | U31 (reuses) |
| DEP-R1–R4 | single/master/client roles; client = config; one installer | U34 |
| DEP-R5/R6/R8 | Git-first gated `commit_note` MCP write tool; reuse gate/guard/audit; withheld from read-only clients | U31 |
| DEP-R7 | Agent writes converge instantly on the master | U31, U28 |
| DEP-R9/R10/R11 | Tailnet auth MVP; write tool a distinct capability; OAuth deferred | U31, U34 |
| DEP-R15 | `serve` returns single-JSON (non-SSE) for `requestUrl` clients | U32 |

---

## Key Technical Decisions

- KTD1 — Convergence is one shared `converge(repo, idx, embedder)` step, not per-entrypoint logic. Every read path calls it; it encapsulates the debounce check, host-aware staleness, `catch_up`, the bounded embed slice, the non-blocking lock, and the oversized-delta guard. Rationale: a single chokepoint keeps the read entrypoints (MCP tools + CLI) thin and guarantees identical freshness semantics everywhere. (see origin: fresh-recall KD8)

- KTD2 — Reuse the non-blocking `FileLock` default; treat `LockBusyError` as "skip convergence, serve current state." `serialize.FileLock.acquire()` already defaults to non-blocking. Convergence catches `LockBusyError` and serves the current index rather than waiting — a concurrent writer or converger is already advancing it. Rationale: reads must never stall on a write. (see origin: fresh-recall R27)

- KTD3 — `embed_stale` gains a `budget` parameter; convergence passes the configured budget, analytical callers pass `None` (unbounded). Today `embed_stale` embeds all stale chunks. A `budget` cap bounds first-read latency; idempotent/resumable progress accumulates across reads. Salience/connections pass no budget so `note_vectors()` sees a complete corpus. Rationale: one primitive serves both bounded interactive reads and full analytical convergence. (see origin: fresh-recall R31, R39)

- KTD4 — The write tool is `commit_note` exposed over MCP, registered as a distinct capability withheld from read-only clients. It reuses `commit_note`'s gate (diff-or-die), write guard / protected-path refusal, explicit path allowlist, and audit log unchanged. It is registered separately from `READ_TOOL_NAMES` so the read-only companion never receives it; whether a given `serve` exposes it is role/flag-gated. Rationale: git-first single write target; no new write machinery; read-only clients stay structurally read-only. (see origin: deployment KD2, KD3, R5–R8)

- KTD5 — MVP auth is tailnet membership for read and write alike; the write tool is a separable capability so future OAuth can gate it per-identity. No per-request auth ships now (accepted risk on a single-operator tailnet); the full write-surface threat model is deferred to the OAuth work. (see origin: deployment KD4, KD5, R9–R11)

- KTD6 — The installer is a role-aware CLI subcommand that provisions per platform; the master service is systemd **or** Docker. `hypermnesic install --role={single|master|client}` follows the existing argparse `_cmd_*` + `--json` pattern. For master it generates and enables a service (a portable systemd unit template, or a Docker container/compose), installs the convergence hook, and records role config; for client it emits/patches the MCP-client config (no engine); single targets localhost. Universal packaging (Homebrew/.deb/Windows) is deferred. Rationale: the master is meaningless without service provisioning, and hand-rolled systemd/env setup is error-prone toil. (see origin: deployment R1–R4; this plan's confirmed installer scope)

- KTD7 — Per-result recency is write-recency derived from git/commit metadata, surfaced as a new `Hit` field. The engine produces it now (Plan 2's companion consumes it for forgetting-curve ranking). The audit log / git commit time is the source; access-recency is out of scope (no read-access logging). (see origin: fresh-recall R42)

---

## High-Level Technical Design

The shared convergence step on the read path, and the git-first write path, both landing in the same projection:

```mermaid
flowchart TB
  subgraph reads[Read entrypoints]
    MCP_R[MCP: search / build_context / think]
    CLI_R[CLI: think / retrieve]
  end
  MCP_R --> CONV
  CLI_R --> CONV
  subgraph conv[converge - one shared step]
    CONV{debounced?} -->|recent| SERVE[serve current]
    CONV -->|due| LOCK{lock non-blocking}
    LOCK -->|busy| SERVE
    LOCK -->|held| HOST[authoring host: overlay refresh on mtime]
    HOST --> CP{HEAD == checkpoint?}
    CP -->|no, within cap| CATCH[catch_up delta-replay]
    CP -->|no, oversized| SIG[signal manual reindex]
    CP -->|yes| EMB[bounded embed_stale]
    CATCH --> EMB --> SERVE
  end
  subgraph write[Agent write path]
    WT[MCP commit_note write tool] --> GATE[gate / guard / allowlist / audit] --> GIT[(git commit on master)]
    GIT --> IDX[(index = projection)]
  end
  CATCH -.-> IDX
  EMB -.-> IDX
  SAL[salience / connections] --> FULL[embed_stale budget=None - full] --> IDX

  ANALYTIC[install --role: master=systemd|docker + hook; client=MCP config; single=localhost]
```

Prose is authoritative where it and the diagram disagree.

---

## Implementation Units

Execution posture is **test-first** throughout — the repo convention (kernel units shipped failing-test-first against temp repos via the `make_corpus` + `fake_embedder` fixtures). Grouped Phase A (convergence) and Phase B (write path + deployment).

### Phase A — Read-time convergence

### U26. Bounded `embed_stale` + convergence tunables

- **Goal:** Add a `budget` cap to `embed_stale` and introduce the convergence tunables (embed budget, debounce window, oversized-delta cap) as config constants.
- **Requirements:** FR-R31 (bounded budget), supports FR-R33/R39.
- **Dependencies:** none.
- **Files:** `src/hypermnesic/index.py` (`embed_stale` signature), `src/hypermnesic/config.py` (constants), `tests/test_index.py`.
- **Approach:** Add `budget: int | None = None` to `embed_stale`; when set, embed at most `budget` stale chunks (and a proportional share of missing doc-surface vectors), leaving the rest for the next call; `None` preserves today's embed-all behavior. Add `config.py` module constants in the existing `EMBED_*` style: `CONVERGE_EMBED_BUDGET`, `CONVERGE_DEBOUNCE_SECONDS`, `CONVERGE_MAX_DELTA_FILES`. Keep idempotence (re-running with the same state embeds 0).
- **Patterns to follow:** `embed_stale` batching at `index.py`; constants at `config.py:18-19`.
- **Test scenarios:**
  - With 300 stale chunks and `budget=128`, one call embeds 128, leaves 172; the next call embeds the next slice; running to exhaustion embeds all 300 with no duplicates.
  - `budget=None` embeds all stale chunks in one pass (unchanged behavior).
  - Idempotent: a second call on a fully-embedded corpus embeds 0 chunks, 0 docs.
  - Empty/clean index → 0 embedded, no error.
- **Verification:** `uv run pytest tests/test_index.py` green; budgeted and unbudgeted paths both covered.

### U27. The `converge()` primitive

- **Goal:** One shared function that brings the index up to `HEAD` (host-aware) and closes a bounded dense slice, lock-safe and never full-reindexing.
- **Requirements:** FR-R24, R25, R26, R27, R29, R30, R32, R33, R34, R35.
- **Dependencies:** U26.
- **Files:** `src/hypermnesic/converge.py` (new), `tests/test_converge.py` (new); reads `src/hypermnesic/index.py` (`catch_up`, `apply_working_tree_overlay`, `get_checkpoint`), `src/hypermnesic/serialize.py` (`FileLock`).
- **Approach:** `converge(repo, idx, embedder, *, role/host signal)` →
  1. Debounce: if converged within `CONVERGE_DEBOUNCE_SECONDS` (tracked via a timestamp in the state dir), return early.
  2. Acquire the single-indexer `FileLock` non-blocking; on `LockBusyError`, return (serve current) — KTD2.
  3. Authoring host only: if tracked/untracked markdown mtimes advanced, re-apply `apply_working_tree_overlay` (lexical only; no checkpoint advance) — FR-R29.
  4. If `HEAD != checkpoint`: if the delta exceeds `CONVERGE_MAX_DELTA_FILES`, do lexical catch-up up to the cap and return a "manual reindex recommended" signal (FR-R33); else `catch_up` delta-replay.
  5. Run `embed_stale(budget=CONVERGE_EMBED_BUDGET)`; on embedder failure, complete lexical/graph catch-up, advance the checkpoint, and return degraded (FR-R34).
  6. Never call `reindex_isolated` (FR-R32). Writes touch only `.hypermnesic/` (FR-R35).
- **Execution note:** test-first; the lock-skip, oversized-delta, and degraded paths are the spec.
- **Patterns to follow:** `catch_up` (lock acquisition, delta-replay return shape), `reindex_isolated` (what NOT to call here).
- **Test scenarios:**
  - HEAD == checkpoint, recently converged → debounce returns early (no lock taken, no embed).
  - HEAD advanced by 3 committed files → catch_up replays them (lexical fresh), then a bounded embed runs; checkpoint advances to HEAD.
  - Lock held by another holder → `converge` returns without waiting; index left as-is.
  - Delta exceeds `CONVERGE_MAX_DELTA_FILES` → no unbounded inline replay; returns the manual-reindex signal.
  - Embedder raises → lexical/graph catch-up still completes, checkpoint advances, result flagged degraded; no zero-vectors written.
  - Authoring-host role with an advanced-mtime uncommitted file → overlay re-applied (findable lexically), checkpoint NOT advanced.
  - `reindex_isolated` is never invoked (assert via monkeypatch/spy).
- **Verification:** `pytest tests/test_converge.py` green across all paths.

### U28. Wire `converge()` into read entrypoints

- **Goal:** Every read converges before serving — MCP `search`/`build_context`/`think`, CLI `think`, and a new CLI `retrieve`.
- **Requirements:** FR-R24, R41 (engine side), R34.
- **Dependencies:** U27.
- **Files:** `src/hypermnesic/mcp_server.py` (`_Backend` gains the repo path; each tool calls `converge` first), `src/hypermnesic/cli.py` (`think` converges; new `_cmd_retrieve` + parser), `tests/test_mcp_server.py`, `tests/test_cli.py`.
- **Approach:** Add the repo path to `_Backend` (today it stores only `index_db`) so `converge` can run. Call `converge` at the top of each of the three MCP tool bodies (or a shared helper they all call). CLI `think` runs `converge` before retrieval; add a `retrieve` subcommand mirroring `think`'s db/embedder construction (try/except embedder → degrade to lexical). Degraded convergence surfaces through the existing `degraded_lexical_only` field.
- **Patterns to follow:** `_Backend.idx` lazy property at `mcp_server.py`; the `think` command's embedder try/except in `cli.py`; argparse `_cmd_*` + `set_defaults`.
- **Test scenarios:**
  - Covers FR-R41. After N committed files, the first MCP `search` returns post-catch-up results; a second immediate search is debounced (no re-converge).
  - CLI `retrieve` returns the same hit shape as `search`; `--json` output well-formed.
  - Embedder absent → reads return lexical-only with `degraded_lexical_only: true`; never error.
  - `build_context` and `think` also converge (assert convergence ran on each tool path).
- **Verification:** `pytest tests/test_mcp_server.py tests/test_cli.py` green; `hypermnesic retrieve` works against a temp repo.

### U29. Per-`Hit` recency field

- **Goal:** Add a write-recency field to `Hit`, populated from commit/audit metadata and surfaced in the MCP serializer, for Plan 2's forgetting-curve ranking.
- **Requirements:** FR-R42.
- **Dependencies:** none (parallelizable with U27).
- **Files:** `src/hypermnesic/retrieve.py` (`Hit` dataclass + construction), `src/hypermnesic/mcp_server.py` (serializer dict), `tests/test_retrieve.py`.
- **Approach:** Add an optional recency field (e.g. a timestamp or epoch) to the `Hit` dataclass; populate it from the per-path write-recency the engine already knows (git commit time / audit log), defaulting to `None` when unavailable. Surface it in the `search` response serializer alongside `path/heading/score/channels/snippet`. Engine-only; no ranking change in this plan.
- **Patterns to follow:** `Hit` dataclass and the MCP serializer dict in `mcp_server.py`.
- **Test scenarios:**
  - A hit for a recently-committed note carries a more-recent recency value than one for an older note.
  - Recency is `None`/absent-safe when the source has no commit metadata; serializer still emits a well-formed result.
  - The field appears in the MCP `search` response payload.
- **Verification:** `pytest tests/test_retrieve.py` green; recency present and ordered sanely.

### U30. Force full convergence for salience + connections

- **Goal:** Salience (U21) and connections (U22) run a full (unbudgeted) convergence before reading `note_vectors()`, and report coverage completeness.
- **Requirements:** FR-R39, R40.
- **Dependencies:** U26 (unbudgeted embed), U27 (converge) — analytical callers pass `budget=None`.
- **Files:** `src/hypermnesic/salience.py`, `src/hypermnesic/connect.py`, `tests/test_salience.py`, `tests/test_connect.py`.
- **Approach:** At the top of `salience.score_notes` and `connect.connection_proposals`/`candidate_pairs`, run a full `embed_stale(budget=None)` (or `converge` with no budget) so `note_vectors()` sees every chunk; then compute. Return/attach a `coverage_complete: bool` so a caller can tell a complete result from a partial one (e.g., embedder unavailable → partial).
- **Execution note:** test-first; the "computes on a complete corpus" guarantee is the spec.
- **Patterns to follow:** existing `idx.note_vectors()` calls in `salience.py` / `connect.py`.
- **Test scenarios:**
  - Covers FR-R39. Given unembedded chunks, calling salience first embeds them fully, then scores; `note_vectors()` returns all paths.
  - Covers FR-R40. With the embedder unavailable mid-fill, the result is flagged `coverage_complete: false`.
  - Connections: a similar-and-unlinked pair is found only after full convergence (not missed due to an unembedded chunk).
  - Determinism preserved for fixed, fully-embedded input.
- **Verification:** `pytest tests/test_salience.py tests/test_connect.py` green.

### Phase B — Write path & deployment

### U31. Git-first gated `commit_note` MCP write tool

- **Goal:** Expose `commit_note` as a gated MCP write tool on the master, distinct from the read tools and withheld from read-only clients.
- **Requirements:** DEP-R5, R6, R8, R7, R9, R10; FR-R28 (reuses inline-lexical write).
- **Dependencies:** U28 (so the write's dense lag closes on the next read-converge).
- **Files:** `src/hypermnesic/mcp_server.py` (register the write tool; role/flag gate), `tests/test_mcp_server.py`.
- **Approach:** Register a `commit_note` MCP tool whose body calls `commit_note.commit_note(...)` with an explicit path allowlist — reusing the gate, write guard, protected-path refusal, and audit log unchanged. Register it OUTSIDE `READ_TOOL_NAMES` and only when the server is started in a write-enabled role (master), so a read-only `serve` (or a read-only client) never sees it. The tool returns the commit result/diff; the agent never merges. Tailnet membership is the only auth (MVP). The index updates via `commit_note`'s existing inline `upsert_lexical`; dense closes on the next read-convergence (U28).
- **Execution note:** test-first; "withheld from read-only clients" and "every write passes the gate" are the spec.
- **Patterns to follow:** `commit_note.commit_note` (gate→commit→audit→diff), the `@mcp.tool` registration + `READ_TOOL_NAMES` in `mcp_server.py`, `test_mcp_server.py`'s tool-set assertions.
- **Test scenarios:**
  - A write-enabled server lists `commit_note` as a tool; a read-only server does NOT (tool set excludes it).
  - A write through the tool commits exactly the intended path and records an audit entry (server-set actor, summary only); HEAD advances by one commit.
  - A write whose diff would touch an unrequested frontmatter line aborts via the gate (no commit, no audit) — diff-or-die holds over MCP.
  - A protected path is refused before any commit.
  - A path outside the declared allowlist is rejected.
  - The new content is densely recall-able after the next read-convergence; a `reindex` does not lose it (git holds it).
- **Verification:** `pytest tests/test_mcp_server.py` green; read-only vs write-enabled tool sets differ exactly by the write tool.

### U32. `serve` single-JSON (non-SSE) response for `requestUrl` clients

- **Goal:** Ensure the `serve` MCP response path returns a buffered single JSON body so Obsidian `requestUrl` clients (Plan 2) work without SSE hangs.
- **Requirements:** DEP-R15 (engine side).
- **Dependencies:** none.
- **Files:** `src/hypermnesic/mcp_server.py` (response/transport configuration), `tests/test_mcp_server.py`.
- **Approach:** Confirm/configure the FastMCP streamable-http path to return a single JSON response for `tools/call` rather than an SSE stream on the client request path the plugin uses, since `requestUrl` buffers and does not stream. If FastMCP defaults to SSE, set the response mode (or document the client `Accept` handling) so a single JSON body is returned.
- **Patterns to follow:** `build_server`/`FastMCP(...)` configuration in `mcp_server.py`.
- **Test scenarios:**
  - A `tools/call` request returns a single JSON body (asserted shape), not a chunked SSE stream, on the client path.
  - Existing MCP tests still pass (read tools unaffected).
- **Verification:** `pytest tests/test_mcp_server.py` green; a buffered-client request parses as one JSON object.
- **Note:** If research at implementation time shows FastMCP already returns single-JSON for non-streaming clients, this unit reduces to a regression test asserting it. Confirm against the installed `mcp` SDK version before building.

### U33. Opt-in `hypermnesic install-hooks` command

- **Goal:** An explicit, idempotent, non-destructive command that installs a git `post-merge` hook running convergence, pre-warming the index after a pull.
- **Requirements:** FR-R36, R37, R38.
- **Dependencies:** U27 (the hook calls `converge`).
- **Files:** `src/hypermnesic/cli.py` (`_cmd_install_hooks` + parser; uninstall path), a hook script template (e.g. `src/hypermnesic/hooks/post-merge` or generated), `tests/test_cli.py`.
- **Approach:** `hypermnesic install-hooks <repo>` writes a `post-merge` (and related) hook into `.git/hooks/` that invokes convergence; idempotent (re-run safe), non-destructive (preserves existing hook content by appending a managed block), with an uninstall path. The write guard already anticipates an `install-git-hooks` file class (`serialize.py` protected-reason). Lazy read-convergence remains the correctness guarantee; the hook only pre-warms (FR-R38).
- **Patterns to follow:** argparse `_cmd_*` pattern; the gbrain-brain `install-git-hooks.sh` managed-block idempotence model.
- **Test scenarios:**
  - Fresh repo → hook installed; re-run → idempotent (no duplicate block).
  - Pre-existing hook content is preserved (managed block appended, not overwritten).
  - Uninstall removes only the managed block.
  - With the hook installed, a simulated `post-merge` invokes convergence (assert converge called).
- **Verification:** `pytest tests/test_cli.py` green; hook install/uninstall idempotent against a temp repo.

### U34. `hypermnesic install --role={single|master|client}` — role-aware installer

- **Goal:** One command that provisions a host into a role end-to-end: master as an always-on service (systemd **or** Docker) + hook, client as MCP-client configuration (no engine), single as localhost.
- **Requirements:** DEP-R1, R2, R3, R4; DEP-R11/R9 (role records write-enablement + tailnet bind).
- **Dependencies:** U27, U28 (convergence to provision), U31, U32 (the write-enabled serve), U33 (hook install reused for master).
- **Files:** `src/hypermnesic/cli.py` (`_cmd_install` + parser), `src/hypermnesic/install.py` (new — role provisioning logic + template rendering), service templates (`src/hypermnesic/templates/hypermnesic.service` systemd unit, `src/hypermnesic/templates/Dockerfile` / `compose.yaml`), an MCP-client-config emitter, `tests/test_install.py` (new).
- **Approach:** `hypermnesic install --role=<role> [--bind=<tailnet-ip>] [--service=systemd|docker]` →
  - **master:** verify package/env (`OPENAI_API_KEY`), `init` the index, write `.hypermnesic/config` (role=master, bind addr, write-enabled), render + enable the service (systemd unit by default on Linux, or a Docker container/compose when `--service=docker`), and install the convergence hook (U33). Serve exposes read + write tools.
  - **client:** no engine; emit or patch the MCP-client config (the companion's settings hint and/or the Claude/Codex MCP server entry) to point at the master endpoint; write `.hypermnesic/config` (role=client) if useful.
  - **single:** master provisioning bound to localhost, no remote exposure; the local plugin/agent points at localhost.
  - Ship portable templates; keep secret handling in the env/gitignored-`.env` discipline (never logged). Defer universal packaging (Homebrew/.deb/Windows).
- **Execution note:** test the role-routing + template rendering + config-emission logic offline; actual systemd `enable`/Docker `run` and live service start are manual verification (integration), not pytest.
- **Patterns to follow:** the existing `init` command and `state_dir_for`; the `serve` bind/tailnet logic in `mcp_server.py`; argparse `_cmd_*`.
- **Test scenarios:**
  - `--role=master --service=systemd` renders a valid unit referencing `hypermnesic serve` with the bind addr and an env reference for the key; writes role=master config; marks write-enabled.
  - `--role=master --service=docker` renders a valid Dockerfile/compose exposing the bind and serve; no systemd unit written.
  - `--role=client` writes NO service unit and NO index; emits an MCP-client config entry pointing at the given master endpoint.
  - `--role=single` binds to localhost and does not expose a remote address.
  - Missing `OPENAI_API_KEY` for an engine role → install fails loud with a clear message (no half-provisioned state).
  - Re-running install is idempotent for config + hook.
  - `Test expectation: provisioning side-effects (systemctl enable / docker run) are manual-verification` — the unit tests assert generated artifacts and routing, not live service start.
- **Verification:** `pytest tests/test_install.py` green (routing + rendered artifacts); a manual master install on the homelab brings up an always-on serve reachable over the tailnet; a manual client install points the companion at it.

---

## Risks & Dependencies

- **R-1 Read-path latency from convergence.** A read that triggers catch-up + an embed batch is slower than a pure read. Mitigation: the debounce (KTD1) limits frequency; the bounded budget (KTD3) caps per-read embed cost; degraded mode (FR-R34) never blocks on the network.
- **R-2 Lock contention skips convergence indefinitely.** If a writer perpetually holds the lock, reads always serve stale. Mitigation: writes are short (single `commit_note`); the next idle read converges. Acceptable for the single-operator workload.
- **R-3 Write tool widens the attack surface over the tailnet.** Any tailnet peer can call `commit_note` in the MVP. Mitigation: accepted risk (KTD5); the write tool is a separable capability and the full threat model lands with OAuth (deferred). The gate/guard/allowlist still bound *what* a write can touch.
- **R-4 FastMCP response-mode assumption (U32).** The single-JSON-vs-SSE behavior depends on the `mcp` SDK version. Mitigation: U32 confirms against the installed version before building; may reduce to a regression test.
- **R-5 Installer provisioning is host-specific and hard to unit-test.** systemd/Docker live behavior is integration territory. Mitigation: unit-test the rendering/routing/config logic; mark live provisioning as manual verification; ship portable templates.
- **Dependency:** the master's git pull cadence (getting the Mac's pushed commits onto the master) is the operator's existing Mac↔origin↔homelab git sync — external to this plan; the `post-merge` hook (U33) converges on each pull.
- **Dependency:** `OPENAI_API_KEY` via env/gitignored `.env` (unchanged); the permissive-license gate (`scripts/license_scan.py`) still applies to any new dependency.

---

## Scope Boundaries

### Deferred to Plan 2 (the companion)

- The Obsidian companion redesign surfaces (build scaffolding, shared retrieval core, calm surfaces, thinking-mode, reinvention nudge, trust/state layer) and the plugin-side Obsidian-compliance fixes (deployment R16–R20: README network/account disclosure, default-empty MCP URL, no leaf-detach on unload, native protocol-handler OAuth). The companion consumes the recency field (U29) and the freshness (U27/U28) this plan produces.

### Deferred to follow-up work

- Universal packaging: Homebrew tap, `.deb`, Windows support. This plan ships portable systemd/Docker templates for the operator's macOS-client + Linux-homelab reality only.
- MCP OAuth + mobile-AI-app reach + per-identity auth + the full write-surface threat model (re-anchored to the OAuth work).

### Outside this product's identity

- DB-first / index-direct writes — the write tool is git-first or it does not exist (would break index-as-projection and re-import gbrain's reconcile pain).
- Auto-triggered full reindex — stays gated/manual (OOM scar); convergence must never invoke `reindex_isolated`.
- A bespoke SSH transport — dissolved; tailnet MCP serves reads + writes, OAuth carries future reach.

---

## Open Questions / Deferred to Implementation

- Default values for `CONVERGE_EMBED_BUDGET`, `CONVERGE_DEBOUNCE_SECONDS`, `CONVERGE_MAX_DELTA_FILES` — pick sensible starting values (a budget near one embedding batch keeps first-read latency to ~one API round-trip) and tune.
- Oversized-delta behavior beyond the cap — signal-only vs lexical-up-to-cap-then-signal; settle when wiring U27.
- Write-tool exposure mechanism — a server start flag (`serve --enable-write`) vs role-config-derived; settle at U31/U34.
- Exact `Hit` recency representation (timestamp vs decayed score) and its derivation (commit time vs audit log) — settle at U29.
- Lock-hold granularity during the bounded embed (hold the whole slice vs release between sub-batches) — settle at U27.
- The MCP-client-config format the installer emits for `client` (companion settings hint vs Claude/Codex MCP entry vs both) — settle at U34.

---

## Sources / Research

- Origin docs: `docs/brainstorms/2026-06-02-phase-2-5-fresh-recall-requirements.md` (engine half: convergence R24–R42), `docs/brainstorms/2026-06-02-deployment-topology-write-model-requirements.md` (roles, write model, auth, R15).
- Engine map (ce-repo-research-analyst, 2026-06-02): `src/hypermnesic/mcp_server.py` (`@mcp.tool` registration, `READ_TOOL_NAMES`, `_Backend` lazy idx storing only `index_db`), `src/hypermnesic/retrieve.py` (`Hit` = chunk_id/path/heading/text/score/channels; `SearchResult.degraded`), `src/hypermnesic/think.py` (pure retrieve+graph; no note_vectors — so convergence on `think` is bounded, not analytical), `src/hypermnesic/index.py` (`catch_up`, `embed_stale` embeds-all today, `reindex_isolated`, `apply_working_tree_overlay`, `note_vectors`, checkpoint), `src/hypermnesic/serialize.py` (`FileLock.acquire(blocking=False)` non-blocking default; `install-git-hooks` protected-reason), `src/hypermnesic/cli.py` (argparse `_cmd_*` + `--json`; no `retrieve`/`install`/`install-hooks` today), `src/hypermnesic/salience.py` / `connect.py` (call `note_vectors()` with no forced embed), `src/hypermnesic/config.py` (module-constant convention).
- Conventions: `implementation-notes.md` (TDD against temp repos; argparse + `--json`; permissive-license gate); `tests/conftest.py` (`make_corpus` git-init fixture + `fake_embedder`); U-IDs tracked as prose headers, highest existing U25.
- Kernel framing: R10 (index = git-tree projection), R13 (multi-writer serialization), R16 (authoring-host overlay vs replica projection), KTD9 (full-reindex OOM scar); `docs/solutions/design-patterns/surgical-scalar-set-frontmatter-byte-preservation.md` (the write path's byte-preservation contract the gate enforces).
