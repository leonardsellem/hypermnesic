---
date: 2026-06-02
topic: hypermnesic public cloud OAuth MCP — ChatGPT/Claude mobile, read+write
status: draft — awaiting operator sign-off
---

# hypermnesic as a cloud-installable OAuth MCP (ChatGPT + Claude, mobile, read+write)

## Summary

Make hypermnesic installable as a **remote OAuth MCP connector** in **ChatGPT Cloud** and
**Claude Cloud (claude.ai)**, reachable from the operator's **mobile** apps, supporting **read
(search/recall/resolve) + write (commit_note)**. hypermnesic runs **its own** SDK-native OAuth
2.1 Authorization Server (DCR + authorization_code + PKCE) fronting a write-enabled MCP serve,
publicly exposed — **not** coupled to honcho or its OAuth proxy. This is a **new, public,
internet-facing surface** and a deliberate departure from the gbrain plan's "tailnet-only,
public/Funnel deferred" boundary, so the threat model is rewritten for public read+write.

This document is the **requirements + threat-model design for operator sign-off**, per the
"design-first" decision (2026-06-02). No code ships until the Open Questions below are answered.

## Problem Frame

The gbrain-decommission plan (008/009) made hypermnesic the memory layer over a **tailnet-only,
OAuth2-authenticated** endpoint, and explicitly deferred *mobile / off-tailnet / public reach*.
The operator now needs to **read and write that memory from mobile LLM apps** (ChatGPT, Claude),
which reach a **public** endpoint via the **interactive cloud-connector OAuth flow** — a different
client class and a different grant than the tailnet machine agents.

The engine's existing auth is fit for the tailnet machine lane only:
- **U2 (RS):** validates bearer tokens, enforces RFC 8707 audience + expiry + per-tool write scope.
- **U12 (AS):** a minimal **client_credentials** AS (machine-to-machine, no browser consent) — it
  cannot serve the interactive cloud-connector flow.

Cloud connectors require an AS that does **Dynamic Client Registration + authorization_code +
PKCE + a consent step**, over a **public HTTPS** endpoint. The **MCP Python SDK natively provides
this** (`OAuthAuthorizationServerProvider` + `create_auth_routes()` → `/authorize` `/token`
`/register` `/revoke`; `FastMCP(auth_server_provider=…)` makes one process both AS and MCP). So
the plumbing is native and tractable; **the hard part is the security design of a public write
surface to the operator's entire memory.**

## Actors

- **A1. ChatGPT Cloud connector** — an interactive OAuth client (DCR + authorization_code + PKCE).
- **A2. Claude Cloud (claude.ai) custom connector** — same client class.
- **A3. The operator** — approves connections (the consent gate); holds revocation.
- **A4. hypermnesic public AS+MCP** — the new SDK-native gateway (this design).
- **A5. The cloud LLM providers (OpenAI/Anthropic)** — hold the issued tokens server-side; can
  read/write memory within the granted scope (inherent to a cloud connector).
- *(Out: the tailnet machine agents — they stay on the U2/U12 tailnet lane, unchanged.)*

## Key Flows

- **F1 — Connect a cloud connector (one-time).** Operator adds the hypermnesic URL in ChatGPT/Claude
  → the connector discovers the protected-resource metadata (RFC 9728) → AS metadata (RFC 8414) →
  **registers via DCR** → opens **/authorize** → **the operator approves (the consent gate)** →
  authorization_code + PKCE → **/token** → access token (+ refresh).
- **F2 — Mobile read.** The connector calls `search`/`build_context`/`think`/`resolve` with the
  bearer token → audience+scope validated → hits returned.
