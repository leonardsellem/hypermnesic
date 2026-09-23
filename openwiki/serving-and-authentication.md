---
type: Reference
title: Serving Topology and Authentication
description: The two serving lanes — a public OAuth 2.1 endpoint with DCR, PKCE, an operator consent gate and audience-bound revocable tokens, and a read-only tailnet companion — plus the invariants that keep them safe.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-362e06c30ccfdafd87339cb0
    resource: repo://ARCHITECTURE.md
  - id: openwiki-source-b056bdca91307e7c890b5f5b
    resource: repo://docs/guides/consent-and-clients.md
  - id: openwiki-source-196170e31ff8ec60a116165b
    resource: repo://docs/README.md
  - id: openwiki-source-e2983cb60d29dab96c31cfed
    resource: repo://src/hypermnesic/auth_cloud.py
  - id: openwiki-source-861fbaa0347100b4d192e5ad
    resource: repo://src/hypermnesic/auth.py
  - id: openwiki-source-d0135879c44e5d0086df3a05
    resource: repo://src/hypermnesic/client_control.py
  - id: openwiki-source-37433895d4b7b6af7cd92f4f
    resource: repo://src/hypermnesic/mcp_server.py
  - id: openwiki-source-87f19794e1a4a64b281d2c35
    resource: repo://tests/test_auth_cloud.py
  - id: openwiki-source-38ecedb631614a845441bec9
    resource: repo://tests/test_auth.py
  - id: openwiki-source-9241ab90871fd251f3253d0f
    resource: repo://tests/test_mcp_server.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Serving Topology and Authentication

**There are exactly two network lanes.** Older material describing a "tailnet-only" system or
four lanes is superseded.

| Lane | Auth | Tools |
|---|---|---|
| Public OAuth `/mcp` | OAuth 2.1: DCR + PKCE + operator consent | Read tools always; the write tool by scope |
| Tailnet read companion | None — tailnet membership is the boundary | Read tools only |

Every remote client — a chat connector, the coding-agent plugin, a companion app — uses the
**same** public lane in the same way. The tailnet companion exists for read surfaces on
tailnet devices, and it is read-only.

## Bind and configuration invariants

Three refusals happen **at construction**, before a server exists to be misused:

1. **`0.0.0.0` is refused.** The server must bind a specific interface address. A wildcard
   bind is not a warning; it fails.
2. **Auth is configured as a pair.** Settings plus *either* a token verifier (resource-server
   only, the tailnet lane) *or* an authorization-server provider (the cloud lane). Settings
   without a validator, a validator without settings, or both validators at once are all
   refused — a half-configured auth surface never starts.
3. **`write_enabled ⇒ auth-required`** on any non-loopback bind. A write-enabled server
   without auth refuses to start, so a unit re-render or a rollback can never silently serve
   the write tool unauthenticated.

A **loopback bind is exempt** from the third rule, because it is reachable only by the local
user — the same trust boundary the CLI write path already has.

There is exactly one bounded opt-out. An explicit tailnet-write flag accepts tailnet
membership itself as the write boundary — valid once the public lane carries all untrusted
traffic — but it is **restricted to the Tailscale CGNAT range**. Passing it with a
non-tailnet host is refused with an explicit message: that would be a public write hole, not a
tailnet one. The wildcard refusal still fires regardless. And every write guard still applies
on top. See [Write Guard and Security Model](write-guard-and-security-model.md).

For the public lane, the issuer and resource must be **HTTPS public origins with DNS
hostnames**. A plain-HTTP URL is refused, and so is a bare IP — not on style grounds, but
because such an endpoint is undiscoverable over the standard metadata chain, which was the
original reason a separate public lane existed at all.

## The tailnet lane: resource-server auth

Here the engine is purely a **Resource Server** validating tokens some Authorization Server
issued. Two invariants are enforced on top of whatever raw validation strategy is injected:

- **Strict audience binding.** A structurally valid token minted for a *different* resource
  server is rejected. Being well-formed and unexpired is not enough; it must have been minted
  for **this** resource.
- **Expiry.**

It **fails closed**: any raw-validation error rejects the request rather than surfacing a
server error, and the token is never echoed.

The production raw strategy uses token introspection, because the upstream server issues opaque
tokens with no key set to verify against. The introspection endpoint is **discovered** from the
issuer rather than hardcoded, and the resource server's own client credentials come from the
environment, never from committed configuration. If the authorization server exposes no
introspection endpoint, the strategy **fails loudly** rather than degrading to trusting the
token — an explicit signal that something upstream must be reconciled.

