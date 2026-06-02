"""Cloud OAuth MCP — the public Authorization Server for the ChatGPT/Claude mobile lane.

Implements the MCP SDK's ``OAuthAuthorizationServerProvider`` so cloud connectors get the
standard interactive flow — Dynamic Client Registration (``/register``), ``/authorize`` →
an **operator-authenticated consent page** → an audience-bound, PKCE-protected authorization
code → ``/token`` (the SDK validates the PKCE ``code_verifier``) → access + refresh tokens.

Why a consent gate (the honcho model): this AS fronts a **public, internet-reachable WRITE**
endpoint. DCR lets any internet client register, so the only thing standing between the
public and write access to the operator's memory is the ``/authorize`` consent — which
therefore **must authenticate the operator** (an approval token the operator holds, stored
hashed here), never auto-approve. ``provider.authorize()`` returns a redirect to the consent
route rather than minting a code directly; only ``finalize_consent()`` with the operator's
approval token issues the code.

Separate from the U12 tailnet ``client_credentials`` AS (different trust boundary) and from
gbrain/honcho. Tokens are opaque + audience-bound; the approval token + secrets are never
logged (threat-model V9). PKCE is validated by the SDK token handler, so this provider only
preserves the ``code_challenge`` on the issued code.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

ACCESS_PREFIX = "hmcloud_at_"
REFRESH_PREFIX = "hmcloud_rt_"
CODE_PREFIX = "hmcloud_code_"


class ConsentError(ValueError):
    """Raised when the operator consent gate is not satisfied (wrong/absent approval token)."""


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _ok(presented: str, stored_hash: str) -> bool:
    return bool(presented) and hmac.compare_digest(_hash(presented), stored_hash)


@dataclass
class _Pending:
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    scopes: tuple[str, ...]
    code_challenge: str
    state: str | None
    resource: str


class CloudAuthProvider:
    """MCP SDK ``OAuthAuthorizationServerProvider`` for the public cloud lane."""

    def __init__(self, *, resource: str, public_url: str, approval_token: str,
                 scopes_supported: list[str], token_ttl_seconds: int = 3600,
                 code_ttl_seconds: int = 300, refresh_ttl_seconds: int = 30 * 24 * 3600,
                 now=None) -> None:
        self._resource = str(resource).rstrip("/")
        self._public = str(public_url).rstrip("/")
        self._approval_hash = _hash(approval_token)        # the operator credential, hashed
        self._scopes_supported = tuple(scopes_supported)
        self._token_ttl = int(token_ttl_seconds)
        self._code_ttl = int(code_ttl_seconds)
        self._refresh_ttl = int(refresh_ttl_seconds)
        self._now = now or (lambda: int(time.time()))
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, _Pending] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self._access: dict[str, AccessToken] = {}
        self._refresh: dict[str, RefreshToken] = {}

    # --- DCR ---------------------------------------------------------------
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

    # --- authorize → operator consent --------------------------------------
    def _grantable(self, requested: list[str] | None) -> tuple[str, ...]:
        req = [s for s in (requested or []) if s in self._scopes_supported]
        return tuple(req or [s for s in self._scopes_supported if s == "read"])  # default: read

    async def authorize(self, client: OAuthClientInformationFull,
                        params: AuthorizationParams) -> str:
        """Stash the authorization request and route the browser to the operator-authenticated
        consent page — never mint a code here (a public write endpoint must not auto-approve)."""
        pending_id = secrets.token_urlsafe(24)
        self._pending[pending_id] = _Pending(
            client_id=client.client_id, redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=self._grantable(params.scopes), code_challenge=params.code_challenge,
            state=params.state, resource=str(params.resource or self._resource).rstrip("/"))
        return f"{self._public}/consent?pending={pending_id}"

    def finalize_consent(self, pending_id: str, approval_token: str) -> str:
        """The consent route calls this after the operator authenticates. The operator's
        approval token is required — otherwise no code is issued (ConsentError)."""
        if not _ok(approval_token, self._approval_hash):
            raise ConsentError("operator approval required: invalid or missing approval token")
        pending = self._pending.pop(pending_id, None)
        if pending is None:
            raise ConsentError("unknown or already-consumed authorization request")
        code = CODE_PREFIX + secrets.token_urlsafe(24)
        self._codes[code] = AuthorizationCode(
            code=code, scopes=list(pending.scopes), expires_at=self._now() + self._code_ttl,
            client_id=pending.client_id, code_challenge=pending.code_challenge,
            redirect_uri=pending.redirect_uri,
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            resource=pending.resource, subject="operator")
        params = {"code": code}
        if pending.state is not None:
            params["state"] = pending.state
        return construct_redirect_uri(pending.redirect_uri, **params)

    # --- code → tokens (PKCE checked by the SDK token handler) --------------
    async def load_authorization_code(self, client: OAuthClientInformationFull,
                                      authorization_code: str) -> AuthorizationCode | None:
        code = self._codes.get(authorization_code)
        if code is None or code.client_id != client.client_id or code.expires_at <= self._now():
            return None
        return code

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        self._codes.pop(authorization_code.code, None)         # single-use
        return self._issue(client.client_id, tuple(authorization_code.scopes),
                           str(authorization_code.resource or self._resource).rstrip("/"))

    # --- refresh -----------------------------------------------------------
    async def load_refresh_token(self, client: OAuthClientInformationFull,
                                 refresh_token: str) -> RefreshToken | None:
        rt = self._refresh.get(refresh_token)
        if rt is None or rt.client_id != client.client_id:
            return None
        if rt.expires_at is not None and rt.expires_at <= self._now():
            return None
        return rt

    async def exchange_refresh_token(self, client: OAuthClientInformationFull,
                                     refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        granted = tuple(s for s in (scopes or refresh_token.scopes) if s in refresh_token.scopes)
        return self._issue(client.client_id, granted or tuple(refresh_token.scopes), self._resource)

    # --- access-token validation (the RS path via ProviderTokenVerifier) ---
    async def load_access_token(self, token: str) -> AccessToken | None:
        at = self._access.get(token)
        if at is None or (at.expires_at is not None and at.expires_at <= self._now()):
            return None
        return at

    async def revoke_token(self, token) -> None:
        tok = getattr(token, "token", token)
        self._access.pop(tok, None)
        self._refresh.pop(tok, None)

    # --- issuance helper ---------------------------------------------------
    def _issue(self, client_id: str, scopes: tuple[str, ...], resource: str) -> OAuthToken:
        access = ACCESS_PREFIX + secrets.token_urlsafe(32)
        refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
        exp = self._now() + self._token_ttl
        self._access[access] = AccessToken(
            token=access, client_id=client_id, scopes=list(scopes), expires_at=exp,
            resource=resource, subject="operator", claims={"aud": resource})
        self._refresh[refresh] = RefreshToken(
            token=refresh, client_id=client_id, scopes=list(scopes),
            expires_at=self._now() + self._refresh_ttl, subject="operator")
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=self._token_ttl,
                          scope=" ".join(scopes), refresh_token=refresh)

    # --- RFC 8414 metadata -------------------------------------------------
    def metadata(self) -> dict:
        return {
            "issuer": self._public,
            "authorization_endpoint": self._public + "/authorize",
            "token_endpoint": self._public + "/token",
            "registration_endpoint": self._public + "/register",
            "revocation_endpoint": self._public + "/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
            "scopes_supported": list(self._scopes_supported),
        }
