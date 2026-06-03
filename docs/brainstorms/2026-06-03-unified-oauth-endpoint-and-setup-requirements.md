---
date: 2026-06-03
topic: unified-oauth-endpoint-and-setup
title: "Hypermnesic — One Unified OAuth MCP Endpoint + `hypermnesic setup`"
type: feat
tags: [hypermnesic, serving, oauth, mcp, tailscale, installer, distribution, consolidation]
origin:
  - "docs/brainstorms/2026-06-02-cloud-oauth-mcp-mobile-requirements.md (the public OAuth lane, promoted here to the sole lane)"
  - "docs/brainstorms/2026-06-02-deployment-topology-write-model-requirements.md (roles, git-first write, 'OAuth later upgrades read+write')"
related_to:
  - "docs/brainstorms/2026-06-02-gbrain-decommission-requirements.md"
  - "docs/brainstorms/2026-06-02-obsidian-companion-plugin-redesign-requirements.md"
  - "docs/plans/2026-06-02-009-feat-gbrain-decommission-plan.md (U8 reach/auth — superseded by this design)"
---

# Hypermnesic — One Unified OAuth MCP Endpoint + `hypermnesic setup`

## Summary

Collapse hypermnesic's four serving lanes into **one** public, Tailscale-funnel'd OAuth MCP
endpoint that every remote client — ChatGPT/Claude mobile, the Claude Code plugin, Codex, the
Obsidian companion — uses identically: **browser-login-once, silent refresh, read+write
separated by OAuth scope**. A one-command `hypermnesic setup` stands it up (server + consent
secret + Tailscale funnel + printed URL). Engine-host-local consumers keep using the **CLI**;
honcho is untouched and coexists on the same hostname.

## Problem Frame

Hypermnesic today serves the same engine through **four** overlapping lanes that accreted one
patch at a time, not by design:

- a **read companion** (tailnet, auth-off) for the Obsidian companion;
- a **write master** (tailnet, auth-on, write-enabled);
- a **tailnet authorization server** published on a bare tailnet IP over **plain HTTP**
  (`client_credentials` grant, for headless tailnet agents + the per-prompt hook);
- a **separate public cloud OAuth MCP** (`authorization_code` + DCR + PKCE, Tailscale Funnel)
  that ChatGPT/Claude Cloud use.

The two public-vs-tailnet lanes exist for one reason: the tailnet AS was never made
public-HTTPS, so when mobile cloud apps needed a standards-discoverable OAuth endpoint, a second
self-contained public-OAuth server was bolted on rather than fixing the first. The cost surfaces
in three places: (1) the distributable Claude Code plugin **hardcodes the operator's homelab
hostname** and carries a non-standard `auth`/`token_env` block, so a stranger who installs it
points at the operator's brain and a stranger can't self-serve; (2) four services are four things
to run, reason about, secure, and document; (3) the operator just hit the seam directly — a
reach flip that "worked" left clients unable to OAuth-discover because the discovery metadata only
lived on the tailnet-IP lane.

The operator's question — *"why two endpoints? couldn't the app just use one that works the way
`/cloud` already works for my mobile apps?"* — is the right one. The public cloud lane already
solved the hard parts (OAuth 2.1 AS, DCR, PKCE, consent gate, a full pre-exposure security
review, read+write by scope). This brainstorm settles the consolidation: make that lane the
**sole** lane, point everything at it, retire the rest, and make standing it up a single command.

## Key Decisions

- **KD1 — One public OAuth MCP endpoint for every remote client.** A single Tailscale-funnel'd,
  HTTPS, OAuth-discovery (RFC 9728 → RFC 8414 → DCR + PKCE) endpoint serves ChatGPT/Claude
  mobile, the Claude Code plugin, Codex, and the Obsidian companion — all the same way. There is
  no separate cloud-vs-tailnet lane and no auth-off read lane. *(Chosen over keeping a passwordless
  tailnet read path: simpler topology, at the cost that local reads now ride the OAuth token too.)*

- **KD2 — Promote the existing cloud OAuth server to the sole lane; don't build new.** The
  approved, security-reviewed public lane (`src/hypermnesic/auth_cloud.py` + the write-enabled
  serve) already is an OAuth 2.1 AS with DCR/PKCE, read+write by scope, and a consent gate. The
  unified endpoint is that server generalized — not a green-field rebuild. The retired lanes' one
  genuinely distinct capability (headless `client_credentials`) is replaced per KD4.

