---
date: 2026-06-03
topic: vault-structure-discovery-and-blocklist-write-model
title: "Hypermnesic — Vault-Structure Discovery for Agent Note Placement + Blocklist Write Model"
type: feat
tags: [hypermnesic, mcp, read-tools, write-guard, blocklist, security, agent-placement]
origin:
  - "operator brainstorm 2026-06-03 (agents must guess a path when committing a note; widen the writable surface)"
related_to:
  - "docs/brainstorms/2026-06-03-unified-oauth-endpoint-and-setup-requirements.md (the unified OAuth endpoint these tools are served on; KD5 write-anywhere)"
  - "docs/2026-06-03-unified-write-anywhere-security-review.md (the G3 sign-off this effort's write-flip must amend)"
  - "docs/threat-model-commit-note.md (V1 protected-path guard; the allowlist-vs-blocklist posture)"
---

# Hypermnesic — Vault-Structure Discovery for Agent Note Placement + Blocklist Write Model

## Summary

Add a read-scoped MCP/CLI tool that lets an agent walk the vault's **content-folder taxonomy**
(drill down by root, optional bounded depth) and see, per folder, whether it is **writable** and
how many notes it holds — so agents place notes where they belong instead of guessing a path.
Coupled with it: flip `commit_note`'s writable surface from the 4-prefix `DEFAULT_WRITE_ALLOWLIST`
to a **blocklist** (everything under the content surface except the protected classes), so the
folders the tool surfaces — `projects/`, `people/`, `companies/`, `meetings/` — are actually
writable. The write-model flip ships behind a fresh, operator-signed security-review delta.

---

## Problem Frame

The one sanctioned write path, `commit_note(path, …)`, takes a **caller-supplied** repo-relative
path and only *validates* it (`src/hypermnesic/serialize.py::check`: within-repo + protected-path
guard + write allowlist). It never infers or suggests a location. The read tools today
(`search`, `build_context`, `think`, `resolve`) help an agent find *content*, but none of them
exposes the vault's **folder taxonomy** or which locations are **writable**. So an agent that wants
to commit a note has to guess a path — and notes land inconsistently.

Two things make the guess worse than a cosmetic nuisance:

1. **The agent is blind to the taxonomy.** The engine already knows the full set of paths
   (`index.Index.all_paths()`, consumed today by `src/hypermnesic/nav_surface.py` and
   `src/hypermnesic/salience.py`) — but there is no tool that lets an agent read it. It cannot see
   that `projects/`, `people/`, `companies/`, and `meetings/` are where the operator's real vault
   keeps things.

2. **The current writable surface is too narrow for that taxonomy.** On the unified cloud endpoint,
   `build_cloud_server` defaults the write allowlist to the 4-prefix `DEFAULT_WRITE_ALLOWLIST`
   (`notes/`, `sources/`, `dashboards/`, `captures/`). A write to `projects/acme/note.md` is
   **refused today** — it is not in the allowlist. So even an agent that guesses the *right*
   conceptual home gets a hard refusal, because the operator's actual content folders were never
   in the list.

The cost is a guess-and-refuse loop, inconsistent placement, and a vault whose real structure is
invisible to the agents meant to maintain it. The operator's intent: let agents discover the vault
structure and writable locations, and make the writable surface match the vault the agent actually
sees.

---

## Actors

- A1. **Writing agent** (Claude / Codex via the unified MCP endpoint, `write` scope): discovers the
  taxonomy, picks a writable folder, then commits a note there via `commit_note`.
- A2. **Read-only cloud connector** (ChatGPT / Claude mobile, `read` scope): can call discovery and
  read the content taxonomy; the writable flags are advisory for it (it holds no write tool).
- A3. **Operator** (Leonard): approves each client at the consent gate, and **signs the
  security-review delta** that gates the write-model flip into production.
- A4. **The engine**: derives the taxonomy from the committed-HEAD index, classifies writability via
  the existing write guard, and enforces `commit_note`'s guards unchanged.

---

## Key Flows

- F1. **Discover-then-place.** **Trigger:** an agent is about to write a note. It calls discovery at
  the root (depth 1), drills into a candidate subtree, reads each folder's `writable` flag and note
  count, picks an existing writable folder (or branches a new child under one), then calls
  `commit_note` with that path. **Outcome:** the note lands in a consistent, writable home on the
  first try. **Covers R1, R2, R3, R7, R10.**

