---
title: "Public flip runbook (AGPL-3.0)"
status: steps-1-5-applied
audience: operator
note: >
  Steps 1-5 were applied in the LS-1677 public-flip PR: the live license metadata,
  root LICENSE, README license text, badges, and CITATION.cff now reflect AGPL-3.0.
  The repo still stays PRIVATE until the later history-rewrite and visibility gates.
---

# Public flip runbook — engine → public AGPL-3.0

This runbook makes the public flip a staged sequence of mechanical, reviewable PRs. Every
*non-mechanical* prerequisite is resolved here first (the license-scan
self-exclusion already shipped; the git-history decision and the legal sanity-check
are recorded below). Steps 1-5 have been applied by LS-1677; do **not** run later
steps until their dedicated gates are reached.

> **Reverse op (abort/rollback):** every step below is reverted by restoring the
> proprietary `LICENSE`, resetting `pyproject.toml` `license = { text = "Proprietary" }`,
> reverting the README license section, removing the badges, and setting repository
> visibility back to Private. Because the visibility flip (Step 8) is last, an abort
> before it leaves a fully private repo.

---

## Step 0 — Confirm preconditions (gate; do not skip)

- [ ] **The repo is still PRIVATE** and you intend to make it public in this session.
- [ ] CI is green on `main` (`ruff`, version-consistency, tests, license gate,
      preflight public scan).
- [ ] The license-scan self-exclusion is in place (shipped in U6): with the engine's
      own license set to `AGPL-3.0-only`, `scripts/license_scan.py` still exits 0
      because it excludes the project's own distribution. **Verify:**
      `uv run pytest tests/test_license_scan.py`.
- [ ] The **git-history decision** (below) is signed off.
- [ ] The **AGPL §13 ↔ GPL-3.0 legal sanity-check** (below) is signed off.
- [ ] The **contributor-IP (DCO) decision** (below) is in effect in `CONTRIBUTING.md`
      + the PR template.
- [ ] The **strict** preflight scan + the process-doc scrub (see
      `public-launch-checklist.md`) are resolved:
      `uv run python scripts/preflight_public_scan.py --strict` exits 0.

## Step 1 — Swap the license text

- [x] Replace the root `LICENSE` with the staged AGPL-3.0 text:
      `cp docs/launch/LICENSE-AGPL-3.0.txt LICENSE`
- [x] (canonical AGPL-3.0; `sha256 0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`)

## Step 2 — Set the package license field

- [x] `pyproject.toml`: `license = { text = "Proprietary" }` → `license = "AGPL-3.0-only"`
      (SPDX expression), and add the matching `License :: OSI Approved :: GNU Affero
      General Public License v3` classifier if classifiers are added.
- [x] Confirm the license gate still passes (self-exclusion):
      `uv run python scripts/license_scan.py` → exit 0.

## Step 3 — Reconcile the README license section

