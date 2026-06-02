"""U2 — OAuth 2.1 Resource-Server auth for the hypermnesic MCP (R12).

The engine is the **Resource Server (RS)**: it validates the bearer tokens a separate
**Authorization Server (AS — U12, tailnet-internal)** issues. This module is the RS
glue, three pieces:

1. ``make_auth_settings`` — builds the SDK :class:`AuthSettings` (issuer + resource +
   required scopes) the FastMCP transport uses to wire ``RequireAuthMiddleware`` +
   ``BearerAuthBackend`` and advertise RFC 9728 Protected-Resource metadata.
2. :class:`StrictResourceTokenVerifier` — the SDK ``TokenVerifier`` the RS enforces.
   It wraps an injected *raw* validation strategy (the deferred-to-impl AS seam) and
   adds the engine's two non-negotiables: **RFC 8707 strict audience binding** (a
   structurally valid token minted for a *different* RS on the tailnet is rejected)
   and **expiry**. Fails closed: any raw-validation error → reject, never a 500, never
   echoing the token (threat-model V9).
3. ``introspection_verify_raw`` / ``verify_raw_from_discovery`` — the production raw
   strategy. The homelab AS (honcho-oauth-proxy) issues **opaque** tokens (no JWKS), so
   the RS validates via **RFC 7662 token introspection**; the introspection endpoint is
   discovered from the issuer (RFC 8414) and RS client credentials come from the env,
   never from a committed config (V9). If the AS exposes no introspection endpoint, the
   raw strategy fails loud — the explicit signal U12 must reconcile (extend the AS or
   issue JWTs).

Auth is **opt-in/additive**: a read-only serve with no auth stays Phase-1-compatible.
The ``write_enabled ⇒ auth-required`` invariant lives in ``mcp_server.build_server``,
not here.
"""

from __future__ import annotations

import inspect
import os
import time
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

# A raw token validator: token string → AccessToken (valid) | None (invalid). May be
# sync or async; the verifier awaits an awaitable result. This is the AS-specific seam.
VerifyRaw = Callable[[str], "AccessToken | None"]

# RS introspection client credentials live in the environment only (never committed).
ENV_RS_CLIENT_ID = "HYPERMNESIC_RS_CLIENT_ID"
ENV_RS_CLIENT_SECRET = "HYPERMNESIC_RS_CLIENT_SECRET"


class ResourceAuthError(ValueError):
    """Raised on a missing/invalid auth configuration. A ``ValueError`` so the CLI's
    existing ``serve`` failure path catches it and exits 1 (no half-open server)."""


# --- AuthSettings glue -------------------------------------------------------

def make_auth_settings(*, issuer_url: str, resource_server_url: str,
                       required_scopes: list[str] | None) -> AuthSettings:
    """Build the SDK :class:`AuthSettings` for RS-only operation.

    Both the issuer and resource URLs are required (enabling auth needs both); an empty
    scope list becomes ``None``. A malformed URL surfaces as a :class:`ResourceAuthError`.
    """
    if not (issuer_url and str(issuer_url).strip()) or not (
            resource_server_url and str(resource_server_url).strip()):
        raise ResourceAuthError(
            "OAuth RS auth requires BOTH --auth-issuer-url and --auth-resource-url")
    scopes = [s for s in (required_scopes or []) if s and s.strip()]
    try:
        return AuthSettings(issuer_url=issuer_url, resource_server_url=resource_server_url,
                            required_scopes=scopes or None)
    except Exception as exc:   # pydantic validation (bad URL) → actionable auth error
        raise ResourceAuthError(f"invalid OAuth RS auth settings: {exc}") from exc


# --- the verifier (audience + expiry invariants) -----------------------------

def _audiences(at: AccessToken) -> set[str]:
    """All audiences a token claims — from the RFC 8707 ``resource`` field and any
    JWT ``aud`` claim (str or array). Trailing slashes are normalized."""
    auds: set[str] = set()
    if at.resource:
        auds.add(str(at.resource).rstrip("/"))
    aud = (at.claims or {}).get("aud")
    if isinstance(aud, str):
        auds.add(aud.rstrip("/"))
    elif isinstance(aud, (list, tuple)):
        auds.update(str(a).rstrip("/") for a in aud)
    return auds


class StrictResourceTokenVerifier:
    """SDK ``TokenVerifier`` enforcing RFC 8707 strict audience binding + expiry on top
    of an injected raw validator. Returns ``None`` (the SDK turns that into a 401) for an
    invalid, expired, or wrong-/no-audience token; the SDK middleware then enforces the
    required scopes. Never raises into the transport and never logs the token (V9)."""

    def __init__(self, *, resource_server_url: str, verify_raw: VerifyRaw,
                 now: Callable[[], int] | None = None) -> None:
        self._resource = str(resource_server_url).rstrip("/")
        self._verify_raw = verify_raw
        self._now = now or (lambda: int(time.time()))

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            at = self._verify_raw(token)
            if inspect.isawaitable(at):
                at = await at
        except Exception:
            return None                       # fail-closed (AS down / malformed) → 401
        if at is None:
            return None
        if at.expires_at is not None and int(at.expires_at) <= int(self._now()):
            return None                       # expired
        if self._resource not in _audiences(at):
            return None                       # RFC 8707: not minted for THIS resource → reject
        return at