- F2. **Bounded descent on a large subtree.** **Trigger:** discovery at `projects/` would exceed the
  node cap. **Steps:** the tool returns a bounded, sorted page with a `truncated` signal; the agent
  narrows `root` to drill further. **Outcome:** a deep vault is navigable without an unbounded
  payload. **Covers R4.**

- F3. **See-but-avoid a protected folder.** **Trigger:** discovery returns `skills/` (which holds
  indexed notes) marked non-writable with a reason. **Outcome:** the agent sees it and does not
  choose it, rather than the folder being silently hidden. **Covers R8, R9.**

- F4. **Write-model sign-off gate.** **Trigger:** the blocklist flip is implemented. **Steps:** the
  operator reviews the security-review delta (R-1 blast radius widened from the 4 note zones to the
  whole content surface), re-validates the controls, and signs off. **Outcome:** the flip is enabled
  in production only after sign-off. **Covers R10, R14.**

- F5. **Re-narrowed install (escape hatch).** **Trigger:** an operator runs with
  `--allowlist captures/`. **Outcome:** discovery's `writable` flags show only `captures/` as
  writable and `commit_note` refuses elsewhere — discovery and the guard agree. **Covers R7, R12.**

---

## Requirements

**Discovery tool — read surface**

- R1. A new read-scoped MCP tool (working name `list_folders`) is registered in `READ_TOOL_NAMES`,
  available to every read-scoped client on the unified endpoint, and mirrored on the `hypermnesic`
  CLI (CLI-for-engine-host-local / MCP-for-remote parity). It converges to HEAD before serving and
  carries `manual_reindex_recommended`, like every other read tool.
- R2. It takes a `root` (repo-relative folder prefix; empty = vault root) and an optional `depth`
  (default 1), and returns the child folders under `root` to `depth` levels. `depth=1` is the
  drill-down loop; `depth>1` returns a bounded sub-tree in one call.
- R3. Each returned folder entry carries: its repo-relative path, a `writable` boolean, a protected
  reason (a string when not writable, else null), and a note count. *(Field names illustrative —
  finalized in planning.)*
- R4. Output is bounded: a maximum node/child cap per call plus a `truncated` signal (and a count of
  omitted entries) so a large subtree (e.g. `projects/`) never returns an unbounded payload. Order
  is deterministic (sorted) for reproducibility.
- R5. The taxonomy is derived from the committed-HEAD index (`index.Index.all_paths()`), so it
  reflects the same source of truth as the other read tools and is **structurally limited to folders
  containing indexed markdown** — the dirs the index already excludes (`.git`, `.obsidian`,
  `.hypermnesic`, `node_modules`, `__pycache__`, and everything non-`.md`, per `ingest._SKIP_DIRS`)
  can never appear.
- R6. The tool advertises a typed MCP `outputSchema` (a `TypedDict` mirroring the existing tool
  outputs in `src/hypermnesic/mcp_server.py`) so connectors understand the result structure.

**Writable awareness — discovery ↔ write parity**

- R7. The `writable` flag is computed from the install's **effective** write configuration, so
  discovery never advertises a folder `commit_note` would refuse, and never hides a writable one.
  Under the blocklist default, writable = `serialize.protected_reason(path) is None`; under a
  narrowed `--allowlist`, writable = within that allowlist **and** not protected.
- R8. Protected folders that contain indexed notes (e.g. `skills/`, `views/` — protected by the
  write guard but **not** skipped by the index) DO appear, marked non-writable with the reason, so an
  agent can see-and-avoid them rather than them being silently hidden.
- R9. The protected classification reuses `serialize.protected_reason()` — no new classifier, no
  divergence from what the write guard actually enforces.

**Blocklist write model — coupled change**

- R10. `commit_note`'s default writable surface flips from the 4-prefix `DEFAULT_WRITE_ALLOWLIST` to
  a **blocklist**: every path under the content surface is writable **except** the
  `protected_reason()` classes. `projects/`, `people/`, `companies/`, `meetings/`, and any future
  content folder become writable without enumeration.
- R11. The flip reuses the existing guard machinery — `serialize.check`'s already-supported
  `allowlist=None` path (protected-path refusal as the sole bound). **No new write tool, no new
  write path, no new write machinery.**
- R12. A narrowed allowlist (e.g. the `captures/` quarantine) remains available as an explicit
  operator opt-in (`--allowlist …` on `setup` / `serve-cloud`), per the 2026-06-03 review's escape
  hatch. It is no longer the default.
- R13. The flip weakens no other control: per-tool `write` scope (V14), the operator-consent gate,
  protected-path refusal, the diff-or-die frontmatter gate, server-set actor, the append-only
  summaries-only audit log, and git-revertability all hold unchanged.

