"""U4 — read-only MCP server: socket-bind invariant + exactly two read tools."""

from __future__ import annotations

import asyncio
import json
import subprocess

import pytest

from hypermnesic import config, index, mcp_server
from hypermnesic import embed as embed_mod

TAILNET_IP = "100.103.0.55"


def _commit(repo, rel, body, msg="add"):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)


def _call(srv, name, args):
    """Invoke an MCP tool closure and return its parsed dict payload."""
    out = asyncio.run(srv.call_tool(name, args))
    if isinstance(out, tuple):          # (content_blocks, structured_result)
        return out[1]
    return json.loads(out[0].text)


class _DownEmbedder:
    dim = config.EMBED_DIM

    def embed(self, texts):
        raise embed_mod.EmbeddingError("API down")

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


def test_only_read_tools_no_write_tool(built_index, fake_embedder):
    # U20 adds a third read tool (think); the invariant is "read-only, structural".
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder)
    tools = asyncio.run(srv.list_tools())
    names = {t.name for t in tools}
    assert names == {"search", "build_context", "think"}
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


# --- U28: reads converge before serving ------------------------------------

def test_search_tool_converges_to_head_then_debounces(make_corpus, fake_embedder):
    # FR-R41: the first read catches the index up to HEAD; a second immediate read
    # is debounced (no re-converge), so a just-committed file is not yet reflected.
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)

    _commit(repo, "first.md", "# First\n\nFIRSTMARKER content.\n", "add first")
    out1 = _call(srv, "search", {"query": "FIRSTMARKER"})
    assert any(h["path"] == "first.md" for h in out1["hits"])      # converged before serving

    _commit(repo, "second.md", "# Second\n\nSECONDMARKER content.\n", "add second")
    out2 = _call(srv, "search", {"query": "SECONDMARKER"})
    assert not any(h["path"] == "second.md" for h in out2["hits"])  # debounced (no re-converge)


def test_each_read_tool_converges(make_corpus, fake_embedder, monkeypatch):
    from hypermnesic import converge as converge_mod
    repo = make_corpus({"hetzner.md": NOTE, "net.md": NOTE2})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)

    calls: list[str] = []
    real = converge_mod.converge

    def spy(*a, **k):
        calls.append("converge")
        return real(*a, **k)

    monkeypatch.setattr(converge_mod, "converge", spy)
    _call(srv, "search", {"query": "Hetzner"})
    _call(srv, "build_context", {"path": "hetzner.md"})
    _call(srv, "think", {"topic": "Hetzner"})
    assert len(calls) == 3              # convergence ran on each read tool path


def test_reads_degrade_to_lexical_when_embedder_down(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nDOWNMARKER alpha homelab.\n"})
    index.build_index(repo, fake_embedder).close()         # built with a real (fake) embedder
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=_DownEmbedder(), repo=repo)
    out = _call(srv, "search", {"query": "DOWNMARKER"})
    assert out["degraded_lexical_only"] is True            # dense channel absent, flagged
    assert any(h["path"] == "a.md" for h in out["hits"])   # lexical still answers; no error
