# Companion recording setup (U10) — Obsidian, GUI, manual

The companion assets (U11, U12) are **Obsidian GUI screen recordings**. Obsidian is not a
terminal, so these are **not `.tape`-scriptable** — this file is the reproducibility
substitute (origin R10 is exempt-by-medium for companion recordings). Anyone can re-record
by following these steps; review every frame against
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
