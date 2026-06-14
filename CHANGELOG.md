# Changelog

All notable changes to **hypermnesic** (the engine) are recorded here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project is
pre-1.0, so it uses `0.x` semantics — any release may carry breaking changes while the
kernel stabilizes.

`pyproject.toml` `[project].version` is the single source of truth for the version;
the plugin manifests and `src/hypermnesic/__init__.__version__` are kept in lockstep
by the CI version-consistency gate (`scripts/check_version_consistency.py`).

The Obsidian companion (`obsidian-plugin/`, shipped as a separate repository) carries
its own changelog and version.

## [Unreleased]

### Added
- Repository social-preview asset for the public GitHub presentation.
- Directory-submission prep for the official MCP Registry, awesome-mcp-servers, and
  Obsidian community plugin directory.
- PyPI publication decision memo for the one-command install gate.
- Launch-week first-contact response SLO checklist and baseline.
- Launch narrative and channel-specific post drafts tied to readiness evidence.
- Launch sequencing plan and public-launch retro template.
- GitHub Discussions welcome and public roadmap prep for the contribution funnel.
- Live GitHub Discussions links in README/docs for the welcome thread and public roadmap.

### Changed
- GitHub repository description and topics were applied for the public release presentation pass.
- Directory-submission prep now reflects the current MCP Registry schema constraint,
  the open awesome-mcp-servers PR, and the Obsidian PR permission handoff.

## [0.1.0] — 2026-06-14

First-class product track and public-launch readiness. Adds the community-health and
technical-reference documents (CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, ARCHITECTURE,
references, guides, glossary, GitHub templates), reconciles doc↔code drift from the
0.0.5 PR set, and stages the AGPL-3.0 license + public-flip runbook under
`docs/launch/` without flipping the live license or repository visibility.

### Added
- **`hypermnesic local-proof`**: a local-first value proof that validates or creates a
  git-backed markdown vault, projects committed files into the disposable index, retrieves
  a natural-language question with the repo-relative source path, explains lexical-only
  degradation in product language, and shows a `commit_note` dry-run diff without creating
  a write commit.
- **`hypermnesic doctor` / `hypermnesic status`**: non-mutating setup diagnostics for local
  index health, remote reach, OAuth discovery, auth challenge, write availability, and
  client-specific next actions, with JSON output for agents and CI.
- **`hypermnesic memory`**: an owner memory-control command group for listing and
  inspecting remembered files, exporting markdown with provenance, previewing and applying
  git-backed forget/delete, reverting safe recent single-file writes, viewing
  summary-only audit/refusal history, and answering what agents may write.
- **`hypermnesic clients`**: an owner client-control command group for listing secret-free
  OAuth grant metadata and previewing/applying grant revocation without exposing bearer
  tokens, refresh tokens, approval credentials, or client secrets.
- **Plugin hook status/test recall**: the Claude Code / Codex auto-recall hook now records
  non-secret outcome status out-of-band, supports host-specific disable controls, and ships a
  helper script for `status` and bounded `test-recall` diagnosis without exposing prompts,
  endpoint URLs, tokens, headers, or raw large snippets.
- **`hypermnesic daily-review`**: a review-gated daily workflow dashboard proposal that composes
  capture backlog, recent writes, generated surfaces, recall guidance, degraded/offline notes, and
  cleanup next actions without moving, deleting, or rewriting source notes.
- **Product readiness proof**: a deterministic `scripts/product_smoke.py` loop, offline
  remote-client contract tests, a remote-client smoke checklist, and a first-class product
  readiness checklist that separate benchmark quality from setup/control/client operability.
- **Hermes Agent CLI plugin pack:** added a Hermes-specific `plugin/hermes/` package
  that registers a namespaced hypermnesic memory skill, includes an optional flat skill
  export, and can opt into bounded `pre_llm_call` recall through the local
  `hypermnesic` CLI. This is distinct from the Claude Code / Codex MCP plugin pack.
- **Default client scope controls:** `serve-cloud` and `setup` now support
  `--default-client-scopes read write`, plus
  `HYPERMNESIC_DEFAULT_CLIENT_SCOPES=read,write`, so operators can make newly registered
  clients request both read and write on the first consent screen.
- **Dense diagnostic live check:** `hypermnesic doctor` / `status` now support
  `--check-dense-live` to opt into a real embedding smoke check while keeping default
  diagnostics offline-friendly and secret-free.

### Changed
- README and getting-started onboarding now lead with the local proof milestone before
  endpoint setup or remote-client connection.
