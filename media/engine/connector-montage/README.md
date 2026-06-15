# Connector montage (U7) — "same endpoint, other clients"

Two deliverables for the multi-client story (origin R5):

## 1. The montage still — `one-endpoint-many-clients.svg` / `.png` ✅

A committed, leak-safe still: Claude Code, ChatGPT, and Claude (mobile/web) all
configured against the **one** placeholder endpoint `https://<your-host>.ts.net/mcp`.
Built from the copy-paste configs in [`connectors.md`](connectors.md) +
[`claude-code.mcp.json`](claude-code.mcp.json). No live hosted-client recording — these
are config stills with placeholder URLs only (origin R5: "no live hosted-client
recording").

## 2. The Claude Code client GIF — `../claude-code-client.gif` ⏳ manual GUI capture

This is a **GUI screen recording** of Claude Code calling the live MCP read/write tools
against a loopback master, and is **not `.tape`-scriptable**. It is flagged for manual
capture (do not fabricate frames). To record it:

1. Start the loopback master over the demo vault (same as the hero):
   `hypermnesic serve --enable-write --host 127.0.0.1 --port 8765 --index-db .hypermnesic/index.db --repo .`
2. Point Claude Code at it with [`claude-code.mcp.json`](claude-code.mcp.json)
   (`url` → `http://127.0.0.1:8765/mcp` for the local capture).
3. Screen-record Claude Code calling `search` / `think` and a real `commit_note`.
4. **Sanitize** per [`docs/guides/demo-asset-frame-review-checklist.md`](../../../docs/guides/demo-asset-frame-review-checklist.md):
   no account badge/avatar, no window-title path bar, no real hostname; use a clean
   profile or crop. Then sign off the GIF's row in [`media/.review-log.md`](../../.review-log.md).