- **F3 — Mobile write.** The connector calls `commit_note` with a **write-scoped** token → per-tool
  write-scope enforced → commit_note's existing guards (allowlist `notes/ sources/ dashboards/
  captures/`, protected-path denylist, diff-or-die, audit, git-first) apply → committed.

## Requirements

**Reach & protocol**
- CR1. A **public HTTPS** MCP endpoint reachable by ChatGPT + Claude cloud connectors, advertising
  RFC 9728 protected-resource metadata and RFC 8414 AS metadata.
- CR2. The AS supports **DCR (RFC 7591)**, **authorization_code + PKCE (S256)**, **refresh**, and
  **revocation** — via the MCP SDK's `OAuthAuthorizationServerProvider` (native primitive).
- CR3. Installable as a connector in **both** ChatGPT Cloud and Claude Cloud; reachable from mobile.

**Capability & scope**
- CR4. **Read** tools (search/build_context/think/resolve) available to a `read`-scoped token.
- CR5. **Write** (commit_note) available **only** to a `write`-scoped token (the per-tool scope fix,
  `e55b75b`); a read token is refused at the write tool.
- CR6. Writes remain bounded by commit_note's existing guards — allowlist, protected-path denylist,
  diff-or-die frontmatter gate, git-first, audit (summaries only). A public write **cannot** escape
  those (no governance files, no arbitrary paths).

**Consent & access control (the crux)**
- CR7. **A public write token is issued only with the operator's explicit consent.** The `/authorize`
  step is **gated** (an out-of-band approval token and/or a per-connection operator approval) so an
  arbitrary internet client that performs DCR cannot obtain a token without the operator approving.
- CR8. Short **access-token TTL** + refresh; **per-connector revocation**; the operator can kill a
  connector's access.

**Safety & isolation**
- CR9. Independent of gbrain (survives the decommission) and independent of honcho / its OAuth proxy.
- CR10. **Rate-limited** + monitored (a public endpoint is internet-scannable).
- CR11. Reversible: the public lane can be turned off (stop the unit / drop the Funnel) without
  affecting the tailnet lane or git (the source of truth).

## Threat model — public read+write (rewrite; extends V11–V14)

A public, internet-reachable endpoint that can **write the operator's memory** is the central risk.
git remains the source of truth (every write is a reviewable commit), and commit_note's guards bound
*where* a write can land — but the surface is real.

- **V15 — Stolen/leaked token → memory write.** A token exfiltrated from a mobile app, the cloud
  provider, or transit grants write access until expiry/revocation. *Mitigation:* short TTL +
  refresh + revocation (CR8); the write-allowlist + protected-path + diff-or-die bound the blast
  radius (CR6); every write is git-committed + audit-logged (reviewable/revertable). *Residual:* a
  live token writes to `notes/ sources/ …` until revoked — accepted, bounded, auditable.
- **V16 — Open DCR → unapproved token.** DCR lets any internet client register; without a consent
  gate, a registrant could drive the flow. *Mitigation (CR7):* the `/authorize` step is
  **approval-gated** (out-of-band token and/or explicit per-connection operator approval) — DCR
  registers a client but cannot mint a token without operator consent.
- **V17 — Public attack surface.** The endpoint is internet-scannable (DoS, exploit probing,
  credential stuffing). *Mitigation:* rate limiting (CR10), TLS, the SDK's hardened handlers, SPOF +
  abuse monitoring, a tight bind behind the proxy/Funnel.
- **V18 — Provider reads all memory (privacy).** Using a cloud connector means OpenAI/Anthropic's
  servers can read whatever the token's scope allows. *Mitigation:* none — **consciously accepted**
  by choosing mobile-app access; scope-limit (read-only connectors where write isn't needed).
- **V19 — Injected cloud LLM writes malicious notes (confused deputy).** A prompt-injected cloud LLM
  could be steered to call commit_note. *Mitigation:* the write-allowlist + protected-path denylist
  (no governance/exec files), diff-or-die, and git review bound it; **accepted residual** that a
  note under `notes/` could be written — reviewable + revertable via git.

## Key Decisions (proposed)

- **SDK-native AS, not honcho.** Build on the MCP SDK's `OAuthAuthorizationServerProvider` +
  `create_auth_routes`; hypermnesic owns its gateway. honcho/its proxy is honcho's; not reused.
- **One process = AS + MCP** (the SDK derives a `ProviderTokenVerifier` from the provider), or an
  AS/RS split reusing U2 — to be settled in the Open Questions.
- **Per-tool write scope is the write gate** (already shipped, `e55b75b`): read connectors can't write.
- **Consent-gated authorize** is mandatory for the public write lane (CR7) — the single most
  important control; bare DCR is not enough.
- **commit_note's existing guards are the blast-radius bound** — no new write-path code; the public
  lane inherits the allowlist/protected-path/diff-or-die/audit unchanged.

## Acceptance Examples

- **AE1 (CR1/CR2):** ChatGPT/Claude's connector setup discovers the metadata, completes DCR +
  authorize (operator approves) + token, and lists hypermnesic's tools.
- **AE2 (CR5):** a `read`-scoped connector calls `commit_note` → refused (insufficient_scope); a
  `write`-scoped one succeeds and the note is a real git commit.
- **AE3 (CR6):** a `commit_note` to `CLAUDE.md` or `../etc/x` from the cloud is refused (protected
  path / outside repo), regardless of scope.
- **AE4 (CR7):** an internet client completes DCR but cannot obtain a token without the operator's
  approval at `/authorize`.
- **AE5 (CR8):** the operator revokes a connector; its next call is 401.

## Scope Boundaries

- **Out:** multi-user / multi-tenant memory, per-note ACLs, non-ChatGPT/Claude clients, and any
  change to the tailnet machine lane (U2/U12) or the gbrain decommission.
- **In:** the public read+write OAuth MCP lane, its AS + consent gate + public exposure + the
  rewritten threat model.

## Open Questions (resolve at sign-off — these shape the build)

1. **Consent model for the public write surface (CR7) — the pivotal one.** Pick:
   (a) an **out-of-band approval token** the operator supplies at `/authorize` (tight, simple — the
   honcho-proxy pattern); (b) a **per-connection approval page** the operator clicks; (c) **two
   scopes**: open self-service for `read` connectors, approval-gated for `write`. *Recommendation:
   (c) — read is low-risk + self-service; write requires explicit approval.*
2. **Exposure mechanism:** **Tailscale Funnel** (fast, consistent with honcho's setup, exposes a
   tailnet node publicly) vs a **TLS reverse proxy** on a real domain (more control, more setup).
   *Recommendation: Funnel to start (lowest friction), revisit if a custom domain is wanted.*
3. **One AS or two?** Unify the cloud authorization_code lane with the U12 tailnet client_credentials
   lane in **one** AS (both grants), or keep them **separate** (cloud AS public, U12 AS tailnet)?
   *Recommendation: separate — different trust boundaries; the public AS never issues tailnet tokens.*
4. **Write path tightness for the public lane:** keep the default allowlist (`notes/ sources/
   dashboards/ captures/`), or **narrow** the public-write allowlist further (e.g. only `notes/` or a
   dedicated `mobile/` zone) so cloud writes land in a reviewable quarantine? *Recommendation: a
   dedicated `captures/` or `mobile/` zone for cloud writes — easy to review/revert.*
5. **Token storage + lifetime values** (TTL, refresh, where issued tokens persist — owner-only,
   never committed) — concrete numbers at impl.
6. **Verify exact ChatGPT + Claude connector requirements at build time** (the connector OAuth
   surface evolves) — a compatibility spike (register → authorize → token → tools/list) against each
   app before declaring done.

## Dependencies / Assumptions

- MCP Python SDK `OAuthAuthorizationServerProvider` + `create_auth_routes` (present, v1.27.2).
- A public-exposure path (Funnel is available; honcho already uses it).
- The per-tool write-scope fix (`e55b75b`) + commit_note's guards (shipped) — the write blast-radius bound.
- Independent of gbrain (decommission parked) and honcho (not reused).
