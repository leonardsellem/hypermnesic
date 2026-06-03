"""hypermnesic — a disposable, rebuildable retrieval index over a markdown/git corpus.

Phase 0 (this slice): read-only index (sqlite-vec KNN + SQLite FTS5 + OpenAI
text-embedding-3-large @ 1536 dims) exposed over a tailnet-only, read-only MCP
server, plus a French/English retrieval-parity harness and a zero-infra
portability probe. Files are the single source of truth; the index is a pure,
disposable projection of the git tree.
"""

__version__ = "0.0.5"