def build_token_verifier(*, resource_server_url: str, verify_raw: VerifyRaw,
                         now: Callable[[], int] | None = None) -> StrictResourceTokenVerifier:
    return StrictResourceTokenVerifier(resource_server_url=resource_server_url,
                                       verify_raw=verify_raw, now=now)


# --- production raw strategy: RFC 7662 introspection of opaque tokens ---------

def _httpx_post(url: str, *, data: dict, auth: tuple[str, str]) -> dict:
    import httpx
    r = httpx.post(url, data=data, auth=auth, timeout=5.0)
    r.raise_for_status()
    return r.json()


def _httpx_get(url: str) -> dict:
    import httpx
    r = httpx.get(url, timeout=5.0)
    r.raise_for_status()
    return r.json()


def introspection_verify_raw(*, introspection_url: str, client_id: str, client_secret: str,
                             post_fn: Callable[..., dict] | None = None) -> VerifyRaw:
    """An RFC 7662 introspection-backed raw validator. The ``post_fn`` (injected in tests)
    posts ``{token}`` to the introspection endpoint with the RS client credentials and
    returns the parsed JSON; an ``active:false`` response → ``None``. The response's
    ``aud``/``scope``/``exp``/``client_id``/``sub`` map onto :class:`AccessToken` (the
    verifier then applies the audience/expiry invariants). Credentials are never logged."""
    post = post_fn or _httpx_post

    def _raw(token: str) -> AccessToken | None:
        resp = post(introspection_url, data={"token": token, "token_type_hint": "access_token"},
                    auth=(client_id, client_secret))
        if not resp or not resp.get("active"):
            return None
        scope = resp.get("scope") or ""
        scopes = scope.split() if isinstance(scope, str) else list(scope)
        aud = resp.get("aud")
        exp = resp.get("exp")
        claims = {k: resp[k] for k in ("iss", "aud", "sub") if k in resp}
        return AccessToken(
            token=token, client_id=str(resp.get("client_id") or ""), scopes=scopes,
            expires_at=int(exp) if exp is not None else None,
            resource=aud if isinstance(aud, str) else None,
            subject=resp.get("sub"), claims=claims or None)

    return _raw


def _discover(issuer_url: str, http_get: Callable[[str], dict] | None) -> dict:
    """Fetch the AS metadata (RFC 8414) for ``issuer_url``, trying the path-aware and
    suffix well-known forms."""
    get = http_get or _httpx_get
    base = str(issuer_url).rstrip("/")
    parts = urlsplit(base)
    candidates = []
    if parts.path:
        candidates.append(urlunsplit((parts.scheme, parts.netloc,
            "/.well-known/oauth-authorization-server" + parts.path, "", "")))
    candidates.append(base + "/.well-known/oauth-authorization-server")
    candidates.append(urlunsplit((parts.scheme, parts.netloc,
        "/.well-known/oauth-authorization-server", "", "")))
    last_exc: Exception | None = None
    for url in candidates:
        try:
            meta = get(url)
            if isinstance(meta, dict) and meta.get("issuer"):
                return meta
        except Exception as exc:                # try the next candidate form
            last_exc = exc
    raise ResourceAuthError(f"could not fetch AS discovery for {issuer_url}: {last_exc}")


def verify_raw_from_discovery(*, issuer_url: str, resource_server_url: str,
                              required_scopes: list[str] | None,
                              http_get: Callable[[str], dict] | None = None,
                              post_fn: Callable[..., dict] | None = None) -> VerifyRaw:
    """Lazy production raw validator: on the first token, discover the issuer's
    introspection endpoint (RFC 8414) and build an introspection-backed validator. RS
    client credentials come from the env (``HYPERMNESIC_RS_CLIENT_ID`` /
    ``HYPERMNESIC_RS_CLIENT_SECRET``), never a committed config (V9). Fails loud with an
    actionable error if the AS exposes no introspection endpoint — the U12 signal that
    the AS must be extended (or issue JWTs)."""
    state: dict = {}

    def _raw(token: str) -> AccessToken | None:
        if "fn" not in state:
            meta = _discover(issuer_url, http_get)
            endpoint = meta.get("introspection_endpoint")
            if not endpoint:
                raise ResourceAuthError(
                    f"AS at {issuer_url} exposes no introspection_endpoint — the hypermnesic "
                    "RS cannot validate its opaque tokens (U12: add RFC 7662 introspection to "
                    "the AS, or issue JWT access tokens with a jwks_uri)")
            cid = os.environ.get(ENV_RS_CLIENT_ID)
            secret = os.environ.get(ENV_RS_CLIENT_SECRET)
            if not (cid and secret):
                raise ResourceAuthError(
                    f"RS introspection credentials missing: set {ENV_RS_CLIENT_ID} / "
                    f"{ENV_RS_CLIENT_SECRET} in the environment (never commit them; V9)")
            state["fn"] = introspection_verify_raw(
                introspection_url=endpoint, client_id=cid, client_secret=secret, post_fn=post_fn)
        return state["fn"](token)

    return _raw
