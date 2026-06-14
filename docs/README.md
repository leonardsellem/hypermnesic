# hypermnesic documentation

The front door to the `docs/` tree. It separates **durable reference** (read these) from
**process history** (how we got here), and pins the current truth so a stale process doc
never misleads you.

## Current truth (pin this)

- **Write model:** a **blocklist** (write-anywhere-under-guards) — a note may land anywhere
  except the protected classes (protected-path + governance-file fence). The legacy
  4-prefix allowlist is an opt-in *narrowing*, not the default. Anything describing an
  "allowlist by default" or a `captures/`-quarantine is **superseded**.
- **Serving topology:** **two lanes** — one **public OAuth `/mcp`** endpoint (every remote
  client) + a **tailnet read companion** (`:8848`, read-only). The `:8849`
  client-credentials AS lane is **retired**. Anything describing "tailnet-only" or four
  lanes is **superseded**. The public OAuth lane supports both confidential clients and
  public clients registered without a client secret; its AS metadata advertises that
  public-client token/revocation method.
- **First-run path:** local proof comes before endpoint setup. `hypermnesic local-proof`
  validates a git-backed markdown vault, retrieves a source-grounded answer, shows the
  disposable index path, and previews a dry-run write before remote-client concepts enter
  the flow.
- **Setup diagnosis:** `hypermnesic doctor` / `hypermnesic status` are non-mutating
  diagnostics. They separate local index health, remote reach, OAuth discovery, auth
  challenge, write availability, and client next actions. `setup --resource` defaults to
  `--public-url` for the common endpoint shape.
- **Memory control:** `hypermnesic memory` is the owner control surface for current
  memory: list/inspect, export markdown with provenance, preview/apply git-backed
  forget/delete, revert safe recent single-file writes, view audit/refusal history, and
  answer write-scope questions using the same guard as `commit_note`.
- **Consent and client control:** OAuth consent is a plain, script-free trust page that
  explains read/write scopes, redirect origin, reject/cancel, and revocation. `hypermnesic
  clients` lists secret-free grant metadata and revokes grants; write approval only allows
  `commit_note` requests and never bypasses write guards. The cloud OAuth lane keeps
  restart-survivable DCR/token runtime state in owner-only
  `.hypermnesic/cloud-oauth-state.json`; the listed grant metadata remains secret-free.
- **Plugin hook observability:** the Claude Code / Codex auto-recall hook remains silent and
  non-blocking in prompts, but records non-secret status out-of-band. Owners can inspect stable
  outcome codes or run test recall without reading hook source; MCP OAuth wiring still uses browser
  discovery and does not require a static token.
- **Memory taxonomy:** Hypermnesic is durable project memory. Semantic facts, source episodes,
  procedures, raw captures, generated summaries with source paths, and current-state mirrors belong
  here; short-term session state and behavioural preferences belong in Honcho or an equivalent
  adjacent behavioural memory layer by default.
- **Product proof:** benchmark quality and product operability are separate gates. LongMemEval
  measures retrieval quality; first-class product claims also require local product smoke, offline
  remote contracts, the remote-client smoke checklist, and the first-class product readiness checklist.
- **License:** the engine is **AGPL-3.0-only**. The repository is public after the
  history-rewrite, license-flip, release, and visibility-flip gates recorded in
  [`launch/`](launch/).