- **KD3 — Browser-login-once, then silent refresh, even for "headless" consumers.** OAuth's
  interactive step happens exactly once and yields a long-lived refresh token; every renewal
  afterward is silent. "Everything via OAuth" is therefore viable for Obsidian and the per-prompt
  hook — they ride the stored token rather than opening a browser per call.

- **KD4 — Engine-host-local consumers use the CLI; only remote app clients use the MCP.** The
  homelab (which runs the engine) drives its per-prompt hook, crons, and local agents through the
  `hypermnesic` CLI — no OAuth, no network. The MCP endpoint exists for clients that can't touch
  the vault on disk. This is the established CLI-for-local / MCP-for-remote split.

- **KD5 — Write = operator-consent then write-anywhere.** Read is the default scope. Write
  (`commit_note`) requires the operator to approve it at login (the existing consent /
  approval-token step). A write-scoped client may then commit anywhere, bounded by `commit_note`'s
  existing guards (allowlist, protected-path refusal, diff-or-die, audit log, git-revertability).
  *This supersedes the cloud lane's current `captures/` review-zone fencing.*

- **KD6 — `hypermnesic setup` is one-command bring-up over Tailscale's native primitives.** It
  starts the unified endpoint as a persistent service, generates the operator consent secret,
  configures the Tailscale **funnel** (public HTTPS via Tailscale's automatic TLS), and prints the
  URL + login instructions. Idempotent / re-runnable. It assumes Tailscale is installed and logged
  in — it does not re-implement Tailscale's own lifecycle.

- **KD7 — The distributed plugin carries zero operator-specific config.** Its MCP wiring is
  `{ type: streamable-http, url: ${HYPERMNESIC_MCP_URL:-<placeholder>} }` with OAuth handled by
  discovery — no hardcoded hostname, no `auth`/`token_env` block, no paths/device names. Author
  metadata is fine.

- **KD8 — honcho is untouched and coexists.** honcho keeps its own MCP endpoint, funnel, and
  well-knowns on the same hostname. The unified hypermnesic endpoint must share the hostname
  without disturbing honcho's routes or discovery documents.

- **KD9 — The `write_enabled ⇒ auth-required` invariant is preserved.** A write-capable serve
  never starts without auth configured; writes are never passwordless over the network (only the
  local loopback/CLI is exempt).

## Actors

- A1. **The operator** — runs `hypermnesic setup` on the engine host; the sole approver of write
  access (grants the `write` scope at consent) and of vault changes.
- A2. **A remote interactive app** — ChatGPT/Claude (mobile/web/desktop), the Claude Code plugin's
  MCP tools, Codex, the Obsidian companion. Authenticates via browser-login-once + silent refresh.
- A3. **The per-prompt hook** — proactively injects memory context. On the engine host it uses the
  CLI; on a remote client it rides the stored OAuth token (read scope).
- A4. **The unified endpoint** — the single OAuth MCP server: AS (DCR + authorization_code + PKCE)
  + read tools always + scope-gated git-first `commit_note`, exposed via Tailscale funnel.
- A5. **The `hypermnesic` CLI** — the engine-host-local interface (reads the on-disk index, writes
  git-first); the local consumers' path, never the MCP.
- A6. **honcho** — a co-tenant MCP on the same hostname; out of scope to change, must keep working.

## Requirements

### Unified endpoint

- R1. There is exactly one hypermnesic MCP endpoint reachable by remote clients: a single public
  HTTPS URL served via Tailscale funnel.
- R2. The endpoint is OAuth-discoverable per the MCP standard: an unauthenticated request returns
  `401` with `WWW-Authenticate` pointing at reachable RFC 9728 protected-resource metadata, which
  advertises an AS whose RFC 8414 metadata is reachable at the same public HTTPS origin (no
  bare-IP / plain-HTTP issuer).
- R3. The endpoint exposes the read tools unconditionally and the git-first `commit_note` write
  tool only when started write-enabled, gated by the `write` scope.
- R4. Every remote client type (mobile cloud connector, Claude Code plugin, Codex, Obsidian)
  connects through this one endpoint with the same discovery + login flow; none requires a
  client-type-specific lane.
- R5. The four prior lanes (read companion, write master, tailnet `client_credentials` AS,
  separate cloud server) are retired in favor of R1's endpoint, with the gbrain strangler rollback
  preserved until its own gate (see R18).

### Authentication & scope

- R6. The AS supports Dynamic Client Registration, `authorization_code`, PKCE (S256), and refresh
  tokens, so a client self-registers and the user authorizes once in a browser.
- R7. After the one-time authorization, access-token renewal is non-interactive (refresh token);
  no per-call browser step.
- R8. The default granted scope is read. The `write` scope is granted only through the operator
  consent / approval-token step at authorization time.
- R9. A write-scoped client may write anywhere permitted by `commit_note`'s existing guards
  (allowlist, protected-path refusal, diff-or-die gate, audit log); no review-zone quarantine is
  imposed.
- R10. The endpoint refuses to start write-enabled without auth configured
  (`write_enabled ⇒ auth-required`); audience is enforced at the resource server.
- R11. The per-prompt hook on a remote client authenticates using the OAuth credential obtained by
  the one-time login (read scope), not a separately minted static token.

### `hypermnesic setup`

- R12. A single `hypermnesic setup` invocation brings the endpoint fully online: starts the server
  as a persistent service, generates/persists the operator consent secret, configures the
  Tailscale funnel for public HTTPS, and prints the resulting URL plus "add this to your apps and
  log in" instructions.
- R13. `setup` is idempotent — re-running it converges to the same running state without
  duplicating services, regenerating a still-valid secret, or breaking an existing funnel route.
- R14. `setup` assumes Tailscale is installed and authenticated; if it isn't, `setup` fails with a
  clear, actionable message rather than attempting to manage Tailscale's lifecycle.
- R15. `setup` uses Tailscale's native funnel + automatic TLS — no hand-rolled reverse proxy or
  certificate management.

### Distribution

- R16. The published plugin's MCP wiring is endpoint-generic: the URL comes from
  `${HYPERMNESIC_MCP_URL}` (with a non-secret placeholder default), with OAuth via discovery and
  **no** `auth`/`token_env` block and **no** static `Authorization` header.
- R17. The published plugin/app tree contains zero operator-specific values (no homelab hostname,
  IPs, absolute paths, chezmoi references, or device names). Author/identity metadata in manifests
  is permitted.

### Migration & coexistence

- R18. The consolidation supersedes the gbrain-decommission plan's U8 reach/auth and the plugin's
  token-block auth, while keeping the gbrain strangler rollback intact until the decommission's own
  gate releases it.
- R19. honcho's MCP endpoint, funnel, and well-knowns continue to work unchanged throughout and
  after the consolidation; hypermnesic's discovery documents must not collide with honcho's.
- R20. ChatGPT/Claude Cloud connectivity has no regression across the migration — the public OAuth
  reach those connectors depend on stays continuously available (or is cut over without a gap).

## Key Flows

- F1. **First-time client setup.** **Trigger:** a user adds hypermnesic to any app. They set
  `HYPERMNESIC_MCP_URL` to the endpoint; the app connects, gets `401` + discovery, prompts login;
  the user authorizes once in a browser (read by default); tokens are stored and auto-refresh.
  **Covers R2, R4, R6, R7, R16.**

- F2. **Granting write.** **Trigger:** a client needs `commit_note`. At authorization the user is
  asked to consent to write (approval-token / operator-auth step); on approval the client receives
  the `write` scope and can commit anywhere the guards permit. **Covers R8, R9.**

- F3. **Proactive hook on a remote client.** **Trigger:** a prompt fires on a Mac running only the
  plugin. The hook reuses the stored OAuth credential (read scope) to fetch context — no browser,
  no separate token. **Covers R11.** *(See Outstanding Questions for the token-access dependency.)*

- F4. **Engine-host-local access.** **Trigger:** the homelab hook/cron/agent needs the brain. It
  calls the `hypermnesic` CLI directly against the on-disk index — no MCP, no OAuth.
  **Covers KD4.**

- F5. **`hypermnesic setup`.** **Trigger:** the operator stands up (or re-converges) the endpoint.
  One command starts the service, generates the consent secret, funnels public HTTPS, and prints
  the URL + login steps. **Covers R12, R13, R14, R15.**

## Acceptance Examples

- AE1. **Covers R2, R16.** A fresh client with only `HYPERMNESIC_MCP_URL` set and no token
  connects, is told to authenticate, completes the browser flow once, and thereafter operates with
  silently-refreshed tokens — with no `auth` block in its config.
- AE2. **Covers R8, R9.** A client that only completed read consent is denied `commit_note`; the
  same client, after the operator approves write at consent, commits a note to an arbitrary
  (guard-permitted) path successfully.
- AE3. **Covers R10.** Starting the endpoint write-enabled with no auth configured refuses to boot.
- AE4. **Covers R13.** Running `hypermnesic setup` twice leaves one service, one valid consent
  secret, and one funnel route — the second run reports convergence, not a duplicate.
- AE5. **Covers R19, R20.** After the cutover, honcho's endpoint and the ChatGPT/Claude Cloud
  connector both still authenticate and respond; hypermnesic's discovery metadata resolves to
  hypermnesic (not a co-tenant).
- AE6. **Covers R17.** A grep of the published plugin tree finds no homelab hostname, IP, absolute
  path, chezmoi reference, or device name.

## Scope Boundaries

**Deferred for later**
- Per-identity authorization policy beyond the read/write scope split (e.g. per-client path
  restrictions, per-device revocation UX).
- A tiered / review-zone write model — explicitly rejected for now in favor of operator-consent +
  write-anywhere (KD5); revisitable if the public write surface proves too permissive.
- `setup` managing Tailscale's own install/login lifecycle.

**Outside this effort's identity**
- Decommissioning or modifying honcho (KD8) — it is a co-tenant to preserve, not touch.
- The gbrain decommission's data-layer phases (orphan audit, snapshot, teardown) — this redesign
  reshapes only the serving/reach/auth layer that the decommission's U8 covered.

## Dependencies / Assumptions

- The existing cloud OAuth server (`src/hypermnesic/auth_cloud.py`) and write-enabled serve are the
  substrate to generalize (KD2); their prior security review carries forward and must be re-checked
  against the write-anywhere change (KD5 widens the write surface beyond `captures/`).
- Tailscale funnel provides public HTTPS + automatic TLS for the single hostname, and can host the
  hypermnesic endpoint path alongside honcho's routes without collision.
- Claude Code performs OAuth discovery from `{type, url}` alone (verified against current Claude
  Code docs) and stores/refreshes the token; the per-prompt hook's ability to *reuse* that stored
  token is assumed but not yet verified (see Outstanding Questions).
- The gbrain decommission remains rollback-capable (gbrain alive) until its own gate, independent
  of this consolidation.

## Outstanding Questions

**Resolve before planning**
- **Sequencing vs. the gbrain decommission.** Do we consolidate the serving layer first (then
  finish the gbrain consumer cutover against the unified endpoint), or finish the gbrain
  decommission on the current lanes and consolidate after? This sets the order of the next concrete
  work and how U8 is rewritten.

**Deferred to planning**
- **Remote-client hook token access (R11/F3).** Can the per-prompt hook script read the OAuth token
  Claude Code stores for the MCP server? If not, the remote-client hook needs an alternative (a
  scoped service credential, or accept that proactive injection is engine-host-only and remote
  clients rely on agent-initiated MCP tool calls). The homelab hook is unaffected (CLI).
- **Endpoint path + discovery layout on the shared hostname** — the exact path and well-known
  routing that gives hypermnesic clean discovery without colliding with honcho (R19).
- **Migration cutover mechanics** — how the four lanes are retired without a gap in ChatGPT/Claude
  Cloud reach (R20) and without stranding the operator's currently-connected clients (re-auth
  once).

## Sources / Research

- `docs/brainstorms/2026-06-02-cloud-oauth-mcp-mobile-requirements.md` — the public OAuth lane
  (APPROVED, code-complete, security-reviewed): DCR + authorization_code + PKCE, consent gate,
  read+write by scope, `captures/` review zone, the pre-exposure adversarial review (2 Critical +
  3 High fixed). This design promotes that lane to the sole lane and changes its write fencing.
- `docs/brainstorms/2026-06-02-deployment-topology-write-model-requirements.md` — roles
  (single/master/client), git-first `commit_note`, companion read-only, and KD4/KD5 there
  ("MVP auth = tailnet membership; OAuth later upgrades read+write together; OAuth is the trigger
  for the full write-surface threat model") — which this brainstorm now acts on.
- `src/hypermnesic/auth_cloud.py`, `src/hypermnesic/mcp_server.py` — the existing AS + consent +
  scope-gated write-tool registration this consolidation builds on.
- Claude Code MCP documentation — confirms OAuth discovery from `{type, url}` and `${VAR}`
  expansion in `.mcp.json` (basis for KD7/R16).
- `docs/plans/2026-06-02-009-feat-gbrain-decommission-plan.md` — U8 (reach + auth repoint), which
  this design supersedes (R18).
