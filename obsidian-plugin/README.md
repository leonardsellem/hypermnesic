# hypermnesic companion (Obsidian plugin)

A strictly **read-only**, **desktop** Obsidian plugin: a calm recall surface over
your tailnet **hypermnesic** index. As you write, it surfaces related notes and a
checkable "you may be reinventing this" nudge — and it **never writes your vault**.

## What it does

- **Pause-triggered** recall (never per-keystroke) of the block around your
  cursor — findings hold while you keep typing and refresh when you pause.
- A calm **status-bar** indicator that expands to a popover; an **opt-in
  sidebar**; an optional editor inline marker.
- **Thinking-mode** — related notes, Socratic questions, and tensions, with a
  visible `wrote: false` badge — and **selection-recall** (recall about the
  highlighted text).
- An **interrogable reinvention nudge**: it expands to the matched snippet and a
  one-hop context peek so the claim is checkable, and it is mutable per note
  (view-only — muting is plugin-local and never edits the note).
- **Forgetting-curve ranking**: genuinely stale-but-relevant notes surface above
  ones you just touched.

## Read-only by construction

This plugin **never writes the vault**. Every engine call routes through a hard
allowlist (`src/core.ts`) of the read tools — **`search` / `build_context` /
`think`** — and it performs no vault modify/create/delete/append/trash and no
adapter writes. The write tool (`commit_note`) is registered only on a
write-enabled master and is structurally unreachable from here; any write you
choose to make flows through an agent calling that gated tool, never this plugin.
It also retains no note text between queries. The Python suite
(`tests/test_obsidian_plugin.py`) statically verifies the allowlist and the
no-write guarantee.

## Network use & privacy (please read)

This plugin talks to exactly **one remote service**: your **hypermnesic** MCP
endpoint on your **tailnet** (a Tailscale address you configure). When recall
fires, it **transmits** the text of the block around your cursor (or your current
selection) to that endpoint to find related notes. Nothing else leaves your
device — no analytics, no telemetry, no third party.

It is strictly **opt-in**: the MCP URL is **empty by default**, so the plugin
**transmits nothing off-device until you set the endpoint** in settings. A
provisioned `--role=client` install pre-fills the URL; a manual install starts
empty until you fill it in. The index itself lives on your own master over the
tailnet; the companion only reads it.

## Build & install (manual, desktop)

```bash
cd obsidian-plugin
npm install
npm run build          # esbuild main.ts (+ src/) -> main.js
# copy manifest.json + main.js + styles.css into
#   <vault>/.obsidian/plugins/hypermnesic-companion/
```

Then enable **hypermnesic companion** in Obsidian → Community plugins, open its
settings, and set the **Tailnet MCP URL** to your hypermnesic `serve` endpoint (a
Tailscale address). Until you do, nothing is sent off-device.

## Known gaps (deferred)

- **Mobile read-only recall** (a CodeMirror-6-free subset) — desktop-first this
  phase; the status-bar surface is desktop-only, so the manifest is
  `isDesktopOnly`.
- **MCP OAuth in the plugin** — only the protocol-handler seam is left here; the
  implementation lands with the engine OAuth work.
- **Community-plugin submission** — would need a sample-scaffolding strip and a
  submission pass (the network/account disclosure above is already done).
