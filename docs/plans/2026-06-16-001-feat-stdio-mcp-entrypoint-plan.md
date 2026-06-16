# Plan — stdio MCP entrypoint (`hypermnesic mcp --stdio`)

- **Date:** 2026-06-16
- **Status:** Planned
- **Type:** feat
- **Workspace/Project:** LS Ventures · hypermnesic
- **Relations:** **blocks** LS-1683 (directory submissions / official MCP Registry)

## Context & motivation

hypermnesic serves MCP over **streamable-http only** — `src/hypermnesic/mcp_server.py` builds a
FastMCP app, and `hypermnesic serve` requires `--host` + `--index-db` and runs a persistent HTTP
service (OAuth-secured on the public lane). There is **no stdio transport**.

Two costs of HTTP-only:

1. **Blocks the official MCP Registry listing (LS-1683).** `mcp-publisher init` models a server as a
   `pypi` package with `transport: stdio`; the hosted-`remotes` lane requires a globally-unique URL
   (the generic `https://{host}/mcp` template collides — verified `400` on publish). A self-hosted
   HTTP service has no honest `server.json` today.
2. **High local-adoption friction.** Every stdio MCP client (Claude Desktop, etc.) expects a
   spawnable stdio server; today a user must stand up Tailscale + OAuth to connect anything.

A stdio entrypoint — spawning the **same** engine tools against a **local vault**, no OAuth — fixes
both: an honest `pypi + stdio` registry entry, and a zero-setup drop-in for stdio clients. It is
on-brand with files-are-truth / local-first.

## Goal

`hypermnesic mcp --stdio` (a new `mcp` CLI command / stdio transport) starts a stdio MCP server
exposing the engine's existing read tools (`search`, `think`, `build_context`, `resolve`,
`list_folders`, `retrieve`) **plus** the gated git-first `commit_note` write tool, against a local
vault + index-db, **reusing the existing tool registrations** — a sibling to streamable-http `serve`.

## Scope & non-goals

**In scope:** stdio transport wiring reusing `mcp_server.py` tool registrations; a `hypermnesic mcp`
CLI command (local index-db/vault resolution like `serve`); local write⇒auth exemption covering
`commit_note` over stdio (no OAuth); a stdio smoke test; a reworked registry `server.json`
(`pypi + stdio`) that passes `mcp-publisher validate`; doc updates.

**Non-goals:** changing the HTTP/OAuth lane; remote stdio; auth/scope redesign; publishing to the
registry (that is LS-1683, unblocked once this ships); packaging changes beyond what stdio needs.

## Design / approach

- Reuse the existing FastMCP construction in `mcp_server.py` (tools are already registered); add a
  path that runs it with the SDK's **stdio** transport instead of streamable-http, parameterized by a
  local index-db. Factor the transport-agnostic server build away from HTTP/OAuth-specific setup if
  needed — **keep the HTTP path unchanged**.
- `commit_note` over stdio is local-only → covered by the existing 127.0.0.1/local write⇒auth
  exemption; no OAuth issuer/consent on stdio.
- New `cli.py` command `hypermnesic mcp` (with `--stdio` and an index-db/vault option consistent with
  `serve` / `local-proof`), documented alongside `serve`.

## Implementation outline (TDD-first)

1. **U1 — stdio transport wiring.** Failing test: a stdio MCP client (in-process SDK client over the
   stdio server) gets a non-empty `tools/list` including the read tools + `commit_note`. Implement the
   transport-agnostic server build + stdio run.
2. **U2 — `hypermnesic mcp` CLI command.** Failing test: the command parses, resolves a local
   index-db, and launches the stdio server. Implement in `cli.py`.
3. **U3 — read + write smoke over stdio.** Failing test: over stdio, a read tool returns a grounded
   result from a fixture vault, and `commit_note` performs a local git-first write (or dry-run) with no
   OAuth. Implement any local-exemption glue.
4. **U4 — registry `server.json` rework.** Replace the colliding `remotes` draft with a `pypi + stdio`
   `server.json` (identifier `hypermnesic`, version pinned); `mcp-publisher validate` passes.
5. **U5 — docs (same PR):** `docs/reference/mcp-tools.md`, `docs/reference/cli.md`, README (How it
   works + quickstart: stdio drop-in for Claude Desktop), `ARCHITECTURE.md` serving section, `CHANGELOG`.

## Test & verification plan

- New stdio tests under `tests/` (`--import-mode=importlib`), offline/deterministic (OpenAI key
  neutralized → dense degrades to lexical), driving the stdio server via the SDK's in-process client.
- Full gate set green: `uv run ruff check .` · `uv run python scripts/check_version_consistency.py` ·
  `uv run pytest` · `uv run python scripts/license_scan.py` · `uv run python scripts/preflight_public_scan.py`.
- `mcp-publisher validate` passes on the reworked `server.json`.

## Acceptance criteria

- **GIVEN** a local vault + built index-db, **WHEN** `hypermnesic mcp --stdio` runs, **THEN** a stdio
  MCP server starts and a stdio client sees the read tools + `commit_note` via `tools/list`.
- **GIVEN** the stdio server, **WHEN** a client calls a read tool, **THEN** it returns a grounded,
  source-cited result from the local vault; **AND WHEN** it calls `commit_note` locally, **THEN** the
  git-first write (or dry-run) succeeds with no OAuth.
- **GIVEN** the reworked `pypi + stdio` `server.json`, **WHEN** `mcp-publisher validate` runs, **THEN**
  it passes (an honest, publishable entry).
- **GIVEN** the change, **WHEN** the full gate set runs, **THEN** all six gates pass and docs are
  updated in the same PR.

## Dependencies

- **Blocks** LS-1683 (official MCP Registry channel — publish proceeds once a valid `pypi + stdio`
  `server.json` exists).
- **Blocked by:** none.

## Risks & rollback

- *Risk:* HTTP/OAuth scaffolding entangled with tool registration → refactor pressure. *Mitigation:*
  keep the HTTP path untouched; factor only the transport-agnostic build. *Rollback:* additive — revert
  the `mcp` command + stdio module; HTTP lane unaffected.
- *Risk:* `commit_note` scope-gating assumptions differ on stdio. *Mitigation:* rely on the existing
  local write⇒auth exemption; cover with the U3 test.

## Definition of Done (Deployment = Done)

Merged to `main`; full gate set green on CI; `hypermnesic mcp --stdio` verified against a fixture
vault; `mcp-publisher validate` green on the new `server.json`; docs updated; LS-1683 registry channel
unblocked. **Done only when DEPLOYED + VERIFIED.**
