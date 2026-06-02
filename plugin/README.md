# hypermnesic plugin (Claude Code + Codex)

Makes **hypermnesic** the default memory layer for coding agents: a skillset that teaches
agents when/how to use it, auto-query hooks that surface relevant context automatically, and
the self-hosted, OAuth2-authenticated tailnet MCP wiring. It replaces gbrain — the plugin
never calls gbrain.

## What's inside

```
plugin/
  .claude-plugin/marketplace.json          # the marketplace listing
  plugins/hypermnesic/
    .claude-plugin/plugin.json             # Claude manifest (skills + hooks [+ mcpServers])
    .codex-plugin/plugin.json              # Codex manifest (skills + interface)
    skills/hypermnesic-memory/SKILL.md     # the skillset (search/recall/resolve/commit_note, disk-first)
    hooks/hooks.json                       # SessionStart + UserPromptSubmit + PreToolUse  (U4)
    hooks/scripts/hypermnesic_agent_hook.py# the auto-query hook (Claude+Codex, --host)   (U4)
    .mcp.json                              # self-hosted MCP wiring (OAuth2 client)        (U5)
```

> Hooks (U4) and the MCP wiring (U5) are added by their respective units; this scaffold (U3)
> is the marketplace + manifests + skillset.

## Reach & auth

The MCP endpoint is **tailnet-only** at `homelab.taildabf2.ts.net/mcp`, fronted by OAuth2.
Both hosts that run agents today — the homelab and the Mac — are on the tailnet. The plugin's
MCP wiring carries the token; **no secret is ever inlined** into a plugin file or an MCP
client config (the token is referenced by env var / obtained at connect time, never stored
in this repo).

## Install (per host)

- **Claude Code:** add this in-repo marketplace and install the `hypermnesic` plugin.
- **Codex:** install via the `.codex-plugin` manifest (the skills directory is shared).

Each host's agent identity is provisioned with an OAuth2 client credential out of band (never
committed). See the engine's install docs for the per-host steps and the Gate-A reach check.
