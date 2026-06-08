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

RES = "https://example.ts.net/cloud/mcp"
PUBLIC = "https://example.ts.net/cloud"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"


def _provider(now=None, token_ttl=3600, code_ttl=300, refresh_ttl=30 * 24 * 3600,
              grant_store_path=None, default_scopes=None):
    return auth_cloud.CloudAuthProvider(
        resource=RES, public_url=PUBLIC, approval_token="op-approval-secret",
        scopes_supported=["read", "write"], token_ttl_seconds=token_ttl,
        code_ttl_seconds=code_ttl, refresh_ttl_seconds=refresh_ttl, now=now,
        grant_store_path=grant_store_path, default_scopes=default_scopes)


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


def test_reject_consent_redirects_with_error_and_no_grant():
    p = _provider()
    _run(p.register_client(_client()))
    pending = _run(p.authorize(_client(), _params(scopes=("read", "write")))).split("pending=")[1]
    redirect = p.reject_consent(pending, decision="reject")
    assert redirect.startswith(REDIRECT)
    assert "error=access_denied" in redirect and "state=xyz" in redirect
    assert "code=" not in redirect
    assert p._codes == {}
    assert p._access == {} and p._refresh == {}
    with pytest.raises(auth_cloud.ConsentError):
        p.finalize_consent(pending, approval_token="op-approval-secret")


def test_finalize_consent_result_includes_confirmation_state():
    p = _provider()
    c = OAuthClientInformationFull(
        client_id="cid-1", client_secret="s", redirect_uris=[REDIRECT],
        grant_types=["authorization_code"], response_types=["code"], scope="read write",
        client_name="ChatGPT", token_endpoint_auth_method="none")
    _run(p.register_client(c))
    pending = _run(p.authorize(c, _params(scopes=("read", "write")))).split("pending=")[1]
    result = p.finalize_consent_result(pending, approval_token="op-approval-secret")
    assert result["redirect_uri"].startswith(REDIRECT)
    assert result["confirmation"]["client_id"] == "cid-1"
    assert result["confirmation"]["client_name"] == "ChatGPT"
    assert result["confirmation"]["scopes"] == ["read", "write"]
    assert result["confirmation"]["write_enabled"] is True
    assert "commit_note" in result["confirmation"]["message"]


def test_authorize_uses_read_only_default_when_client_omits_scope():
    p = _provider()
    _run(p.register_client(_client()))
    pending = _run(p.authorize(_client(), _params(scopes=()))).split("pending=")[1]
    details = p.pending_details(pending)
    assert details is not None
    assert details["scopes"] == ["read"]


def test_authorize_uses_configured_default_scopes_when_client_omits_scope():
    p = _provider(default_scopes=["read", "write"])
    _run(p.register_client(_client()))
    pending = _run(p.authorize(_client(), _params(scopes=()))).split("pending=")[1]
    details = p.pending_details(pending)
    assert details is not None
    assert details["scopes"] == ["read", "write"]
    result = p.finalize_consent_result(pending, approval_token="op-approval-secret")
    assert result["confirmation"]["write_enabled"] is True


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


def test_grant_listing_records_read_and_write_metadata_without_tokens():
    p = _provider()
    c = OAuthClientInformationFull(
        client_id="cid-1", client_secret="s", redirect_uris=[REDIRECT],
        grant_types=["authorization_code"], response_types=["code"], scope="read write",
        client_name="ChatGPT", token_endpoint_auth_method="none")
    _run(p.register_client(c))
    read_tokens = _redeem(p, scopes=("read",))
    write_tokens = _redeem(p, scopes=("read", "write"))
    grants = p.list_grants()
    assert len(grants) == 2
    assert [g["write_enabled"] for g in grants] == [False, True]
    assert {g["client_id"] for g in grants} == {"cid-1"}
    assert {g["client_name"] for g in grants} == {"ChatGPT"}
    assert {g["redirect_origin"] for g in grants} == {"https://chatgpt.com"}
    blob = json.dumps(grants)
    assert read_tokens.access_token not in blob and read_tokens.refresh_token not in blob
    assert write_tokens.access_token not in blob and write_tokens.refresh_token not in blob
    assert "op-approval-secret" not in blob and "csecret" not in blob