- [x] Swap "Proprietary / private (pre-release)" → an AGPL-3.0 statement.
- [x] Keep the **dependency-scoped** clarification of `scripts/license_scan.py`
      (it governs third-party deps, not the project's own license) — it is already
      written to be correct post-flip.
- [x] Keep the **engine ↔ companion boundary** paragraph (AGPL engine ↔ GPL-3.0
      companion, arm's-length over the MCP wire, no-vendoring/no-linking invariant).

## Step 4 — Enable the staged badges

- [x] Activate the CI / license / version badges in the README hero (staged
      commented in U18). They resolve only once the repo is public (shields.io 404s
      on a private repo), so they go live with this flip, not before.

## Step 5 — Land the citation file

- [x] `cp docs/launch/CITATION.cff CITATION.cff` (carries the AGPL license field;
      staged because it presumes the public license).

## Step 6 — Execute the git-history decision (see "Decisions" below)

- [ ] Per the signed-off decision: run the `git-filter-repo` redaction **OR** record
      the accept-as-residual sign-off. Do **not** improvise this at flip time.

## Step 7 — Publish the companion (separate repo)

- [x] Make the `hypermnesic-companion` repo public / cut its first
      release. Update `obsidian-plugin/README.md` to state the repo is now public.

## Step 8 — Flip repository visibility (last; irreversible-ish)

- [ ] `gh repo edit <owner>/hypermnesic --visibility public`
- [ ] Enable GitHub **private vulnerability reporting** (off by default for
      repos that were private) so `SECURITY.md`'s reporting channel is live.
- [ ] Confirm the community profile is 100% (LICENSE, CODE_OF_CONDUCT, CONTRIBUTING,
      SECURITY, issue/PR templates all detected).

---

## Decisions (resolve before the flip — recorded here per the plan's Open Questions)

These are operator-owned judgment calls. A recommendation + rationale is recorded;
each needs an explicit `signed_off:` before Step 0 passes. **None is executed by this
plan** (per the staged-not-flipped discipline and the no-unilateral-history-rewrite
rule).

### D1 — Git-history strategy (rewrite vs. accept-as-residual)

**Problem.** The operator's real homelab node identifiers persist in historical commit
diffs even though the working tree is scrubbed: the tailnet IP `100.64.0.55`
(~25 commits) and hostname `homelab.<tailnet-host>.ts.net` (~24 commits). A public push
exposes all history via `git log -p`. Verify the current count any time with
`uv run python scripts/preflight_public_scan.py --history`.

**Options.**
- **(A) Rewrite history with `git-filter-repo`** before the first public push.
  Removes the identifiers from every commit; **rewrites all SHAs**, which breaks any
  existing clone/fork. Example (operator runs, not this plan):
  `git filter-repo --replace-text <(printf '%s\n' '<tailnet-host>==>example' '100.64.0.55==>100.64.0.55')`
- **(B) Accept-as-residual.** The IP is a Tailscale CGNAT address (`100.64.0.0/10`) —
  non-routable on the public internet; the hostname resolves only inside the operator's
  tailnet (MagicDNS). The realistic exposure of a non-routable IP + non-resolvable host
  is low. Record a signed acceptance instead of rewriting.

**Recommendation:** **(A) rewrite now.** The repo is private with no external
clones/forks today, so the SHA-rewrite cost is near-zero *now* and only grows once the
project is public and forked. Rewriting is the only way to truly remove the values, and
doing it before the first public push is the cheapest it will ever be. Fall back to (B)
only if a clean rewrite proves disruptive to in-flight branches.

`decision:` **(A) git-filter-repo rewrite** (replace `<tailnet-host>==>example`,
`100.64.0.55==>100.64.0.55`)   `signed_off:` 2026-06-03 (operator)

> **Execution note.** A `git filter-repo` rewrite rewrites **every commit SHA across all
> branches**, so it must run **once, on a fresh full mirror clone of the canonical repo**
> (not from this agent worktree, and not before the docs PR is merged), then be
> force-pushed to all refs — after which **every existing clone (MacBook, homelab) must
> re-clone**. filter-repo also drops the `origin` remote as a safety measure; re-add it
> before pushing. Sequence it as the dedicated history-rewrite step **after** this docs
> work lands on `main` and **immediately before** the visibility flip (Step 8), so the
> rewrite and the public push are one coordinated change.

### D2 — Contributor IP: DCO vs. CLA

**Problem.** Once public + AGPL, inbound contributions default to inbound=outbound
AGPL, which forecloses any future relicensing without tracking down every contributor.

**Decision (in effect):** Adopt a lightweight **DCO** (Developer Certificate of
Origin) `Signed-off-by:` attestation — documented in `CONTRIBUTING.md` and a checkbox
in `.github/PULL_REQUEST_TEMPLATE.md`. A heavier CLA is **deferred** (more friction,
not needed for an AGPL inbound=outbound project). Rationale: DCO is the cheapest
provenance attestation and keeps the audit trail clean; it does not itself enable
relicensing, which is consciously accepted as foreclosed under inbound=outbound AGPL.

`decision:` DCO (CLA deferred)   `signed_off:` 2026-06-03 (operator)

### D3 — AGPL §13 ↔ GPL-3.0 companion legal sanity-check

**Problem.** The "neither is a derivative of the other" boundary between the AGPL
engine and the GPL-3.0 companion is legally meaningful and currently rests on a
self-authored README assertion + the no-vendoring/no-linking invariant (U7).

**Decision (recommended in scope):** A brief legal sanity-check of the AGPL §13
(remote network interaction) ↔ GPL-3.0 boundary **is in scope before the public
flip**. The arm's-length claim holds because the two are separate processes coupled
only over the MCP network protocol with no shared or statically-linked code; the
review confirms that framing and the keep-it-true invariant. Until signed off, the
self-authored README assertion stands and the flip is gated on this item.

`decision:` legal sanity-check before flip   `signed_off:` 2026-06-12 (operator)
