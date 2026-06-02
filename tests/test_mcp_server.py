"""U4 — read-only MCP server: socket-bind invariant + exactly two read tools."""

from __future__ import annotations

import asyncio
import json
import subprocess

import pytest

from hypermnesic import config, index, mcp_server
from hypermnesic import embed as embed_mod

TAILNET_IP = "100.64.0.55"


def _commit(repo, rel, body, msg="add"):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


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


def test_search_response_carries_recency_field(make_corpus, fake_embedder):
    # U29: per-result recency surfaces in the MCP search payload (committed note → float epoch).
    repo = make_corpus({"hetzner.md": "# Hetzner\n\nRECENCYMARKER homelab.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    out = _call(srv, "search", {"query": "RECENCYMARKER"})
    hit = next(h for h in out["hits"] if h["path"] == "hetzner.md")
    assert "recency" in hit and isinstance(hit["recency"], (int, float))   # committed → epoch


# --- U31: git-first gated commit_note write tool ----------------------------

_NONCANON = "---\nstatus:    active\ncreated: 2026-05-02\n---\nbody\n"


def _write_server(repo, fake_embedder, **kw):
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    return mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo,
                                   write_enabled=True, **kw)


def test_write_enabled_lists_commit_note_read_only_excludes_it(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    ro = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    rw = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo,
                                 write_enabled=True)
    ro_names = {t.name for t in asyncio.run(ro.list_tools())}
    rw_names = {t.name for t in asyncio.run(rw.list_tools())}
    assert "commit_note" not in ro_names                       # read-only structurally excludes it
    assert "commit_note" in rw_names                           # write-enabled includes it
    assert ro_names == mcp_server.READ_TOOL_NAMES
    assert rw_names == mcp_server.READ_TOOL_NAMES | mcp_server.WRITE_TOOL_NAMES


def test_write_tool_commits_exactly_one_path_and_audits(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    srv = _write_server(repo, fake_embedder, audit_actor_fn=lambda: "tailnet:test-node")
    head_before = _git(repo, "rev-parse", "HEAD")
    out = _call(srv, "commit_note",
                {"path": "notes/n.md", "body": "# N\n\nwidget body.\n", "summary": "add n"})
    assert out["committed"] and out["created"] and out["new_sha"]
    assert (repo / "notes/n.md").exists()
    assert _git(repo, "rev-parse", "HEAD~1") == head_before    # HEAD advanced by exactly one commit
    from hypermnesic import audit_log as al
    e = al.AuditLog(repo / ".hypermnesic" / "audit.jsonl").entries()[-1]
    assert e["path"] == "notes/n.md" and e["new_sha"] == out["new_sha"]
    assert e["verb"] == "create"
    assert e["actor"] == "tailnet:test-node"                   # server-set; caller can't supply
    assert e["summary"] == "add n" and "widget body" not in e["summary"]   # summaries only


def test_write_tool_gate_abort_no_commit_no_audit(make_corpus, fake_embedder):
    repo = make_corpus({"notes/doc.md": _NONCANON})            # non-canonical frontmatter
    srv = _write_server(repo, fake_embedder, audit_actor_fn=lambda: "tailnet:t")
    head_before = _git(repo, "rev-parse", "HEAD")
    before = (repo / "notes/doc.md").read_text()
    out = _call(srv, "commit_note", {"path": "notes/doc.md", "set_fields": {"newkey": "x"}})
    assert out["committed"] is False and out["refused"]        # diff-or-die over MCP
    assert (repo / "notes/doc.md").read_text() == before       # file untouched
    assert _git(repo, "rev-parse", "HEAD") == head_before      # no commit
    audit_path = repo / ".hypermnesic" / "audit.jsonl"
    assert not audit_path.exists() or audit_path.read_text().strip() == ""   # no audit entry


def test_write_tool_protected_path_refused(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    srv = _write_server(repo, fake_embedder)
    head_before = _git(repo, "rev-parse", "HEAD")
    out = _call(srv, "commit_note", {"path": "CLAUDE.md", "body": "# pwned\n"})
    assert out["committed"] is False and out["refused"]
    assert not (repo / "CLAUDE.md").exists()
    assert _git(repo, "rev-parse", "HEAD") == head_before      # nothing committed


def test_write_tool_rejects_path_outside_allowlist(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    srv = _write_server(repo, fake_embedder, write_allowlist=["notes/"])
    out = _call(srv, "commit_note", {"path": "other/x.md", "body": "# X\n\nbody.\n"})
    assert out["committed"] is False and out["refused"]
    assert not (repo / "other/x.md").exists()


def test_write_then_read_converges_dense_and_reindex_keeps_it(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    srv = _write_server(repo, fake_embedder)
    out = _call(srv, "commit_note",
                {"path": "notes/w.md", "body": "# W\n\nWRITEMARKER content.\n", "summary": "add w"})
    assert out["committed"] and out["new_sha"]
    # the next read converges → embeds the new chunk → densely recall-able
    res = _call(srv, "search", {"query": "WRITEMARKER content."})
    assert any(h["path"] == "notes/w.md" and "dense" in h["channels"] for h in res["hits"])
    # git-first durability: a full reindex rebuilds from git and never loses the write
    index.reindex_isolated(repo, fake_embedder)
    idx2 = index.Index(index.state_dir_for(repo) / "index.db")
    assert "notes/w.md" in idx2.all_paths()
    idx2.close()
