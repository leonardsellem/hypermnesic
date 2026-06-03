# hypermnesic plugin (Claude Code + Codex)

Makes **hypermnesic** the default memory layer for coding agents: a skillset that teaches
agents when/how to use it, a lightweight auto-recall hook that surfaces relevant context at
prompt time, and the self-hosted, OAuth2-authenticated tailnet MCP wiring.

## What's inside

```
plugin/
  .claude-plugin/marketplace.json          # the marketplace listing
  plugins/hypermnesic/
    .claude-plugin/plugin.json             # Claude manifest (skills auto-discovered; hooks/MCP auto-loaded)
    .codex-plugin/plugin.json              # Codex manifest (skills + interface)
    skills/hypermnesic-memory/SKILL.md     # the skillset (search/recall/resolve/commit_note, disk-first)
    hooks/hooks.json                       # one UserPromptSubmit auto-recall hook
    hooks/scripts/hypermnesic_agent_hook.py# the auto-recall hook (Claude+Codex, --host)
    .mcp.json                              # self-hosted MCP wiring (OAuth2 client)
```

## How it surfaces memory

- **The SKILL** is the primary surface: its description is always discoverable, and the agent
  reaches for `search` / `build_context` / `think` / `resolve` / `commit_note` when memory is
  relevant. This is the lightweight, on-demand path — no per-turn cost.
- **One auto-recall hook** (`UserPromptSubmit`) adds *optional* proactive recall: when a prompt
  looks memory-relevant AND an endpoint + token are configured, it runs a single bounded search
  and injects the top hits. It is **silent and non-blocking** otherwise (off-topic prompt,
  unconfigured, 401, timeout, no hits) so it never pollutes or blocks a turn. There is no
  SessionStart preamble and no Bash interception — the hook does exactly one thing.

## Configuration (per host)

The auto-recall hook reads its endpoint and token from the environment, so the plugin is
user-neutral and carries no hardcoded host:

- `HYPERMNESIC_MCP_URL` — the MCP `search` endpoint (e.g. `https://<your-host>/mcp`).
- `HYPERMNESIC_MCP_TOKEN` — the bearer token (provisioned out of band; **never** inlined or
  committed). With either unset, the hook stays silent.

The bundled `.mcp.json` wires the MCP server for the host's agents; the token is referenced by
env var / obtained at connect time, never stored in this repo.

## Install (per host)

- **Claude Code:** add this in-repo marketplace and install the `hypermnesic` plugin
  (`claude plugin marketplace add <path>/plugin` → `claude plugin install hypermnesic@hypermnesic`).
- **Codex:** add the marketplace and `codex plugin add hypermnesic@hypermnesic` (the skills
  directory is shared).

The manifest declares no `hooks`/`skills` paths — Claude Code auto-discovers `hooks/hooks.json`
and `skills/`, so the plugin loads cleanly with no duplicate-load conflict.
