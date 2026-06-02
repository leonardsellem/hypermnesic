"""Cloud OAuth MCP — the public authorization_code + DCR + PKCE Authorization Server
provider (ChatGPT/Claude mobile lane). Test-first, security-sensitive.

This is the SDK's OAuthAuthorizationServerProvider, so cloud connectors get the standard
interactive flow: DCR (/register) → /authorize → an operator-authenticated consent page
(the honcho model: a public WRITE endpoint must not be anonymous-approvable) → an
audience-bound, scoped authorization code → /token (the SDK validates PKCE) → access +
refresh tokens. The spec here is the provider methods + the consent gate, exercised
directly (no sockets). Secrets/tokens are never echoed; the approval token is stored hashed.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull

from hypermnesic import auth_cloud

RES = "https://homelab.taildabf2.ts.net/cloud/mcp"
PUBLIC = "https://homelab.taildabf2.ts.net/cloud"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"


def _provider(now=None, token_ttl=3600, code_ttl=300):
    return auth_cloud.CloudAuthProvider(
        resource=RES, public_url=PUBLIC, approval_token="op-approval-secret",
        scopes_supported=["read", "write"], token_ttl_seconds=token_ttl,
        code_ttl_seconds=code_ttl, now=now)


def _client(scope="read write") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="cid-1", client_secret="csecret", redirect_uris=[REDIRECT],
        grant_types=["authorization_code", "refresh_token"], response_types=["code"],
        scope=scope, token_endpoint_auth_method="client_secret_post")


def _params(scopes=("read",), challenge="abc123challenge"):
    return AuthorizationParams(state="xyz", scopes=list(scopes), code_challenge=challenge,
                               redirect_uri=REDIRECT, redirect_uri_provided_explicitly=True,
                               resource=RES)


def _run(coro):
    return asyncio.run(coro)


# --- DCR --------------------------------------------------------------------

def test_register_then_get_client_roundtrip():
    p = _provider()
    c = _client()
    _run(p.register_client(c))
    got = _run(p.get_client("cid-1"))
    assert got is not None and got.client_id == "cid-1"
    assert _run(p.get_client("nope")) is None


# --- authorize → operator-authenticated consent (the public-write gate) ------

def test_authorize_routes_to_consent_not_straight_to_code():
    p = _provider()
    _run(p.register_client(_client()))
    url = _run(p.authorize(_client(), _params()))
    # the public WRITE endpoint must NOT mint a code anonymously: authorize routes to the
    # operator-authenticated consent page, carrying a pending id (not a code to the client).
    assert url.startswith(PUBLIC + "/consent")
    assert "pending=" in url
    assert "code=" not in url


def test_consent_with_approval_token_issues_code_redirect():
    p = _provider()
    _run(p.register_client(_client()))
    pending = _run(p.authorize(_client(), _params(scopes=("read", "write")))).split("pending=")[1]
    # wrong/empty approval token → denied, no code
    with pytest.raises(auth_cloud.ConsentError):
        p.finalize_consent(pending, approval_token="WRONG")
    with pytest.raises(auth_cloud.ConsentError):
        p.finalize_consent(pending, approval_token="")
    # the operator's approval token → redirect to the client with code + state
    redirect = p.finalize_consent(pending, approval_token="op-approval-secret")
    assert redirect.startswith(REDIRECT) and "code=" in redirect and "state=xyz" in redirect


def test_consent_token_never_compared_in_plaintext_storage():
    p = _provider()
    # the approval token is stored hashed, never as plaintext on the instance/state
    blob = repr(vars(p))
    assert "op-approval-secret" not in blob


# --- code exchange (PKCE validated by the SDK; we issue audience-bound tokens) ---

def _issue_code(p, scopes=("read", "write")):
    pending = _run(p.authorize(_client(), _params(scopes=scopes))).split("pending=")[1]
    redirect = p.finalize_consent(pending, approval_token="op-approval-secret")
    return redirect.split("code=")[1].split("&")[0]


def _redeem(p, scopes=("read", "write")):
    """Issue a code and exchange it for tokens (the SDK validates PKCE at /token)."""
    auth_code = _run(p.load_authorization_code(_client(), _issue_code(p, scopes=scopes)))
    return _run(p.exchange_authorization_code(_client(), auth_code))


def test_load_and_exchange_authorization_code_issues_bound_tokens():
    p = _provider()
    _run(p.register_client(_client()))
    code = _issue_code(p, scopes=("read", "write"))
    auth_code = _run(p.load_authorization_code(_client(), code))
    assert auth_code is not None
    assert auth_code.code_challenge == "abc123challenge"          # PKCE challenge kept for the SDK
    assert str(auth_code.resource).rstrip("/") == RES             # RFC 8707 audience bound
    assert "write" in auth_code.scopes
    tokens = _run(p.exchange_authorization_code(_client(), auth_code))
    assert tokens.access_token and tokens.refresh_token and tokens.token_type.lower() == "bearer"
    # single-use: the code cannot be loaded again after exchange
    assert _run(p.load_authorization_code(_client(), code)) is None


def test_access_token_validates_then_expires():
    clock = {"t": 1_000_000}
    p = _provider(now=lambda: clock["t"], token_ttl=10)
    _run(p.register_client(_client()))
    tokens = _redeem(p, scopes=("read",))
    at = _run(p.load_access_token(tokens.access_token))
    assert at is not None and str(at.resource).rstrip("/") == RES and "read" in at.scopes
    clock["t"] += 11                                              # past TTL
    assert _run(p.load_access_token(tokens.access_token)) is None


def test_refresh_then_revoke():
    p = _provider()
    _run(p.register_client(_client()))
    tokens = _redeem(p, scopes=("read",))
    rt = _run(p.load_refresh_token(_client(), tokens.refresh_token))
    assert rt is not None
    refreshed = _run(p.exchange_refresh_token(_client(), rt, scopes=["read"]))
    assert refreshed.access_token and refreshed.access_token != tokens.access_token
    # revoke the (refreshed) access token → no longer valid
    at = _run(p.load_access_token(refreshed.access_token))
    _run(p.revoke_token(at))
    assert _run(p.load_access_token(refreshed.access_token)) is None


def test_metadata_advertises_authorization_code_and_dcr():
    p = _provider()
    meta = p.metadata()
    assert "authorization_code" in meta["grant_types_supported"]
    assert "S256" in meta["code_challenge_methods_supported"]
    assert meta["registration_endpoint"].endswith("/register")
    assert meta["authorization_endpoint"].endswith("/authorize")
    assert set(meta["scopes_supported"]) >= {"read", "write"}


# --- security-review fixes (pre-public-exposure) ----------------------------

def test_revocation_kills_the_whole_grant_incl_refresh():
    # Critical: revoking the access token must also kill its refresh token (the operator's
    # kill switch) — otherwise a leaked grant re-mints access tokens for the refresh TTL.
    p = _provider()
    _run(p.register_client(_client()))
    tokens = _redeem(p)
    _run(p.revoke_token(_run(p.load_access_token(tokens.access_token))))
    assert _run(p.load_access_token(tokens.access_token)) is None
    assert _run(p.load_refresh_token(_client(), tokens.refresh_token)) is None   # refresh dead too


def test_refresh_rotates_old_token_invalidated():
    # High: exchanging a refresh token must invalidate the old one (rotation), not leave both live.
    p = _provider()
    _run(p.register_client(_client()))
    tokens = _redeem(p)
    old_rt = _run(p.load_refresh_token(_client(), tokens.refresh_token))
    _run(p.exchange_refresh_token(_client(), old_rt, scopes=["read"]))
    assert _run(p.load_refresh_token(_client(), tokens.refresh_token)) is None   # old refresh dead


def test_wrong_approval_token_drops_pending_after_max_failures():
    # High: a fixed pending_id must not be brute-forceable indefinitely.
    p = _provider()
    _run(p.register_client(_client()))
    pending = _run(p.authorize(_client(), _params())).split("pending=")[1]
    for _ in range(5):
        with pytest.raises(auth_cloud.ConsentError):
            p.finalize_consent(pending, approval_token="WRONG")
    # after the failure cap the pending is gone — the correct token no longer works either
    with pytest.raises(auth_cloud.ConsentError):
        p.finalize_consent(pending, approval_token="op-approval-secret")


def test_pending_expires():
    clock = {"t": 1_000_000}
    p = auth_cloud.CloudAuthProvider(resource=RES, public_url=PUBLIC,
                                     approval_token="op-approval-secret",
                                     scopes_supported=["read", "write"], now=lambda: clock["t"])
    _run(p.register_client(_client()))
    pending = _run(p.authorize(_client(), _params())).split("pending=")[1]
    clock["t"] += 10_000                                          # well past the pending TTL
    with pytest.raises(auth_cloud.ConsentError):
        p.finalize_consent(pending, approval_token="op-approval-secret")


def test_access_token_audience_enforced_at_load():
    # Low (defense-in-depth): a token whose bound resource isn't ours is rejected at the RS.
    p = _provider()
    _run(p.register_client(_client()))
    tokens = _redeem(p)
    at = _run(p.load_access_token(tokens.access_token))
    assert str(at.resource).rstrip("/") == RES                   # bound to our single resource
    # tamper the stored resource → load rejects it
    p._access[tokens.access_token].resource = "https://homelab.taildabf2.ts.net/other"
    assert _run(p.load_access_token(tokens.access_token)) is None


def test_pending_details_exposes_client_for_an_identified_consent():
    p = _provider()
    c = OAuthClientInformationFull(
        client_id="cid-1", client_secret="s", redirect_uris=[REDIRECT],
        grant_types=["authorization_code"], response_types=["code"], scope="read write",
        client_name="ChatGPT", token_endpoint_auth_method="none")
    _run(p.register_client(c))
    pending = _run(p.authorize(c, _params(scopes=("read", "write")))).split("pending=")[1]
    details = p.pending_details(pending)
    assert details is not None
    assert details["client_id"] == "cid-1" and "write" in details["scopes"]
    assert REDIRECT.split("/")[2] in str(details["redirect_uri"])  # operator sees the host
    assert p.pending_details("unknown-id") is None                 # unknown → None (no reflection)


# --- serve wiring: build_cloud_server (AS+RS + DCR + consent + write tool) ----

def test_build_cloud_server_wires_as_dcr_consent_and_write_tool(make_corpus, fake_embedder):
    import asyncio as _aio

    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(
        db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
        resource=RES, public_url=PUBLIC, approval_token="op-secret")
    assert srv.settings.auth is not None
    assert str(srv.settings.auth.resource_server_url).rstrip("/") == RES
    assert srv.settings.auth.client_registration_options.enabled is True      # DCR wired
    assert srv.settings.auth.revocation_options.enabled is True               # revocation wired
    names = {t.name for t in _aio.run(srv.list_tools())}
    assert "commit_note" in names and {"search", "resolve"} <= names          # read + write
    assert "/consent" in [r.path for r in srv._custom_starlette_routes]       # consent route added


def test_consent_render_escapes_client_fields_and_hides_unknown_pending():
    # Critical (XSS): the consent page must HTML-escape attacker-controlled DCR fields, and
    # must NOT reflect an unknown/arbitrary pending id at all (the reflected-XSS sink).
    from hypermnesic import mcp_server
    p = _provider()
    evil = OAuthClientInformationFull(
        client_id="cid-evil", client_secret="s", redirect_uris=["https://evil.example/cb"],
        grant_types=["authorization_code"], response_types=["code"], scope="read write",
        client_name="<script>alert(1)</script>", token_endpoint_auth_method="none")
    _run(p.register_client(evil))
    pending = _run(p.authorize(evil, _params(scopes=("read", "write")))).split("pending=")[1]
    html, status = mcp_server._render_consent(p, pending)
    assert status == 200
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html  # escaped
    assert "write" in html and "chatgpt.com" in html              # scopes + target shown
    html2, status2 = mcp_server._render_consent(p, '"><script>evil()</script>')
    assert status2 == 404 and "<script>evil()</script>" not in html2 and "evil()" not in html2


def test_cloud_server_defaults_to_tighter_write_zone(make_corpus, fake_embedder):
    # residual: the public lane defaults writes to a dedicated review zone (captures/), not the
    # full vault — a cloud write to notes/ is refused.
    import asyncio as _aio

    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
                                        resource=RES, public_url=PUBLIC,
                                        approval_token="op-approval-token-24chars-or-more")

    def _call(name, args):
        out = _aio.run(srv.call_tool(name, args))
        return out[1] if isinstance(out, tuple) else json.loads(out[0].text)

    var = auth_context_var.set(AuthenticatedUser(AccessToken(
        token="t", client_id="c", scopes=["read", "write"], resource=RES, claims={"aud": RES})))
    try:
        refused = _call("commit_note", {"path": "notes/x.md", "body": "# x\n\nbody.\n"})
        ok = _call("commit_note", {"path": "captures/x.md", "body": "# x\n\nbody.\n"})
    finally:
        auth_context_var.reset(var)
    assert refused["committed"] is False and refused["refused"]    # notes/ outside the cloud zone
    assert ok["committed"] is True                                 # captures/ = cloud zone
