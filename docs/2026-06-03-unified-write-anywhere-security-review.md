---
date: 2026-06-03
type: security-review
title: "Write-anywhere re-review for the unified public OAuth endpoint (U6)"
plan: docs/plans/2026-06-03-001-feat-unified-oauth-endpoint-and-setup-plan.md
supersedes_review: docs/brainstorms/2026-06-02-cloud-oauth-mcp-mobile-requirements.md
status: awaiting-operator-sign-off
---

# Write-anywhere re-review — unified public OAuth endpoint (U6)

## Why this re-review exists

The public cloud OAuth lane passed a pre-exposure adversarial review (2 Critical + 3 High,
all fixed — see `docs/brainstorms/2026-06-02-cloud-oauth-mcp-mobile-requirements.md`) **while its
write surface was fenced to `captures/`** (`CLOUD_WRITE_ALLOWLIST`, the V19 quarantine zone). The
unified endpoint (KD3/KD5) **removes that fence**: a write-scoped principal now defaults to the
full master surface `DEFAULT_WRITE_ALLOWLIST = (notes/, sources/, dashboards/, captures/)`. That
widens the public write blast radius, so every control from the prior review is re-validated here
against the wider surface, and the new delta is analysed.

This is the **G3 gate artifact**: the cutover (U7–U8) must not proceed until the operator signs off
on the widened public write surface.

## The write-anywhere delta — what actually changed

| | Before (cloud lane) | After (unified lane) |
|---|---|---|
| Default write allowlist | `captures/` only | `notes/`, `sources/`, `dashboards/`, `captures/` |
| Who can write | operator-consent-approved `write` scope | **unchanged** — operator-consent-approved `write` scope |
| Per-write guards | allowlist + protected-path + diff-or-die + audit + git-revert | **unchanged** |
| Read clients | reach read tools only (V14 per-tool scope) | **unchanged** |

**The only thing that widened is the allowlist.** Everything that gates *whether* a caller may
write at all, and *what* it may not touch, is unchanged.

## Control re-validation (each holds under write-anywhere)

All controls are enforced in `src/hypermnesic/auth_cloud.py` / `src/hypermnesic/mcp_server.py` and
locked by regression guards in `tests/test_auth_cloud.py` / `tests/test_mcp_server.py`.

1. **Per-tool write-scope (V14) — the read/write split on one endpoint.** `commit_note`
   self-enforces the `write` scope from `get_access_token()`, independent of the transport's global
   `required_scopes`. A read-scoped principal reaches the read tools but is refused `commit_note`.
   *Widening the allowlist does not touch this* — a read client still cannot write anywhere.
   Guards: `test_cloud_server_read_scoped_principal_is_denied_commit_note`,
   `..._reaches_read_tools`, `test_commit_note_rejects_read_scoped_principal`.

2. **Protected-path refusal is allowlist-INDEPENDENT — the property that makes write-anywhere
   safe.** `serialize.protected_reason()` refuses agent-instruction files (`AGENTS.md`/`CLAUDE.md`)
   *anywhere*, `.git`/`.github`/`.obsidian`/`.claude`/`.codex` dirs, CI workflow dirs, git-hook
   installers, `.gitignore`/`.gitattributes`, path traversal, and absolute paths — **regardless of
   the allowlist**. So widening the allowlist to the master surface does NOT widen access to the
   protected classes: `notes/AGENTS.md` and `sources/.github/x.md` are still refused even though
   `notes/` and `sources/` are now allowed. The blast radius is the note zones, never `.git` or the
   agent's own instructions. Guard:
   `test_write_anywhere_still_refuses_protected_paths_inside_allowed_dirs`.

3. **Operator consent gates the `write` scope.** DCR lets any internet client register, but
   `authorize()` never mints a code — it routes to an operator-authenticated consent page, and only
   `finalize_consent()` with the operator's approval token issues a code. A write-anywhere principal
   is therefore one the operator explicitly approved at login. Guards:
   `test_authorize_routes_to_consent_not_straight_to_code`,
   `test_consent_with_approval_token_issues_code_redirect`.

