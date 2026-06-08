"""Tailnet-bound MCP server: read tools always, a gated git-first write tool only
when ``write_enabled``.

The default build is read-only **structurally** — no write tool is registered, so
a read-only ``serve`` (or a read-only client) can never reach a write path. The
write tool (U31) is a *separable capability*: it is registered OUTSIDE
``READ_TOOL_NAMES``, only when the server is started write-enabled (the master
role), and it reuses ``commit_note``'s gate / write-guard / protected-path refusal
/ explicit allowlist / audit log unchanged — git-first, single write target, index
stays a rebuildable projection (a reindex never loses a committed write).

The server binds to a specific Tailscale interface address at the socket level
(KTD10) — "tailnet-only" is a binding invariant, never ``0.0.0.0`` and never the
mere absence of a public DNS record.

Auth (U2/R12): the server is an OAuth 2.1 **Resource Server**. Auth is opt-in and
additive — a read-only ``serve`` with no auth keeps the Phase-1 tailnet-only-no-auth
build — but a **write-enabled master refuses to start without auth configured**
(``write_enabled ⇒ auth-required``, an engine invariant mirroring the ``0.0.0.0``
bind refusal): the tailnet is no longer the sole boundary for the write tool. When a
``token_verifier`` + ``AuthSettings`` are supplied, the FastMCP transport validates
the bearer token (the verifier enforces RFC 8707 audience binding + expiry), enforces
the required scope, and advertises RFC 9728 Protected-Resource metadata. The token
*issuer* is a separate tailnet-internal AS (U12), independent of gbrain's AS. (This
supersedes the prior "per-identity OAuth is a deferred seam" posture, KTD5.)

The dense channel degrades gracefully: if the embedding API is unreachable,
lexical + graph results still return (the dense channel is simply absent).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

# Pydantic (the SDK's schema generator) requires typing_extensions.TypedDict on Python < 3.12.
from typing_extensions import TypedDict

from hypermnesic import audit_log as audit_mod
from hypermnesic import commit_note as commit_note_mod
from hypermnesic import config, retrieve
from hypermnesic import converge as converge_mod
from hypermnesic import folders as folders_mod
from hypermnesic import frontmatter_gate as fg_mod
from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod
from hypermnesic import serialize as serialize_mod
from hypermnesic import think as think_mod

DEFAULT_PORT = 8848
DEFAULT_PATH = "/mcp"


# --- MCP tool output schemas (U2/connector quality) -------------------------------------
# Typed result shapes so the MCP server advertises an ``outputSchema`` per tool — clients
# (ChatGPT/Claude connectors + agents) then understand a result's structure instead of an
# opaque object. TypedDicts: the tool functions keep returning plain dicts (validated against
# these), so this is schema-only — no behavior change.
class SearchHit(TypedDict):
    path: str
    heading: str
    score: float
    channels: list[str]
    snippet: str
    recency: float | None


class SearchOutput(TypedDict):
    query: str
    degraded_lexical_only: bool
    manual_reindex_recommended: bool
    hits: list[SearchHit]


class BuildContextOutput(TypedDict):
    start: str
    depth: int
    context: list[str]                 # page paths reachable via wikilinks (sorted)
    manual_reindex_recommended: bool


class ResolveOutput(TypedDict):
    name: str
    resolved: str | None               # the resolved page path, or null if ambiguous/missing
    slug: str | None                   # the ``.md``-stripped wikilink target, or null
    manual_reindex_recommended: bool


class ThinkOutput(TypedDict):
    topic: str
    wrote: bool                        # always False — the observable no-write assertion
    related: list[dict]                # each: {path, heading, title, score, channels, snippet}
    context: list[str]
    questions: list[str]
    unlinked: list[dict]               # not-yet-linked pairs: {a_path, a_title, b_path, b_title}
    degraded_lexical_only: bool
    note: str
    manual_reindex_recommended: bool


# total=False: the result is a union — a success carries path/created/noop/new_sha/diff; a
# refusal carries refused; and committed is present on both. commit_note returns an explicit
# CallToolResult so FastMCP does not materialize absent union fields as null in HTTP
# structuredContent and then reject them against the generated output schema.
class CommitNoteOutput(TypedDict, total=False):
    committed: bool                    # present on every path; the rest depend on the outcome
    path: str
    created: bool
    noop: bool
    new_sha: str
    diff: str
    refused: str                       # set (with committed=False) when a gate/guard refuses


def _commit_note_tool_result(payload: CommitNoteOutput) -> CallToolResult:
    """Return a minimal structured union branch without FastMCP injecting nulls."""
    data = dict(payload)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))],
        structuredContent=data,
    )


class FolderEntry(TypedDict):
    path: str                          # repo-relative, trailing-slash (e.g. "projects/acme/")
    writable: bool                     # a note can be written directly here (matches commit_note)
    protected_reason: str | None       # why not writable (protected class / allowlist), else null
    note_count: int                    # indexed notes at/under this folder (recursive)


class ListFoldersOutput(TypedDict):
    root: str                          # the normalized root the listing is under ("" = vault root)
    depth: int                         # the (clamped) drill-down depth
    folders: list[FolderEntry]
    truncated: bool                    # the node cap was hit (drill deeper by narrowing root)
    omitted: int                       # folders dropped by the cap
    manual_reindex_recommended: bool   # convergence signal, surfaced like the other read tools
# Loopback binds are exempt from the write_enabled⇒auth-required invariant (U2): a
# localhost serve is reachable only by the local user — never the tailnet.
_LOCALHOST_BINDS = {"127.0.0.1", "::1", "localhost"}
# Tailscale's CGNAT range. With the explicit `trust_tailnet_write` opt-in, a bind inside this
# range may serve a write-enabled, auth-off `commit_note` (tailnet membership IS the write
# boundary) — but ONLY inside this range, so the opt-in can never open an auth-off write on an
# arbitrary public/LAN IP.
_TAILNET_CIDR = "100.64.0.0/10"


def _is_tailnet_ip(host: str) -> bool:
    """True iff ``host`` is a literal Tailscale CGNAT address (100.64.0.0/10)."""
    import ipaddress
    try:
        return ipaddress.ip_address(host) in ipaddress.ip_network(_TAILNET_CIDR)
    except ValueError:
        return False
# The legacy 4-prefix note-zone surface (KTD4). As of the Phase-B blocklist flip this is NO
# LONGER the default (``_effective_write_surface(None)`` returns ``None`` = blocklist); it is
# kept as a NAMED escape-hatch an operator can pass via ``--allowlist`` to restore the old
# note-zone-only write surface. The protected-path guard + governance fence refuse the
# dangerous classes regardless; an explicit allowlist further bounds *where* a write may land.
DEFAULT_WRITE_ALLOWLIST = ("notes/", "sources/", "dashboards/", "captures/")
# The OAuth scope the write tool requires of its caller (U2/V14). Enforced PER-TOOL inside
# commit_note, independent of the transport's global required_scopes — the SDK middleware
# applies one scope list to ALL tools, so it cannot separate read clients from write clients
# on a single endpoint. A read-scoped token that reaches commit_note is refused here.
WRITE_SCOPE = "write"


def normalize_default_client_scopes(default_client_scopes=None, *,
                                    scopes_supported=("read", "write")) -> list[str]:
    """Normalize admin-provided OAuth DCR defaults and fail loud on unsupported scopes."""
    supported = [str(s).strip() for s in scopes_supported if str(s).strip()]
    supported_set = set(supported)
    raw = default_client_scopes
    if raw is None:
        raw = ["read"]
    elif isinstance(raw, str):
        raw = [raw]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        for scope in str(item).replace(",", " ").split():
            if scope not in seen:
                normalized.append(scope)
                seen.add(scope)
    if not normalized:
        raise ValueError("default_client_scopes must include at least one scope")
    invalid = [s for s in normalized if s not in supported_set]
    if invalid:
        raise ValueError(
            "default_client_scopes must be a subset of scopes_supported "
            f"({', '.join(supported)}); invalid: {', '.join(invalid)}")
    return normalized


def _effective_write_surface(write_allowlist: list[str] | None) -> list[str] | None:
    """The SOLE coercion of a caller's ``--allowlist`` into the effective write surface.

    Consumed by BOTH the write path (``commit_note``'s ``allowlist``) and the read flag
    (``list_folders``' writability), so the two can never disagree — they read the same
    value (KTD: single coercion site).

    **Phase B (U5) — blocklist default:** ``None`` (no ``--allowlist``) passes through as
    ``None``, i.e. blocklist mode — the protected-path refusal + governance fence in
    ``serialize`` are the sole bound, so the operator's content folders (``projects/``,
    ``people/``, ``companies/``, ``meetings/``, …) are writable and the discovery flag flips
    with the write path by construction. An explicit list still narrows (the named
    ``DEFAULT_WRITE_ALLOWLIST`` remains an escape-hatch an operator can pass to restore the
    old note-zone-only surface). This flip is gated on the signed blocklist security-review
    delta (tests/test_blocklist_write_gate.py / G6) — it must not merge/enable unsigned.
    """
    if write_allowlist is None:
        return None
    return list(write_allowlist)


class _Backend:
    """Lazily-loaded read-only index + graph + embedder.

    ``repo`` is the git repo the index projects; convergence (U27) runs against
    it before every read. It defaults to the parent of the state dir
    (``<repo>/.hypermnesic/index.db`` → ``<repo>``) when not given explicitly.
    """

    def __init__(self, index_db: Path, embedder=None, *, repo: Path | None = None,
                 authoring_host: bool = False):
        self.index_db = Path(index_db)
        self.repo = Path(repo) if repo is not None else self._derive_repo(self.index_db)
        self.authoring_host = authoring_host
        self._embedder = embedder
        self._idx = None
        self._graph = None

    @staticmethod
    def _derive_repo(index_db: Path) -> Path:
        if index_db.name != "index.db" or index_db.parent.name != index_mod.STATE_DIRNAME:
            raise ValueError(
                "cannot derive repo from --index-db; pass --repo /path/to/vault when "
                "the index path is not <repo>/.hypermnesic/index.db"
            )
        return index_db.parent.parent

    def converge(self):
        """Bring the index up to HEAD + close a bounded dense slice before serving
        (U27/U28). Resets the cached graph when the index actually changed so
        ``build_context`` reflects freshly-replayed pages. Never raises."""
        result = converge_mod.converge(self.repo, self.idx, self.embedder,
                                       authoring_host=self.authoring_host)
        if result.replayed or result.overlay_paths:
            self._graph = None     # index advanced → rebuild the graph lazily
        return result

    @property
    def idx(self):
        if self._idx is None:
            self._idx = index_mod.Index(self.index_db)
        return self._idx

    @property
    def graph(self):
        if self._graph is None:
            self._graph = graph_mod.Graph.from_index(self.idx)
        return self._graph

    @property
    def embedder(self):
        # Construct lazily; a missing key surfaces only as dense degradation,
        # not a server-start failure (lexical + graph remain available).
        if self._embedder is None:
            try:
                from hypermnesic import embed
                self._embedder = embed.OpenAIEmbedder(repo=self.repo)
            except Exception:
                self._embedder = False  # sentinel: tried, unavailable
        return self._embedder or None


def build_server(index_db: Path, *, host: str, port: int = DEFAULT_PORT,
                 path: str = DEFAULT_PATH, embedder=None, repo: Path | None = None,
                 authoring_host: bool = False, write_enabled: bool = False,
                 write_allowlist: list[str] | None = None,
                 audit_actor_fn: Callable[[], str] | None = None,
                 token_verifier=None, auth=None, auth_server_provider=None,
                 write_scope: str = WRITE_SCOPE,
                 json_response: bool = True,
                 stateless_http: bool = True,
                 public_hosts: list[str] | None = None,
                 trust_tailnet_write: bool = False) -> FastMCP:
    """Build the tailnet MCP server bound to ``host`` (a Tailscale IP).

    Refuses ``0.0.0.0`` — the bind invariant is enforced at construction. Every
    read tool converges first (U28): the index catches up to HEAD and closes a
    bounded dense slice before serving, so a freshly pushed/committed note is
    recall-able on the next read without a manual reindex.

    ``write_enabled`` (U31) registers the git-first ``commit_note`` write tool (the
    master role). It is omitted by default, so a read-only serve is structurally
    incapable of writing. ``write_allowlist`` bounds the writable paths (defaults to
    ``DEFAULT_WRITE_ALLOWLIST``); ``audit_actor_fn`` overrides the server-set audit
    actor (defaults to the verified Tailscale node identity).

    A buffering, handshake-less client (Obsidian ``requestUrl``, Plan 2) needs BOTH
    streamable-http axes flipped from the mcp SDK defaults:

    ``json_response`` (U32/DEP-R15, default True) makes ``tools/call`` return a buffered
    single JSON body instead of an SSE stream, so a buffering client does not hang
    waiting to stream. The SDK defaults this to ``False`` (SSE); we flip it on.
    Single-JSON is spec-compliant for standard MCP clients too (they accept
    application/json).

    ``stateless_http`` (default True) serves each JSON-RPC POST independently, with no
    ``initialize`` handshake and no ``Mcp-Session-Id`` required. The SDK defaults to
    STATEFUL session mode, which 400s a bare single-shot call ("Missing session ID") —
    exactly the call the Obsidian companion makes. Stateless drops nothing we use: all
    four tools (search / build_context / think / commit_note) are stateless
    request/response with no session-scoped state or server-initiated streaming.
    Full-handshake SDK clients still connect (a stateless server accepts the handshake).
    """
    if host in ("0.0.0.0", "::", ""):
        raise ValueError(
            f"refusing to bind to {host!r}: hypermnesic MCP is tailnet-only and "
            "must bind a specific Tailscale interface address (KTD10)"
        )
    # U2: auth is configured as a pair — AuthSettings + EITHER a token_verifier (RS-only,
    # the tailnet lane) OR an auth_server_provider (AS+RS, the cloud lane). Supplying settings
    # without a validator (or vice versa), or both validators, is a half-/mis-configured auth
    # surface; refuse before constructing FastMCP so the message is engine-level.
    if token_verifier is not None and auth_server_provider is not None:
        raise ValueError("specify a token_verifier OR an auth_server_provider, not both")
    _auth_configured = token_verifier is not None or auth_server_provider is not None
    if (auth is None) ^ (not _auth_configured):
        raise ValueError(
            "OAuth auth requires BOTH AuthSettings and a token_verifier/auth_server_provider "
            "(or neither): supply them together, or omit auth entirely"
        )
    # U2 engine invariant: write_enabled ⇒ auth-required on any tailnet-reachable bind.
    # A write-enabled master serving a Tailscale interface address MUST run auth-on —
    # mirroring the 0.0.0.0 refusal — so a unit re-render or a Phase-1 rollback can never
    # silently serve commit_note unauthenticated *on the tailnet* (R12). A loopback bind is
    # exempt: it is reachable only by the local user (the same trust boundary the CLI write
    # path already has), preserving the Phase-1 single-user localhost drop-in. (The live
    # master binds the tailnet IP directly, so it is always covered.)
    #
    # ``trust_tailnet_write`` is the operator's EXPLICIT opt-out: tailnet membership IS the write
    # boundary (the "MVP auth = tailnet membership" model — valid once the public OAuth lane carries
    # all untrusted traffic). It is BOUNDED to the Tailscale CGNAT range, so it can never relax the
    # invariant on an arbitrary public/LAN IP — and the 0.0.0.0 refusal above still always fires.
    if write_enabled and auth is None and host not in _LOCALHOST_BINDS:
        if trust_tailnet_write and _is_tailnet_ip(host):
            pass                                   # explicit, tailnet-IP-bounded opt-in
        elif trust_tailnet_write:
            raise ValueError(
                "trust_tailnet_write only relaxes the auth requirement for a Tailscale IP "
                f"({_TAILNET_CIDR}); {host!r} is not in that range. Refusing an auth-off write "
                "on a non-tailnet bind — that would be a public write hole, not a tailnet one."
            )
        else:
            raise ValueError(
                "refusing a write-enabled tailnet serve without auth configured: "
                "write_enabled ⇒ auth-required on a non-loopback bind (R12 engine invariant, "
                "mirroring the 0.0.0.0 refusal). Pass --auth-issuer-url + --auth-resource-url "
                "(+ --required-scope), serve read-only, bind 127.0.0.1 for a local drop-in, or "
                "— to accept tailnet membership AS the write boundary — pass --allow-tailnet-write."
            )
    # An explicit but effectively-empty allowlist on a write-enabled serve would narrow
    # writes to NOTHING — a silent brick. Refuse at construction (no half-open server),
    # before any disk/backend touch. Omitting write_allowlist (None) keeps the default.
    if write_enabled and write_allowlist is not None and not [
        a for a in write_allowlist if a and a.strip()
    ]:
        raise ValueError(
            "refusing a write-enabled serve with an empty --allowlist: it would permit "
            "no writes at all. Omit --allowlist for the default, or pass real prefixes (U1)."
        )
    # Behind a TLS-terminating reverse proxy (Tailscale Funnel → loopback bind), the forwarded
    # Host header is the PUBLIC hostname, not 127.0.0.1. FastMCP auto-enables DNS-rebinding
    # protection on a loopback bind with a loopback-ONLY allowlist, so every proxied /mcp call
    # 421s ("Invalid Host header"). When the caller declares its public host(s), trust them too —
    # protection STAYS on (an arbitrary attacker Host is still rejected); we only widen the
    # allowlist to the proxy's hostname. Direct-IP binds (the tailnet master) never hit this
    # branch — FastMCP only auto-protects loopback — so they are unaffected.
    transport_security = None
    if public_hosts:
        from mcp.server.transport_security import TransportSecuritySettings
        allowed = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*"]
        origins: list[str] = []
        for h in public_hosts:
            if h and h not in allowed:
                allowed += [h, f"{h}:*"]
                origins += [f"https://{h}", f"https://{h}:*"]
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed, allowed_origins=origins)
    backend = _Backend(index_db, embedder=embedder, repo=repo, authoring_host=authoring_host)
    mcp = FastMCP("hypermnesic", host=host, port=port, streamable_http_path=path,
                  json_response=json_response, stateless_http=stateless_http,
                  transport_security=transport_security,       # proxy-host trust (None = default)
                  token_verifier=token_verifier, auth=auth,   # U2 RS-only / no-auth …
                  auth_server_provider=auth_server_provider)  # … or the cloud AS+RS lane
    # The single coercion site (KTD): the effective write surface is computed ONCE here and
    # shared by the write path (commit_note's allowlist) and the read flag (list_folders'
    # writability), so discovery can never advertise a path commit_note would refuse.
    effective_surface = _effective_write_surface(write_allowlist)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Hybrid (lexical + dense) search over the read-only index.")
    def search(query: str, k: int = 10) -> SearchOutput:
        cr = backend.converge()
        res = retrieve.search(backend.idx, query, embedder=backend.embedder, k=k,
                              recency_fn=retrieve.git_commit_recency(backend.repo))
        return {
            "query": query,
            "degraded_lexical_only": res.degraded or cr.degraded,
            "manual_reindex_recommended": cr.manual_reindex_recommended,
            "hits": [
                {"path": h.path, "heading": h.heading, "score": round(h.score, 6),
                 "channels": sorted(h.channels),
                 "snippet": h.text[:280], "recency": h.recency}
                for h in res.hits
            ],
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Pages reachable from a page via body wikilinks (in+out edges).")
    def build_context(path: str, depth: int = 1) -> BuildContextOutput:
        cr = backend.converge()
        reachable = graph_mod.build_context(backend.graph, path, depth=depth)
        return {"start": path, "depth": depth, "context": reachable,
                "manual_reindex_recommended": cr.manual_reindex_recommended}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Entity resolution: resolve a name to an existing page path "
                          "(gbrain's `get` role), or null if ambiguous/missing. The caller "
                          "strips `.md` (use `slug`) to form a wikilink target.")
    def resolve(name: str) -> ResolveOutput:
        cr = backend.converge()
        resolved = backend.graph.resolve(name)
        slug = resolved[:-3] if resolved and resolved.endswith(".md") else resolved
        return {"name": name, "resolved": resolved, "slug": slug,
                "manual_reindex_recommended": cr.manual_reindex_recommended}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Thinking-mode: related notes + Socratic prompts + "
                          "related-but-not-yet-linked pairs. Pass the active note's `path` to "
                          "exclude it from its own results. Never writes (wrote: false).")
    def think(topic: str, k: int = 8, depth: int = 1, path: str | None = None) -> ThinkOutput:
        cr = backend.converge()
        out = think_mod.think(backend.idx, topic, embedder=backend.embedder,
                              graph=backend.graph, k=k, depth=depth, path=path,
                              repo=backend.repo).as_dict()
        out["manual_reindex_recommended"] = cr.manual_reindex_recommended
        return out

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Discover the vault's folder taxonomy + writable locations before "
                          "placing a note: child folders under `root` (drill-down) to `depth` "
                          "levels, each with its writability, protected reason, and recursive "
                          "note count. Read-only; the `writable` flag matches what `commit_note` "
                          "accepts. Narrow `root` to drill deeper when `truncated` is true.")
    def list_folders(root: str = "", depth: int = 1) -> ListFoldersOutput:
        cr = backend.converge()
        try:
            listing = folders_mod.derive_folders(
                backend.idx.all_paths(), root=root, depth=depth,
                effective_surface=effective_surface,
                max_nodes=config.LIST_FOLDERS_MAX_NODES,
                max_depth=config.LIST_FOLDERS_MAX_DEPTH)
        except ValueError:
            # an absolute / traversal root is rejected at the boundary — return an empty,
            # leak-free listing (never out-of-vault paths) rather than an error to the client.
            listing = {"root": "", "depth": 1, "folders": [], "truncated": False, "omitted": 0}
        return {"root": listing["root"], "depth": listing["depth"],
                "folders": listing["folders"], "truncated": listing["truncated"],
                "omitted": listing["omitted"],
                "manual_reindex_recommended": cr.manual_reindex_recommended}

    if write_enabled:
        # The one sanctioned write path, exposed over MCP only on a write-enabled
        # (master) server. Git-first: file → git commit → index follows. Reuses
        # commit_note's gate/guard/allowlist/audit unchanged; the agent never merges.
        audit = audit_mod.AuditLog(
            backend.repo / index_mod.STATE_DIRNAME / "audit.jsonl",
            actor_fn=audit_actor_fn or audit_mod.tailscale_actor)   # actor is server-set (R17)
        allowlist = effective_surface   # the single coercion site (shared with list_folders)

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False),
                  description="Git-first write: commit a single note on the master "
                              "(guard → diff-or-die gate → git commit → audit; never merges). "
                              "The index follows as a projection — a reindex never loses it.")
        def commit_note(path: str, body: str | None = None,
                        set_fields: dict | None = None,
                        summary: str | None = None) -> CommitNoteOutput:
            # V14 / security-review fix: when auth is on, the write tool self-enforces the
            # write scope — independent of the transport's (misconfigurable, global)
            # required_scopes. The HTTP auth middleware guarantees a principal for any
            # authenticated request; a None principal is only the in-process bypass (no HTTP,
            # no attacker). A token lacking the write scope is refused before any write.
            if auth is not None:
                from mcp.server.auth.middleware.auth_context import get_access_token
                principal = get_access_token()
                if principal is not None and write_scope not in (principal.scopes or []):
                    return _commit_note_tool_result(
                        {"committed": False,
                         "refused": (
                                f"insufficient_scope: {write_scope} scope is required for "
                                "commit_note. Reconnect this client and approve write access "
                                "before requesting memory writes. Write approval only allows "
                                "the client to request commit_note; it does not bypass "
                                "protected-path, frontmatter, dirty-tree, head-drift, audit, "
                                "or git coordination guards."
                            )})
            try:
                r = commit_note_mod.commit_note(
                    backend.repo, path, body=body, set_fields=set_fields, summary=summary,
                    idx=backend.idx, log=audit, allowlist=allowlist)
            except (serialize_mod.WriteGuardError, fg_mod.FrontmatterDriftError,
                    serialize_mod.HeadDriftError, serialize_mod.DirtyTreeError,
                    commit_note_mod.GitCoordinationError) as exc:
                # diff-or-die / protected-path / allowlist refusal, OR a coordination
                # refusal (remote drift / push could not reach origin/main) — no commit
                # reached the shared remote, no audit entry (U11). Never a silent success.
                return _commit_note_tool_result({"committed": False, "refused": str(exc)})
            return _commit_note_tool_result(
                {"committed": not r.noop, "path": r.path, "created": r.created,
                 "noop": r.noop, "new_sha": r.new_sha or "", "diff": r.diff})

    return mcp


_CONSENT_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>hypermnesic — authorize</title></head>
<body style="font-family:system-ui;max-width:42rem;margin:3rem auto;padding:0 1rem;line-height:1.5">
<main>
<h1 style="font-size:1.6rem;margin-bottom:.25rem">Authorize Hypermnesic access</h1>
<p style="margin-top:0;color:#444">Review what this client can do before approving. This page
does not show or reveal your operator approval credential.</p>
{warning}
<section aria-labelledby="request-details">
<h2 id="request-details" style="font-size:1.1rem">Request details</h2>
<dl>
<dt><b>Client</b></dt><dd>{client}</dd>
<dt><b>Redirect origin</b></dt><dd>{redirect_origin}</dd>
<dt><b>Redirect URI</b></dt><dd>{redirect}</dd>
<dt><b>Requested scopes</b></dt><dd>{scopes}</dd>
</dl>
</section>
<section aria-labelledby="scope-details">
<h2 id="scope-details" style="font-size:1.1rem">What access means</h2>
<ul>{scope_explanations}</ul>
<p>Write access can request <code>commit_note</code>, but it does not bypass protected paths,
frontmatter validation, dirty-tree checks, head-drift checks, audit logging, or git coordination
guards.</p>
</section>
<section aria-labelledby="revoke-details">
<h2 id="revoke-details" style="font-size:1.1rem">Revocation</h2>
<p>You can reject this request now. Use client control after approval to revoke this client and stop
future access.</p>
</section>
{error}
<form method="post" action="{action}">
<input type="hidden" name="pending" value="{pending}">
<label for="approval-token"><b>Approval credential</b></label><br>
<input id="approval-token" type="password" name="approval_token" autocomplete="off"
style="width:100%;padding:.5rem;margin:.25rem 0 1rem">
<div style="display:flex;gap:.5rem;flex-wrap:wrap">
<button type="submit" name="decision" value="approve" style="padding:.5rem 1rem">
{approve_label}</button>
<button type="submit" name="decision" value="reject" style="padding:.5rem 1rem">Reject</button>
<button type="submit" name="decision" value="cancel" style="padding:.5rem 1rem">Cancel</button>
</div>
</form>
</main></body></html>"""

_CONSENT_ERROR_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>hypermnesic — authorize</title></head>
<body style="font-family:system-ui;max-width:34rem;margin:4rem auto;padding:0 1rem">
<h2>Authorization request not found</h2>
<p>This authorization request is unknown or has expired. Start the connection again
from your app.</p></body></html>"""

# Anti-clickjacking + no-script CSP + no-store: the page where the operator types the token.
def _consent_headers(redirect_uri: str = "") -> dict:
    """CSP + anti-clickjacking headers for the consent page. The form posts to ``<public>/consent``
    (self); on approval the AS **302-redirects to the OAuth client's registered redirect_uri** — a
    cross-origin navigation. CSP ``form-action`` is enforced against redirect targets too, so a bare
    ``form-action 'self'`` makes the browser silently drop that 302 (the grant is consumed but the
    app never receives the code → "first Approve does nothing, retry says expired"). We therefore
    allow ``'self'`` plus that single registered client origin. No scripts run (``default-src
    'none'``) and the redirect carries only the authorization code (never the approval token)."""
    from urllib.parse import urlsplit
    extra = ""
    sp = urlsplit(redirect_uri) if redirect_uri else None
    if sp and sp.scheme and sp.netloc:
        extra = f" {sp.scheme}://{sp.netloc}"          # e.g. https://chatgpt.com / https://claude.ai
    return {
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; "
            f"form-action 'self'{extra}; frame-ancestors 'none'"),
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
    }


def _render_consent(provider, pending_id: str, error: str = "") -> tuple[str, int]:
    """Render the consent page. Looks the pending id up FIRST and renders a generic error for an
    unknown id — the raw id (attacker input) is never reflected (no XSS sink). All client-supplied
    fields (DCR client_name, redirect) are HTML-escaped. Returns (html, status)."""
    import html as _html

    details = provider.pending_details(pending_id)
    if details is None:
        return _CONSENT_ERROR_HTML, 404          # do not reflect an unknown/arbitrary id
    from urllib.parse import urlsplit

    err = f'<p role="alert" style="color:#b00">{_html.escape(error)}</p>' if error else ""
    # the form must POST back to the PUBLIC consent path (<public>/consent), not a root-absolute
    # "/consent" — behind the Funnel's /cloud mount the latter posts to the host root and 404s.
    action = _html.escape(f"{provider.public_url}/consent")
    scopes = list(details["scopes"])
    scope_explanations: list[str] = []
    if "read" in scopes:
        scope_explanations.append(
            "<li><b>Read access</b>: the client can search and recall indexed memory.</li>"
        )
    if "write" in scopes:
        scope_explanations.append(
            "<li><b>Write access</b>: the client can request commit_note writes, subject to "
            "all Hypermnesic write guards.</li>"
        )
    for scope in scopes:
        if scope not in {"read", "write"}:
            scope_explanations.append(
                f"<li><b>{_html.escape(str(scope))}</b>: unrecognized scope.</li>"
            )
    if not scope_explanations:
        scope_explanations.append("<li>No recognized scopes were requested.</li>")
    redirect_uri = str(details["redirect_uri"])
    redirect_origin = urlsplit(redirect_uri)
    redirect_origin_text = (
        f"{redirect_origin.scheme}://{redirect_origin.netloc}"
        if redirect_origin.scheme and redirect_origin.netloc else "(unknown)"
    )
    client_name = details.get("client_name")
    client_label = str(client_name or details["client_id"])
    generic_names = {"client", "mcp client", "oauth client", "unknown", "hypermnesic client"}
    warning = ""
    if not client_name or str(client_name).strip().lower() in generic_names:
        warning = (
            '<p role="note" style="border:1px solid #b88700;padding:.75rem;background:#fff8df">'
            "Warning: this request has a generic or missing client identity. Approve only if you "
            "recognize the app and redirect origin.</p>"
        )
    approve_label = "Approve read and write" if "write" in scopes else "Approve read"
    html = _CONSENT_HTML.format(
        action=action, pending=_html.escape(pending_id),
        client=_html.escape(client_label),
        redirect_origin=_html.escape(redirect_origin_text),
        redirect=_html.escape(redirect_uri),
        scopes=_html.escape(" ".join(scopes)), scope_explanations="\n".join(scope_explanations),
        warning=warning, approve_label=_html.escape(approve_label), error=err)
    return html, (403 if error else 200)


def _require_public_https_origin(url: str, label: str) -> None:
    """Refuse a non-HTTPS or bare-IP ``url`` for the unified lane's issuer/resource (R2). A
    standards-discoverable OAuth endpoint needs an HTTPS public-origin issuer + resource; a
    bare-IP / plain-HTTP one is undiscoverable over the RFC 9728→8414 chain (the original reason
    a separate public lane was bolted on). Raised at construction — never a half-open server."""
    import ipaddress
    from urllib.parse import urlparse

    u = urlparse(str(url))
    if u.scheme != "https":
        raise ValueError(
            f"refusing a non-HTTPS {label} {url!r}: the unified OAuth endpoint must advertise an "
            "HTTPS public origin (R2). Use the Tailscale-funnel'd https:// hostname.")
    host = (u.hostname or "")
    try:
        ipaddress.ip_address(host)                # a literal IP, not a DNS name
        raise ValueError(
            f"refusing a bare-IP {label} {url!r}: the unified OAuth endpoint must advertise a "
            "public DNS hostname (R2), not a tailnet IP — that lane is undiscoverable over the "
            "standard OAuth chain. Use the Tailscale-funnel'd hostname.")
    except ValueError as exc:
        if "refusing a bare-IP" in str(exc):
            raise
        # ip_address() raised ValueError → host is a DNS name (the wanted case): accept.


def _register_consent_route(mcp: FastMCP, provider) -> None:
    """Add the operator-authenticated ``/consent`` route. ``provider.authorize`` routes the
    browser here; only the operator's approval token issues the code (the public-write gate).
    The page is escaped, framed-denied, and shows which client is being approved."""
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, RedirectResponse

    from hypermnesic import auth_cloud

    def _redirect_uri_of(pending_id: str) -> str:
        d = provider.pending_details(pending_id)
        return d["redirect_uri"] if d else ""

    @mcp.custom_route("/consent", methods=["GET", "POST"])
    async def consent(request: Request):
        if request.method == "GET":
            pid = request.query_params.get("pending", "")
            html, status = _render_consent(provider, pid)
            # the GET page's CSP governs the form submit (incl. its 302 redirect to the client)
            return HTMLResponse(html, status_code=status,
                                headers=_consent_headers(_redirect_uri_of(pid)))
        form = await request.form()
        pending = str(form.get("pending", ""))
        redirect_uri = _redirect_uri_of(pending)          # capture BEFORE finalize consumes it
        try:
            decision = str(form.get("decision", "approve"))
            if decision in {"reject", "cancel"}:
                redirect = provider.reject_consent(pending, decision=decision)
            else:
                redirect = provider.finalize_consent(pending, approval_token=str(
                    form.get("approval_token", "")))
        except auth_cloud.ConsentError as exc:
            html, status = _render_consent(provider, pending, error=str(exc))
            return HTMLResponse(html, status_code=status,
                                headers=_consent_headers(redirect_uri))
        return RedirectResponse(redirect, status_code=302,
                                headers=_consent_headers(redirect_uri))


def _patch_public_client_metadata_route(mcp: FastMCP, provider) -> None:
    """Advertise the AS metadata contract Hypermnesic actually supports.

    The MCP SDK's generated metadata route currently hard-codes confidential-client
    token auth methods. Hypermnesic's DCR/token path also accepts public clients
    (`token_endpoint_auth_method=none`), which Codex app connectors rely on. Insert a
    first-match route that returns the provider metadata while leaving the SDK token,
    registration, revocation, and protected-resource routes intact.
    """
    from mcp.server.auth.routes import cors_middleware
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    original = mcp.streamable_http_app

    async def metadata(_request):
        return JSONResponse(provider.metadata())

    def streamable_http_app_with_hypermnesic_metadata():
        app = original()
        app.routes.insert(
            0,
            Route(
                "/.well-known/oauth-authorization-server",
                endpoint=cors_middleware(metadata, ["GET", "OPTIONS"]),
                methods=["GET", "OPTIONS"],
            ),
        )
        return app

    mcp.streamable_http_app = streamable_http_app_with_hypermnesic_metadata


def build_cloud_server(index_db: Path, *, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                       path: str = DEFAULT_PATH, repo: Path | None = None, embedder=None,
                       resource: str, public_url: str, approval_token: str,
                       scopes_supported=("read", "write"), token_ttl_seconds: int = 3600,
                       default_client_scopes: list[str] | None = None,
                       write_allowlist: list[str] | None = None,
                       audit_actor_fn: Callable[[], str] | None = None) -> FastMCP:
    """Build the **unified public** OAuth MCP — the sole network lane for every remote client
    (ChatGPT/Claude mobile, the Claude Code plugin, Codex, Obsidian): the SDK's authorization_code
    + DCR + PKCE Authorization Server (``auth_cloud.CloudAuthProvider``) wired into a write-enabled
    serve, plus the operator-authenticated ``/consent`` route. The same read tools + the gated
    ``commit_note`` (per-tool ``write`` scope, V14) on one endpoint — read clients reach the read
    tools, a write-scoped principal reaches ``commit_note``. Exposed publicly via Funnel; the
    operator's approval token gates every connection.

    The write surface defaults to ``DEFAULT_WRITE_ALLOWLIST`` (the full master surface,
    write-anywhere-under-guards — KD3/KD5), not a ``captures/`` quarantine; ``write_allowlist``
    still lets ``setup``/CLI narrow or widen it. ``commit_note``'s guards (allowlist, protected-path
    refusal, diff-or-die, audit log, git-revertability) remain the write bound."""
    from mcp.server.auth.settings import (
        AuthSettings,
        ClientRegistrationOptions,
        RevocationOptions,
    )

    from hypermnesic import auth_cloud, client_control

    # R2 (engine invariant): the unified lane must advertise an HTTPS public-origin issuer +
    # resource — never a bare-IP / plain-HTTP one. A non-HTTPS or bare-IP issuer is exactly the
    # defect that forced a separate public lane (the tailnet AS was bare-IP HTTP and undiscoverable
    # over the standard chain). Refuse it at construction — fail loud, no half-open server.
    _require_public_https_origin(public_url, "public_url")
    _require_public_https_origin(resource, "resource")
    default_scopes = normalize_default_client_scopes(
        default_client_scopes, scopes_supported=scopes_supported)

    provider = auth_cloud.CloudAuthProvider(
        resource=resource, public_url=public_url, approval_token=approval_token,
        scopes_supported=list(scopes_supported), token_ttl_seconds=token_ttl_seconds,
        default_scopes=default_scopes,
        grant_store_path=(client_control.grant_store_path(repo) if repo is not None else None))
    auth = AuthSettings(
        issuer_url=public_url, resource_server_url=resource, required_scopes=None,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=list(scopes_supported), default_scopes=default_scopes),
        revocation_options=RevocationOptions(enabled=True))
    # Pass write_allowlist (including None) STRAIGHT THROUGH — no pre-coercion here. The single
    # coercion site is build_server's _effective_write_surface, so the cloud default and the
    # discovery flag are in sync by construction (KTD). Phase A: None → the 4-prefix default
    # there (the full master surface, write-anywhere-under-guards — KD3/KD5); an explicit
    # write_allowlist still narrows/widens it. An explicit empty --allowlist is still refused at
    # build_server construction (write_enabled ⇒ non-empty allowlist).
    # the cloud serve always runs behind the Funnel (loopback bind, public Host) — trust the
    # public hostname(s) from the issuer + resource URLs so proxied /mcp calls don't 421.
    from urllib.parse import urlparse
    public_hosts: list[str] = []
    for _u in (public_url, resource):
        _nl = urlparse(str(_u)).netloc
        if _nl and _nl not in public_hosts:
            public_hosts.append(_nl)
    mcp = build_server(index_db, host=host, port=port, path=path, repo=repo, embedder=embedder,
                       write_enabled=True, write_allowlist=write_allowlist,
                       audit_actor_fn=audit_actor_fn, auth_server_provider=provider, auth=auth,
                       public_hosts=public_hosts)
    _patch_public_client_metadata_route(mcp, provider)
    _register_consent_route(mcp, provider)
    return mcp


READ_TOOL_NAMES = {"search", "build_context", "think", "resolve", "list_folders"}
WRITE_TOOL_NAMES = {"commit_note"}            # registered only when write_enabled (U31)
