---
date: 2026-06-03
type: security-review
title: "Blocklist write-surface re-review (Phase B — allowlist→blocklist flip)"
plan: docs/plans/2026-06-03-002-feat-vault-folder-discovery-blocklist-write-plan.md
amends: docs/2026-06-03-unified-write-anywhere-security-review.md
status: pending-sign-off
signed_off: PENDING
---

# Blocklist write-surface re-review (Phase B)

## Why this delta exists — the prior proof does NOT transfer for free

The prior write-anywhere review (`docs/2026-06-03-unified-write-anywhere-security-review.md`,
signed 2026-06-03) cleared the unified public endpoint on a single load-bearing claim: *"the only
thing that widened is the allowlist."* That claim reasoned about a strictly narrower delta —
`captures/` → `DEFAULT_WRITE_ALLOWLIST = (notes/, sources/, dashboards/, captures/)`, where **every
path on both sides was already a note zone**. The protected-path guard sat *behind* a 4-prefix
allowlist that, by construction, refused everything outside those four note prefixes by exclusion.

Phase B (U5) **removes that allowlist as the default**: `_effective_write_surface(None)` now returns
`None` (blocklist mode), so `commit_note`'s default surface becomes *everything under the content
root except the protected + governance classes*. The blast radius widens from four note zones to the
whole content surface, so the prior proof must be **re-derived for the wider surface, not cited**.
This delta is the Phase-B sign-off gate (G6): the flip must not merge/enable until it is signed
(enforced by `tests/test_blocklist_write_gate.py`).

## The delta — what actually changed

| | Before (Phase A / prior review) | After (Phase B blocklist) |
|---|---|---|
| Default write surface | 4-prefix allowlist `notes/ sources/ dashboards/ captures/` | **blocklist**: anything under the content root except the protected + governance classes |
| Operator content folders (`projects/`, `people/`, `companies/`, `meetings/`) | refused (not in allowlist) | **writable** (the goal of the change) |
| Governance/CI/build/credential files | refused **by exclusion** (outside the 4 prefixes) | refused by a **new positive fence** (see §Enumerated re-audit) |
| Who can write | operator-consent-approved `write` scope | **unchanged** |
| Per-write guards (diff-or-die, protected-path, audit, git-revert, server-set actor) | as prior review | **unchanged** + governance fence + case-folded dir match |
| Read clients | reach read tools only (V14 per-tool scope) | **unchanged** |
| `--allowlist` | narrows | **unchanged** — still narrows; `DEFAULT_WRITE_ALLOWLIST` kept as a named escape-hatch to restore the note-zone-only surface |

The widened dimension is no longer "the allowlist" — it is **the entire content surface**. Two new
exposures follow from that, each enumerated and decided below.

## Enumerated re-audit (load-bearing, falsifiable)

### Part A — protected classes STILL refused under the blocklist

`serialize.protected_reason()` is **allowlist-independent**: it refuses these classes regardless of
the (now absent) allowlist, including when nested under a now-writable content folder. Worked
examples (each refused; locked by `tests/test_serialize.py::test_protected_paths_refused` and
`..._is_case_insensitive`, and over MCP by
`tests/test_auth_cloud.py::test_cloud_blocklist_default_writes_content_folders_and_fences_governance`):

| Example path (nested under a writable content folder) | Refused as |
|---|---|
| `projects/acme/.github/workflows/ci.yml` | protected dir (`.github/`) + CI workflow dir |
| `people/bob/scripts/deploy.sh` | protected dir (`scripts/`) |
| `meetings/2026/.cursorrules` | agent-instruction file |
| `companies/x/AGENTS.md`, `projects/y/CLAUDE.md` | agent-instruction file (anywhere) |
| `projects/Scripts/evil.sh` (case-insensitive FS) | protected dir (`Scripts/` → case-folded `scripts/`) |
| `projects/.hypermnesic/index.db`, `notes/.git/config` | protected dir |
| `projects/.gitignore` | never-write file |

**Conclusion A:** widening to the content surface does **not** widen access to the protected classes.
The note-zone→content-surface widening keeps the same protected-class floor.

### Part B — newly-exposed governance/code-exec classes, and the fence decision

