# U12 native-primitive finding — can honcho-oauth-proxy be the hypermnesic AS?

**Date:** 2026-06-02 · **Unit:** U12 · **Rule:** native-primitives-first (CLAUDE.md) — evaluate
reusing the existing homelab AS before building a new one. **Verdict: cannot reuse as-is; build
a new minimal AS** (which U12 does, gbrain-independent).

## What was evaluated

`honcho-oauth-proxy.service` — a custom OAuth 2.1 proxy on the homelab, live at
`127.0.0.1:8788`, public issuer `https://homelab.taildabf2.ts.net/honcho/`. Source:
`~/.honcho/oauth-proxy/honcho_oauth_proxy.py` (607 lines, stdlib HTTP, JSON state file). Its
discovery advertises `authorization_endpoint`, `token_endpoint`, `revocation_endpoint`,
`registration_endpoint` (DCR), and `scopes_supported: [read, write]`.

## Why it does not fit (three hard blockers)

1. **No token-validation surface for an external RS.** honcho issues **opaque** access tokens
   (`access_token = "honcho_at_" + secrets.token_urlsafe(32)`) and validates them only
   **internally** (`validate_bearer()`), to gate its own `proxy_mcp()` reverse-proxy. There is
   **no RFC 7662 `/introspect` endpoint** (probe: HTTP 404) and **no `jwks_uri` / JWT** (probe:
   404). A separate Resource Server (hypermnesic) therefore has **no way to validate** an honcho
   token — neither by introspection nor by JWT signature.
2. **Audience hardwired to honcho's own resource.** `protected_resource_metadata()` returns
   `resource = public_url + "/mcp"` → `homelab.taildabf2.ts.net/honcho/mcp`. Issuance does not
   honor a per-request RFC 8707 `resource` indicator, so honcho **cannot mint an audience-bound
   token for `homelab.taildabf2.ts.net/mcp`** (hypermnesic's resource). Every honcho token is, in
   effect, for honcho's own MCP.
3. **Shared-service blast radius.** honcho is a live reverse-proxy fronting honcho's MCP for
   another integration. Adding introspection + a second resource audience would be surgery on a
   running shared service — higher risk than a separate, isolated AS, and it would couple
   hypermnesic's auth lifecycle to honcho's.

A fourth, softer point: the plan requires the hypermnesic AS to be **independent of any AS that
gets torn down** so the gbrain decommission (U11) can never lock hypermnesic out. Co-tenanting on
honcho would re-introduce exactly that coupling risk.

## Decision

Build a **new minimal AS** (`src/hypermnesic/auth_server.py`, `MinimalAS`) that **reuses honcho's
proven *shape*** — stdlib HTTP, JSON state file, opaque tokens — but as a **separate,
gbrain-independent** service that adds what honcho lacks:

- the **client_credentials** grant (the three agent identities are machine clients — no
  interactive authorize/redirect lane needed);
- **RFC 8707 audience binding** to the requested resource, with a resource allowlist;
- **RFC 7662 introspection** so the hypermnesic RS (U2) can validate the opaque token;
- **revocation** + a **token-lifetime ceiling** (a leaked token is bounded);
- **DCR locked** to pre-seeded static clients (tighter than tailnet-wide DCR).

Cost of the new AS over reuse: one more small always-on service to run + monitor (a recall SPOF —
mitigated by U11's AS-availability monitoring and the hook's silent-degrade). This is accepted as
strictly lower-risk than modifying the running honcho, and it keeps the gbrain-independence
invariant the teardown depends on.

## Probes (read-only, 2026-06-02)

- `GET /.well-known/oauth-authorization-server` → 200 (no `jwks_uri`, no `introspection_endpoint`).
- `GET /.well-known/jwks.json`, `/jwks`, `/introspect` → 404.
- Source: opaque token mint (`honcho_at_…`), internal `validate_bearer`, `resource = …/honcho/mcp`.
