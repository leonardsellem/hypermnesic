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
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

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
OAUTH_STATE_VERSION = 1

PENDING_TTL_SECONDS = 600          # an unconsented /authorize request is short-lived
MAX_CONSENT_FAILURES = 5           # drop a pending after this many wrong approval-token tries
MAX_PENDING = 256                  # cap anonymous /authorize growth (DoS bound)
MIN_APPROVAL_TOKEN_LEN = 24        # entropy floor for the single public-write gate secret


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
    expires_at: int
    failures: int = 0


class CloudAuthProvider:
    """MCP SDK ``OAuthAuthorizationServerProvider`` for the public cloud lane."""

    def __init__(self, *, resource: str, public_url: str, approval_token: str,
                 scopes_supported: list[str], default_scopes: list[str] | None = None,
                 token_ttl_seconds: int = 3600,
                 code_ttl_seconds: int = 300, refresh_ttl_seconds: int = 30 * 24 * 3600,
                 now=None, grant_store_path: Path | None = None,
                 oauth_state_path: Path | None = None) -> None:
        self._resource = str(resource).rstrip("/")
        self._public = str(public_url).rstrip("/")
        self._approval_hash = _hash(approval_token)        # the operator credential, hashed
        self._scopes_supported = tuple(scopes_supported)
        self._default_scopes = tuple(default_scopes or [
            s for s in self._scopes_supported if s == "read"
        ])
        if not self._default_scopes:
            raise ValueError("default_scopes must include at least one supported scope")
        invalid = [s for s in self._default_scopes if s not in self._scopes_supported]
        if invalid:
            raise ValueError(
                "default_scopes must be a subset of scopes_supported; "
                f"invalid: {', '.join(invalid)}")
        self._token_ttl = int(token_ttl_seconds)
        self._code_ttl = int(code_ttl_seconds)
        self._refresh_ttl = int(refresh_ttl_seconds)
        self._now = now or (lambda: int(time.time()))
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, _Pending] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self._access: dict[str, AccessToken] = {}
        self._refresh: dict[str, RefreshToken] = {}
        self._sibling: dict[str, str] = {}        # access<->refresh linkage (whole-grant revoke)
        self._grants: dict[str, dict] = {}
        self._grant_by_token: dict[str, str] = {}
        self._grant_tokens: dict[str, tuple[str, str]] = {}
        self._grant_store_path = Path(grant_store_path) if grant_store_path is not None else None
        self._oauth_state_path = Path(oauth_state_path) if oauth_state_path is not None else None
        self._load_oauth_state()

    @property
    def public_url(self) -> str:
        """The externally-reachable base URL (RFC 8414 issuer). The consent form posts back to
        ``<public_url>/consent`` — a root-absolute action would miss the Funnel's path mount."""
        return self._public

    def _sweep(self) -> None:
        """Evict expired/over-cap state — bounds anonymous /authorize + DCR growth (DoS)."""
        now = self._now()
        before = (len(self._pending), len(self._codes), len(self._access), len(self._refresh))
        self._pending = {k: v for k, v in self._pending.items() if v.expires_at > now}
        self._codes = {k: v for k, v in self._codes.items() if v.expires_at > now}
        self._access = {k: v for k, v in self._access.items()
                        if v.expires_at is None or v.expires_at > now}
        self._refresh = {k: v for k, v in self._refresh.items()
                         if v.expires_at is None or v.expires_at > now}
        self._sync_grant_statuses()
        if len(self._pending) > MAX_PENDING:       # drop the oldest pendings past the cap
            ordered = sorted(self._pending, key=lambda x: self._pending[x].expires_at)
            for k in ordered[:-MAX_PENDING]:
                self._pending.pop(k, None)
        after = (len(self._pending), len(self._codes), len(self._access), len(self._refresh))
        if before != after:
            self._persist_oauth_state()

    def _load_oauth_state(self) -> None:
        """Load restart-survivable OAuth state from the owner-only cloud state file.

        ``client-grants.json`` remains the secret-free owner-control surface. This separate
        file holds the opaque bearer/refresh material needed for OAuth refresh across service
        restarts, and is written 0600 outside the git tree's committed content.
        """
        if self._oauth_state_path is None or not self._oauth_state_path.exists():
            return
        data = json.loads(self._oauth_state_path.read_text(encoding="utf-8"))
        if data.get("version") != OAUTH_STATE_VERSION:
            raise ValueError(f"unsupported cloud OAuth state version: {data.get('version')}")
        self._clients = {
            c["client_id"]: OAuthClientInformationFull.model_validate(c)
            for c in data.get("clients", [])
        }
        self._access = {
            t["token"]: AccessToken.model_validate(t)
            for t in data.get("access", [])
        }
        self._refresh = {
            t["token"]: RefreshToken.model_validate(t)
            for t in data.get("refresh", [])
        }
        self._sibling = {
            str(k): str(v)
            for k, v in (data.get("sibling") or {}).items()
            if k and v
        }
        self._grants = {
            g["grant_id"]: dict(g)
            for g in data.get("grants", [])
            if g.get("grant_id")
        }
        self._grant_by_token = {
            str(k): str(v)
            for k, v in (data.get("grant_by_token") or {}).items()
            if k and v
        }
        self._grant_tokens = {
            str(k): (str(v[0]), str(v[1]))
            for k, v in (data.get("grant_tokens") or {}).items()
            if isinstance(v, (list, tuple)) and len(v) == 2
        }

    def _persist_oauth_state(self) -> None:
        if self._oauth_state_path is None:
            return
        path = self._oauth_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": OAUTH_STATE_VERSION,
            "clients": [
                c.model_dump(mode="json")
                for c in sorted(self._clients.values(), key=lambda c: c.client_id)
            ],
            "access": [
                t.model_dump(mode="json")
                for t in sorted(self._access.values(), key=lambda t: t.token)
            ],
            "refresh": [
                t.model_dump(mode="json")
                for t in sorted(self._refresh.values(), key=lambda t: t.token)
            ],
            "sibling": dict(sorted(self._sibling.items())),
            "grants": [
                dict(g)
                for g in sorted(self._grants.values(), key=lambda g: g.get("grant_id") or "")
            ],
            "grant_by_token": dict(sorted(self._grant_by_token.items())),
            "grant_tokens": {
                k: list(v)
                for k, v in sorted(self._grant_tokens.items())
            },
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)

    def _persist_grant(self, grant: dict) -> None:
        if self._grant_store_path is None:
            return
        from hypermnesic import client_control
        client_control.upsert_grant(self._grant_store_path, grant)

    def _stored_revoked(self, grant_id: str) -> bool:
        if self._grant_store_path is None:
            return False
        from hypermnesic import client_control
        stored = client_control.find_grant(self._grant_store_path, grant_id)
        return bool(stored and stored.get("status") == "revoked")

    def _mark_grant(self, grant_id: str, status: str) -> None:
        grant = self._grants.get(grant_id)
        if grant is None:
            return
        grant["status"] = status
        grant["active"] = status == "active"
        grant["updated_at"] = self._now()
        if status == "revoked":
            grant["revoked_at"] = self._now()
        self._persist_grant(grant)
        self._persist_oauth_state()

    def _sync_grant_statuses(self) -> None:
        for grant_id, grant in list(self._grants.items()):
            if grant.get("status") == "revoked":
                continue
            if self._stored_revoked(grant_id):
                self._revoke_grant_tokens(grant_id)
                self._mark_grant(grant_id, "revoked")
                continue
            tokens = self._grant_tokens.get(grant_id)
            if not tokens:
                self._mark_grant(grant_id, "expired")
                continue
            access, refresh = tokens
            if access not in self._access and refresh not in self._refresh:
                self._mark_grant(grant_id, "expired")

    def _revoke_grant_tokens(self, grant_id: str) -> None:
        tokens = self._grant_tokens.pop(grant_id, None)
        if not tokens:
            return
        for tok in tokens:
            sib = self._sibling.pop(tok, None)
            self._sibling.pop(sib, None) if sib else None
            self._access.pop(tok, None)
            self._refresh.pop(tok, None)
            self._grant_by_token.pop(tok, None)
            if sib:
                self._access.pop(sib, None)
                self._refresh.pop(sib, None)
                self._grant_by_token.pop(sib, None)

    # --- DCR ---------------------------------------------------------------
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info
        self._persist_oauth_state()

    # --- authorize → operator consent --------------------------------------
    def _grantable(self, requested: list[str] | None) -> tuple[str, ...]:
        req = [s for s in (requested or []) if s in self._scopes_supported]
        return tuple(req or self._default_scopes)

    async def authorize(self, client: OAuthClientInformationFull,
                        params: AuthorizationParams) -> str:
        """Stash the authorization request and route the browser to the operator-authenticated
        consent page — never mint a code here (a public write endpoint must not auto-approve)."""
        self._sweep()
        pending_id = secrets.token_urlsafe(24)
        self._pending[pending_id] = _Pending(
            client_id=client.client_id, redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=self._grantable(params.scopes), code_challenge=params.code_challenge,
            state=params.state, expires_at=self._now() + PENDING_TTL_SECONDS)
        return f"{self._public}/consent?pending={pending_id}"

    def pending_details(self, pending_id: str) -> dict | None:
        """The client/redirect/scopes for a live pending request, so the consent page can show
        the operator WHO they are approving. ``None`` for an unknown/expired id — the consent
        route then renders a generic error and never reflects the raw id (XSS)."""
        p = self._pending.get(pending_id)
        if p is None or p.expires_at <= self._now():
            return None
        client = self._clients.get(p.client_id)
        return {"client_id": p.client_id,
                "client_name": (client.client_name if client else None),
                "redirect_uri": p.redirect_uri, "scopes": list(p.scopes)}

    def finalize_consent(self, pending_id: str, approval_token: str) -> str:
        return self.finalize_consent_result(pending_id, approval_token)["redirect_uri"]

    def finalize_consent_result(self, pending_id: str, approval_token: str) -> dict:
        """The consent route calls this after the operator authenticates. The operator's approval
        token is required; a wrong token is counted and the pending is dropped after the failure
        cap (no indefinite online brute force). The issued code is bound to our single resource."""
        self._sweep()
        pending = self._pending.get(pending_id)
        if pending is None or pending.expires_at <= self._now():
            self._pending.pop(pending_id, None)
            raise ConsentError("unknown, expired, or already-consumed authorization request")
        if not _ok(approval_token, self._approval_hash):
            pending.failures += 1
            if pending.failures >= MAX_CONSENT_FAILURES:
                self._pending.pop(pending_id, None)        # stop online brute force on this pending
            raise ConsentError("operator approval required: invalid or missing approval token")
        self._pending.pop(pending_id, None)
        client = self._clients.get(pending.client_id)
        code = CODE_PREFIX + secrets.token_urlsafe(24)
        self._codes[code] = AuthorizationCode(
            code=code, scopes=list(pending.scopes), expires_at=self._now() + self._code_ttl,
            client_id=pending.client_id, code_challenge=pending.code_challenge,
            redirect_uri=pending.redirect_uri,
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            resource=self._resource, subject="operator")          # always our single resource
        params = {"code": code}
        if pending.state is not None:
            params["state"] = pending.state
        return {
            "redirect_uri": construct_redirect_uri(pending.redirect_uri, **params),
            "confirmation": {
                "client_id": pending.client_id,
                "client_name": client.client_name if client else None,
                "redirect_uri": pending.redirect_uri,
                "scopes": list(pending.scopes),
                "write_enabled": "write" in pending.scopes,
                "message": (
                    "Approved write access: this client can request commit_note, subject to "
                    "Hypermnesic write guards."
                    if "write" in pending.scopes
                    else "Approved read access: this client can search and recall memory."
                ),
            },
        }

    def reject_consent(self, pending_id: str, *, decision: str = "reject") -> str:
        """Consume a pending request without issuing a code. The client receives the OAuth
        denial redirect and no grant state is created."""
        self._sweep()
        pending = self._pending.pop(pending_id, None)
        if pending is None or pending.expires_at <= self._now():
            raise ConsentError("unknown, expired, or already-consumed authorization request")
        description = (
            "Hypermnesic authorization cancelled by the operator"
            if decision == "cancel" else "Hypermnesic authorization rejected by the operator"
        )
        params = {"error": "access_denied", "error_description": description}
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
        tokens = self._issue(client.client_id, tuple(authorization_code.scopes),
                             redirect_uri=str(authorization_code.redirect_uri))
        self._persist_oauth_state()
        return tokens

    # --- refresh -----------------------------------------------------------
    async def load_refresh_token(self, client: OAuthClientInformationFull,
                                 refresh_token: str) -> RefreshToken | None:
        rt = self._refresh.get(refresh_token)
        if rt is None or rt.client_id != client.client_id:
            return None
        if rt.expires_at is not None and rt.expires_at <= self._now():
            return None
        grant_id = self._grant_by_token.get(refresh_token)
        if grant_id and self._stored_revoked(grant_id):
            self._revoke_grant_tokens(grant_id)
            self._mark_grant(grant_id, "revoked")
            return None
        return rt

    async def exchange_refresh_token(self, client: OAuthClientInformationFull,
                                     refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        granted = tuple(s for s in (scopes or refresh_token.scopes) if s in refresh_token.scopes)
        # rotate: invalidate the consumed refresh token (the old access keeps its short TTL)
        old = refresh_token.token
        grant_id = self._grant_by_token.get(old)
        redirect_uri = self._grants.get(grant_id or "", {}).get("redirect_uri")
        self._refresh.pop(old, None)
        old_access = self._sibling.pop(old, None)
        if old_access:
            self._sibling.pop(old_access, None)
            self._grant_by_token.pop(old_access, None)
        self._grant_by_token.pop(old, None)
        tokens = self._issue(client.client_id, granted or tuple(refresh_token.scopes),
                             redirect_uri=redirect_uri, grant_id=grant_id)
        self._persist_oauth_state()
        return tokens

    # --- access-token validation (the RS path via ProviderTokenVerifier) ---
    async def load_access_token(self, token: str) -> AccessToken | None:
        at = self._access.get(token)
        if at is None or (at.expires_at is not None and at.expires_at <= self._now()):
            return None
        if str(at.resource or "").rstrip("/") != self._resource:   # audience enforced at the RS
            return None
        grant_id = self._grant_by_token.get(token)
        if grant_id and self._stored_revoked(grant_id):
            self._revoke_grant_tokens(grant_id)
            self._mark_grant(grant_id, "revoked")
            return None
        return at

    async def revoke_token(self, token) -> None:
        """RFC 7009: revoking either token of a grant kills the whole grant (access + its
        refresh sibling) — the operator's kill switch must really cut access."""
        tok = getattr(token, "token", token)
        grant_id = self._grant_by_token.get(tok)
        sib = self._sibling.pop(tok, None)
        self._access.pop(tok, None)
        self._refresh.pop(tok, None)
        self._grant_by_token.pop(tok, None)
        if sib:
            self._sibling.pop(sib, None)
            self._access.pop(sib, None)
            self._refresh.pop(sib, None)
            self._grant_by_token.pop(sib, None)
        if grant_id:
            self._grant_tokens.pop(grant_id, None)
            self._mark_grant(grant_id, "revoked")
        self._persist_oauth_state()

    def list_grants(self) -> list[dict]:
        self._sweep()
        return [
            dict(grant)
            for grant in sorted(
                self._grants.values(),
                key=lambda g: g.get("issued_at") or 0,
            )
        ]

    def revoke_grant(self, grant_id: str) -> dict:
        self._sweep()
        grant = self._grants.get(grant_id)
        if grant is None:
            return {"status": "not_found", "grant_id": grant_id}
        if grant.get("status") == "revoked":
            return {"status": "already_revoked", "grant_id": grant_id, "active": False}
        self._revoke_grant_tokens(grant_id)
        self._mark_grant(grant_id, "revoked")
        return {"status": "revoked", "grant_id": grant_id, "active": False}

    # --- issuance helper ---------------------------------------------------
    def _issue(self, client_id: str, scopes: tuple[str, ...], *,
               redirect_uri: str | None = None, grant_id: str | None = None) -> OAuthToken:
        from urllib.parse import urlsplit

        access = ACCESS_PREFIX + secrets.token_urlsafe(32)
        refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
        grant_id = grant_id or ("grant_" + secrets.token_urlsafe(16))
        exp = self._now() + self._token_ttl
        refresh_exp = self._now() + self._refresh_ttl
        self._access[access] = AccessToken(
            token=access, client_id=client_id, scopes=list(scopes), expires_at=exp,
            resource=self._resource, subject="operator", claims={"aud": self._resource})
        self._refresh[refresh] = RefreshToken(
            token=refresh, client_id=client_id, scopes=list(scopes),
            expires_at=refresh_exp, subject="operator")
        self._sibling[access] = refresh        # link the grant so revoke kills both
        self._sibling[refresh] = access
        self._grant_by_token[access] = grant_id
        self._grant_by_token[refresh] = grant_id
        self._grant_tokens[grant_id] = (access, refresh)
        client = self._clients.get(client_id)
        redirect_uri = redirect_uri or (
            str(client.redirect_uris[0]) if client and client.redirect_uris else ""
        )
        parsed = urlsplit(redirect_uri)
        redirect_origin = (
            f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        )
        prior = self._grants.get(grant_id, {})
        now = self._now()
        grant = {
            "grant_id": grant_id,
            "client_id": client_id,
            "client_name": client.client_name if client else None,
            "redirect_uri": redirect_uri,
            "redirect_origin": redirect_origin,
            "scopes": list(scopes),
            "write_enabled": "write" in scopes,
            "issued_at": prior.get("issued_at", now),
            "updated_at": now,
            "access_expires_at": exp,
            "refresh_expires_at": refresh_exp,
            "status": "active",
            "active": True,
            "revoked_at": None,
        }
        self._grants[grant_id] = grant
        self._persist_grant(grant)
        self._persist_oauth_state()
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
            "token_endpoint_auth_methods_supported": [
                "client_secret_post", "client_secret_basic", "none"],
            "scopes_supported": list(self._scopes_supported),
            "revocation_endpoint_auth_methods_supported": [
                "client_secret_post", "client_secret_basic", "none"],
        }