The blocklist would, on `_PROTECTED_DIRS`/instruction-files alone, **permit** a class the 4-prefix
allowlist refused only by exclusion: governance / CI / build / credential files that
`protected_reason()` did not name — and `commit_note` enforces **no `.md` suffix**, so these are
real arbitrary-code / credential write targets. Enumerated exposures (pre-fence):

- **Code-exec on build:** `Dockerfile`, `Makefile`, `Containerfile`
- **CI / config:** `*.yml`, `*.yaml` anywhere not already under `.github/` (e.g. `.gitlab-ci.yml`,
  `.circleci/config.yml`, `.pre-commit-config.yaml`)
- **Build / dependency (script-exec):** `pyproject.toml`, `setup.py`, `setup.cfg`, `package.json`,
  `package-lock.json`, and lockfiles `*.lock` (`uv.lock`, `Cargo.lock`, `poetry.lock`, `yarn.lock`)
- **Credentials:** `.env` (+ `.env.*`), `.npmrc`, `.netrc`
- **Never-discovered-but-writable:** `node_modules/…`, `__pycache__/…` — writable by the guard but
  never surfaced by `list_folders` (the index skips them), so an agent can only reach them by
  guessing the literal path.

**Decision (operator, 2026-06-03): add a positive content-surface fence — a governance-extension
denylist.** Implemented in `serialize.protected_reason()` as a caller-independent class refusal
(like the other rules), matched case-insensitively, applied AFTER the dir checks:

- `_GOVERNANCE_FILES = {dockerfile, makefile, containerfile, setup.py, setup.cfg, package.json,
  package-lock.json, .npmrc, .netrc}` + `.env` / `.env.*`
- `_GOVERNANCE_EXTS = (.yml, .yaml, .lock, .toml)`

So under the blocklist default a write-scoped principal may commit notes into `projects/`/`people/`/
`meetings/` etc., but **not** a `Dockerfile`, CI yaml, lockfile, build config, or credential file —
anywhere. Locked by `tests/test_serialize.py::test_governance_fence_refuses_code_exec_and_credential_classes`
and `tests/test_auth_cloud.py::test_cloud_blocklist_default_writes_content_folders_and_fences_governance`.

*Discovery parity note:* `list_folders` reports a content folder `writable` because a **note** (`.md`)
can land there; the governance fence is a per-file *class* bound, orthogonal to folder-level note
placement (the probe is `.md`). So `projects/` is "writable" yet `projects/Dockerfile` is refused —
this is not a discovery lie (the folder is writable for notes, which is what discovery answers).

*Residuals on the fence (accepted):* the denylist is, by nature, not exhaustive — a dangerous
extension not on the list could be written (e.g. `*.sh` at a non-`scripts/` path; mitigated in part
by `scripts/`/`bin/`/`hooks/` dirs being protected, and `.sh` requiring explicit execution). The
list is the single point to extend if a new class surfaces. `node_modules/`/`__pycache__/` remain
writable-but-undiscovered (ACCEPT: not surfaced, single-note, git-revertable).

### Part C — case-folding mismatch (named in-scope, decided)

