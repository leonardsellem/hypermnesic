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
  lanes is **superseded**.
- **License:** proprietary/private today; the public license (**AGPL-3.0**) is **staged,
  not live** — see [`launch/`](launch/).

## Durable reference (start here)

| Topic | Doc |
|---|---|
| What it is, quick start, benchmarks | [`../README.md`](../README.md) |
| Why it's different (positioning) | [`why-hypermnesic.md`](why-hypermnesic.md) |
| How it works (architecture + diagram) | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Getting started (3 paths + failure modes) | [`guides/getting-started.md`](guides/getting-started.md) |
| MCP tool reference | [`reference/mcp-tools.md`](reference/mcp-tools.md) |
| CLI reference | [`reference/cli.md`](reference/cli.md) |
| Configuration reference | [`reference/configuration.md`](reference/configuration.md) |
| Security policy + threat model | [`../SECURITY.md`](../SECURITY.md), [`threat-model-commit-note.md`](threat-model-commit-note.md) |
| Glossary | [`../GLOSSARY.md`](../GLOSSARY.md) |
| Contributing / agent contract | [`../CONTRIBUTING.md`](../CONTRIBUTING.md), [`../AGENTS.md`](../AGENTS.md) |
| Changelog | [`../CHANGELOG.md`](../CHANGELOG.md) |
| Deploy (current) | [`unified-oauth-mcp-deploy-runbook.md`](unified-oauth-mcp-deploy-runbook.md) |
| Security reviews (dated deltas) | [`2026-06-03-unified-write-anywhere-security-review.md`](2026-06-03-unified-write-anywhere-security-review.md), [`2026-06-03-blocklist-write-surface-security-review.md`](2026-06-03-blocklist-write-surface-security-review.md) |

## Public-launch staging

[`launch/`](launch/) holds everything gated on the public flip — the staged AGPL-3.0
license text, the one-PR flip runbook, the launch checklist, and the staged
`CITATION.cff`. Nothing there is live; the live `LICENSE` stays proprietary until the
flip PR. See [`launch/public-flip-runbook.md`](launch/public-flip-runbook.md).

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
> gate artifacts, dated reviews, and the archived docs) still contain operator-specific
> homelab values. They are inert while the repo is private; before the public flip they
> are scrubbed or pruned per [`launch/public-launch-checklist.md`](launch/public-launch-checklist.md)
> (the `scripts/preflight_public_scan.py --strict` gate covers them, including
> `archive/`). The full taxonomy relocation of the history tree is deferred follow-up.
