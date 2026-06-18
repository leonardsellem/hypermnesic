# Companion recording setup (U10) — Obsidian

> **UPDATE 2026-06-18 (LS-1778): the STILLS are now scripted, not manual.** Obsidian's official
> CLI (`dev:screenshot`, GA installer 1.12.4) screenshots its own window via CDP — TCC-free and
> repeatable. [`capture-obsidian-stills.sh`](capture-obsidian-stills.sh) materializes a disposable
> vault, wires the companion to a loopback master, opens it, drives each surface, and captures
> `thinking-mode.png` / `sidebar.png` / `reinvention-nudge.png` / `obsidianmd-still.png` plus the
> read-only-proof companion still. Prereq: Obsidian **installer ≥ 1.12.4** (the in-app "Check for
> updates" only bumps the asar — reinstall from https://obsidian.md/download). `read-only-proof.gif`
> is the scripted terminal `.tape` composited (`ffmpeg vstack`) with that companion still.
> **Only the live-motion GIFs remain manual**: `companion-hero.gif` (graph edge animating) and
> the marketplace `demo.gif` (status-bar popover on pause) need real window *video* — see §3.

The remaining manual assets are **Obsidian GUI screen recordings**; this file is the
reproducibility substitute (origin R10 is exempt-by-medium for companion recordings). Review every
frame against
[`../../docs/guides/demo-asset-frame-review-checklist.md`](../../docs/guides/demo-asset-frame-review-checklist.md)
and sign off in [`../.review-log.md`](../.review-log.md).

## 1. Open the demo vault

1. Copy the seed to a scratch location so the demo never touches a real vault:
   `cp -R media/companion/demo-vault-seed /tmp/companion-demo-vault`
2. Obsidian → **Open folder as vault** → `/tmp/companion-demo-vault`.
3. Open **Graph view** (left ribbon). You should see ~10 connected nodes (daily notes
   hubbing out to people / ideas / projects) — the structure is the proof, so let it breathe
   (increase node size, enable text fade-in).

## 2. Connect the companion (read-only by construction)

The companion is a **read** surface: its tool allowlist is `search` / `build_context` /
`think` only — it has **no write control**. Point it at the master MCP endpoint:

- Local capture: a loopback master — `http://127.0.0.1:8765/mcp`.
- Tailnet: the placeholder `https://<your-host>.ts.net/mcp` (never a real host on screen).

## 3. The two recordings (U11)

### `companion-hero.gif` — a live agent-written note
Split view: **Obsidian graph + note list on the left**, an **agent (Claude Code) calling the
master's `commit_note` on the right**. When the write lands, the new note appears in the
vault and a **graph edge is added live** (R7). Drive the write with the engine helper:
`python media/engine/hero_commit.py --url http://127.0.0.1:8765/mcp --path ideas/atomic-notes.md --summary '...' --body '... links [[ideas/evergreen-notes]] ...'`
(include a `[[wikilink]]` in the body so a new graph edge appears).

### `read-only-proof.gif` — the guard refuses a write
The companion has no write affordance, so do **not** stage a companion-initiated write
(there is none). Instead show the **server-side guard rejecting an agent write to a
protected path** — e.g. drive `commit_note` against `CLAUDE.md` or `.git/config` and capture
the `{"committed": false, "refused": "..."}` refusal — with the companion shown alongside as
the passive read surface that exposes only read controls (AE5: shown, not captioned).

## 4. Sanitize before recording (mandatory)

- Vault name on screen must be the generic demo name (`companion-demo-vault`), never a real
  vault.
- No account badge / avatar / sync status; no window-title path bar; crop or use a clean
  Obsidian profile.
- Companion endpoint shown only as `127.0.0.1` (local) or `<your-host>.ts.net` (placeholder).
- Then OCR-sweep + eyeball every frame and sign off in `../.review-log.md`.

## 5. Marketplace assets (U12) — scripted via `capture-obsidian-stills.sh`

**Prerequisite (met 2026-06-15):** the `hypermnesic-companion` repo is public and its gates
are green (CI + Release `success` on the latest push), so these land in *that* repo — no
deferral. The screenshots are produced by [`capture-obsidian-stills.sh`](capture-obsidian-stills.sh)
(Obsidian CLI `dev:screenshot`, installer ≥ 1.12.4) — captured, not fabricated — except the
top-of-README **`demo.gif`** (pause-triggered status-bar recall popover), which is live motion and
still needs a real screen recording.

Target the [Obsidian community-plugin directory conventions](https://docs.obsidian.md/Plugins/Releasing/Submission+requirements+for+plugins):
a clear top-of-README **demo GIF or hero screenshot**, then feature screenshots. The
companion README currently has **no images** — these fill that gap.

Capture against `/tmp/companion-demo-vault` (sanitized per §4), then add to the
**`hypermnesic-companion` repo** README (its own conventions + gates):

| Asset (in `hypermnesic-companion`) | Shows |
|---|---|
| `docs/media/demo.gif` (top of README) | Pause-triggered recall: type, pause, related notes appear in the status-bar popover. |
| `docs/media/thinking-mode.png` | The dockable thinking-mode panel — related notes, Socratic questions, the `wrote: false` badge. |
| `docs/media/sidebar.png` | The opt-in sidebar with first-class `internal-link` references + hover page-preview. |
| `docs/media/reinvention-nudge.png` | The interrogable reinvention nudge expanded to its matched snippet. |

Plus the **r/ObsidianMD still** in this repo: `media/companion/obsidianmd-still.png` — the
vault + **graph view** + an **agent-written note** together (one frame; reuse the
`companion-hero.gif` end-state).

Wiring the captured images into the companion README is a small cross-repo follow-up once
the frames exist + pass review.