4. **Consent-page XSS / clickjacking.** Client-supplied DCR fields are HTML-escaped; an unknown
   pending id is never reflected (generic error, no sink); `X-Frame-Options: DENY` +
   `frame-ancestors 'none'`. Guard: `test_consent_render_escapes_client_fields_and_hides_unknown_pending`.

5. **Per-request consent CSP `form-action` (regression `c164bd8`).** The consent CSP is built
   per-request and allows `'self'` plus the registered client's redirect origin, so the post-consent
   302 to the OAuth client's cross-origin callback is not silently dropped — without re-opening an
   XSS hole (`default-src 'none'`, no scripts). Guard:
   `test_consent_csp_allows_the_oauth_client_redirect_origin`.

6. **Audience enforced at the RS (RFC 8707).** Tokens are audience-bound to our single `resource`;
   `load_access_token()` rejects a token whose bound resource isn't ours. Applies to every tool,
   `commit_note` included (the token is rejected before the tool is reached). Guards:
   `test_access_token_audience_enforced_at_load`, `test_access_token_validates_then_expires`.

7. **Refresh rotation + whole-grant revoke.** Exchanging a refresh token invalidates the old one
   (no double-live refresh); revoking either token of a grant kills both (the operator's kill
   switch really cuts access). Guards: `test_refresh_rotates_old_token_invalidated`,
   `test_revocation_kills_the_whole_grant_incl_refresh`.

8. **Approval-token brute-force cap + pending TTL + entropy floor.** A pending is dropped after
   `MAX_CONSENT_FAILURES` wrong tokens (no indefinite online brute force); pendings TTL-expire
   (`PENDING_TTL_SECONDS`) and are capped (`MAX_PENDING`, DoS bound); the approval token must meet
   `MIN_APPROVAL_TOKEN_LEN` (enforced in `serve-cloud` and in `setup`'s secret generation/reuse).
   Guards: `test_wrong_approval_token_drops_pending_after_max_failures`, `test_pending_expires`,
   `test_serve_cloud_refuses_weak_approval_token`, `test_setup_regenerates_a_weak_existing_secret`.

9. **`write_enabled ⇒ auth-required`.** A write-capable serve never starts without auth configured;
   the unified lane (`build_cloud_server`) always wires the AS. New in U2: the lane also refuses a
   non-HTTPS / bare-IP issuer or resource (R2). Guards: `test_write_enabled_without_auth_refused`,
   `test_unified_lane_refuses_bare_ip_or_plain_http_issuer`.

## Residual risk (accepted, with mitigation)

- **R-1 — A prompt-injected, operator-approved cloud LLM can write to `notes/`/`sources/`/
  `dashboards/` instead of only `captures/`.** This is the deliberate KD5 trade (operator-consent +
  write-anywhere over a review-zone quarantine). *Disposition: ACCEPT.* Mitigation in depth: the
  `write` scope requires explicit operator consent; the protected classes remain unreachable
  (control 2); every write is single-path, audited (server-set actor), and git-revertable; a reindex
  never loses or hides a write. The review-zone model remains available (`--allowlist captures/` on
  `setup`/`serve-cloud`) if the public write surface later proves too permissive (plan Scope
  Boundaries: revisitable).

- **R-2 — No app-layer rate limiting on `/register`, `/authorize`, `/consent`.** The provider caps
  pending growth and consent failures, but request-rate throttling is not in the app. *Disposition:
  ACCEPT as an edge/funnel concern.* Specified for `setup`/the funnel edge (Tailscale Funnel +
  optional edge throttle); the brute-force cap + pending TTL + DCR being consent-gated bound the
  app-layer exposure in the meantime.

## Conclusion

The write-anywhere surface clears the same bar the `captures/`-fenced lane did: the only widened
dimension is the allowlist, and the allowlist-independent protected-path guard plus the
operator-consent write gate keep the protected classes and unapproved clients out. The new R2 guard
closes the bare-IP/plain-HTTP issuer gap. Residuals R-1 and R-2 are accepted with the mitigations
above.

**G3 sign-off required:** operator approval of the widened public write surface (R-1) before the
U7–U8 cutover.
