# Gate A — plugin live, OAuth2 enforced on the write tool, AS up, gbrain not consulted

**Phase:** A (engine readiness + plugin · reversible) · **Status: AWAITING OPERATOR APPROVAL**
**Date:** 2026-06-02 · **Plan:** `docs/plans/2026-06-02-009-feat-gbrain-decommission-plan.md`

Phase A units U1–U5 + U12 are implemented, test-first, and committed on
`claude/condescending-sutherland-4d9b29` (merged to `main`, PR #15). The agent-executable
pytest gate passes and the OAuth2 enforcement loop is proven live over HTTP. The remaining PASS
items are operational and partly cross-host (the Mac) — they need the operator. **Execution
halts here.**

## 🟢 Session update (2026-06-02, post-Mac-evidence) — all agent-executable criteria now GREEN

The operator ran `docs/handoff-macbook-prompt.md` on the Mac and pasted the evidence; two
remaining Phase-A defects were then fixed live this session. Net: **every agent-executable
Gate-A criterion is GREEN; only the operator's explicit approval remains.**

- **Criterion 5 (2nd-peer round-trip) — ✅ PROVEN.** Mac evidence: unauth `:8851`→401 (RFC 9728
  `WWW-Authenticate`), authed `tools/list`→200 `[build_context, commit_note, resolve, search,
  think]`, authed `search`→ real hits. (Token minted on-Mac via `:8849`, audience `…/mcp`,
  scope `write`; never printed.)
- **Plugin load defect FIXED (`69e0096`) → criteria 7 + 9 now real.** `claude plugin list`
  reproduced `✘ failed to load: Duplicate hooks file detected`. The manifest re-declared the
  auto-loaded `hooks/hooks.json`; dropped the redundant key. Now: homelab **Claude `✔ enabled`**,
  homelab **Codex `installed, enabled`**; Mac both (same fix). Regression-guarded.
- **`.mcp.json` issuer corrected off honcho (`69e0096`).** Was `…/honcho/` (honcho can't be the
  AS — U12); repointed to the hypermnesic origin, audience stays canonical `…/mcp`. Guard added.
- **Cloud lane (separate workstream) DEPLOYED + verified** — see
  `docs/cloud-oauth-mcp-deploy-runbook.md` (banner) and `services/hypermnesic-cloud.md`.

## ✅ Homelab deploy EXECUTED (2026-06-02, operator-approved)

The homelab Gate-A rollout is **live** (option-2, companion-safe; mirrored to
`gbrain-brain/projects/homelab/services/hypermnesic-as.md` + `LOG.md`):

- **AS** `hypermnesic-as.service` — `100.64.0.55:8849`, `client_credentials` + RFC 8707 audience
  + RFC 7662 introspection + DCR-locked. 4 identities enrolled (homelab-claude, homelab-codex,
  Mac, RS); secrets in `~/.config/hypermnesic-as/*.env` (0600).
- **Write master (auth-on)** `hypermnesic-master-auth.service` — `100.64.0.55:8851`, write-enabled,
  introspects the AS. **Live-verified: unauth `commit_note` → 401, authed `search` → 200.**
- **Companion preserved** — `:8848` flipped to **read-only auth-off** (`tools/list` =
  `[search, build_context, think]`, `commit_note` retired, reads → 200). The Obsidian companion
  keeps its URL; the auth-off **write** surface on the tailnet is gone (invariant honored).
- **Agent token** — `hypermnesic-token.timer` mints `HYPERMNESIC_MCP_TOKEN` (45-min) to a 0600 file.
- **write-master refuses auth-off** — re-proven **live** on the homelab.
- **Reversible** — `hypermnesic.service.pre-phase2.bak` + stop the 3 new units.
- **Provenance** — services worktree-pinned to the merged Phase-2 (clean reinstall-from-`main` is a
  follow-up; uv wheel-cache needs a version bump). gbrain/honcho/vault untouched.

**Open for Gate A (operator):** the **Mac 2nd-peer round-trip** (run `docs/handoff-macbook-prompt.md`
with the `mac` identity's secret from `~/.config/hypermnesic-as/mac.env`) + the **plugin install**
(homelab + Mac) + **final Gate-A approval**. Wrong-audience rejection (RFC 8707) is unit- +
ephemeral-proven (the live `:8851` uses the same `StrictResourceTokenVerifier`).

---

## Gate-A PASS checklist

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 0 | `uv run pytest tests/` exit 0 | ✅ PASS | **465 passed, 1 skipped** (this session); ruff clean. Named set test_cli/graph/mcp_server/converge/auth/install/plugin/plugin_hook all green (+ test_auth_server/auth_cloud). |
| 1 | Unauth `tools/call` to **commit_note** rejected | ✅ PASS (live) | Ephemeral HTTP proof: `commit_note` unauthenticated → **HTTP 401**. Unit: `test_mcp_server` auth suite. |
| 2 | Wrong-audience token rejected (RFC 8707) | ✅ PASS (live) | Ephemeral proof: token minted for `…/other` → **HTTP 401** against the `…/mcp` RS. Unit: `test_auth::test_wrong_audience_rejected_rfc8707`. |
| 3 | Write-master refuses to start auth-off | ✅ PASS (live) | `serve --enable-write --host 100.64.0.55` (no auth) → **exit 1**, clear message. Unit: `test_mcp_server::test_write_enabled_without_auth_refused`. |
| 4 | Live AS issues a token; full AS→RS loop works | ✅ PASS (live, homelab) | Ephemeral proof: AS `client_credentials` mint → valid token → `commit_note` **HTTP 200** (introspection + audience check over the wire). Unit end-to-end: `test_auth_server::test_end_to_end_as_token_validates_through_rs_verifier`. |
| 5 | AS round-trip from a **2nd tailnet peer (the Mac)** | ✅ PASS (operator evidence in) | Mac pasted: unauth `:8851`→401 (RFC 9728), authed `tools/list`→200 full toolset, authed `search`→ real hits. |
| 6 | All **three identities** provisioned (homelab Claude, homelab Codex, Mac) | ✅ PASS | All three enrolled (secrets in chmod-600 env files, never echoed); the Mac minted + round-tripped a `write` token. |
| 7 | Plugin installed on Claude + Codex (both hosts) | ✅ PASS (live) | After the load-defect fix (`69e0096`): homelab **Claude `✔ enabled`** + **Codex `installed, enabled`** (verified via `claude/codex plugin list`); Mac both (same fix). |
| 8 | Auto-query hook injects on a relevant prompt, **silent on 401** | ✅ PASS (unit) | `test_plugin_hook`: relevant→inject, off-topic→silent, timeout/401/missing-token→silent-never-blocks. Token never echoed. |
| 9 | SKILL loadable on both hosts | ✅ PASS (live) | The plugin loads enabled on both homelab hosts (so the bundled `hypermnesic-memory` SKILL loads); Mac confirmed. The duplicate-hooks defect that previously failed the whole load is fixed + guarded. |
| 10 | The plugin path **never calls gbrain** | ✅ PASS | SKILL says "do NOT use gbrain"; no hook command invokes gbrain (`test_plugin_hook`); the daemon-re-arm guard blocks `gbrain serve/init/sync --watch/autopilot --install` (but not `gbrain delete`, needed by U9/U10). |

**Verdict:** **all 11 criteria are GREEN** (0–10). Criterion 5 is satisfied by the operator's
pasted Mac evidence; 7/9 are live-verified on both homelab hosts after the plugin load-defect
fix; the Mac mirrors them. **The only thing left is the operator's explicit "Gate A approved"** —
the gate itself, which the agent cannot self-cross. Execution halts here per the plan.

---

## Per-unit changes (committed)

| Unit | Commit | What shipped |
|------|--------|--------------|
| anchor | `14b88f5` | Plan + origin requirements onto the branch. |
| U1 | `decef64` | `resolve` verb (name→page, gbrain's `get` role) + `--now` convergence-freshness knob on resolve/retrieve/converge + CLI `manual_reindex_recommended` surfacing + MCP `resolve` read tool. |
| U2 | `f25ad71` | OAuth 2.1 Resource-Server: `auth.py` (audience+expiry verifier, RFC 7662 introspection strategy), `build_server` plumbs `token_verifier`/`auth` + the `write_enabled⇒auth-required` invariant (loopback-exempt), CLI/install auth flags, threat-model RS rewrite (V11–V14). |
| U3 | `51f4f94` | Plugin marketplace + Claude/Codex manifests + `hypermnesic-memory` SKILL (steers off gbrain) + README. |
| U4 | `dce065b` | Auto-query hook (Claude+Codex) + `hooks.json`: relevance gate, token-gated bounded lookup, silent-on-401/timeout/missing-token, dangerous-op guard. |
| U5 | `9c3d71e` | Plugin `.mcp.json` (OAuth2, secret-free) + `_install_client` OAuth2-aware client emission (token by env pointer, never inlined). |
| U12 | `ca35328` + `(finding)` | Minimal tailnet-internal AS (`auth_server.py`): client_credentials, RFC 8707 audience binding, RFC 7662 introspection, revocation, TTL ceiling, DCR locked; CLI `serve-auth` + `auth-add-client` (secret→chmod-600 file). honcho native-primitive finding recorded (`docs/oauth-as-finding.md`). |

---

## Native-primitive finding (U12) — recorded

honcho-oauth-proxy **cannot** be hypermnesic's AS: opaque tokens, **no introspection endpoint**,
**no JWKS**, audience hardwired to `…/honcho/mcp`, and modifying a running shared service is
higher-risk than an isolated AS. → built a **new, gbrain-independent** minimal AS. Full rationale:
`docs/oauth-as-finding.md`.

---

## ⚠ Critical finding — the live master auth-on flip breaks the Obsidian companion

The live `hypermnesic.service` master (`:8848`, Phase-1 **auth-off**) currently serves the
**read-only Obsidian companion** (and a canary). Source check: `obsidian-plugin/src/core.ts`
sends **no `Authorization` header — zero OAuth support**. Because the U2 auth middleware gates
**every** tool (not just `commit_note`), flipping the write-master to **auth-on** would return
**401 to the companion's read calls** and break it. The plan's U8 precondition *"every consumer
holds a valid token before the flip"* is **not satisfiable for the companion as written**.

This is an operator decision (it was not resolved in the plan). Options, for you to pick:
1. **Add OAuth (a `read`-scoped token) to the Obsidian companion** before the flip (companion code change — separate from this plan).
2. **Serve the companion from a read-only, auth-off endpoint** (a `client`/read-replica bind) while the **write** master runs auth-on — two binds, one boundary.
3. **Accept a brief companion outage** at the flip and re-provision it immediately after.

Until this is chosen, the **live master must NOT be flipped to auth-on** — so the persistent
homelab rollout (AS unit, master flip, hostname repoint) waits for your call. (It also waits on
a **branch merge**: a persistent AS/master unit should run the installed engine, not this
feature-branch worktree.) The ephemeral proof above already demonstrates the enforcement works.

## Security review (pre-deploy, 2026-06-02)

The new OAuth surface (RS verifier, AS, the `write_enabled⇒auth` invariant, the hook) was
**adversarially reviewed before any live deploy**, since it gates write access to the memory
layer. Audience binding (RFC 8707), fail-closed paths, introspection-client auth, scope clamp,
the loopback exemption, and secret/token non-leakage **held**. Three real issues were found and
**fixed test-first** (commit `e55b75b`):
- **HIGH (V14 realized):** a write-enabled master started without a write scope exposed
  `commit_note` to any valid token (the SDK enforces scopes globally). Fixed: `commit_note`
  **self-enforces the `write` scope** from the authenticated principal, independent of the
  transport scope list.
- **LOW:** RFC 7009 token-ownership not checked in `revoke()` → fixed (only the owner revokes).
- **LOW:** the hook sanitized only `snippet` newlines → fixed (path/heading too).

This **sharpens the companion finding above**: with per-tool write-scope enforcement, a single
endpoint can require only a base scope (so read clients pass) while `commit_note` rejects
non-`write` principals — so option 2 (a `read`-scoped companion token on the same auth-on
endpoint) is now cleanly supported by the engine, if the companion is given OAuth.

## Rollback state

**Fully reversible — nothing live was changed.** All Phase-A work is in-repo code + the plugin;
the live `:8848` hypermnesic master, the live honcho AS, gbrain, and the vault are **untouched**.
The live OAuth proof ran on **alt ports (127.0.0.1:8849 AS, :8850 throwaway master)** in a temp
dir and was torn down (zero residual homelab state). Rollback = uninstall the plugin / `git`
revert; gbrain remains the live memory layer.

---

## What the operator needs to decide / do at this gate

To complete Gate A and authorize Phase B, the operator should:

1. **Approve the persistent homelab rollout** of Phase A (these are the reversible self-drive
   ops I will then execute, mirroring each into `gbrain-brain/projects/homelab/` + `LOG.md`):
   - Deploy the AS as a persistent user unit (tailnet-internal `tailscale serve` route),
     enroll the homelab Claude + Codex identities + the RS introspection client.
   - Install the plugin on the homelab Claude + Codex.
   - Stand up the auth-on hypermnesic master endpoint (the `tailscale serve /mcp` repoint —
     U8 pulled forward). **Blocked on the companion finding above** — pick how the read-only
     companion survives an auth-on master before this runs. Follows the U8 no-gap order
     (AS up → tokens provisioned+verified → flip); reversible.
2. **Provide the Mac-side evidence** (criteria 5, 7): from the Mac, an authenticated
   `tools/list`/`search` against the endpoint + the Mac plugin install, pasted here.
3. **Approve Gate A** so Phase B (read-parity U6 → content-distill cutover U7 → reach repoint
   U8 → consumer sweep U13) may begin.

> Per the autonomous-run rule, I stop here and await your decision. I have **not** crossed the
> gate. Open follow-ups for later phases: U6 parity harness, U7 content-distill cutover, U8/U13
> consumer cutover, U9 reconciliation, U10 snapshot+soak, U11 irreversible teardown.
