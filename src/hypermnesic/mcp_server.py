"""Read-only MCP server: ``search`` + ``build_context``, tailnet socket-bound.

Read-only is **structural**, not a runtime flag: no write tool exists in this
build. The server binds to a specific Tailscale interface address at the socket
level (KTD10) — "tailnet-only" is a binding invariant, never ``0.0.0.0`` and
never the mere absence of a public DNS record.

The dense channel degrades gracefully: if the embedding API is unreachable,
lexical + graph results still return (the dense channel is simply absent).
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod
from hypermnesic import retrieve

DEFAULT_PORT = 8848
DEFAULT_PATH = "/mcp"


class _Backend:
    """Lazily-loaded read-only index + graph + embedder."""

    def __init__(self, index_db: Path, embedder=None):
        self.index_db = Path(index_db)
        self._embedder = embedder
        self._idx = None
        self._graph = None

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
                 path: str = DEFAULT_PATH, embedder=None) -> FastMCP:
    """Build the read-only MCP server bound to ``host`` (a Tailscale IP).

    Refuses ``0.0.0.0`` — the bind invariant is enforced at construction.
    """
    if host in ("0.0.0.0", "::", ""):
        raise ValueError(
            f"refusing to bind to {host!r}: hypermnesic MCP is tailnet-only and "
            "must bind a specific Tailscale interface address (KTD10)"
        )
    backend = _Backend(index_db, embedder=embedder)
    mcp = FastMCP("hypermnesic", host=host, port=port, streamable_http_path=path)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Hybrid (lexical + dense) search over the read-only index.")
    def search(query: str, k: int = 10) -> dict:
        res = retrieve.search(backend.idx, query, embedder=backend.embedder, k=k)
        return {
            "query": query,
            "degraded_lexical_only": res.degraded,
            "hits": [
                {"path": h.path, "heading": h.heading, "score": round(h.score, 6),
                 "channels": sorted(h.channels),
                 "snippet": h.text[:280]}
                for h in res.hits
            ],
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True),
              description="Pages reachable from a page via body wikilinks (in+out edges).")
    def build_context(path: str, depth: int = 1) -> dict:
        reachable = graph_mod.build_context(backend.graph, path, depth=depth)
        return {"start": path, "depth": depth, "context": reachable}

    return mcp


READ_TOOL_NAMES = {"search", "build_context"}
