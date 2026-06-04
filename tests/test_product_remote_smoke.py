"""U8 remote-client product contracts, offline and deterministic."""

from __future__ import annotations

import asyncio
import json
import subprocess

from mcp.server.auth.provider import AccessToken, AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull

from hypermnesic import auth, auth_cloud, index, mcp_server

RESOURCE = "https://example.ts.net/mcp"
ISSUER = "https://example.ts.net/hypermnesic"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
TAILNET_IP = "100.64.0.1"


def _call(srv, name, args):
    out = asyncio.run(srv.call_tool(name, args))
    if isinstance(out, tuple):
        return out[1]
    return json.loads(out[0].text)


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _auth_settings():
    return auth.make_auth_settings(
        issuer_url=ISSUER,
        resource_server_url=RESOURCE,
        required_scopes=None,
    )


def _provider():
    return auth_cloud.CloudAuthProvider(
        resource=RESOURCE,
        public_url=ISSUER,
        approval_token="operator-approval-secret",
        scopes_supported=["read", "write"],
    )


def _client(scope="read write"):
    return OAuthClientInformationFull(
        client_id="remote-client",
        client_secret="client-secret",
        redirect_uris=[REDIRECT],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=scope,
        token_endpoint_auth_method="client_secret_post",
    )


def _params(scopes=("read",)):
    return AuthorizationParams(
        state="remote-smoke",
        scopes=list(scopes),
        code_challenge="challenge",
        redirect_uri=REDIRECT,
        redirect_uri_provided_explicitly=True,
        resource=RESOURCE,
    )


def _issue_tokens(provider, scopes=("read",)):
    client = _client()
    asyncio.run(provider.register_client(client))
    pending = asyncio.run(provider.authorize(client, _params(scopes=scopes))).split("pending=")[1]
    redirect = provider.finalize_consent(pending, approval_token="operator-approval-secret")
    code = redirect.split("code=")[1].split("&")[0]
    auth_code = asyncio.run(provider.load_authorization_code(client, code))
    return client, asyncio.run(provider.exchange_authorization_code(client, auth_code))


def _principal(scopes):
    return AccessToken(
        token="opaque-test-token",
        client_id="remote-client",
        scopes=list(scopes),
        expires_at=None,
        resource=RESOURCE,
    )


def test_remote_contract_discovery_read_default_and_revocation():
    provider = _provider()

    meta = provider.metadata()
    assert meta["issuer"] == ISSUER
    assert meta["registration_endpoint"] == ISSUER + "/register"
    assert meta["authorization_endpoint"] == ISSUER + "/authorize"
    assert meta["token_endpoint"] == ISSUER + "/token"
    assert meta["revocation_endpoint"] == ISSUER + "/revoke"
    assert set(meta["scopes_supported"]) >= {"read", "write"}

    client, tokens = _issue_tokens(provider, scopes=("read",))
    access = asyncio.run(provider.load_access_token(tokens.access_token))
    refresh = asyncio.run(provider.load_refresh_token(client, tokens.refresh_token))
    assert access is not None and access.scopes == ["read"]
    assert refresh is not None and refresh.scopes == ["read"]

    asyncio.run(provider.revoke_token(access))
    assert asyncio.run(provider.load_access_token(tokens.access_token)) is None
    assert asyncio.run(provider.load_refresh_token(client, tokens.refresh_token)) is None


def test_remote_contract_read_client_can_read_but_cannot_write(
    make_corpus, fake_embedder, monkeypatch
):
    repo = make_corpus({"projects/atlas.md": "# Atlas\n\nRemote contract marker.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(
        db,
        host=TAILNET_IP,
        repo=repo,
        embedder=fake_embedder,
        write_enabled=True,
        token_verifier=auth.build_token_verifier(
            resource_server_url=RESOURCE,
            verify_raw=lambda _token: _principal(["read"]),
        ),
        auth=_auth_settings(),
    )

    from mcp.server.auth.middleware import auth_context

    monkeypatch.setattr(auth_context, "get_access_token", lambda: _principal(["read"]))
    read = _call(srv, "search", {"query": "Remote contract marker"})
    assert any(hit["path"] == "projects/atlas.md" for hit in read["hits"])

    head_before = _git(repo, "rev-parse", "HEAD")
    refused = _call(srv, "commit_note", {"path": "memory/remote.md", "body": "# Remote\n\nbody.\n"})
    assert refused["committed"] is False
    assert "insufficient_scope" in refused["refused"]
    assert _git(repo, "rev-parse", "HEAD") == head_before


def test_remote_contract_write_client_still_hits_write_guards(
    make_corpus, fake_embedder, monkeypatch
):
    repo = make_corpus({"projects/atlas.md": "# Atlas\n\nRemote contract marker.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(
        db,
        host=TAILNET_IP,
        repo=repo,
        embedder=fake_embedder,
        write_enabled=True,
        token_verifier=auth.build_token_verifier(
            resource_server_url=RESOURCE,
            verify_raw=lambda _token: _principal(["read", "write"]),
        ),
        auth=_auth_settings(),
    )

    from mcp.server.auth.middleware import auth_context

    monkeypatch.setattr(auth_context, "get_access_token", lambda: _principal(["read", "write"]))
    refused = _call(srv, "commit_note", {"path": "AGENTS.md", "body": "# blocked\n"})
    assert refused["committed"] is False and refused["refused"]

    committed = _call(
        srv,
        "commit_note",
        {"path": "memory/remote.md", "body": "# Remote\n\nwrite-scoped client body.\n"},
    )
    assert committed["committed"] is True and committed["path"] == "memory/remote.md"
    assert (repo / "memory" / "remote.md").is_file()
