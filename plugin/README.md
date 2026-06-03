# hypermnesic plugin (Claude Code + Codex)

Makes **hypermnesic** the default memory layer for coding agents: a skillset that teaches
agents when/how to use it, a lightweight auto-recall hook that surfaces relevant context at
prompt time, and OAuth-discovery MCP wiring (point it at your endpoint, log in once in a
browser, then silent refresh).

## What's inside

```
plugin/
  .claude-plugin/marketplace.json          # the marketplace listing
  plugins/hypermnesic/
    .claude-plugin/plugin.json             # Claude manifest (skills auto-discovered; hooks/MCP auto-loaded)
    .codex-plugin/plugin.json              # Codex manifest (skills + interface)
    skills/hypermnesic-memory/SKILL.md     # the skillset (search/build_context/think/resolve/list_folders/commit_note, disk-first)
    hooks/hooks.json                       # one UserPromptSubmit auto-recall hook
    hooks/scripts/hypermnesic_agent_hook.py# the auto-recall hook (Claude+Codex, --host)
    .mcp.json                              # OAuth-discovery MCP wiring (env-templated URL, no host, no token)
```

## How it surfaces memory

- **The SKILL** is the primary surface: its description is always discoverable, and the agent
  reaches for `search` / `build_context` / `think` / `resolve` / `list_folders` / `commit_note`
  when memory is relevant. This is the lightweight, on-demand path — no per-turn cost.
- **One auto-recall hook** (`UserPromptSubmit`) adds *optional* proactive recall: when a prompt
  looks memory-relevant AND an endpoint + token are configured, it runs a single bounded search
  and injects the top hits. It is **silent and non-blocking** otherwise (off-topic prompt,
  unconfigured, 401, timeout, no hits) so it never pollutes or blocks a turn. There is no
  SessionStart preamble and no Bash interception — the hook does exactly one thing.

## Configuration (per host)

The plugin is **distribution-generic** — it carries no operator hostname and no token. Point it
at your own endpoint with one environment variable:

- `HYPERMNESIC_MCP_URL` — your hypermnesic MCP endpoint (e.g. `https://<your-host>/mcp`). The
  bundled `.mcp.json` templates the URL from this var (`${HYPERMNESIC_MCP_URL:-…}`).

### First connect (one browser login)

The `.mcp.json` is **OAuth-discovery-only**: there is no `auth` block and no static token. On the
first connect the agent host (Claude Code / Codex / a cloud connector) discovers the OAuth
Authorization Server from `{type, url}` alone, opens a browser once for you to authorize (read by
default; approve **write** at the consent page to enable `commit_note`), then stores and silently
refreshes the token. A static `Authorization` header is deliberately omitted — it would suppress
that OAuth discovery.

> The auto-recall hook (below) is the one exception: on a remote device it reads
> `HYPERMNESIC_MCP_TOKEN` for its bounded read, or rides the tailnet read route — see the hook
> section. The MCP tool wiring itself needs no token.

## Install (per host)

- **Claude Code (recommended — straight from GitHub):** no local checkout needed —
  `claude plugin marketplace add leonardsellem/hypermnesic` → `claude plugin install hypermnesic@hypermnesic`.
  This resolves the repo-root [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json),
  a git-backed source, so the plugin checkout is content-addressed and reused across sessions
  (a local `directory` source re-materializes a fresh checkout every session).
- **Local checkout / Codex:** add the in-repo `plugin/` directory as a marketplace
  (`claude plugin marketplace add <path>/plugin`, `codex plugin marketplace add <path>/plugin`)
  → `… plugin install hypermnesic@hypermnesic`. The skills directory is shared.

> **Two marketplace manifests — intentional and drift-proofed.** Claude Code only discovers
> `marketplace.json` at a checkout *root*, never in a subdirectory, so the repo carries one at
> [`./.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) (enables the GitHub
> source above) **in addition to** this `plugin/.claude-plugin/marketplace.json` (the local
> `plugin/`-directory source). The root manifest points its plugin `source` at
> `./plugin/plugins/hypermnesic` and deliberately lists only `name`/`source` — `version` and
> `description` live solely in `plugin/plugins/hypermnesic/.claude-plugin/plugin.json`, so a
> version bump touches one file and the two manifests cannot drift.

The manifest declares no `hooks`/`skills` paths — Claude Code auto-discovers `hooks/hooks.json`
and `skills/`, so the plugin loads cleanly with no duplicate-load conflict.