def test_revoke_grant_invalidates_access_refresh_and_listing():
    p = _provider()
    _run(p.register_client(_client()))
    tokens = _redeem(p, scopes=("read", "write"))
    grant_id = p.list_grants()[0]["grant_id"]
    result = p.revoke_grant(grant_id)
    assert result["status"] == "revoked" and result["grant_id"] == grant_id
    assert _run(p.load_access_token(tokens.access_token)) is None
    assert _run(p.load_refresh_token(_client(), tokens.refresh_token)) is None
    grant = p.list_grants()[0]
    assert grant["status"] == "revoked" and grant["active"] is False


def test_expired_grant_not_reported_active_after_sweep():
    clock = {"t": 1_000_000}
    p = _provider(now=lambda: clock["t"], token_ttl=10, refresh_ttl=10)
    _run(p.register_client(_client()))
    _redeem(p, scopes=("read",))
    clock["t"] += 11
    grant = p.list_grants()[0]
    assert grant["status"] == "expired" and grant["active"] is False


def test_grant_store_persists_secret_free_metadata(tmp_path):
    store = tmp_path / "client-grants.json"
    p = _provider(grant_store_path=store)
    _run(p.register_client(_client()))
    tokens = _redeem(p, scopes=("read", "write"))
    raw = store.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["grants"][0]["write_enabled"] is True
    assert data["grants"][0]["status"] == "active"
    assert tokens.access_token not in raw and tokens.refresh_token not in raw
    assert "op-approval-secret" not in raw


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
    p._access[tokens.access_token].resource = "https://example.ts.net/other"
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
    assert srv.settings.auth.client_registration_options.default_scopes == ["read"]
    assert srv.settings.auth.revocation_options.enabled is True               # revocation wired
    names = {t.name for t in _aio.run(srv.list_tools())}
    assert "commit_note" in names and {"search", "resolve"} <= names          # read + write
    assert "/consent" in [r.path for r in srv._custom_starlette_routes]       # consent route added


def test_build_cloud_server_wires_configured_default_client_scopes(make_corpus, fake_embedder):
    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(
        db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
        resource=RES, public_url=PUBLIC, approval_token="op-secret",
        default_client_scopes=["read", "write"])
    assert srv.settings.auth.client_registration_options.default_scopes == ["read", "write"]


def test_cloud_server_metadata_advertises_public_client_token_auth(make_corpus, fake_embedder):
    from starlette.testclient import TestClient

    from hypermnesic import index, mcp_server

    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(
        db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
        resource=RES_U, public_url=PUBLIC_U,
        approval_token="op-approval-token-24chars-or-more")

    with TestClient(srv.streamable_http_app()) as client:
        resp = client.get("/.well-known/oauth-authorization-server")

    assert resp.status_code == 200
    meta = resp.json()
    assert "none" in meta["token_endpoint_auth_methods_supported"]
    assert "none" in meta["revocation_endpoint_auth_methods_supported"]


def test_cloud_server_trusts_public_host_behind_proxy(make_corpus, fake_embedder):
    # Regression (live 421): behind the Funnel the forwarded Host is the PUBLIC hostname, not
    # loopback. FastMCP auto-enables DNS-rebinding protection on a 127.0.0.1 bind with a
    # loopback-only allowlist, so a proxied /mcp call returns 421 "Invalid Host header".
    # build_cloud_server must trust the public host (from public_url/resource) so the mobile
    # connector's calls pass — while protection stays ON (an arbitrary attacker Host is rejected).
    from urllib.parse import urlparse

    from mcp.server.transport_security import TransportSecurityMiddleware

    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(
        db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
        resource=RES, public_url=PUBLIC, approval_token="op-approval-token-24chars-or-more")
    ts = srv.settings.transport_security
    assert ts is not None and ts.enable_dns_rebinding_protection is True     # protection stays ON
    mw = TransportSecurityMiddleware(ts)
    assert mw._validate_host(urlparse(PUBLIC).netloc) is True       # Funnel Host passes
    assert mw._validate_host("127.0.0.1:8850") is True              # loopback healthcheck ok
    assert mw._validate_host("evil.attacker.example") is False      # rebinding still blocked