**Security sign-off gate**

- R14. The write-model flip ships behind a fresh **security-review delta** amending/superseding
  `docs/2026-06-03-unified-write-anywhere-security-review.md`: that review's blast-radius analysis
  was scoped to the 4 note zones; the blocklist widens residual **R-1** to the entire content
  surface minus protected classes. The delta re-validates each control under the wider surface and
  must be **operator-signed (a G-gate)** before the change is enabled in production.

---

## Acceptance Examples

- AE1. **Covers R2, R4.** Given `projects/` holds 40 subfolders and the node cap is below 40, when an
  agent calls discovery at `projects/`, then it receives a bounded, sorted page of child folders with
  a `truncated` signal and an omitted-count — not all 40 at once.
- AE2. **Covers R7, R10.** Given the blocklist default, when an agent discovers `projects/acme/`, then
  it is marked writable, and a subsequent `commit_note` to `projects/acme/note.md` succeeds.
- AE3. **Covers R7, R12.** Given an install started with `--allowlist captures/`, when an agent
  discovers `projects/acme/`, then it is marked **not** writable, and a `commit_note` there is refused
  — discovery and the guard agree.
- AE4. **Covers R8, R9.** Given `skills/onboarding.md` is indexed, when an agent discovers under root,
  then `skills/` appears marked non-writable with a protected reason — it is not omitted.
- AE5. **Covers R5.** Given `.obsidian/` and `node_modules/` exist in the repo, when an agent
  discovers at root, then neither appears (the index never ingested them).
- AE6. **Covers R10, R14.** Given the blocklist flip is implemented but the security-review delta is
  unsigned, when production is brought up, then the write-model change is **not** enabled until the
  operator signs off (read-only discovery may still ship).
- AE7. **Covers R6.** The discovery tool advertises an `outputSchema`; a connector receives a
  structured result (folders with path / writable / reason / count) rather than an opaque object.

---

## Visualization

Illustrative drill-down (field names not final):

```
list_folders(root="", depth=1) →
  projects/     writable ✓   notes: 128
  people/       writable ✓   notes: 64
  companies/    writable ✓   notes: 41
  meetings/     writable ✓   notes: 312
  sources/      writable ✓   notes: 89
  skills/       writable ✗   (protected dir: skills/)   notes: 7
  truncated: false
  manual_reindex_recommended: false

list_folders(root="projects/", depth=1) →
  projects/acme/      writable ✓   notes: 18
  projects/hermes/    writable ✓   notes: 53
  …                                              ← node cap reached
  truncated: true   omitted: 12
```

Each entry: `path`, `writable`, protected reason (when not writable), note count. Envelope:
`truncated` + omitted count, plus the inherited `manual_reindex_recommended`. `.obsidian/`, `.git/`,
`node_modules/` never appear — the index never ingested them.

---

## Success Criteria

- An agent connecting fresh, with no prior knowledge of the vault, can discover where notes live and
  place a new note in a correct, **writable** folder on the first try — no guess-and-refuse loop.
- Discovery's `writable` flag and `commit_note`'s actual guard **never disagree** on any path, under
  any install configuration (blocklist default or a narrowed `--allowlist`).
- `projects/`, `people/`, `companies/`, `meetings/` (and future top-level content folders) are
  writable without anyone editing an allowlist.
- The write-model widening is **not** enabled in production until the operator has signed a
  security-review delta re-validating the controls under the blocklist blast radius.
- `ce-plan` can implement without inventing product behavior: the tool's inputs, the meaning of each
  output field, the bounding behavior, the writable semantics, and the sign-off gate are all
  specified here.

---

## Scope Boundaries

### Deferred for later

- An optional **taxonomy hint in `commit_note`'s refusal** — a cheap recovery aid when an agent still
  guesses wrong. Complementary to discovery, not a substitute for it (it is write-only and
  post-guess); addable later.
- Exact **bounding constants** (node/child cap, default and max depth, pagination shape) — tuned in
  planning, not a product decision.
- Folder metadata **beyond** writable / protected / note count (e.g. last-modified, salience) — not
  needed for placement.

### Outside this effort's identity

- A **"suggest-a-path-for-this-note" helper** that infers placement from a note's content — this
  reintroduces exactly the placement inference `commit_note` deliberately refuses. The engine
  surfaces structure; the agent decides. (Never.)
- A **scope-gated full-vs-writable exposure split** — the model has only `read`/`write` scopes,
  full-content exposure is the accepted posture, and the approval-token consent gate is the boundary.
  A third "privileged" scope is not this effort's identity.
