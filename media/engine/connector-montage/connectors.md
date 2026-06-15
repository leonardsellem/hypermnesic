# One endpoint, every client — connector config (placeholder URLs only)

The montage's claim: the **same** MCP endpoint serves every client. These are the
copy-paste connector configs, all pointing at the one placeholder endpoint
`https://<your-host>.ts.net/mcp`. Swap in your own tailnet host; never a real one here.

## Claude Code / Claude Desktop

[`claude-code.mcp.json`](claude-code.mcp.json) — drop into the project's `.mcp.json`:

```json
{
  "mcpServers": {
    "hypermnesic": {
      "type": "streamable-http",
      "url": "${HYPERMNESIC_MCP_URL:-https://<your-host>.ts.net/mcp}"
    }
  }
}
```

Or one line: `claude mcp add --transport http hypermnesic https://<your-host>.ts.net/mcp`

## ChatGPT (Settings → Connectors)

`Settings → Connectors → Add → Custom connector` → URL `https://<your-host>.ts.net/mcp`

## Claude (mobile / web)

`Settings → Connectors → Add custom connector` → URL `https://<your-host>.ts.net/mcp`

---

All three discover the OAuth Authorization Server from the endpoint and complete the
consent flow on first connect — the read tools (`search` / `build_context` / `think` /
`list_folders`) for any client, plus `commit_note` for a write-approved principal.