# --- U2: discovery layout on the shared hostname (HTTPS public-origin, honcho-distinct) -------

# the unified lane is scoped under /mcp on the shared hostname (mirrors the cloud lane's /cloud
# and honcho's /honcho). issuer == resource == the public MCP URL the client points at.
PUBLIC_U = "https://example.ts.net/mcp"
RES_U = "https://example.ts.net/mcp"


def _unified(make_corpus, fake_embedder, **kw):
    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    return mcp_server.build_cloud_server(
        db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
        resource=kw.pop("resource", RES_U), public_url=kw.pop("public_url", PUBLIC_U),
        approval_token="op-approval-token-24chars-or-more", **kw)


def test_unified_lane_refuses_bare_ip_or_plain_http_issuer(make_corpus, fake_embedder):
    # R2: the unified endpoint must advertise an HTTPS public-origin issuer/resource, never a
    # bare-IP / plain-HTTP one (the reason the separate cloud lane existed at all). Refuse it at
    # construction — fail loud, no half-open server (mirrors the 0.0.0.0 / no-auth refusals).
    import pytest

    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})        # one corpus; the guard fires pre-index
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"

    def _build(**kw):
        return mcp_server.build_cloud_server(
            db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
            resource=kw.get("resource", RES_U), public_url=kw.get("public_url", PUBLIC_U),
            approval_token="op-approval-token-24chars-or-more")

    for bad in ("http://example.ts.net/mcp",        # plain HTTP
                "https://100.64.0.55:8850/mcp"):              # bare IP literal
        with pytest.raises(ValueError):
            _build(public_url=bad)
        with pytest.raises(ValueError):
            _build(resource=bad)
    _build()                                                  # the good HTTPS config still builds


def test_unified_lane_advertises_https_public_origin_metadata(make_corpus, fake_embedder):
    # AS metadata (RFC 8414) + protected-resource metadata (RFC 9728) are all HTTPS public-origin
    # URLs sharing one netloc — never a bare IP or http:// — and name the correct resource + AS.
    from urllib.parse import urlparse

    from mcp.server.auth.routes import build_resource_metadata_url
    from mcp.shared.auth import AnyHttpUrl

    from hypermnesic import auth_cloud
    p = auth_cloud.CloudAuthProvider(
        resource=RES_U, public_url=PUBLIC_U, approval_token="op-approval-token-24chars-or-more",
        scopes_supported=["read", "write"])
    meta = p.metadata()
    netloc = urlparse(PUBLIC_U).netloc
    for url in (meta["issuer"], meta["authorization_endpoint"], meta["token_endpoint"],
                meta["registration_endpoint"], meta["revocation_endpoint"]):
        u = urlparse(url)
        assert u.scheme == "https" and u.netloc == netloc        # HTTPS, shared public origin
        assert not u.hostname.replace(".", "").isdigit()         # not a bare IPv4 literal
    # RFC 9728 protected-resource metadata URL (what WWW-Authenticate points at) is HTTPS + names
    # our resource as the audience and our issuer as the AS.
    prm = str(build_resource_metadata_url(AnyHttpUrl(RES_U)))
    assert prm.startswith("https://") and netloc in prm
    srv = _unified(make_corpus, fake_embedder)
    assert str(srv.settings.auth.resource_server_url).rstrip("/") == RES_U.rstrip("/")
    assert str(srv.settings.auth.issuer_url).rstrip("/") == PUBLIC_U.rstrip("/")


