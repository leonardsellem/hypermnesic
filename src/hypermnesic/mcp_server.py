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
mere absence of a public DNS record. Tailnet membership is the MVP auth boundary
for both read and write (KTD5); per-identity OAuth is a deferred seam.

The dense channel degrades gracefully: if the embedding API is unreachable,
lexical + graph results still return (the dense channel is simply absent).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from hypermnesic import audit_log as audit_mod
from hypermnesic import commit_note as commit_note_mod
from hypermnesic import converge as converge_mod
from hypermnesic import frontmatter_gate as fg_mod
from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod
from hypermnesic import retrieve
from hypermnesic import serialize as serialize_mod
from hypermnesic import think as think_mod

DEFAULT_PORT = 8848
DEFAULT_PATH = "/mcp"
# The write tool's explicit allowlist (KTD4). The protected-path guard refuses the
# dangerous classes regardless; this further bounds *where* an agent write may land.
# Overridable per install (U34 role config); tune to the vault's writable zones.
DEFAULT_WRITE_ALLOWLIST = ("notes/", "sources/", "dashboards/", "captures/")


class _Backend:
    """Lazily-loaded read-only index + graph + embedder.

    ``repo`` is the git repo the index projects; convergence (U27) runs against
    it before every read. It defaults to the parent of the state dir
    (``<repo>/.hypermnesic/index.db`` → ``<repo>``) when not given explicitly.
    """

    def __init__(self, index_db: Path, embedder=None, *, repo: Path | None = None,
                 authoring_host: bool = False):
        self.index_db = Path(index_db)
        self.repo = Path(repo) if repo is not None else self.index_db.parent.parent
        self.authoring_host = authoring_host
        self._embedder = embedder
        self._idx = None
        self._graph = None

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
                self._embedder = embed.OpenAIEmbedder()
            except Exception:
                self._embedder = False  # sentinel: tried, unavailable
        return self._embedder or None


def build_server(index_db: Path, *, host: str, port: int = DEFAULT_PORT,
                 path: str = DEFAULT_PATH, embedder=None, repo: Path | None = None,
                 authoring_host: bool = False, write_enabled: bool = False,
                 write_allowlist: list[str] | None = None,
                 audit_actor_fn: Callable[[], str] | None = None,
                 json_response: bool = True) -> FastMCP:
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

    ``json_response`` (U32/DEP-R15, default True) makes the streamable-http transport
    return a buffered single JSON body for ``tools/call`` instead of an SSE stream, so
    a buffering client (Obsidian ``requestUrl``, Plan 2) does not hang waiting to
    stream. The mcp SDK defaults this to ``False`` (SSE); we flip it on. Single-JSON is
    spec-compliant for standard MCP clients too (they accept application/json).
    """
    if host in ("0.0.0.0", "::", ""):
        raise ValueError(
            f"refusing to bind to {host!r}: hypermnesic MCP is tailnet-only and "
            "must bind a specific Tailscale interface address (KTD10)"
        )
    backend = _Backend(index_db, embedder=embedder, repo=repo, authoring_host=authoring_host)
    mcp = FastMCP("hypermnesic", host=host, port=port, streamable_http_path=path,
                  json_response=json_response)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Hybrid (lexical + dense) search over the read-only index.")
    def search(query: str, k: int = 10) -> dict:
        backend.converge()
        res = retrieve.search(backend.idx, query, embedder=backend.embedder, k=k,
                              recency_fn=retrieve.git_commit_recency(backend.repo))
        return {
            "query": query,
            "degraded_lexical_only": res.degraded,
            "hits": [
                {"path": h.path, "heading": h.heading, "score": round(h.score, 6),
                 "channels": sorted(h.channels),
                 "snippet": h.text[:280], "recency": h.recency}
                for h in res.hits
            ],
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Pages reachable from a page via body wikilinks (in+out edges).")
    def build_context(path: str, depth: int = 1) -> dict:
        backend.converge()
        reachable = graph_mod.build_context(backend.graph, path, depth=depth)
        return {"start": path, "depth": depth, "context": reachable}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Thinking-mode: related notes + Socratic prompts + tensions. "
                          "Never writes (wrote: false) — a help-me-think surface, not a write.")
    def think(topic: str, k: int = 8, depth: int = 1) -> dict:
        backend.converge()
        return think_mod.think(backend.idx, topic, embedder=backend.embedder,
                               graph=backend.graph, k=k, depth=depth).as_dict()

    if write_enabled:
        # The one sanctioned write path, exposed over MCP only on a write-enabled
        # (master) server. Git-first: file → git commit → index follows. Reuses
        # commit_note's gate/guard/allowlist/audit unchanged; the agent never merges.
        audit = audit_mod.AuditLog(
            backend.repo / index_mod.STATE_DIRNAME / "audit.jsonl",
            actor_fn=audit_actor_fn or audit_mod.tailscale_actor)   # actor is server-set (R17)
        allowlist = (list(write_allowlist) if write_allowlist is not None
                     else list(DEFAULT_WRITE_ALLOWLIST))

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False),
                  description="Git-first write: commit a single note on the master "
                              "(guard → diff-or-die gate → git commit → audit; never merges). "
                              "The index follows as a projection — a reindex never loses it.")
        def commit_note(path: str, body: str | None = None,
                        set_fields: dict | None = None, summary: str | None = None) -> dict:
            try:
                r = commit_note_mod.commit_note(
                    backend.repo, path, body=body, set_fields=set_fields, summary=summary,
                    idx=backend.idx, log=audit, allowlist=allowlist)
            except (serialize_mod.WriteGuardError, fg_mod.FrontmatterDriftError) as exc:
                # diff-or-die / protected-path / allowlist refusal — no commit, no audit.
                return {"committed": False, "refused": str(exc)}
            return {"committed": not r.noop, "path": r.path, "created": r.created,
                    "noop": r.noop, "new_sha": r.new_sha, "diff": r.diff}

    return mcp


READ_TOOL_NAMES = {"search", "build_context", "think"}
WRITE_TOOL_NAMES = {"commit_note"}            # registered only when write_enabled (U31)
