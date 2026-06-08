# Security Policy

hypermnesic self-hosts a memory layer over an authenticated MCP endpoint with a
git-first write path. We take the security of that surface seriously.

## Reporting a vulnerability

**Do not open a public issue for security problems.** Report privately, by either:

- **Email** the maintainer directly: **leonard@sellem.me** (PGP available on request),
  or
- **GitHub private vulnerability reporting** — use *Security → Report a vulnerability*
  on the repository. (This is enabled at the public launch; while the repository is
  private, use email.)

Please include: affected version, deployment shape (self-hosted endpoint / local CLI /
plugin client), a description of the issue, and reproduction steps. **Never include
live tokens, hostnames, or IPs** in a report.

We aim to acknowledge a report within a few days, agree on a disclosure timeline, and
credit reporters who wish to be named once a fix ships.

## Supported versions

The engine is pre-1.0 (`0.0.x`); only the **latest released version** is supported.
There are no backports — please reproduce on the latest before reporting.

## Security model (where to read deeper)

The write surface is the highest-value target. Its design and the accepted-risk
decisions are documented and signed off:

- **Threat model (living):** [`docs/threat-model-commit-note.md`](docs/threat-model-commit-note.md)
  — the `commit_note` write surface: protected-path escalation, ingested-content
  prompt injection, frontmatter churn, actor spoofing, log leak, path traversal,
  concurrent-writer corruption, credential exposure, crash recovery. Carries dated
  topology amendments.
- **Security deltas (chronological):**
  - [`docs/2026-06-03-unified-write-anywhere-security-review.md`](docs/2026-06-03-unified-write-anywhere-security-review.md)
    — write-anywhere re-review for the unified public OAuth endpoint.
  - [`docs/2026-06-03-blocklist-write-surface-security-review.md`](docs/2026-06-03-blocklist-write-surface-security-review.md)
    — allowlist → blocklist write-surface flip (governance-extension fence; case-fold).
  - [`docs/oauth-as-finding.md`](docs/oauth-as-finding.md) — native-primitive evaluation
    of the OAuth Authorization Server.

These reviews carry `amends:` / `signed_off:` frontmatter forming the audit chain; they
are immutable deltas (a new finding is a new dated review, not an edit).

## Current security posture (summary)

- **Serving topology (current):** one **public OAuth `/mcp`** endpoint (OAuth 2.1, DCR
  + PKCE, RFC 8707 audience-bound tokens, operator-consent gate on the `write` scope)
  plus a **tailnet read companion** (`:8848`, auth-off, read-only). The retired
  `:8849` client-credentials AS lane is gone. The public AS supports both confidential
  clients and public clients registered without a client secret; write access remains
  consent- and scope-gated.
- **Write requires auth:** `write_enabled ⇒ auth-required` on any non-loopback bind
  (mirroring the `0.0.0.0` refusal). `--allow-tailnet-write` is a bounded opt-in that
  accepts tailnet membership as the write boundary, permitted only on a CGNAT bind.
- **Write is bounded:** a blocklist guard (protected-path + governance-file fence),
  a diff-or-die frontmatter gate, single-writer locks, and an append-only audit log
  (summaries only — never bodies, never credentials).
- **Credentials** (OpenAI key, OAuth consent secret, tokens) are read from the
  environment / a gitignored `.env` only — never written to the index, audit log, or
  any output.