def test_unified_discovery_path_is_hypermnesic_scoped_distinct_from_honcho():
    # AE5: hypermnesic's protected-resource metadata path is scoped to its own segment (/mcp) and
    # is distinct from honcho's (/honcho) — the two co-tenants never share a well-known route.
    from mcp.server.auth.routes import build_resource_metadata_url
    from mcp.shared.auth import AnyHttpUrl
    hm = str(build_resource_metadata_url(AnyHttpUrl(RES_U)))
    honcho = str(build_resource_metadata_url(
        AnyHttpUrl("https://example.ts.net/honcho")))
    assert hm.endswith("/oauth-protected-resource/mcp")          # hypermnesic-scoped
    assert honcho.endswith("/oauth-protected-resource/honcho")   # honcho-scoped
    assert hm != honcho                                          # no collision


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


def test_consent_page_explains_scopes_reject_cancel_and_revocation():
    from hypermnesic import mcp_server
    p = _provider()
    _run(p.register_client(_client()))
    pending = _run(p.authorize(_client(), _params(scopes=("read", "write")))).split("pending=")[1]
    html, status = mcp_server._render_consent(p, pending)
    assert status == 200
    assert "Read access" in html and "search and recall" in html
    assert "Write access" in html and "request commit_note" in html
    assert "does not bypass protected paths" in html
    assert 'name="decision" value="approve"' in html
    assert 'name="decision" value="reject"' in html
    assert 'name="decision" value="cancel"' in html
    assert "revoke this client" in html
    assert "op-approval-secret" not in html


def test_consent_page_warns_for_generic_client_identity():
    from hypermnesic import mcp_server
    p = _provider()
    generic = OAuthClientInformationFull(
        client_id="cid-generic", client_secret="s", redirect_uris=[REDIRECT],
        grant_types=["authorization_code"], response_types=["code"], scope="read write",
        token_endpoint_auth_method="none")
    _run(p.register_client(generic))
    pending = _run(p.authorize(generic, _params(scopes=("read",)))).split("pending=")[1]
    html, status = mcp_server._render_consent(p, pending)
    assert status == 200
    assert "generic or missing client identity" in html
    assert "chatgpt.com" in html


def test_consent_form_posts_to_the_public_path_not_root():
    # Regression (live "Cannot POST /consent"): the consent page is served at <public>/consent
    # behind a Funnel that strips the /cloud mount, so a ROOT-absolute form action="/consent"
    # makes the browser POST to the host root (a different app) → 404, and the OAuth grant dies
    # ("connected, but not all permissions were granted"). The form must POST back to the public
    # consent endpoint.
    from hypermnesic import mcp_server
    p = _provider()                              # public_url == https://example.ts.net/cloud
    _run(p.register_client(_client()))
    pending = _run(p.authorize(_client(), _params(scopes=("read", "write")))).split("pending=")[1]
    html, status = mcp_server._render_consent(p, pending)
    assert status == 200
    assert 'action="https://example.ts.net/cloud/consent"' in html  # full public path
    assert 'action="/consent"' not in html       # the root-absolute bug is gone


def test_consent_csp_allows_the_oauth_client_redirect_origin():
    # Regression (live "first Approve does nothing; second says expired"): CSP `form-action`
    # applies to a form submission's REDIRECT targets too, so a bare `form-action 'self'` silently
    # blocks the post-consent 302 to the OAuth client's cross-origin callback — the grant is
    # consumed server-side but the browser never navigates, so the app never receives the code and
    # the retry hits an already-consumed pending. The consent page's CSP must allow the client's
    # registered redirect origin (in addition to 'self').
    from hypermnesic import mcp_server
    csp = mcp_server._consent_headers("https://chatgpt.com/connector/oauth/abc")["Content-Security-Policy"]
    assert "form-action 'self' https://chatgpt.com" in csp     # the client origin is allowed
    assert "frame-ancestors 'none'" in csp                     # clickjacking protection intact
    assert "default-src 'none'" in csp                         # no-script baseline intact
    # no redirect_uri (e.g. the unknown-pending error page, which has no form) → just 'self'
    csp0 = mcp_server._consent_headers("")["Content-Security-Policy"]
    assert "form-action 'self';" in csp0 and "https://" not in csp0