- Exposing anything **beyond the content surface** (governance / dot / binary dirs) — structurally
  precluded by the index and deliberately not reintroduced.

---

## Key Decisions

- **KD1 — A new thin read tool, assembled from existing primitives, not a new abstraction.**
  Discovery genuinely needs a read-scoped, **pre-write** surface (agents choose a path before calling
  `commit_note`; read-only clients never even see `commit_note`), which a `commit_note` refusal-hint
  cannot provide as a substitute. But the tool invents nothing: it composes `index.all_paths()`
  (taxonomy), `serialize.protected_reason()` (protected classification), and the effective write
  config (writability). Satisfies native-primitives-first — expose existing primitives, don't
  reinvent.

- **KD2 — Blocklist over a broadened allowlist.** Chosen over enumerating `projects/`, `people/`,
  `companies/`, `meetings/` in the allowlist, because an enumerated list silently fails every time
  the vault grows a new top-level folder; a blocklist auto-includes future content folders.
  Durability over a list the operator must maintain.

- **KD3 — Full content taxonomy exposed, not writable-zones-only.** The operator's intent is a fully
  navigable vault. The residual (an approved-but-compromised read client gets a one-shot content map)
  is bounded: the index already fences out governance/dot dirs, every read client passed the
  approval-token consent gate, and `search`/`resolve` already leak paths piecemeal. A tree tool
  changes enumeration *efficiency*, not the *category* exposed.

- **KD4 — Couple the write-flip with a fresh sign-off gate.** The 2026-06-03 review approved
  write-anywhere only across the **4 note zones**; the blocklist widens R-1's blast radius to the
  whole content surface. Rather than let a default change slip past the signed scope, the flip ships
  behind an explicit security-review delta the operator signs.

- **KD5 — Source of truth = committed HEAD, inherited free.** Discovery converges to HEAD like every
  read tool and returns `manual_reindex_recommended`; no new convergence or source-of-truth decision.

- **KD6 — Writability is single-sourced from the write guard.** The tool reuses
  `serialize.protected_reason()` + the effective allowlist, so it can never diverge from what
  `commit_note` enforces. Discovery that lies about writability would be worse than no discovery.

---

## Dependencies / Assumptions

- The shipped `origin/main` contract is the substrate (verified against `origin/main`; this worktree
  is ~105 commits behind): `READ_TOOL_NAMES = {search, build_context, think, resolve}`, the
  converge-before-serve read path, `serialize.check`'s `allowlist=None` blocklist path,
  `serialize.protected_reason()`, `index.all_paths()`, and `DEFAULT_WRITE_ALLOWLIST`.
- `build_cloud_server` currently defaults the write allowlist to the 4-prefix
  `DEFAULT_WRITE_ALLOWLIST` — the stale narrowing this effort replaces with the blocklist (its own
  comment already describes the intent as "write-anywhere-under-guards (KD3/KD5)").
- `serialize.check` already treats `allowlist=None` as "protected_reason is the only bound" (verified
  in `src/hypermnesic/serialize.py`), so blocklist mode needs **no new guard code**.
- `index.all_paths()` returns *file* paths; folders are derived prefixes. Empty folders (no notes)
  are not discoverable, and a brand-new folder is created implicitly by a `commit_note` write under a
  writable parent — discovery shows where notes already live for consistent placement.
- Delivered **TDD-first** per repo convention; no write path is exercised against the live
  `gbrain-brain` canonical checkout without an explicit per-action go-ahead (carried from the
  threat-model dev-safety proviso). Never commit to `main`/`dev`.

---

## Outstanding Questions

### Deferred to planning

- [Affects R4][Technical] Bounding constants — node/child cap per call, default and max `depth`, and
  whether truncation paginates via a cursor or by narrowing `root`.
- [Affects R3, R6][Technical] Final field names and the exact `TypedDict` output shape (mirror the
  existing `*Output` TypedDicts).
- [Affects R3][Technical] Note-count semantics — count notes *directly in* a folder vs. *recursively
  at/under* it (and whether to expose both).
- [Affects R1][Technical] Tool/verb name (`list_folders` is a working name) and the CLI subcommand
  surface for parity.
- [Affects R10, R14][Sequencing] One PR (read tool + write-flip gated together) vs. two (read tool
  first; write-flip after the signed delta). The read-only tool carries no security gate, so it may
  safely land first — confirm the delivery split during planning.
- [Affects R7][Needs research] Whether any existing read client caps or streams tool output in a way
  the bounding contract must accommodate.
