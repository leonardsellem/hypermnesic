"""U12 — the minimal tailnet-internal Authorization Server (the token issuer the U2
Resource Server validates). Test-first, security-sensitive.

honcho-oauth-proxy can't be reused (opaque tokens, no introspection, audience hardwired
to its own resource — see docs/oauth-as-finding.md), so this is a new minimal AS. It uses
the **client_credentials** grant (the three agent identities are machine clients — no
interactive authorize/redirect), binds the token audience to the requested resource
(RFC 8707), exposes RFC 7662 introspection (so the RS can validate the opaque token), and
supports revocation + a token-lifetime ceiling. DCR is locked to pre-seeded static clients.

The spec here is the AS core (issue / introspect / audience / scope / expiry / revoke /
client-auth) plus the end-to-end loop with the U2 verifier — all offline (no sockets).
Secrets are never echoed.
"""

from __future__ import annotations

import json

import pytest

from hypermnesic import auth_server

RES = "https://homelab.taildabf2.ts.net/mcp"
OTHER = "https://homelab.taildabf2.ts.net/other"


def _as(ttl=3600, now=None):
    a = auth_server.MinimalAS(allowed_resources=[RES], token_ttl_seconds=ttl, now=now)
    a.add_client("homelab-claude", "claude-secret", scopes=["read", "write"])
    a.add_client("hypermnesic-rs", "rs-secret", scopes=[], is_rs=True)   # the introspection client
    return a


# --- client_credentials issuance + audience binding --------------------------

def test_issue_binds_audience_to_requested_resource():
    a = _as()
    tok = a.issue_client_credentials("homelab-claude", "claude-secret", resource=RES, scope="write")
    assert "access_token" in tok and tok["token_type"].lower() == "bearer"
    intro = a.introspect(tok["access_token"], "hypermnesic-rs", "rs-secret")
    assert intro["active"] is True
    assert intro["aud"] == RES                      # RFC 8707: audience == requested resource
    assert "write" in intro["scope"].split()
    assert intro["client_id"] == "homelab-claude"


def test_issue_rejects_bad_client_secret():
    a = _as()
    with pytest.raises(auth_server.OAuthError) as exc:
        a.issue_client_credentials("homelab-claude", "WRONG", resource=RES, scope="write")
    assert exc.value.error == "invalid_client"


def test_issue_rejects_unknown_client():
    a = _as()
    with pytest.raises(auth_server.OAuthError):
        a.issue_client_credentials("ghost", "x", resource=RES, scope="write")


def test_issue_rejects_disallowed_resource():
    a = _as()
    with pytest.raises(auth_server.OAuthError) as exc:
        a.issue_client_credentials("homelab-claude", "claude-secret", resource=OTHER, scope="write")
    assert exc.value.error == "invalid_target"      # RFC 8707: unknown resource → refused


def test_issued_scope_is_clamped_to_client_grant():
    a = _as()
    a.add_client("reader", "r-secret", scopes=["read"])
    tok = a.issue_client_credentials("reader", "r-secret", resource=RES, scope="read write")
    intro = a.introspect(tok["access_token"], "hypermnesic-rs", "rs-secret")
    assert "write" not in intro["scope"].split() and "read" in intro["scope"].split()


# --- RFC 7662 introspection --------------------------------------------------

def test_introspect_requires_valid_rs_credentials():
    a = _as()
    tok = a.issue_client_credentials("homelab-claude", "claude-secret", resource=RES, scope="write")
    with pytest.raises(auth_server.OAuthError):
        a.introspect(tok["access_token"], "hypermnesic-rs", "WRONG-rs-secret")


def test_introspect_unknown_token_is_inactive():
    a = _as()
    assert a.introspect("honcho_at_nope", "hypermnesic-rs", "rs-secret") == {"active": False}


def test_introspect_expired_token_is_inactive():
    clock = {"t": 1_000_000}
    a = _as(ttl=10, now=lambda: clock["t"])
    tok = a.issue_client_credentials("homelab-claude", "claude-secret", resource=RES, scope="write")
    clock["t"] += 11                                # past the TTL ceiling
    assert a.introspect(tok["access_token"], "hypermnesic-rs", "rs-secret") == {"active": False}


def test_revoke_then_introspect_inactive():
    a = _as()
    tok = a.issue_client_credentials("homelab-claude", "claude-secret", resource=RES, scope="write")
    assert a.revoke(tok["access_token"], "homelab-claude", "claude-secret") is True
    assert a.introspect(tok["access_token"], "hypermnesic-rs", "rs-secret") == {"active": False}


def test_revoke_requires_token_ownership():
    # RFC 7009: only the client a token was issued to may revoke it — a different
    # authenticated client cannot revoke (or even confirm) another identity's token.
    a = _as()
    a.add_client("other", "other-secret", scopes=["read"])
    tok = a.issue_client_credentials("homelab-claude", "claude-secret", resource=RES, scope="write")
    assert a.revoke(tok["access_token"], "other", "other-secret") is False        # not the owner
    assert a.introspect(tok["access_token"], "hypermnesic-rs", "rs-secret")["active"] is True
    assert a.revoke(tok["access_token"], "homelab-claude", "claude-secret") is True  # owner can
    assert a.introspect(tok["access_token"], "hypermnesic-rs", "rs-secret") == {"active": False}


