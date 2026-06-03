---
date: 2026-06-03
topic: first-class-documentation
---

# First-Class Documentation — Public-Launch Readiness

## Summary

Make the `hypermnesic` repository first-class documented and ready to flip to a
public open-source project in a single, reviewable step — without going public
yet. The work spans four concerns: correcting the doc↔code drift today's 7 PRs
introduced, staging the license + public-switch readiness, adding the
community-health and technical-reference documents contributors and GitHub
expect, and building a marketing/positioning layer (README hero, surfaced
benchmarks, visuals, comparison) over a reorganized `docs/` tree that separates
durable reference from process history.

---

## Problem Frame

The repository is built faster than its documentation can keep up. Seven PRs
landed on `main` on 2026-06-03 and materially reshaped the product — the serving
topology collapsed from four lanes to two (one public OAuth `/mcp` endpoint plus
a tailnet read companion on `:8848`), the `:8849` client-credentials auth lane
was retired, an opt-in `--allow-tailnet-write` boundary was added, a
`list_folders` discovery tool shipped, the write surface flipped from a 4-prefix
allowlist to a write-anywhere-under-guards blocklist, and the engine bumped to
0.0.5. The README was refreshed (#17) and is mostly current, but the drift
pooled in the surfaces that weren't touched: `pyproject.toml` still calls the
product a "tailnet-only MCP server"; the bundled agent skill still teaches the
retired allowlist write model; three plugin manifests still report 0.0.4; the
`--allow-tailnet-write` and `list_folders` features are documented nowhere
user-facing; and the running decision log stops at PR #5.

Underneath the drift is a deeper gap. The `docs/` tree holds 40+ files, but they
are almost entirely *process exhaust* — brainstorms, per-phase plans, gate
artifacts, machine-to-machine handoffs, dated security reviews — with no index,
no durable reader-facing reference layer, and none of the documents a serious
project is judged by: no `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
`CHANGELOG.md`, `ARCHITECTURE.md`, API/CLI/config reference, issue/PR templates,
or `AGENTS.md`. The project documents its *process* exhaustively and its
*product* almost not at all. The single strongest credibility asset — a
LongMemEval V1 result of 88.6/89.7 with session recall@10 of 0.949, fully pinned
and reproducible — is buried in `harness/` and absent from the README.

Finally, the intended public-launch identity is not yet legally coherent: the
engine is `Proprietary` across `LICENSE`, `pyproject.toml`, and the README, while
the companion already shipped externally under GPL-3.0, and the repo's own
`scripts/license_scan.py` advertises a "zero AGPL/GPL/SSPL" posture that reads
oddly against the planned copyleft relicense. The goal of this effort is to close
all of these gaps so that *both repos can stay private now* and the eventual flip
to public is a small, prepared, reviewable change rather than a scramble.

---

## Key Decisions

- **Prepare-for-public-while-private — stage, don't flip.** Every requirement
  here produces a repository that is *ready* to go public, but nothing is
  published or relicensed live in this effort. The engine repo and the external
  `hypermnesic-companion` repo both stay private until an explicit, separate
  go-public decision. Requirements that touch the public identity (license text,
  badges, the companion pointer's public link) are authored in a *staged* state
  whose activation is the flip itself.

- **The requirements doc is the deliverable; authoring the docs is downstream.**
  This document specifies *which* documents must exist and *what each must be
  true of*, not their prose. Producing the actual files is follow-on planning/
  execution work.

- **Comprehensive but prioritized.** Requirements are grouped into P0 (drift /
  correctness — the repo currently misdirects readers and agents), P1
  (community-health + technical reference + release hygiene — required to look
  and behave like a real project), and P2 (marketing/positioning + `docs/`
  reorganization — required to convert and orient newcomers). The grouping is a
  sequencing signal for the planner, not a scope cut.

- **License is AGPL-3.0 (engine) ↔ GPL-3.0 (companion), confirmed and staged.**
  Per `docs/plans/2026-06-02-010-feat-companion-directory-publishing-plan.md`
  (R7), the U9 handoff, and the operator's 2026-06-03 decision, the engine
  relicenses to AGPL-3.0 so the GPL-3.0 companion can interoperate at arm's
  length over the read-only MCP wire. The accepted trade-off is that some
  enterprises avoid AGPL dependencies; copyleft protection and the "derivatives
  stay open" guarantee win. This effort prepares that flip and reconciles the
  "copyleft-free" narrative; it does not execute the relicense.

- **`docs/` splits into durable-reference vs process-history, with an index.**
  The current flat pile becomes a navigable tree: a maintained reference layer
  (architecture, reference, runbooks, a consolidated security front door) and an
  unmaintained history layer (brainstorms, plans, gate artifacts, handoffs,
  archive). A `docs/README.md` index is the missing front door that makes the
  existing investment legible and points readers at current truth.

---

## Requirements

**P0 — Doc↔Code drift correction (today's 7 PRs).** Each item below is a place a
current doc actively misdirects a reader or agent.

- R1. `pyproject.toml`'s `[project].description` no longer describes the product
  as a "tailnet-only MCP server"; it reflects the unified public OAuth `/mcp`
  endpoint plus the tailnet read companion, and drops the retired
  "write-enabled master" framing (`pyproject.toml:4`).
- R2. All distributed version strings agree with the engine version. The three
  plugin/marketplace manifests pinned at `0.0.4`
  (`plugin/.claude-plugin/marketplace.json`,
  `plugin/plugins/hypermnesic/.claude-plugin/plugin.json`,
  `plugin/plugins/hypermnesic/.codex-plugin/plugin.json`) match the engine
  (`pyproject.toml`, `src/hypermnesic/__init__.py`), and a single-source-of-
  version mechanism prevents recurrence (see R20).
- R3. The bundled agent skill teaches the **blocklist** write model, not the
  retired 4-prefix allowlist: writes are bounded by the protected-path class and
  the governance-file fence, with the named allowlist as an opt-in narrowing
  only (`plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md:45-46,62`).
- R4. The README's write-path description is internally consistent — it does not
  frame the allowlist as the default guard in one place while describing the
  blocklist write-anywhere model in another (`README.md:92` vs `README.md:85-90`).
- R5. The `list_folders` read tool (shipped #19) appears in every user-facing
  tool catalog — the agent skill's MCP tool list and the plugin README's tool
  list — not only as a self-describing runtime tool
  (`SKILL.md:29-37`, `plugin/README.md:25-26`).
- R6. The `--allow-tailnet-write` opt-in (shipped #18) is documented in a
  user-facing surface, including its security-relevant semantics (tailnet
  membership as the write boundary; only honored for a CGNAT bind; every
  `commit_note` guard still applies). It is currently undocumented everywhere.
- R7. The running decision record is current through 2026-06-03 — the unified
  endpoint, the 4→2 lane collapse, the `:8849` retirement, and the
  allowlist→blocklist flip are recorded — or `implementation-notes.md` is retired
  in favor of `CHANGELOG.md` + decision records (resolve in R20/Outstanding
  Questions). Today it stops at PR #5.

**P0 — License & public-switch readiness (staged, not flipped).**

- R8. The OSI license decision is staged so the flip is a single reviewable
  change: the chosen license text (plan-of-record AGPL-3.0) is prepared and the
  set of files that change at flip time is enumerated (`LICENSE`,
  `pyproject.toml` license field, the README license section, badges) — but
  nothing is relicensed live.
- R9. The "copyleft-free" narrative is reconciled with the project's own intended
  copyleft license. `scripts/license_scan.py`'s zero-AGPL/GPL/SSPL gate is
  clearly scoped to *transitive dependencies* (KTD1, which still holds), and the
  README/pyproject framing no longer implies the *project itself* must avoid
  copyleft. The gate's intent and the engine's own license are documented as
  non-contradictory.
- R10. The engine↔companion license boundary is documented for a public reader: a
  short licensing note (and a README License-section line) explaining the AGPL-3.0
  engine ↔ GPL-3.0 companion arm's-length MCP-wire relationship and that neither
  is a derivative of the other.
- R11. A pre-public readiness checklist / "flip to public" runbook exists,
  covering: a secret/private-host scrub gate (no tailnet IPs, operator
  hostnames, tokens, or consent secrets in any to-be-public file — building on
  the homelab-IP scrub already done in #6/#21), the companion-repo public-flip
  sequencing, and the ordered steps of the license + visibility flip.

**P1 — Community-health & contributor docs (staged for the public flip).**

- R12. `CONTRIBUTING.md` exists: dev setup (`uv sync --extra dev`), the three CI
  gates promoted from a README footnote to a contract (`ruff check .`, `pytest`,
  `scripts/license_scan.py`), branch strategy, commit/PR conventions, and how to
  run a local endpoint to test against.
- R13. `CODE_OF_CONDUCT.md` exists (Contributor Covenant + enforcement contact).
- R14. A root `SECURITY.md` exists as the canonical vulnerability-reporting policy
  (private channel, supported versions, disclosure expectations) and as the index
  into the threat model and dated security deltas (see R26).
- R15. `.github/ISSUE_TEMPLATE/` (bug + feature, capturing engine host, client,
  vault size, Tailscale/Funnel state) and `PULL_REQUEST_TEMPLATE.md` (a checklist
  tying PRs to the CI gates and flagging security-surface changes) exist.
- R16. `CODEOWNERS` exists, at minimum routing `src/hypermnesic/auth*`,
  `mcp_server.py`, and the security docs to the owner.
- R17. A root `AGENTS.md` exists giving agent contributors the build/test/gate/
  branch/worktree contract this repo is actually developed under.

**P1 — Versioning & release.**

- R18. `CHANGELOG.md` exists in Keep-a-Changelog form, backfilled at least to
  0.0.5 and the 2026-06-03 PR set.
- R19. A release/versioning policy is documented: pre-1.0 `0.0.x` semantics,
  tagging, who cuts releases.
- R20. A single source of truth for the version exists so engine and plugin
  manifests cannot drift again (mechanism chosen in planning — derive manifests
  from `pyproject.toml`, or a `VERSION` file, or a CI assertion). Resolves the
  recurrence behind R2.

**P1 — Technical reference.**

- R21. `ARCHITECTURE.md` exists with a diagram: how the index, retrieval,
  read-time convergence, the MCP server, the git-first write path, and the two
  serving lanes fit together, and the load-bearing invariant that the files are
  the source of truth and the index is a disposable, rebuildable projection.
- R22. An MCP tool / API reference documents the read tools (`search`,
  `build_context`, `think`, `resolve`, `list_folders`) and the gated write tool
  (`commit_note`) with their input/output shapes, scopes, and read-only
  annotations — the actual client contract.
- R23. A complete CLI reference documents all subcommands and flags — including
  the currently-undocumented `embed`, `reindex`, `capture`, `converge`,
  `install-hooks`, `install`, and `serve-cloud` — so the documented surface
  matches the registered surface.
- R24. A configuration reference documents the user-facing knobs: `OPENAI_API_KEY`,
  the `HYPERMNESIC_MCP_URL` / `HYPERMNESIC_MCP_TOKEN` / cloud consent-secret
  variables, and the `config.py` tunables (convergence budget/debounce/delta,
  `LIST_FOLDERS_MAX_*`, embed model/dim). `.env.example` documents only
  `OPENAI_API_KEY` today.
- R25. A getting-started / installation guide beyond the README quick start covers
  the three paths (self-host the endpoint, connect a client, use it locally) and
  their failure modes (Tailscale Funnel prerequisites, the discovery-chain
  verification, offline/lexical-only operation).
- R26. A glossary defines the project's jargon used without definition in the
  README and docs: convergence, salience, sidecar, MOC, thinking-mode, RRF,
  DCR/PKCE, RFC 8707 audience-binding, "diff-or-die frontmatter gate", consent
  secret, tailnet read lane.

**P2 — Marketing & positioning.**

- R27. The README's first screen answers what / who / why-care / how-it-differs in
  addition to what-and-how: the target user ("you already keep markdown notes in
  git and want every agent to share that memory") and the one-line differentiator
  are stated before the architecture detail.
- R28. The LongMemEval benchmark is surfaced in the README — the headline numbers
  (88.6 overall / 89.7 task-avg with the GPT-4.1 reader; session recall@10 =
  0.949) with their honest GPT-4o-judge framing and a link to
  `harness/BENCHMARKS.md`.
- R29. A positioning / "why hypermnesic" document argues the differentiator
  explicitly against the adjacent tools (mem0, Letta/MemGPT, basic-memory, plain
  Obsidian): files-are-truth with a disposable index, git-first writes, one OAuth
  MCP endpoint any client shares, no vendor memory DB.
- R30. At least one visual asset exists: a companion screenshot or short demo, and
  the architecture diagram from R21 — the project currently ships zero images.
- R31. README badges (CI, license, version) are prepared, staged to render
  correctly once the repo is public and the license is flipped.
- R32. A `CITATION.cff` is prepared (landing with the license flip) surfacing the
  headline benchmark numbers and the LongMemEval / Zep paper anchors so the result
  is citable.

**P2 — `docs/` information architecture.**

- R33. A `docs/README.md` index is the front door: a map splitting durable
  reference from process history, each entry one line, with explicit
  current-truth pointers (current write-surface model = blocklist; current
  topology = two lanes / unified `/mcp`) so a reader does not land on a stale
  2026-06-02 brainstorm and mistake it for current.
- R34. `docs/` is reorganized into a durable layer and a history layer (e.g.
  `reference/`, `security/`, `solutions/`, `history/{brainstorms,plans,gate-artifacts,handoffs}`,
  `archive/`), with the durable layer maintained and the history layer frozen.
- R35. The scattered security docs are consolidated behind one canonical front
  door: `docs/threat-model-commit-note.md` is promoted to the living threat model
  + index, and the dated reviews
  (`docs/2026-06-03-unified-write-anywhere-security-review.md`,
  `docs/2026-06-03-blocklist-write-surface-security-review.md`,
  `docs/oauth-as-finding.md`) become immutable deltas it indexes. Pairs with R14.
- R36. Superseded and stale docs are archived with pointers, not left to read as
  current: the cloud OAuth runbook (already marked superseded), the gate-A
  rollout runbook, and the two oldest brainstorms describing the retired
  `captures/`-quarantine / 4-prefix allowlist model.
- R37. The Obsidian companion pointer (`obsidian-plugin/README.md`) is reconciled
  with reality: the pointer shape is kept, but it is annotated as flipping public
  on the companion's first community-directory release (its external repo is still
  private, so the link 404s today), and the README notes the companion is a
  separate, separately-licensed install.

---

## Acceptance Examples

- AE1. **Covers R1–R7.** Every feature shipped in the 2026-06-03 PR set — the
  unified `/mcp` endpoint, `list_folders`, `--allow-tailnet-write`, the blocklist
  write model, and version 0.0.5 — is described in at least one user-facing doc,
  and no user-facing doc describes a retired behavior (tailnet-only serving,
  the 4-prefix allowlist default, the `:8849` auth lane, plugin version 0.0.4).
- AE2. **Covers R8, R10, R31, R32.** When the maintainer decides to go public,
  the license + visibility flip is a single reviewable PR (swap `LICENSE` text,
  set the `pyproject.toml` license field, update the README license section,
  enable badges, land `CITATION.cff`) — no first-class document has to be
  *authored* at flip time because they already exist in staged form.
- AE3. **Covers R12–R16.** The moment the repo is made public, GitHub's
  community-profile checklist reads 100% — README, LICENSE, CODE_OF_CONDUCT,
  CONTRIBUTING, SECURITY, and issue + PR templates all resolve.
- AE4. **Covers R27–R29.** A newcomer landing on the public README can answer
  "what is this, who is it for, why should I care, and how is it different from
  mem0/Letta/basic-memory" from the first screen, and can find the headline
  benchmark result without opening `harness/`.
- AE5. **Covers R33–R36.** A reader entering `docs/` hits an index that routes
  them to current truth in one hop; following any durable-reference link lands on
  a maintained, accurate doc, and every superseded doc they could reach carries a
  pointer to its replacement.

---

## Success Criteria

- The repo can be flipped public in a single reviewable PR with no
  documentation authored at flip time (only activated).
- GitHub community-profile checklist is at 100% on flip.
- Zero doc↔code drift for the current `main`: the documented CLI surface, MCP
  tool set, serving topology, write model, and version all match the code.
- A new contributor can go clone → passing local gates using `CONTRIBUTING.md`
  alone.
- A reader can build an accurate architecture mental model from `ARCHITECTURE.md`
  without reading source.
- The strongest credibility asset (the LongMemEval result) is visible from the
  README, not buried in `harness/`.
- No to-be-public file contains a private host, tailnet IP, operator hostname,
  token, or consent secret.

---

## Scope Boundaries

**Deferred for later (eventually, not in this effort):**

- Actually flipping either repo to public, and executing the license relicense.
- Making the external `hypermnesic-companion` repo public / cutting its first
  release.
- Authoring the prose/content of each document (downstream planning + execution).
- A rendered documentation website / static docs site.

**Outside this effort's identity (not a docs problem):**

- Any code or product-behavior change — this is a documentation effort; the audit
  is read-only.
- The live homelab cutover and ongoing deployment operations.
- The in-flight gbrain-decommission migration (tracked by its own STATE doc).
- The internals of the companion's external repository.

---

## Dependencies / Assumptions

- The license plan-of-record is AGPL-3.0 (engine) ↔ GPL-3.0 (companion) per
  `docs/plans/2026-06-02-010-feat-companion-directory-publishing-plan.md` and the
  U9 handoff; this effort assumes that direction holds unless redirected (see
  Outstanding Questions).
- Both the engine repo and the companion repo stay private until a separate,
  explicit go-public decision.
- The README is already substantially current (refreshed in #17); the drift to
  correct is concentrated in `pyproject.toml`, the agent skill, the plugin
  manifests, and `implementation-notes.md`.
- The LongMemEval numbers in `harness/BENCHMARKS.md` are current and reproducible
  from the committed harness + pinned dataset manifest.
- The `docs/` security reviews already carry `supersedes`/`amends` frontmatter, so
  the consolidation in R35 is a structuring task, not a content merge.

---

## Outstanding Questions

No items block planning — the license direction (AGPL-3.0) is resolved above.

**Deferred to planning:**

- Single-source-of-version mechanism for R20 (derive manifests from
  `pyproject.toml`, a `VERSION` file, or a CI drift assertion) — an
  implementation choice, but pick it before fixing R2 so the drift is fixed once.
- The exact `docs/` folder taxonomy and which existing files move where (R34).
- Whether `implementation-notes.md` is brought current or retired in favor of
  `CHANGELOG.md` + decision records (R7/R18).
- Whether to add a CI guard that asserts the documented tool/CLI surface equals
  the registered surface, to keep R1–R6/R22–R23 from re-drifting.

---

## Sources / Research

**The 2026-06-03 PRs that drove the drift (all merged to `main`):**

- #16 — unified OAuth MCP endpoint + `hypermnesic setup`; 4 serving lanes → 2;
  retired the `:8849` client-credentials auth lane (`auth_server.py` deleted).
- #17 — `setup` per-mount funnel targets + serve-at-root; README quick-start
  refresh; 0.0.3 → 0.0.4.
- #18 — `--allow-tailnet-write` (tailnet membership as an opt-in write boundary).
- #19 — `list_folders` discovery tool (MCP + CLI), Phase A.
- #21 — write surface flipped allowlist → blocklist (write-anywhere-under-guards),
  Phase B; landed corrective after a stacked-merge missed `main`.
- #22 / #23 — engine 0.0.4 → 0.0.5 + `__init__` version sync.

**Audit findings by surface (cited for the planner):**

- README↔code drift: `pyproject.toml:4` ("tailnet-only"); `SKILL.md:45-46,62`
  (allowlist write model); plugin manifests at `0.0.4`; `list_folders` /
  `--allow-tailnet-write` undocumented; `README.md:92` internal inconsistency.
- Missing first-class docs: no `SECURITY.md`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, API/CLI/config
  reference, `.github` templates, `CODEOWNERS`, `AGENTS.md`, glossary,
  `CITATION.cff`; `.env.example` documents 1 of ~8 user-facing knobs.
- `docs/` structure: 40+ files, no index; `implementation-notes.md` stops at
  PR #5; `docs/cloud-oauth-mcp-deploy-runbook.md` superseded;
  `docs/threat-model-commit-note.md` is the natural canonical security index.
- Distribution / research: `obsidian-plugin/` is a pointer to a still-private
  GPL-3.0 repo (404s for end-users); the LongMemEval result
  (`harness/BENCHMARKS.md`: 88.6 / 89.7, recall@10 0.949, $31.30, pinned dataset
  SHA-256) is absent from the README.
- License posture: engine `Proprietary` (`LICENSE`, `pyproject.toml`, README) vs
  companion GPL-3.0; planned engine relicense to AGPL-3.0
  (`docs/plans/2026-06-02-010-feat-companion-directory-publishing-plan.md` R7,
  U9 handoff) not yet executed.