def _cloud_call_as(srv, scopes, name, args):
    """Invoke a tool on the unified cloud server under an authenticated principal carrying
    ``scopes`` (mirrors the HTTP auth middleware setting the access-token context)."""
    import asyncio as _aio

    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    var = auth_context_var.set(AuthenticatedUser(AccessToken(
        token="t", client_id="c", scopes=list(scopes), resource=RES, claims={"aud": RES})))
    try:
        out = _aio.run(srv.call_tool(name, args))
        if isinstance(out, tuple):
            return out[1]
        if getattr(out, "structuredContent", None) is not None:
            return out.structuredContent
        return json.loads(out[0].text)
    finally:
        auth_context_var.reset(var)


def test_cloud_server_defaults_to_write_anywhere_under_guards(make_corpus, fake_embedder):
    # KD3/KD5 (unified lane): the promoted public endpoint defaults writes to the full master
    # surface (DEFAULT_WRITE_ALLOWLIST), not the cloud lane's old captures/-only review zone.
    # A write-scoped principal may commit to a non-captures/ path (e.g. notes/) bounded only by
    # commit_note's existing guards. (Covers AE2 write half.)
    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
                                        resource=RES, public_url=PUBLIC,
                                        approval_token="op-approval-token-24chars-or-more")
    ok = _cloud_call_as(srv, ["read", "write"], "commit_note",
                        {"path": "notes/x.md", "body": "# x\n\nbody.\n"})
    assert ok["committed"] is True                                 # notes/ now in the default zone


def test_list_folders_writable_flag_matches_commit_note_acceptance(make_corpus, fake_embedder):
    # G5 / single coercion site: build_cloud_server(write_allowlist=None) feeds ONE effective
    # surface (build_server's _effective_write_surface) to BOTH the write path and the discovery
    # flag, so list_folders' `writable` for a folder equals commit_note's acceptance for a file
    # written directly into it. Phase-B blocklist default: notes/ AND projects/ are writable+
    # accepted — they moved together when U5 flipped the one helper (re-pointed from Phase A).
    from hypermnesic import index, mcp_server
    repo = make_corpus({"notes/a.md": "# A\n\nalpha.\n", "projects/p.md": "# P\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
                                        resource=RES, public_url=PUBLIC,
                                        approval_token="op-approval-token-24chars-or-more")
    by = {e["path"]: e for e in _cloud_call_as(srv, ["read"], "list_folders",
                                               {"root": "", "depth": 1})["folders"]}
    # parity for notes/: discovery flag writable AND commit_note accepts a note there
    assert by["notes/"]["writable"] is True
    ok = _cloud_call_as(srv, ["read", "write"], "commit_note",
                        {"path": "notes/x.md", "body": "# x\n\nbody.\n"})
    assert ok["committed"] is True
    # parity for projects/ under the blocklist default: discovery writable AND commit_note accepts
    assert by["projects/"]["writable"] is True
    ok2 = _cloud_call_as(srv, ["read", "write"], "commit_note",
                         {"path": "projects/y.md", "body": "# y\n\nbody.\n"})
    assert ok2["committed"] is True


def test_cloud_blocklist_default_writes_content_folders_and_fences_governance(make_corpus,
                                                                              fake_embedder):
    # AE2 + U6 decision encoded: the Phase-B blocklist default lets a write-scoped principal commit
    # into the operator's content folders (projects/, people/, meetings/) — bounded only by the
    # protected-path guard + governance fence. The newly-exposed governance/CI/build/credential
    # classes are REFUSED by the fence the operator chose; protected paths stay refused.
    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
                                        resource=RES, public_url=PUBLIC,
                                        approval_token="op-approval-token-24chars-or-more")
    # content folders are writable under the blocklist default (AE2 write half, widened)
    for p in ("projects/acme/note.md", "people/bob.md", "meetings/2026/standup.md"):
        out = _cloud_call_as(srv, ["read", "write"], "commit_note",
                             {"path": p, "body": "# n\n\nx.\n"})
        assert out["committed"] is True, p
    # governance fence: code-exec / CI / build / credential classes are refused (U6 decision)
    for governance in ("Dockerfile", "projects/acme/ci.yml", "uv.lock", ".env", "package.json"):
        out = _cloud_call_as(srv, ["read", "write"], "commit_note",
                             {"path": governance, "body": "x\n"})
        assert out["committed"] is False and out["refused"], governance
    # protected classes stay refused regardless (allowlist-independent)
    for protected in ("notes/AGENTS.md", "scripts/evil.sh", ".github/workflows/ci.yml"):
        out = _cloud_call_as(srv, ["read", "write"], "commit_note",
                             {"path": protected, "body": "x\n"})
        assert out["committed"] is False and out["refused"], protected


