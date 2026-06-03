---
title: "Public launch checklist"
status: staged
audience: operator
note: >
  STAGED. A human checklist for the public flip. It does not perform the flip;
  it enumerates every prerequisite so nothing is missed. Pair with
  public-flip-runbook.md (the ordered mechanical steps).
---

# Public launch checklist

Run top-to-bottom. Each box is a hard gate; the flip PR (see
`public-flip-runbook.md`) is mechanical only once all of these are checked.

## 1. Repository hygiene

- [ ] CI green on `main`: `ruff`, version-consistency, tests, license gate, preflight
      public scan (default).
- [ ] **Strict** preflight passes: `uv run python scripts/preflight_public_scan.py --strict`
      exits 0. This is stricter than the CI default — it also scans the inherited
      *process-exhaust* docs (handoffs, gate-artifacts, brainstorms, plans, deploy
      runbooks, dated security reviews, threat model, gbrain-decommission state), which
      the default gate defers. **These still contain the operator hostname/IP today**
      (the default gate reports the deferred count). Resolve them before the flip:
  - [ ] Scrub or prune the operator hostname/IP from the process-exhaust docs. Note
        `--strict` scans `docs/archive/` too, so archiving a doc (U21) tidies the IA but
        does **not** clear the gate — decide scrub-vs-consciously-accept for each,
        mirroring the git-history decision (D1).
  - [ ] Re-run `--strict` → exit 0.
- [ ] **Git history** decision (D1 in the runbook) is signed off and executed
      (filter-repo rewrite) or consciously accepted-as-residual. Audit with
      `uv run python scripts/preflight_public_scan.py --history`.

## 2. License flip (mechanical — runbook Steps 1–5)

- [ ] `LICENSE` ← staged AGPL-3.0 text.
- [ ] `pyproject.toml` `license` → `AGPL-3.0-only`; license gate still green
      (self-exclusion shipped in U6).
- [ ] README license section reconciled (AGPL statement; dependency-gate clarification
      kept; engine ↔ companion boundary kept).
- [ ] Staged badges activated (they 404 on a private repo, so only now).
- [ ] `CITATION.cff` landed from `docs/launch/CITATION.cff`.

## 3. Contributor IP (D2 in the runbook)

- [ ] DCO `Signed-off-by:` attestation documented in `CONTRIBUTING.md` and present as a
      checkbox in `.github/PULL_REQUEST_TEMPLATE.md` (CLA deferred).

## 4. Legal (D3 in the runbook)

- [ ] AGPL §13 ↔ GPL-3.0 companion arm's-length boundary sanity-checked and signed off
      (rests on the no-vendoring / no-linking invariant in U7).

## 5. Security reporting

- [ ] After visibility flip, enable GitHub **private vulnerability reporting** (off by
      default for repos that were private) so `SECURITY.md`'s channel is functional.

## 6. Companion

- [ ] Make `hypermnesic-companion` public / cut its first release.
- [ ] `obsidian-plugin/README.md` updated from private-until-release → public (U22).

## 7. Community profile

- [ ] GitHub community profile reads 100%: LICENSE, CODE_OF_CONDUCT, CONTRIBUTING,
      SECURITY, issue templates, PR template all detected.

## 8. Visibility (runbook Step 8 — last)

- [ ] `gh repo edit <owner>/hypermnesic --visibility public`.
- [ ] Smoke-check: README badges resolve; benchmark link works; community profile 100%.
