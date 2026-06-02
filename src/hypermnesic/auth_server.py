"""U12 — minimal tailnet-internal OAuth 2.1 Authorization Server (the token issuer the
U2 Resource Server validates). Independent of gbrain's AS (no shared issuer/endpoint), so
the gbrain teardown (U11) never locks out hypermnesic.

Why new (native-primitive-first finding): honcho-oauth-proxy issues opaque tokens with no
introspection endpoint and an audience hardwired to its own resource — an external RS can't
validate them. This AS reuses honcho's proven shape (stdlib HTTP, state-file-backed) but is a
separate service that:

- uses the **client_credentials** grant — the three agent identities (homelab Claude, homelab
  Codex, Mac) are machine clients, so there is no interactive authorize/redirect;
- **binds the audience to the requested resource (RFC 8707)** and refuses an unknown resource,
  so a token is only ever valid for the resource it was minted for;
- exposes **RFC 7662 introspection** so the RS can validate the opaque token (the U2 seam);
- supports **revocation** + a **token-lifetime ceiling** (a leaked token is bounded);
- **locks DCR to pre-seeded static clients** — `/register` is refused, so an arbitrary tailnet
  node cannot self-enroll a write credential (tighter than bare DCR).

Secrets (client secrets, tokens) are never logged (threat-model V9). Client secrets are stored
hashed; tokens are opaque random strings keyed in a state map.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs

ISSUER_SUFFIX = ""          # the issuer IS the public_url (no extra path component)
TOKEN_PREFIX = "hmem_at_"   # opaque access-token prefix (distinct from honcho's honcho_at_)


@dataclass(frozen=True)
class OAuthError(Exception):
    """An OAuth error with an RFC 6749/7662 ``error`` code (returned, never leaking secrets)."""
    error: str
    description: str | None = None
    status: int = 400


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _secret_ok(presented: str, stored_hash: str) -> bool:
    return hmac.compare_digest(_hash_secret(presented), stored_hash)


@dataclass
class _Client:
    client_id: str
    secret_hash: str
    scopes: tuple[str, ...]
    is_rs: bool = False


@dataclass
class _Token:
    client_id: str
    scopes: tuple[str, ...]
    aud: str
    exp: int
    subject: str


@dataclass
class MinimalAS:
    """The AS core. ``allowed_resources`` is the RFC 8707 resource allowlist (only these
    audiences may be minted). ``now`` is injectable for deterministic expiry tests."""

    allowed_resources: list[str]
    token_ttl_seconds: int = 3600
    state_path: Path | None = None
    now: object = None
    dcr_enabled: bool = False                      # DCR locked by default (static clients only)
    public_url: str = ""                           # the AS's own issuer URL (for /metadata)
    _clients: dict = field(default_factory=dict)
    _tokens: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._allowed = {r.rstrip("/") for r in self.allowed_resources}
        self._now = self.now or (lambda: int(time.time()))
        if self.state_path:
            self._load()

    # --- clients -----------------------------------------------------------
    def add_client(self, client_id: str, client_secret: str, *, scopes: list[str],
                   is_rs: bool = False) -> None:
        """Pre-seed a static client (an agent identity, or the RS introspection client)."""
        self._clients[client_id] = _Client(client_id, _hash_secret(client_secret),
                                            tuple(scopes), is_rs)
        self._persist()

    def client_ids(self) -> list[str]:
        return sorted(self._clients)

    def register_dynamic_client(self, *, client_name: str) -> dict:
        if not self.dcr_enabled:
            raise OAuthError("access_denied",
                             "dynamic client registration is locked; clients are pre-seeded "
                             "static identities (tighter than tailnet-wide DCR)", status=403)
        # (Intentionally minimal — DCR stays off in the deployed posture.)
        cid = "dyn_" + secrets.token_urlsafe(8)
        sec = secrets.token_urlsafe(24)
        self.add_client(cid, sec, scopes=["read"])
        return {"client_id": cid, "client_secret": sec, "client_name": client_name}

    def _auth_client(self, client_id: str, client_secret: str) -> _Client:
        client = self._clients.get(client_id)
        if client is None or not _secret_ok(client_secret, client.secret_hash):
            raise OAuthError("invalid_client", "client authentication failed", status=401)
        return client

    # --- grant: client_credentials ----------------------------------------
    def issue_client_credentials(self, client_id: str, client_secret: str, *,
                                 resource: str, scope: str) -> dict:
        client = self._auth_client(client_id, client_secret)
        aud = (resource or "").rstrip("/")
        if aud not in self._allowed:               # RFC 8707: only allowlisted resources
            raise OAuthError("invalid_target", "the requested resource is not served here")
        requested = [s for s in (scope or "").split() if s]
        granted = tuple(s for s in requested if s in client.scopes)   # clamp to the grant
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        exp = int(self._now()) + int(self.token_ttl_seconds)
        self._tokens[token] = _Token(client_id=client_id, scopes=granted, aud=aud, exp=exp,
                                     subject=f"agent:{client_id}")
        self._persist()
        return {"access_token": token, "token_type": "Bearer",
                "expires_in": int(self.token_ttl_seconds), "scope": " ".join(granted)}

    # --- RFC 7662 introspection -------------------------------------------
    def introspect(self, token: str, rs_client_id: str, rs_client_secret: str) -> dict:
        rs = self._auth_client(rs_client_id, rs_client_secret)
        if not rs.is_rs:
            raise OAuthError("invalid_client", "client may not introspect", status=403)
        rec = self._tokens.get(token)
        if rec is None or rec.exp <= int(self._now()):
            return {"active": False}               # unknown/expired → inactive (no detail leak)
        return {"active": True, "client_id": rec.client_id, "scope": " ".join(rec.scopes),
                "aud": rec.aud, "exp": rec.exp, "sub": rec.subject, "token_type": "Bearer"}

    # --- revocation --------------------------------------------------------
    def revoke(self, token: str, client_id: str, client_secret: str) -> bool:
        self._auth_client(client_id, client_secret)
        rec = self._tokens.get(token)
        if rec is None or rec.client_id != client_id:   # RFC 7009: only the owner may revoke
            return False                                 # uniform reply — leaks no existence
        self._tokens.pop(token, None)
        self._persist()
        return True

    # --- metadata (RFC 8414) ----------------------------------------------
    def metadata(self, public_url: str) -> dict:
        base = public_url.rstrip("/")
        return {
            "issuer": base,
            "token_endpoint": base + "/token",
            "introspection_endpoint": base + "/introspect",
            "revocation_endpoint": base + "/revoke",
            "registration_endpoint": base + "/register",
            "grant_types_supported": ["client_credentials"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "scopes_supported": ["read", "write"],
            "response_types_supported": [],
        }

    # --- HTTP dispatch (testable in-process; serve() wires http.server) ----
    @staticmethod
    def _client_creds(headers: dict, form: dict) -> tuple[str, str]:
        """RFC 6749 client auth: client_secret_basic (Authorization header) takes
        precedence, else client_secret_post (form fields). Never logged."""
        auth = headers.get("authorization", "")
        if auth.lower().startswith("basic "):
            try:
                cid, _, sec = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
                return cid, sec
            except Exception:
                return "", ""
        return form.get("client_id", [""])[0], form.get("client_secret", [""])[0]

    def _json(self, status: int, obj: dict) -> tuple[int, dict, bytes]:
        return status, {"Content-Type": "application/json"}, json.dumps(obj).encode("utf-8")

    def handle(self, method: str, path: str, headers: dict, body: bytes) -> tuple[int, dict, bytes]:
        """Dispatch one request → (status, headers, body). Pure; testable without a socket."""
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        try:
            if method == "GET" and path == "/.well-known/oauth-authorization-server":
                return self._json(200, self.metadata(self.public_url))
            form = parse_qs(body.decode("utf-8")) if body else {}
            if method == "POST" and path == "/token":
                cid, sec = self._client_creds(headers, form)
                if form.get("grant_type", [""])[0] != "client_credentials":
                    raise OAuthError("unsupported_grant_type")
                return self._json(200, self.issue_client_credentials(
                    cid, sec, resource=form.get("resource", [""])[0],
                    scope=form.get("scope", [""])[0]))
            if method == "POST" and path == "/introspect":
                cid, sec = self._client_creds(headers, form)
                return self._json(200, self.introspect(form.get("token", [""])[0], cid, sec))
            if method == "POST" and path == "/revoke":
                cid, sec = self._client_creds(headers, form)
                self.revoke(form.get("token", [""])[0], cid, sec)
                return self._json(200, {})
            if method == "POST" and path == "/register":
                raise OAuthError("access_denied", "dynamic registration is locked", status=403)
            return self._json(404, {"error": "not_found"})
        except OAuthError as exc:
            return self._json(exc.status,
                              {"error": exc.error, "error_description": exc.description})

    def serve(self, host: str, port: int) -> None:                 # pragma: no cover (socket)
        """Run the AS over a stdlib threading HTTP server (tailnet-internal). Request
        logging is suppressed so a token in a path/body never lands in a log (V9)."""
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        as_ref = self

        class _Handler(BaseHTTPRequestHandler):
            def _do(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                status, hdrs, payload = as_ref.handle(
                    method, self.path.split("?")[0], dict(self.headers), body)
                self.send_response(status)
                for k, v in hdrs.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                self._do("GET")

            def do_POST(self) -> None:
                self._do("POST")

            def log_message(self, *a) -> None:      # never log (avoids token leakage)
                return

        ThreadingHTTPServer((host, port), _Handler).serve_forever()

    # --- persistence (opaque token + client map) --------------------------
    def _persist(self) -> None:
        if not self.state_path:
            return
        data = {
            "clients": {c.client_id: {"secret_hash": c.secret_hash, "scopes": list(c.scopes),
                                      "is_rs": c.is_rs} for c in self._clients.values()},
            "tokens": {t: {"client_id": r.client_id, "scopes": list(r.scopes), "aud": r.aud,
                           "exp": r.exp, "subject": r.subject} for t, r in self._tokens.items()},
        }
        p = Path(self.state_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(p)                              # atomic
        try:
            p.chmod(0o600)                          # secrets-bearing → owner-only
        except OSError:
            pass

    def _load(self) -> None:
        try:
            data = json.loads(Path(self.state_path).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return
        for cid, c in data.get("clients", {}).items():
            self._clients[cid] = _Client(cid, c["secret_hash"], tuple(c.get("scopes", [])),
                                         bool(c.get("is_rs")))
        for tok, r in data.get("tokens", {}).items():
            self._tokens[tok] = _Token(r["client_id"], tuple(r.get("scopes", [])), r["aud"],
                                       int(r["exp"]), r.get("subject", ""))