# --- metadata (RFC 8414) ----------------------------------------------------

def test_metadata_advertises_introspection_and_token_endpoints():
    a = _as()
    meta = a.metadata("https://homelab.taildabf2.ts.net/hypermnesic-as")
    assert meta["issuer"]
    assert meta["token_endpoint"].endswith("/token")
    assert meta["introspection_endpoint"].endswith("/introspect")
    assert "client_credentials" in meta["grant_types_supported"]
    assert set(meta["scopes_supported"]) >= {"read", "write"}


# --- DCR lock ----------------------------------------------------------------

def test_dcr_locked_refuses_dynamic_registration():
    a = _as()                                       # default: DCR locked to static clients
    with pytest.raises(auth_server.OAuthError) as exc:
        a.register_dynamic_client(client_name="rogue")
    assert exc.value.error in {"access_denied", "invalid_request"}


# --- secrets never echoed ----------------------------------------------------

def test_introspection_response_never_includes_secret():
    a = _as()
    tok = a.issue_client_credentials("homelab-claude", "claude-secret", resource=RES, scope="write")
    intro = a.introspect(tok["access_token"], "hypermnesic-rs", "rs-secret")
    blob = repr(intro) + repr(tok)
    assert "claude-secret" not in blob and "rs-secret" not in blob


# --- end-to-end: U12 AS issues → U2 RS verifier validates --------------------

def test_end_to_end_as_token_validates_through_rs_verifier():
    from hypermnesic import auth as rs_auth
    a = _as()
    tok = a.issue_client_credentials("homelab-claude", "claude-secret", resource=RES, scope="write")

    # the RS verifier introspects against THIS AS (no network: call introspect directly)
    def verify_raw(token):
        intro = a.introspect(token, "hypermnesic-rs", "rs-secret")
        if not intro.get("active"):
            return None
        from mcp.server.auth.provider import AccessToken
        return AccessToken(token=token, client_id=intro["client_id"],
                           scopes=intro["scope"].split(), expires_at=intro.get("exp"),
                           resource=intro.get("aud"), subject=intro.get("sub"),
                           claims={"aud": intro.get("aud")})

    verifier = rs_auth.build_token_verifier(resource_server_url=RES, verify_raw=verify_raw)
    import asyncio
    at = asyncio.run(verifier.verify_token(tok["access_token"]))
    assert at is not None and "write" in at.scopes      # full loop: AS → RS, audience-bound, valid


def test_end_to_end_cross_resource_token_rejected_by_rs():
    # a token the AS would only mint for RES; if an RS for a DIFFERENT resource introspects
    # it, the audience check rejects it (defense in depth on top of the AS's resource allowlist)
    from hypermnesic import auth as rs_auth
    a = _as()
    tok = a.issue_client_credentials("homelab-claude", "claude-secret", resource=RES, scope="write")

    def verify_raw(token):
        intro = a.introspect(token, "hypermnesic-rs", "rs-secret")
        if not intro.get("active"):
            return None
        from mcp.server.auth.provider import AccessToken
        return AccessToken(token=token, client_id=intro["client_id"],
                           scopes=intro["scope"].split(), expires_at=intro.get("exp"),
                           resource=intro.get("aud"), claims={"aud": intro.get("aud")})

    other_rs = rs_auth.build_token_verifier(resource_server_url=OTHER, verify_raw=verify_raw)
    import asyncio
    assert asyncio.run(other_rs.verify_token(tok["access_token"])) is None  # wrong audience


# --- HTTP dispatch (the deployed surface) -----------------------------------

def _form(d: dict) -> bytes:
    from urllib.parse import urlencode
    return urlencode(d).encode()


def test_http_metadata_then_token_then_introspect_roundtrip():
    a = _as()
    a.public_url = "https://homelab.taildabf2.ts.net/hypermnesic-as"
    status, _, body = a.handle("GET", "/.well-known/oauth-authorization-server", {}, b"")
    assert status == 200
    meta = json.loads(body)
    assert meta["introspection_endpoint"].endswith("/introspect")

    status, _, body = a.handle("POST", "/token", {}, _form(
        {"grant_type": "client_credentials", "client_id": "homelab-claude",
         "client_secret": "claude-secret", "resource": RES, "scope": "write"}))
    assert status == 200
    token = json.loads(body)["access_token"]

    status, _, body = a.handle("POST", "/introspect", {}, _form(
        {"token": token, "client_id": "hypermnesic-rs", "client_secret": "rs-secret"}))
    assert status == 200 and json.loads(body)["active"] is True


def test_http_bad_client_returns_401_no_secret_leak():
    a = _as()
    status, _, body = a.handle("POST", "/token", {}, _form(
        {"grant_type": "client_credentials", "client_id": "homelab-claude",
         "client_secret": "WRONG", "resource": RES, "scope": "write"}))
    assert status == 401
    assert "WRONG" not in body.decode() and json.loads(body)["error"] == "invalid_client"


def test_http_register_is_locked():
    a = _as()
    status, _, body = a.handle("POST", "/register", {}, _form({"client_name": "rogue"}))
    assert status == 403 and json.loads(body)["error"] == "access_denied"
