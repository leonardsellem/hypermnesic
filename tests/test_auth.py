"""U2 — OAuth 2.1 Resource-Server auth (R12). Security-sensitive, test-first.

The engine is the RS: it validates bearer tokens a separate AS (U12) issues. The
spec here is the verifier's invariants — RFC 8707 strict audience binding + expiry —
on top of an injected raw-validation strategy (the deferred-to-impl AS seam), plus
the AuthSettings glue and the introspection resolver. No network: the raw validator
and the introspection POST are injected.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

from hypermnesic import auth

RES = "https://homelab.<tailnet-host>.ts.net/mcp"
ISS = "https://homelab.<tailnet-host>.ts.net/honcho/"


def _tok(**kw) -> AccessToken:
    base = dict(token="tok", client_id="homelab-claude", scopes=["write"],
                expires_at=None, resource=RES, subject="agent:homelab-claude",
                claims={"aud": RES, "iss": ISS})
    base.update(kw)
    return AccessToken(**base)


def _verify(v, token):
    return asyncio.run(v.verify_token(token))


# --- AuthSettings glue -------------------------------------------------------

def test_make_auth_settings_requires_issuer_and_resource():
    with pytest.raises(auth.ResourceAuthError):
        auth.make_auth_settings(issuer_url=ISS, resource_server_url="", required_scopes=["write"])
    with pytest.raises(auth.ResourceAuthError):
        auth.make_auth_settings(issuer_url="", resource_server_url=RES, required_scopes=["write"])
    s = auth.make_auth_settings(issuer_url=ISS, resource_server_url=RES, required_scopes=["write"])
    assert isinstance(s, AuthSettings)
    assert str(s.resource_server_url).rstrip("/") == RES
    assert s.required_scopes == ["write"]


def test_make_auth_settings_rejects_malformed_url():
    with pytest.raises(auth.ResourceAuthError):
        auth.make_auth_settings(issuer_url="not-a-url", resource_server_url=RES,
                                required_scopes=["write"])


# --- verifier: valid / invalid / expired ------------------------------------

def test_valid_token_with_audience_passes():
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=lambda t: _tok())
    at = _verify(v, "anytok")
    assert at is not None and "write" in at.scopes


def test_invalid_token_rejected():
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=lambda t: None)
    assert _verify(v, "bad") is None


def test_expired_token_rejected():
    past = int(time.time()) - 10
    v = auth.build_token_verifier(resource_server_url=RES,
                                  verify_raw=lambda t: _tok(expires_at=past))
    assert _verify(v, "expired") is None


def test_verify_raw_exception_fails_closed():
    def boom(_t):
        raise RuntimeError("AS unreachable")
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=boom)
    assert _verify(v, "x") is None          # fail-closed (no 500, no allow)


# --- RFC 8707 strict audience binding ---------------------------------------

def test_wrong_audience_rejected_rfc8707():
    other = "https://homelab.<tailnet-host>.ts.net/other"
    bad = _tok(resource=other, claims={"aud": other})
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=lambda t: bad)
    assert _verify(v, "crossrs") is None     # token minted for a different RS → rejected


def test_missing_audience_rejected_strict():
    noaud = _tok(resource=None, claims={})
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=lambda t: noaud)
    assert _verify(v, "noaud") is None       # strict: no audience → cannot bind → reject


def test_audience_accepted_from_claims_aud_list():
    multi = _tok(resource=None, claims={"aud": ["https://x/mcp", RES]})
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=lambda t: multi)
    assert _verify(v, "multi") is not None   # our resource present in the aud array


def test_audience_match_is_trailing_slash_insensitive():
    t = _tok(resource=RES + "/", claims={"aud": RES + "/"})
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=lambda t_: t)
    assert _verify(v, "slash") is not None


# --- async raw validator + credential hygiene -------------------------------

def test_async_verify_raw_supported():
    async def araw(_t):
        return _tok()
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=araw)
    assert _verify(v, "x") is not None


def test_verifier_never_logs_token(capsys):
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=lambda t: _tok())
    _verify(v, "SUPERSECRETTOKEN")
    cap = capsys.readouterr()
    assert "SUPERSECRETTOKEN" not in (cap.out + cap.err)     # tokens never echoed (V9)


# --- RFC 7662 introspection resolver (the production raw strategy) ------------

def test_introspection_resolver_maps_active_response():
    captured = {}

    def fake_post(url, *, data, auth):       # injected HTTP — no network
        captured["url"] = url
        captured["token"] = data["token"]
        return {"active": True, "scope": "read write", "aud": RES,
                "client_id": "homelab-claude", "exp": int(time.time()) + 3600,
                "sub": "agent:homelab-claude", "iss": ISS}

    raw = auth.introspection_verify_raw(introspection_url="https://as/introspect",
                                        client_id="rs", client_secret="shh", post_fn=fake_post)
    at = raw("opaque-token")
    assert at is not None
    assert (at.resource or "").rstrip("/") == RES      # aud (str) → RFC 8707 resource
    assert "write" in at.scopes and at.client_id == "homelab-claude"
    assert captured["token"] == "opaque-token"


def test_introspection_inactive_is_none():
    raw = auth.introspection_verify_raw(introspection_url="https://as/introspect",
                                        client_id="rs", client_secret="shh",
                                        post_fn=lambda *a, **k: {"active": False})
    assert raw("revoked") is None


def test_introspection_end_to_end_through_verifier_enforces_audience():
    # an active-but-wrong-audience introspection result is still rejected by the verifier
    def wrong_aud_post(url, *, data, auth):
        return {"active": True, "scope": "write", "aud": "https://homelab.<tailnet-host>.ts.net/other",
                "client_id": "c", "exp": int(time.time()) + 60}
    raw = auth.introspection_verify_raw(introspection_url="https://as/introspect",
                                        client_id="rs", client_secret="shh", post_fn=wrong_aud_post)
    v = auth.build_token_verifier(resource_server_url=RES, verify_raw=raw)
    assert _verify(v, "tok") is None
