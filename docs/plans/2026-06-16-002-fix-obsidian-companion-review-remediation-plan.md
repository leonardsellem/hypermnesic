# Plan — Obsidian companion review remediation (all lights green)

- **Date:** 2026-06-16
- **Status:** Planned
- **Type:** fix
- **Workspace/Project:** LS Ventures · hypermnesic
- **Target repo:** `leonardsellem/hypermnesic-companion` (separate GPL-3.0 repo; the engine repo holds
  only `obsidian-plugin/README.md` as a pointer — all source + file:line refs below are in the
  companion repo).
- **Relations:** **related** LS-1683 (Obsidian directory submission — this remediation gets the
  currently-pending submission approved).

## Context

The Obsidian community-plugin review of the pending `hypermnesic-companion` submission returned
Errors, Warnings, and Recommendations across four areas (Network, Dependencies, and Obfuscation
already **Pass**). The goal is to get **every light green** so the submission is approvable. Work
is grouped into three independent workstreams (the sub-issues).

## Goal

Re-running the Obsidian review (and `eslint-plugin-obsidianmd` / CSS lint locally) reports **no
Errors and no Warnings**; the Recommendations are addressed; a new tagged companion release carries
build provenance + release notes; the submission is approvable.

## Workstream 1 — Source-code + CSS lint green (blocking Errors + Warnings)

`main.ts:243/440/446` carry **both** the unsupported-API error and the floating-promise warning —
fix together. Items:

- **ERROR** `obsidianmd/no-unsupported-api` — `main.ts:243, 440, 446` use APIs newer than the declared
  `minAppVersion`. **Fix:** either bump `minAppVersion` in `manifest.json` to the version that
  introduced those APIs, or refactor to APIs supported at the current floor. Decide per the specific
  API at each site (prefer not raising the floor more than necessary).
- **ERROR** `obsidianmd/prefer-window-timers` (disable not allowed) — `src/think-helpers.ts:95, 99`.
  **Fix:** use `window.setTimeout` / `window.clearTimeout`; remove the eslint-disable.
- **WARNING** floating promises — `main.ts:243, 440, 446`. **Fix:** `await`, `.catch(...)`, or `void`.
- **WARNING** `builtin-modules` should be replaced — `package.json:21`. **Fix:** swap for an
  approved alternative per module-replacements guidance (e.g. drop the dep / use the bundler's
  builtin handling).
- **WARNING** unsafe `any` assignment / argument — `src/core.ts:248, 250`
  (`@typescript-eslint/no-unsafe-assignment` / `-argument`). **Fix:** type the value / narrow before use.
- **WARNING** use `activeDocument` not `document` (popout-window compat) — `src/surfaces/gutter.ts:36`,
  `src/surfaces/reference.ts:260`, `src/surfaces/statusbar.ts:68, 74, 85`.
- **WARNING (CSS)** `text-decoration` only partially supported by Obsidian 1.4.5 — `styles.css:294`.
  **Fix:** use a supported property/longhand, or guard the decoration.

## Workstream 2 — Release provenance + notes

- **RECOMMENDATION** Missing GitHub artifact attestations for `main.js` + `styles.css`. **Fix:** add
  `actions/attest-build-provenance` to the companion's release workflow with `id-token: write` +
  `attestations: write`, attesting the built release assets.
- **RECOMMENDATION** Release has no description. **Fix:** add release notes / a description to the
  release (and a repeatable notes step for future releases).

## Workstream 3 — Clipboard-access disclosure

- **RECOMMENDATION** Behavior: clipboard read/write may expose externally-copied content. **Fix:**
  confirm the clipboard access is intentional + minimal, and **disclose** it to users (README +
  the plugin listing / a data-handling note). Remove the access if not essential.

## Acceptance criteria

- **GIVEN** the companion source after WS1, **WHEN** `eslint-plugin-obsidianmd` + the Obsidian review
  run, **THEN** the two Errors and all Source/CSS Warnings are gone (zero Errors, zero Warnings).
- **GIVEN** a new tagged release after WS2, **WHEN** the Obsidian review inspects it, **THEN** `main.js`
  and `styles.css` have artifact attestations and the release has a description.
- **GIVEN** WS3, **WHEN** the review inspects Behavior, **THEN** clipboard usage is disclosed (or
  removed) and no longer flagged as an undisclosed behavior.
- **GIVEN** all three, **WHEN** the full Obsidian review re-runs, **THEN** every section is Pass and the
  submission is approvable.

## Test & verification plan

- Run `eslint-plugin-obsidianmd` + the companion repo's lint/build gates locally; zero Errors/Warnings.
- CSS lint clean at `styles.css:294`.
- Cut a release via the updated workflow; confirm attestations on `main.js` + `styles.css` and a
  populated release description.
- Re-trigger / await the Obsidian community review; confirm all-green.

## Sequencing

WS1 (blocking Errors) is highest priority; WS2 and WS3 are independent and can run in parallel. All
three land in the companion repo, then a new tagged release (carrying WS1 fixes + WS2 attestations +
notes) is published and the submission re-reviewed.

## Risks & rollback

- *Risk:* raising `minAppVersion` drops older-Obsidian users. *Mitigation:* prefer refactoring to
  supported APIs; bump only if necessary, and by the minimum. *Rollback:* per-workstream revert in the
  companion repo; each is independent.

## Definition of Done (Deployment = Done)

Companion review **all-green** (no Errors/Warnings; Recommendations addressed); a new tagged release
with provenance attestations + notes is live; clipboard usage disclosed; the Obsidian submission is
approvable. **Done only when DEPLOYED + VERIFIED** (re-review green).