def test_cloud_server_read_scoped_principal_is_denied_commit_note(make_corpus, fake_embedder):
    # AE2 read half / V14: a principal who only completed read consent reaches commit_note (the
    # SDK applies one required-scopes list to all tools) but is refused by the per-tool write-scope
    # guard before any write — read and write clients share the one endpoint safely.
    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
                                        resource=RES, public_url=PUBLIC,
                                        approval_token="op-approval-token-24chars-or-more")
    refused = _cloud_call_as(srv, ["read"], "commit_note",
                             {"path": "notes/x.md", "body": "# x\n\nbody.\n"})
    assert refused["committed"] is False
    assert "insufficient_scope" in refused["refused"]              # write scope required


def test_write_anywhere_still_refuses_protected_paths_inside_allowed_dirs(make_corpus,
                                                                          fake_embedder):
    # U6 (write-anywhere security re-review): widening the default allowlist to the master surface
    # must NOT widen access to protected paths. The protected-path guard is allowlist-INDEPENDENT,
    # so a write-scoped principal is still refused an agent-instruction file (or .git/CI/traversal)
    # even when it is nested inside a now-allowed dir like notes/. This is the property that makes
    # write-anywhere safe — the blast radius is the note zones, never the protected classes.
    import subprocess

    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
                                        resource=RES, public_url=PUBLIC,
                                        approval_token="op-approval-token-24chars-or-more")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    for protected in ("notes/AGENTS.md", "sources/.github/x.md"):     # inside the widened allowlist
        out = _cloud_call_as(srv, ["read", "write"], "commit_note",
                             {"path": protected, "body": "# x\n\nbody.\n"})
        assert out["committed"] is False and out["refused"]           # protected-path guard holds
    after = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True).stdout.strip()
    assert head == after                                              # nothing committed


def test_cloud_server_read_scoped_principal_reaches_read_tools(make_corpus, fake_embedder):
    # G1: on the one unified endpoint a read-scoped principal reaches the read tools (the read
    # half of the split that lets read + write clients share the endpoint).
    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha is here.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
                                        resource=RES, public_url=PUBLIC,
                                        approval_token="op-approval-token-24chars-or-more")
    out = _cloud_call_as(srv, ["read"], "search", {"query": "alpha"})
    assert "hits" in out and out["query"] == "alpha"               # read tool reached on read scope


def test_cloud_server_honors_an_explicit_narrower_allowlist(make_corpus, fake_embedder):
    # The default widens to the master surface, but setup/CLI can still narrow it: an explicit
    # captures/-only allowlist refuses a notes/ write even for a write-scoped principal.
    from hypermnesic import index, mcp_server
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_cloud_server(db, host="127.0.0.1", repo=repo, embedder=fake_embedder,
                                        resource=RES, public_url=PUBLIC,
                                        approval_token="op-approval-token-24chars-or-more",
                                        write_allowlist=["captures/"])
    refused = _cloud_call_as(srv, ["read", "write"], "commit_note",
                             {"path": "notes/x.md", "body": "# x\n\nbody.\n"})
    ok = _cloud_call_as(srv, ["read", "write"], "commit_note",
                        {"path": "captures/x.md", "body": "# x\n\nbody.\n"})
    assert refused["committed"] is False and refused["refused"]    # notes/ outside the narrow zone
    assert ok["committed"] is True                                 # captures/ honored