- **Public roadmap/community:** GitHub Discussions are the public community surface:
  [welcome](https://github.com/leonardsellem/hypermnesic/discussions/73) and
  [roadmap](https://github.com/leonardsellem/hypermnesic/discussions/74). The roadmap
  discussion is the public direction pin; this docs index remains the reference truth pin.

## Durable reference (start here)

| Topic | Doc |
|---|---|
| What it is, quick start, benchmarks | [`../README.md`](../README.md) |
| Why it's different (positioning) | [`why-hypermnesic.md`](why-hypermnesic.md) |
| How it works (architecture + diagram) | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Getting started (local proof + setup diagnosis + client/plugin failure modes) | [`guides/getting-started.md`](guides/getting-started.md) |
| Memory taxonomy (what belongs here) | [`guides/memory-taxonomy.md`](guides/memory-taxonomy.md) |
| Daily workflows (capture, triage, recall, review, cleanup) | [`guides/daily-workflows.md`](guides/daily-workflows.md) |
| Memory control (inspect/export/forget/revert/audit/write scope) | [`guides/memory-control.md`](guides/memory-control.md) |
| Consent and clients (scopes/reject/revoke/grants) | [`guides/consent-and-clients.md`](guides/consent-and-clients.md) |
| Remote-client smoke checklist | [`guides/remote-client-smoke-checklist.md`](guides/remote-client-smoke-checklist.md) |
| First-class product readiness checklist | [`launch/first-class-product-readiness-checklist.md`](launch/first-class-product-readiness-checklist.md) |
| MCP tool reference | [`reference/mcp-tools.md`](reference/mcp-tools.md) |
| CLI reference | [`reference/cli.md`](reference/cli.md) |
| Configuration reference | [`reference/configuration.md`](reference/configuration.md) |
| Security policy + threat model | [`../SECURITY.md`](../SECURITY.md), [`threat-model-commit-note.md`](threat-model-commit-note.md) |
| Glossary | [`../GLOSSARY.md`](../GLOSSARY.md) |
| Contributing / agent contract | [`../CONTRIBUTING.md`](../CONTRIBUTING.md), [`../AGENTS.md`](../AGENTS.md) |
| Changelog | [`../CHANGELOG.md`](../CHANGELOG.md) |
| Deploy (current) | [`unified-oauth-mcp-deploy-runbook.md`](unified-oauth-mcp-deploy-runbook.md) |
| Agent plugins and hook status | [`../plugin/README.md`](../plugin/README.md) |
| Public community and roadmap | [Welcome discussion](https://github.com/leonardsellem/hypermnesic/discussions/73), [roadmap discussion](https://github.com/leonardsellem/hypermnesic/discussions/74) |
| Product/design reports | [`reports/2026-06-04-hypermnesic-product-design-review.md`](reports/2026-06-04-hypermnesic-product-design-review.md) |
| Security reviews (dated deltas) | [`2026-06-03-unified-write-anywhere-security-review.md`](2026-06-03-unified-write-anywhere-security-review.md), [`2026-06-03-blocklist-write-surface-security-review.md`](2026-06-03-blocklist-write-surface-security-review.md) |

## Public-launch staging

[`launch/`](launch/) records the completed public-flip gates, the remaining public-surface
follow-ups, the `v0.1.0` GitHub Release notes, and the staged copies used to land the live
AGPL license and `CITATION.cff`. The live root `LICENSE` and `CITATION.cff` now reflect
the AGPL flip, and repository visibility is public. See
[`launch/public-flip-runbook.md`](launch/public-flip-runbook.md) and
[`launch/public-launch-checklist.md`](launch/public-launch-checklist.md).

## Process history (how we got here — not current truth)

These record the path and are not maintained as reference. Treat them as history; when
they conflict with the "current truth" above, the pins above win.

- **Brainstorms** ([`brainstorms/`](brainstorms/)) — the per-feature "what to build".
- **Plans** ([`plans/`](plans/)) — the per-phase "how to build", the authoritative scope
  of record at the time each was written.
- **Gate artifacts** ([`gate-artifacts/`](gate-artifacts/)) — recorded gate evidence.
- **Handoffs** (`handoff-macbook-*.md`, [`handoffs/`](handoffs/)) — cross-machine session
  handoffs.
- **Archive** ([`archive/`](archive/)) — superseded docs kept for the record, each with a
  pointer banner to its replacement.
- `implementation-notes.md` (repo root) — the narrative build log; release history is
  [`../CHANGELOG.md`](../CHANGELOG.md).

> **Note for the public flip.** Several process-history docs (handoffs, deploy runbooks,
> gate artifacts, dated reviews, and the archived docs) previously contained
> operator-specific homelab values. They were scrubbed or pruned per
> [`launch/public-launch-checklist.md`](launch/public-launch-checklist.md), and the
> `scripts/preflight_public_scan.py --strict` gate covers them, including `archive/`.
> The full taxonomy relocation of the history tree is deferred follow-up.
