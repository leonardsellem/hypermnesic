---
title: "Public launch checklist"
status: live
audience: operator
note: >
  LIVE. This checklist records the public flip state. Pair with
  public-flip-runbook.md (the ordered mechanical steps).
---

# Public launch checklist

Run top-to-bottom. Each box is a hard gate; the flip PR (see
`public-flip-runbook.md`) is mechanical only once all of these are checked.

## 1. Repository hygiene

- [x] CI green on `main`: `ruff`, version-consistency, tests, license gate, preflight
      public scan (default).
- [x] **Strict** preflight passes: `uv run python scripts/preflight_public_scan.py --strict`
      exits 0. This is stricter than the CI default — it also scans the inherited
      *process-exhaust* docs (handoffs, gate-artifacts, brainstorms, plans, deploy
      runbooks, dated security reviews, threat model, gbrain-decommission state).
  - [x] Scrub or prune the operator hostname/IP from the process-exhaust docs. Note
        `--strict` scans `docs/archive/` too, so archiving a doc (U21) tidies the IA but
        does **not** clear the gate — decide scrub-vs-consciously-accept for each,
        mirroring the git-history decision (D1).
  - [x] Re-run `--strict` → exit 0.
- [x] **Git history** decision (D1 in the runbook) is signed off and executed
      (filter-repo rewrite) or consciously accepted-as-residual. Audit with
      `uv run python scripts/preflight_public_scan.py --history`.

## 2. License flip (mechanical — runbook Steps 1–5)

- [x] `LICENSE` ← staged AGPL-3.0 text.
- [x] `pyproject.toml` `license` → `AGPL-3.0-only`; license gate still green
      (self-exclusion shipped in U6).
- [x] README license section reconciled (AGPL statement; dependency-gate clarification
      kept; engine ↔ companion boundary kept).
- [x] Staged badges activated (they 404 on a private repo, so only now).
- [x] `CITATION.cff` landed from `docs/launch/CITATION.cff`.

## 3. Contributor IP (D2 in the runbook)

- [x] DCO `Signed-off-by:` attestation documented in `CONTRIBUTING.md` and present as a
      checkbox in `.github/PULL_REQUEST_TEMPLATE.md` (CLA deferred).

## 4. Legal (D3 in the runbook)

- [x] AGPL §13 ↔ GPL-3.0 companion arm's-length boundary sanity-checked and signed off
      (rests on the no-vendoring / no-linking invariant in U7).

## 5. Security reporting

- [x] After visibility flip, enable GitHub **private vulnerability reporting** (off by
      default for repos that were private) so `SECURITY.md`'s channel is functional.

## 6. Companion

- [x] Make `hypermnesic-companion` public / cut its first release.
- [x] `obsidian-plugin/README.md` updated from private-until-release → public (U22).

## 7. Community profile

- [x] GitHub community profile reads 100%: LICENSE, CODE_OF_CONDUCT, CONTRIBUTING,
      SECURITY, issue templates, PR template all detected.
      Confirmed after PR-13 / LS-1682 repo description/topics were applied.
- [ ] Upload `docs/assets/social-preview.png` in GitHub Settings -> Social preview.
      GitHub documents this as a manual PNG/JPG/GIF upload flow; there is no supported
      REST or GraphQL upload endpoint.

## 8. Visibility (runbook Step 8 — last)

- [x] `gh repo edit <owner>/hypermnesic --visibility public`.
- [x] Smoke-check: README badges resolve; benchmark link works; community profile checked.
      Custom Social preview remains pending the manual GitHub Settings upload.

## 9. Directories

- [ ] External directory submissions are prepared in `docs/launch/directory-submission-prep.md`.
      Submit only after the PR-14 operator approval gate.

## 10. Discussions and roadmap

- [ ] GitHub Discussions welcome and roadmap posts are prepared in
      `docs/launch/discussions-roadmap-prep.md`.
      Enable Discussions and pin official posts only after the PR-17 operator approval gate.
