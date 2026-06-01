"""U4 — read-only MCP server: socket-bind invariant + exactly two read tools."""

from __future__ import annotations

import asyncio

import pytest

from hypermnesic import index, mcp_server

TAILNET_IP = "100.64.0.55"

NOTE = """# Hetzner

Homelab on Hetzner, linked to [[net]].
"""
NOTE2 = "# net\n\nNetwork topology, see [[Hetzner]].\n"


@pytest.fixture
def built_index(make_corpus, fake_embedder):
    repo = make_corpus({"hetzner.md": NOTE, "net.md": NOTE2})
    idx = index.build_index(repo, fake_embedder)
    db = index.state_dir_for(repo) / "index.db"
    idx.close()
    return db


def test_refuses_to_bind_wildcard(built_index):
    for bad in ("0.0.0.0", "::", ""):
        with pytest.raises(ValueError):
            mcp_server.build_server(built_index, host=bad)


def test_binds_to_tailscale_ip_not_wildcard(built_index):
    srv = mcp_server.build_server(built_index, host=TAILNET_IP)
    assert srv.settings.host == TAILNET_IP
    assert srv.settings.host != "0.0.0.0"


def test_exactly_two_read_tools_no_write_tool(built_index, fake_embedder):
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder)
    tools = asyncio.run(srv.list_tools())
    names = {t.name for t in tools}
    assert names == {"search", "build_context"}
    # read-only is structural: no write-ish tool exists
    assert not any(
        kw in n for t in tools for n in [t.name]
        for kw in ("write", "commit", "delete", "put", "update", "create")
    )
    for t in tools:
        assert t.annotations is not None and t.annotations.readOnlyHint is True


def test_search_tool_returns_hits(built_index, fake_embedder):
    assert mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder)
    backend = mcp_server._Backend(built_index, embedder=fake_embedder)
    from hypermnesic import retrieve
    res = retrieve.search(backend.idx, "Hetzner", embedder=fake_embedder, k=5)
    assert any(h.path == "hetzner.md" for h in res.hits)
    backend.idx.close()


def test_build_context_tool(built_index, fake_embedder):
    backend = mcp_server._Backend(built_index, embedder=fake_embedder)
    from hypermnesic import graph
    ctx = graph.build_context(backend.graph, "hetzner.md", depth=1)
    assert "net.md" in ctx
    backend.idx.close()
