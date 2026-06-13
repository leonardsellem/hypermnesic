---
title: "Handoff: companion directory publishing — U9 + U10 (gated tail)"
type: handoff
status: open
date: 2026-06-02
origin: docs/plans/2026-06-02-010-feat-companion-directory-publishing-plan.md
---

# Handoff — companion directory publishing: the gated tail (U9 + U10)

U1–U8 shipped this session (plugin repo extracted, licensed GPL-3.0, packaged,
read-only proof ported + green CI, monorepo cut over). U9 and U10 were
**deliberately deferred** — they are irreversible / outward-facing and U9 is
owned by the separate engine open-sourcing effort. This is the actionable
checklist to finish.

## State at handoff

- **Plugin repo:** `leonardsellem/hypermnesic-companion` exists, is **PRIVATE**,
  default branch `main`, **CI green** (Node 24). It is not yet public and has no
  release tag.
- **Engine repo:** `leonardsellem/hypermnesic` is still **private** (this
  monorepo). Not yet AGPL, not yet publicly installable.
- **Monorepo:** plugin source retired to a pointer; read-only proof lives only in
  the plugin repo now (no coverage gap — U4 landed before U8).

## Pre-conditions this session stopped before (do these first)

1. **Flip the plugin repo public.** Per the session boundary, the plugin repo was
   left private for review. It was created as a **fresh repo with no inherited
   history** (U1), so the public flip carries no pre-scrub homelab IP — but still
   eyeball the 7 commits before flipping. `gh repo edit leonardsellem/hypermnesic-companion --visibility public`.

2. **Decide `minAppVersion`** (brainstorm flagged "confirm before release").
   `obsidianmd/no-unsupported-api` lint warns that `Workspace.revealLeaf` (used in
   3 UI spots) requires Obsidian **1.7.2**, while the manifest declares **1.5.0**.
   It *runs* on 1.5.0 (it became async in 1.7.2; the calls are fire-and-forget UI),
   so 1.5.0 is functionally valid. Either keep 1.5.0, or bump `minAppVersion` to
   `1.7.2` in `manifest.json` **and** update `versions.json` (`"0.3.0": "1.7.2"`)
   to silence the warning and be strictly correct. The Obsidian release bot does
   not hard-fail on this, but reviewers may note it.

3. **(Optional) Lockfile npm-version coverage.** CI/release are pinned to Node 24
   (npm 11) because the committed `package-lock.json` dedupes `vitest`→`vite@8`'s
   *optional* `esbuild` (`^0.27||^0.28`) onto the build's `esbuild@0.20.2` — valid
   under npm 11, rejected by npm 10 under `npm ci`. For broader npm/Node coverage,
   regenerate the lock so vite gets a satisfying esbuild (e.g. pin
   `obsidian`/`@codemirror/*` to their current working versions to avoid the
   unrelated peer conflict on a from-scratch resolve, or bump the build's esbuild
   to `^0.28`). Not required for a working release.

---

## U9 — Minimal AGPL engine release (R7). **Gates U10.**

Make the engine publicly installable under AGPL-3.0 so the plugin README's engine
link resolves and directory users have something to run.

**Hard precondition — full-history secrets/IP audit before any public flip
(IRREVERSIBLE).**

- Tooling is **not installed on this machine** — install first:
  `gitleaks` and/or `trufflehog`, plus `git-filter-repo` for remediation.
- Scan the **full object store across all refs**, not a HEAD grep:
  - `gitleaks detect --source . --log-opts="--all"`
  - `trufflehog git file://. --branch=all` (or `trufflehog git <url> --only-verified`)
- **Pass criterion:** zero live credentials **and** zero private IPs outside IANA
  documentation ranges. Known specific risk: the pre-scrub homelab Tailscale IP
  **`<your-host>.ts.net`** in old plugin-source commits.
- **Remediation:** `git-filter-repo` history rewrite, or prefer a **fresh
  clean-history public repo** if the rewrite scope is large.
- Treat the public flip as **permanent disclosure**.

**Minimal scope (the rest is the separate open-sourcing effort):**
- `LICENSE` → `AGPL-3.0-or-later`.
- Engine `README.md` → public-facing install instructions the plugin links to;
  note the optional future commercial dual-license.
- Make the repo public (after the audit passes).

**Verify:** a stranger can find, install, and run the engine under AGPL; the
plugin README's engine link (`https://github.com/leonardsellem/hypermnesic`)
resolves.

---

## U10 — Directory submission PR (R12). Needs U9 + a published release.

**Preflight (all must hold):**
1. Engine publicly installable under AGPL (U9 done).
2. Plugin repo **public**.
3. A **published** GitHub release exists with `main.js` + `manifest.json` +
   `styles.css` attached as individual assets. To create it:
   - `cd hypermnesic-companion && npm version 0.3.0` (or the next version) — runs
     `version-bump.mjs`, tags **without** a leading `v` (`.npmrc`
     `tag-version-prefix=""`).
   - `git push --follow-tags` → `release.yml` builds and creates a **draft**
     release → **publish the draft** in the GitHub UI (the resolver needs it
     published, not draft).
4. Verify `id` `hypermnesic-companion` is **unique** in the current
   `obsidianmd/obsidian-releases` `community-plugins.json` (unverified assumption
   in origin). If taken: rename `id` + repo *before* submitting (cheap now, costly
   after listing).

**The PR:** fork `obsidianmd/obsidian-releases`, append this entry to
`community-plugins.json`, open the PR:

```json
{
	"id": "hypermnesic-companion",
	"name": "Hypermnesic Companion",
	"author": "Leonard Sellem",
	"description": "Surface read-only, pause-triggered related notes and an interrogable reinvention nudge from your tailnet hypermnesic index as you write. Never writes the vault.",
	"repo": "leonardsellem/hypermnesic-companion"
}
```

**Bot feedback loop:** address findings by publishing **incremented releases**
(`npm version <patch>` → push tag → publish release), never by re-submitting the
PR. The listing is a one-time slot-claim; later changes ship as ordinary releases.

**Verify:** the automated validation bot passes (covers AE5) and the plugin
becomes installable from the community directory.
