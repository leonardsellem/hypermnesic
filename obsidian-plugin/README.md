# hypermnesic companion (Obsidian plugin) — U25 / Phase 2b

A thin, **read-only**, **desktop** Obsidian plugin for *retrieval-while-writing*
(H2). As you write, it debounces and asks the existing tailnet **hypermnesic MCP**
(`search` / `build_context`) for related notes, and warns when you may be
**reinventing** an existing note.

## What it does

- On `editor-change` (debounced, default 1200 ms) it sends the current note's text
  (bounded to 4000 chars) to the read-only MCP `search` tool.
- Renders related notes in a right-sidebar panel; clicking opens the existing note.
- If the top hit's similarity ≥ a threshold, shows **"⚠ You may be reinventing
  [[X]]"**.

## Read-only by construction

This plugin **never writes the vault**. It calls **only** the two read tools
(`search`, `build_context`) — a hard allowlist in `callTool` refuses anything else
— and performs no `vault.modify/create/delete/append/trash` and no
`adapter.write`. Any write the owner decides to make flows through hypermnesic's
**U18 git proposal path**, never from this plugin. It retains no note text between
calls.

The Python test suite includes a scripted read-only assertion
(`tests/test_obsidian_plugin.py`) that statically verifies this.

## Build & install (manual, desktop)

The plugin is a single `main.ts` with no committed build tooling (no
`package.json` yet). Bundle it to `main.js` with a one-off esbuild invocation:

```bash
cd obsidian-plugin
npx esbuild main.ts --bundle --format=cjs --target=es2018 --external:obsidian --outfile=main.js
# copy manifest.json + main.js into <vault>/.obsidian/plugins/hypermnesic-companion/
```

Then enable **hypermnesic companion** in Obsidian → Community plugins. The plugin
ships with **no default endpoint** — set the **Tailnet MCP URL** to your
hypermnesic `serve` endpoint (a Tailscale address) before use. Until it's set, no
note text leaves your device.

## Known gaps (deferred)

- **Mobile parity** (CodeMirror 6) — desktop-first this phase (R-5).
- **Plugin↔MCP access control** (SEC-003) — the tailnet membership is the boundary
  for Phase 2; revisit with a Tailscale ACL tag / bearer token if the tailnet
  widens.