`protected_reason()` historically matched `_PROTECTED_DIRS` case-**sensitively** but instruction
files case-**insensitively**. On a case-insensitive FS (the operator's macOS) `Scripts/evil.sh`
lands in the protected `scripts/` dir on disk yet was reported writable — inert under the old
allowlist, **reachable under the blocklist**.

**Decision (operator, 2026-06-03): case-fold the protected-dir comparison** (a one-line guard
behavior change with its own characterization test —
`tests/test_serialize.py::test_protected_dir_match_is_case_insensitive`). *Residual (accepted):*
`_NEVER_FILES` (`.gitignore`/`.gitattributes`/`.gitmodules`) remain case-sensitive — a `.GITIGNORE`
on a case-insensitive FS is a low-severity edge (it is not an exec/cred vector and a real conflict
is implausible). Logged, not fixed in this pass.

## Control re-validation (each holds under the blocklist surface)

All controls from the prior review are re-checked against the wider surface. Each is unchanged by the
flip except where the new fence/ case-fold strengthens it; each is locked by a regression guard.

1. **Per-tool write-scope (V14).** `commit_note` self-enforces the `write` scope; a read-scoped
   principal reaches read tools (incl. `list_folders`) but is refused `commit_note`. *Unchanged by
   the flip.* Guards: `test_cloud_server_read_scoped_principal_is_denied_commit_note`,
   `test_commit_note_rejects_read_scoped_principal`.
2. **Protected-path refusal — now the PRIMARY bound** (no allowlist behind it), **plus** the
   governance fence + case-fold. Allowlist-independent; refuses the protected + governance classes
   anywhere, nested or not (Parts A–C). This is the property that makes the blocklist safe.
   Guards: `test_governance_fence_*`, `test_protected_dir_match_is_case_insensitive`,
   `test_write_anywhere_still_refuses_protected_paths_inside_allowed_dirs`.
3. **Operator consent gates the `write` scope.** A write principal is one the operator approved at
   the consent page. *Unchanged.* Guards: `test_authorize_routes_to_consent_not_straight_to_code`,
   `test_consent_with_approval_token_issues_code_redirect`.
4. **Audience binding (RFC 8707), refresh rotation + whole-grant revoke, brute-force cap + pending
   TTL + entropy floor, `write_enabled ⇒ auth-required`, HTTPS public-origin issuer.** *All
   unchanged by the flip* (they gate *whether* a caller may write at all, not *where*). Guards as in
   the prior review (`test_access_token_audience_enforced_at_load`,
   `test_refresh_rotates_old_token_invalidated`, `test_revocation_kills_the_whole_grant_incl_refresh`,
   `test_wrong_approval_token_drops_pending_after_max_failures`, `test_write_enabled_without_auth_refused`,
   `test_unified_lane_refuses_bare_ip_or_plain_http_issuer`).
5. **Diff-or-die, server-set actor, body-free audit, single-path commit, git-revertability.**
   *Unchanged.* Every write is one file, one commit, audited (actor not caller-supplied), and
   revertable; a reindex never loses or hides a write.
6. **Single coercion site.** The write surface and the discovery `writable` flag read the one
   `_effective_write_surface`, so they cannot disagree and they flipped together. Guard:
   `test_list_folders_writable_flag_matches_commit_note_acceptance`.

## Residual risk (accepted, with mitigation)

- **R-1 — A prompt-injected, operator-approved cloud LLM can now write a note into any content
  folder (`projects/`, `people/`, `companies/`, `meetings/`, …), not only the note zones.** Wider
  blast radius than the prior review's note zones. *Disposition: ACCEPT* (this is the goal of the
  change). Mitigation in depth: the protected + governance classes are unreachable (control 2);
  `write` requires explicit operator consent; every write is single-note, audited, git-revertable;
  the note-zone-only surface remains available via `--allowlist`.
- **R-3 — The governance fence is a denylist, not an allowlist; a dangerous extension not on the
  list could be written.** *Disposition: ACCEPT* with the enumerated list as the single extension
  point; `scripts/`/`bin/`/`hooks/` dirs already cover the common exec dirs, and `.sh`/binaries
  require explicit execution by a separate actor.
- **R-4 — `_NEVER_FILES` case-sensitivity residual** (Part C). *Disposition: ACCEPT* (low severity,
  not an exec/cred vector).
- **R-2 (carried) — no app-layer rate limiting on `/register`/`/authorize`/`/consent`.** Unchanged;
  edge/funnel concern as in the prior review.

## Conclusion

The blocklist surface clears the bar the 4-prefix surface did, re-derived for the wider blast radius:
the protected-class floor is unchanged (Part A), the newly-exposed governance/code-exec classes are
fenced by a positive class denylist (Part B), the case-folding hole is closed (Part C), and every
auth/consent/audit/revert control is unchanged. Residuals R-1, R-3, R-4 are accepted with the
mitigations above.

## Operator sign-off (G6 gate)

The Phase-B flip (`_effective_write_surface(None) → None`, U5) **must not merge or enable** until an
operator signs off here. Sign-off = replacing the `signed_off: PENDING` frontmatter value with an
attestation (e.g. `signed_off: 2026-06-03 (operator approved the blocklist surface; R-1/R-3/R-4
accepted)`). `tests/test_blocklist_write_gate.py` fails while the flip is live and this value is
absent/`PENDING`, blocking the merge.

- [ ] Governance-extension denylist reviewed (Part B exact list) and approved
- [ ] Case-fold protected-dir decision (Part C) approved
- [ ] Residuals R-1, R-3, R-4 accepted
- [ ] Phase-A intermediate-state cost (writable flag pre-flip) accepted

**Sign-off:** _pending operator_