- The remote-client smoke checklist now makes read-scope leak checks explicit for local absolute
  paths and private or `/mcp` endpoint URLs, records client-side write-refusal blocks as
  `INCONCLUSIVE/FAIL`, and uses a protected `scripts/<smoke-id>-protected-refusal.md` write so
  hosted clients can prove the MCP guard without tripping their own `AGENTS.md` safety layer first.
- The remote-client smoke checklist now records hosted ChatGPT and Claude as operator-approved
  read+write clients: true read-only grant refusal is N/A for those hosted clients, while
  read-scoped principal behavior remains covered by automated MCP/auth contract tests.
- `list_folders` and `hypermnesic list-folders --json` now include an `agent_instruction`
  field. It is `{source, content}` for direct root-local `AGENTS.md` guidance, falls back to
  direct `CLAUDE.md`, and is `null` when neither file exists at the requested root.
- `hypermnesic setup --resource` now defaults to `--public-url` for the common endpoint
  shape, while preserving explicit resource overrides for advanced deployments.
- OAuth consent now explains read/write scope consequences, generic-client warnings,
  reject/cancel choices, revocation guidance, and clearer write-scope refusal language.
- README, getting-started, plugin skills, glossary, and references now teach the memory taxonomy:
  Hypermnesic is durable project memory, while behavioural preferences and session state route to
  Honcho or an equivalent adjacent layer by default.
- Daily workflow docs now teach capture -> triage -> recall -> write -> review -> clean up,
  including recipes and the Obsidian companion's read-only role.
- README and launch docs now point to the public `hypermnesic-companion` repository and
  its first `0.3.0` release instead of the private-until-release staging language.
- README now opens with a local-proof demo asset, a 5-minute quickstart, and a scoped
  comparison against hosted memory layers.

### Fixed
- Public OAuth AS metadata now advertises public-client token and revocation auth support
  (`none`) alongside confidential-client methods, matching the DCR/token behavior and
  preventing Codex app connectors from staying stuck at 401 after OAuth authorization.
- Public OAuth clients can now refresh across `serve-cloud` restarts. The cloud lane persists
  DCR client registrations and live token state in an owner-only
  `.hypermnesic/cloud-oauth-state.json` file, while keeping `client-grants.json` as the
  secret-free owner-control metadata surface.
- The MCP server now advertises `hypermnesic_search` as a read-only compatibility alias for
  `search`, matching Codex app connector calls that prefix tool names.
- Incremental convergence now invalidates stale doc-surface vectors for changed markdown
  paths and lets the bounded dense fill refresh them without a full-vault reindex.
- Existing doc-lane rows are now reused reliably when writing refreshed doc-surface vectors.
- Dense embedding key lookup is now repo-scoped across CLI, setup/install, MCP serve, and
  diagnostics: process `OPENAI_API_KEY` still wins, but an explicit repo uses that repo's
  gitignored `.env` instead of depending on the caller's current working directory.
- Dense diagnostics now distinguish key configuration, opt-in live validation, missing/unbuilt
  indexes, and stale or absent vector coverage without printing secrets.
- MCP serving now refuses ambiguous custom `--index-db` paths without `--repo`, preventing
  dense credential lookup from guessing a vault from an unrelated parent directory.
- `commit_note` protected-path and write-scope refusals now survive Streamable HTTP structured-output
  validation, so remote clients receive a clean `{committed:false, refused:"..."}` payload instead
  of an MCP output validation error.
- Retrieval now skips orphaned disposable-index candidates instead of crashing when an FTS/vector
  row outlives its backing chunk row during projection churn.
- Degraded lexical recall now self-heals older FTS projections that omitted markdown headings,
  so committed notes remain recallable by title/body queries even when embeddings are unavailable.
- `think(topic, path=...)` now falls back to the active note's graph context when
  self-exclusion removes the only lexical hit, so well-linked notes still surface related
  material in degraded lexical-only clients such as the Obsidian companion.
- `list_folders` / `hypermnesic list-folders` now redact local absolute paths and endpoint URLs
  from returned `agent_instruction.content`, preventing read-only remote clients from receiving
  private host coordinates embedded in root-local guidance files.

## [0.0.6] — 2026-06-03

The think-surface quality release.

### Fixed
- **Thinking-mode (`think`) surface quality (U42–U47):** exclude the active note from
  its own results; resolve note titles by their H1 rather than the chunk section
  heading; strip a leading ATX marker from the topic; gate Socratic questions to
  note-grounded prompts; replace prose "tensions" with structured `unlinked` pairs
  (deduped by note).

### Changed
- Engine bumped `0.0.5 → 0.0.6` to force a clean redeploy.

## [0.0.5] — 2026-06-03

