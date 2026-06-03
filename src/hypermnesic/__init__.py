"""hypermnesic — a disposable, rebuildable retrieval index over a markdown/git corpus.

Hybrid retrieval (sqlite-vec KNN + SQLite FTS5 + OpenAI text-embedding-3-large @
1536 dims, fused with RRF) over a git-tracked vault, plus a gated, git-first
``commit_note`` write tool. Served over one OAuth-secured MCP endpoint (read tools
always; the write tool by scope) and a tailnet read companion for local devices.
Files are the single source of truth; the index is a pure, disposable projection of
the git tree.
"""

__version__ = "0.0.6"
