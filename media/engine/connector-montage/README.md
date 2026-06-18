# Connector montage (U7) — "same endpoint, other clients"

Two deliverables for the multi-client story (origin R5):

## 1. The montage still — `one-endpoint-many-clients.svg` / `.png` ✅

A committed, leak-safe still: Claude Code, ChatGPT, and Claude (mobile/web) all
configured against the **one** placeholder endpoint `https://<your-host>.ts.net/mcp`.
Built from the copy-paste configs in [`connectors.md`](connectors.md) +
[`claude-code.mcp.json`](claude-code.mcp.json). No live hosted-client recording — these
are config stills with placeholder URLs only (origin R5: "no live hosted-client
recording").

## 2. The Claude Code client GIF — `../claude-code-client.gif` ⏳ scripted (render-pending auth)

This shows the Claude Code TUI calling the live MCP read/write tools against a loopback
master. Originally flagged "manual / not `.tape`-scriptable"; the LS-1778 research corrected
that — **Claude Code is a TUI in a real terminal, so VHS drives it** like any other shell
program. It is now scripted in [`../claude-code-client.tape`](../claude-code-client.tape)
(do not fabricate frames):

- The tape starts the loopback master, registers it with
  `claude mcp add --transport http --scope local hypermnesic http://127.0.0.1:8765/mcp`
  (the `127.0.0.1` write⇒auth exemption means no auth/consent on screen), launches the
  Claude Code TUI with a prompt that calls `search` → `think` → a real `commit_note`, and
  uses `Wait+Screen /commit_note/` then `Wait+Screen /committed|wrote/` so it is tolerant of
  model latency rather than racing fixed `Sleep`s.
- **To render:** `claude login` first (a standalone `claude` invocation needs its own
  Anthropic auth — the agent session's token is not reusable by a subprocess), then
  `vhs media/engine/claude-code-client.tape`. Model wording is non-deterministic, so
  re-render until clean (the committed `.tape` keeps it re-runnable → R10).
- **Sanitize** per [`docs/guides/demo-asset-frame-review-checklist.md`](../../../docs/guides/demo-asset-frame-review-checklist.md):
  no account badge/avatar, no window-title path bar, no real hostname; use a clean
  profile or crop. Then sign off the GIF's row in [`media/.review-log.md`](../../.review-log.md).

The static config still [`claude-code.mcp.json`](claude-code.mcp.json) remains the
placeholder-URL reference for the montage still (§1).