The serving-topology and write-surface release.

### Changed
- **Serving topology collapsed from four lanes to two:** a single **public OAuth
  `/mcp`** endpoint (Tailscale-funnel'd HTTPS; OAuth 2.1 with DCR + PKCE; read tools
  always, the gated `commit_note` write tool by scope) used by every remote client,
  plus a **tailnet read companion** (`:8848`, auth-off) for the Obsidian companion and
  the per-prompt recall hook.
- **Default write surface flipped from a 4-prefix allowlist to a blocklist**
  ("write-anywhere-under-guards"): a note may land anywhere in the vault except the
  protected classes; an explicit allowlist is now an opt-in way to *narrow* the
  surface. Gated on a signed blocklist write-surface security review.
- Engine bumped `0.0.4 → 0.0.5`; `__init__.__version__` synced to the authority.

### Added
- **`list_folders`** MCP read tool + **`list-folders`** CLI subcommand: discover the
  vault's folder taxonomy and writable locations (the `writable` flag matches exactly
  what `commit_note` accepts), via a single shared write-surface coercion.
- **`--allow-tailnet-write`**: a bounded opt-in that accepts tailnet membership as the
  write boundary (auth-off write-enabled serve), permitted **only** on a Tailscale
  CGNAT bind; all `commit_note` guards still apply.
- Governance-extension fence in `serialize.py` (refuses `Dockerfile`/`Makefile`/CI
  YAML/lockfiles/`.env*`/`package.json` everywhere) and case-folded protected-dir
  matching, so the blocklist default cannot land an executable/governance file.
- Per-tool MCP `outputSchema` declarations so connectors understand result shapes.

### Removed
- The `:8849` client-credentials Authorization Server lane and its `serve-auth` /
  `auth-add-client` subcommands — folded into the unified public OAuth endpoint.

### Fixed
- The convergence `manual_reindex_recommended` / degraded signal is surfaced in the
  read-tool responses (previously dropped).
- Test fixtures use a CGNAT documentation IP range instead of a real homelab IP.

## [0.0.4] — 2026-06-03

The one-command bring-up and distribution-generic plugin release.

### Added
- **`hypermnesic setup`**: one idempotent command brings the unified public OAuth
  endpoint online — render + start the service, persist the operator consent secret,
  configure the Tailscale funnel, and verify the live HTTPS discovery chain before
  reporting success.

### Changed
- The Claude Code / Codex plugin is now **distribution-generic** — it carries no
  operator hostname and no token; point it at your endpoint with `HYPERMNESIC_MCP_URL`.
- Slimmed to a single neutral `UserPromptSubmit` auto-recall hook.
- README reworked into a first-class quick start for the unified OAuth endpoint + CLI.

## [0.0.3 and earlier] — 2026-06-01 … 2026-06-02

Phase 0 → Phase 2.5 foundation (pre-public, internal milestones).

### Added
- **Hybrid retrieval core:** SQLite FTS5 (lexical) fused with sqlite-vec KNN (dense;
  OpenAI `text-embedding-3-large` @ 1536 dims) via RRF, degrading to lexical-only when
  embeddings are unavailable; entity-resolution and wikilink graph context.
- **Read-only MCP server** binding a specific Tailscale interface (refuses `0.0.0.0`).
- **Git-first `commit_note` write kernel:** diff-or-die frontmatter gate,
  protected-path write guard, append-only audit log, single-writer locks,
  worktree-isolated reindex — the index is always a rebuildable projection of the git
  tree (a reindex never loses a committed write).
- **Read-time convergence:** every read catches the index up to `HEAD` and closes a
  bounded dense slice, so a just-committed note is recall-able without a manual reindex.
- **Role-aware installer** (`single` | `master` | `client`) + an opt-in post-merge
  convergence hook.
- **Human/product surfaces:** thinking-mode, salience + spaced-review digest,
  serendipity connections, always-organized navigation, frictionless capture, and
  multi-format sidecar extraction (PDF/DOCX/XLSX/PPTX/PNG) via permissive extractors.
- **Obsidian companion** (`obsidian-plugin/`): a strictly read-only recall surface.
- **LongMemEval benchmark harness** (`harness/`) and a French/English retrieval-parity
  harness.

[Unreleased]: https://github.com/leonardsellem/hypermnesic/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/leonardsellem/hypermnesic/compare/v0.0.6...v0.1.0
[0.0.6]: https://github.com/leonardsellem/hypermnesic/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/leonardsellem/hypermnesic/releases/tag/v0.0.5
[0.0.4]: https://github.com/leonardsellem/hypermnesic/releases/tag/v0.0.4