Auth on this lane is opt-in and additive: a read-only serve with no auth remains valid.

## The public lane: a full Authorization Server

The public lane implements the interactive flow end to end: Dynamic Client Registration →
authorize → an **operator-authenticated consent page** → an audience-bound, PKCE-protected
authorization code → token exchange yielding access and refresh tokens.

### Why consent must authenticate the operator

This is the load-bearing reasoning. The lane fronts a **public, internet-reachable write**
endpoint, and DCR means *any* internet client can register itself. The only thing between the
open internet and write access to someone's memory is the consent step — so consent must
authenticate the operator and must never auto-approve.

Concretely: authorize returns a **redirect to the consent route** rather than minting a code,
and only finalizing consent with the operator's approval token issues one. The approval token
is stored **hashed** and compared in constant time, with an enforced entropy floor.

The pending-request pool is bounded on three axes so an anonymous endpoint cannot be turned
into a resource sink: unconsented requests expire on a short TTL, a pending request is dropped
after a small number of wrong approval-token attempts, and the total pending count is capped.

### The consent page

Plain, script-free, and not cached. Its headers deny framing, set a no-store cache policy and a
no-referrer policy, and apply a content-security policy of `default-src 'none'` so no script
runs.

One subtlety is documented because getting it wrong produces a baffling bug: the policy's
`form-action` is enforced against **redirect targets**, so a bare `'self'` would make the
browser silently drop the post-approval redirect to the client — the grant would be consumed
while the app never received the code, presenting as "the first Approve does nothing, and the
retry says expired". The policy therefore allows self plus the single registered client origin,
and nothing else. The redirect carries only the authorization code, never the approval token.

The page also avoids being an injection sink: an unknown pending id renders a **generic** error
rather than reflecting attacker-supplied input, and every client-supplied field — the
registered client name, the redirect URI — is HTML-escaped.

### Why the metadata advertises a public-client method

The published authorization-server metadata lists `none` alongside the client-secret methods
for both token and revocation endpoints. That is deliberate: app connectors and coding-agent
hosts frequently register through DCR **without** a client secret, and an AS that advertised
only confidential-client methods would be unusable by them. PKCE with `S256` is what protects
the code exchange for those public clients, and it is validated on token exchange.

### Tokens, rotation, and whole-grant revocation

Tokens are opaque and audience-bound. Refresh **rotates**: exchanging a refresh token
invalidates the consumed one.

Access and refresh tokens are linked as **siblings under one grant**, and that linkage is the
point — revoking a grant kills the whole path, not just the current access token. A client
whose grant was revoked cannot quietly recover by refreshing. The provider also re-checks the
owner-visible grant store on load and refresh, so a grant marked revoked out of band is honoured
on the next validation rather than at the next restart.

### Two state files, deliberately separate

| File | Contains | Purpose |
|---|---|---|
| Grant metadata store | Secret-free reviewable fields only | The **owner control surface** — listing and revocation |
| Cloud OAuth state | Client registrations and opaque bearer/refresh material | **Restart survivability** for refresh across deploys |

The second is written owner-only, outside committed content, and is **not** a listing surface —
it is never committed, logged, or shared. Keeping them apart is what lets an owner inspect and
revoke grants without ever touching credential material. It carries a version field and refuses
to load an unrecognized version rather than guessing at the format. See
[Memory and Client Control](memory-and-client-control.md).

## Scopes

Read tools are always registered. The write tool is registered **only** on a write-enabled
server and additionally self-enforces the `write` scope per call, independently of the
transport's global scope list — because the SDK middleware applies one scope list to every
tool and therefore cannot separate read clients from write clients on a single endpoint. See
[MCP Tool Surface](mcp-tool-surface.md).

Unsupported scope values are rejected loudly at startup rather than being silently dropped
into the metadata.

## Transport shape

The server serves buffered single-JSON responses and runs stateless by default, both flipped
from the SDK defaults. This is for a concrete reason: a buffering, handshake-less client hangs
waiting on a streamed response, and a stateful server rejects a bare single-shot call for a
missing session id — exactly the call such a client makes. Nothing is lost, because every tool
is a stateless request/response with no session-scoped state and no server-initiated streaming,
and full-handshake clients still connect normally.
