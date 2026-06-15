"""U4 — read-only MCP server: socket-bind invariant + exactly two read tools."""

from __future__ import annotations

import asyncio
import json
import subprocess

import pytest
from starlette.testclient import TestClient

from hypermnesic import config, index, mcp_server
from hypermnesic import embed as embed_mod

TAILNET_IP = "100.64.0.1"   # CGNAT/Tailscale documentation range — not a real node


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
    if getattr(out, "structuredContent", None) is not None:
        return out.structuredContent
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


def test_serve_returns_single_json_not_sse(built_index, fake_embedder):
    # U32/DEP-R15: tools/call returns a buffered single JSON body, not an SSE stream,
    # so an Obsidian requestUrl (buffering) client does not hang. SDK default is SSE.
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder)
    assert srv.settings.json_response is True
    # opt-out remains available for a streaming client
    sse = mcp_server.build_server(built_index, host=TAILNET_IP, json_response=False)
    assert sse.settings.json_response is False


def test_serve_is_stateless_for_handshakeless_clients(built_index, fake_embedder):
    # The Obsidian companion (requestUrl) issues single-shot JSON-RPC POSTs with no
    # initialize handshake and no Mcp-Session-Id. The SDK default is STATEFUL session
    # mode, which 400s those calls ("Missing session ID"). We default stateless so a
    # bare tools/call returns 200. This guard locks the contract: if a refactor drops
    # stateless_http, FastMCP reverts to the stateful default and this test fails
    # (the live transport proof is the bare-curl tools/call in the deploy VERIFY).
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder)
    assert srv.settings.stateless_http is True
    # opt-out remains available for a session-stateful client
    stateful = mcp_server.build_server(built_index, host=TAILNET_IP, stateless_http=False)
    assert stateful.settings.stateless_http is False


def test_only_read_tools_no_write_tool(built_index, fake_embedder):
    # U20 adds think; U1 adds resolve; U3 adds list_folders. Invariant: "read-only, structural".
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder)
    tools = asyncio.run(srv.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "search", "hypermnesic_search", "build_context", "think", "resolve", "list_folders"}
    # read-only is structural: no write-ish tool exists
    assert not any(
        kw in n for t in tools for n in [t.name]
        for kw in ("write", "commit", "delete", "put", "update", "create")
    )
    for t in tools:
        assert t.annotations is not None and t.annotations.readOnlyHint is True


def test_every_tool_advertises_an_output_schema(built_index, fake_embedder):
    # connector quality (ChatGPT "OUTPUT SCHEMA RECOMMENDED"): each tool declares a typed result
    # so clients understand its structure. Read tools + the write tool on a write-enabled master.
    # loopback host so write_enabled is allowed without auth (the invariant exempts 127.0.0.1)
    srv = mcp_server.build_server(built_index, host="127.0.0.1", embedder=fake_embedder,
                                  write_enabled=True, repo=built_index.parent.parent)
    schemas = {t.name: t.outputSchema for t in asyncio.run(srv.list_tools())}
    assert set(schemas) == {
        "search", "hypermnesic_search", "build_context", "think", "resolve", "list_folders",
        "commit_note"}
    for name, sch in schemas.items():
        assert sch and sch.get("properties"), f"{name} has no outputSchema"
    # spot-check the declared shapes match the real returns
    assert "hits" in schemas["search"]["properties"]
    assert schemas["hypermnesic_search"] == schemas["search"]
    assert "context" in schemas["build_context"]["properties"]
    assert {"resolved", "slug"} <= set(schemas["resolve"]["properties"])
    assert {"questions", "unlinked"} <= set(schemas["think"]["properties"])
    assert {"folders", "truncated", "omitted", "agent_instruction"} <= set(
        schemas["list_folders"]["properties"]
    )
    assert {"committed", "refused"} <= set(schemas["commit_note"]["properties"])


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
    _call(srv, "list_folders", {})
    assert len(calls) == 4              # convergence ran on each read tool (incl. list_folders)


def test_reads_degrade_to_lexical_when_embedder_down(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nDOWNMARKER alpha homelab.\n"})
    index.build_index(repo, fake_embedder).close()         # built with a real (fake) embedder
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=_DownEmbedder(), repo=repo)
    out = _call(srv, "search", {"query": "DOWNMARKER"})
    assert out["degraded_lexical_only"] is True            # dense channel absent, flagged
    assert out["degraded_reason"] == "embedding_error"
    assert any(h["path"] == "a.md" for h in out["hits"])   # lexical still answers; no error


def test_think_surfaces_rate_limit_degraded_reason(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nRATELIMITMARKER alpha homelab.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"

    class RateLimitedEmbedder:
        dim = fake_embedder.dim

        def embed(self, texts):
            raise embed_mod.EmbeddingError("quota exhausted", reason="rate_limited")

    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=RateLimitedEmbedder(), repo=repo)
    out = _call(srv, "think", {"topic": "RATELIMITMARKER"})

    assert out["degraded_lexical_only"] is True
    assert out["degraded_reason"] == "rate_limited"
    assert any(h["path"] == "a.md" for h in out["related"])


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
    # U2 invariant: a write-enabled master runs auth-on. Inject a test verifier+settings
    # (the in-process _call bypasses the HTTP auth middleware, so write-tool behavior is
    # unchanged — this just satisfies write_enabled⇒auth-required at construction).
    kw.setdefault("token_verifier", _verifier())
    kw.setdefault("auth", _auth_settings())
    return mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo,
                                   write_enabled=True, **kw)


def test_write_enabled_lists_commit_note_read_only_excludes_it(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    ro = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    rw = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo,
                                 write_enabled=True, token_verifier=_verifier(),
                                 auth=_auth_settings())
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


def test_write_tool_protected_path_refusal_survives_http_output_validation(make_corpus,
                                                                           fake_embedder):
    # Regression from the live remote-client smoke: the in-process tool returned a refusal dict,
    # but FastMCP's HTTP structured-output validation expanded optional TypedDict fields to null
    # and rejected them against the generated string/boolean schema. Remote clients must receive
    # the clean refusal payload, not "Output validation error".
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    srv = mcp_server.build_server(index.state_dir_for(repo) / "index.db", host="127.0.0.1",
                                  repo=repo, embedder=fake_embedder, write_enabled=True,
                                  public_hosts=["testserver"])
    head_before = _git(repo, "rev-parse", "HEAD")
    with TestClient(srv.streamable_http_app()) as client:
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "commit_note",
                    "arguments": {"path": "AGENTS.md", "body": "# pwned\n"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert resp.status_code == 200
    payload = resp.json()["result"]
    assert payload.get("isError") is not True
    structured = payload["structuredContent"]
    assert structured["committed"] is False
    assert "protected path" in structured["refused"]
    assert "Output validation error" not in payload["content"][0]["text"]
    assert _git(repo, "rev-parse", "HEAD") == head_before


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


def test_search_surfaces_manual_reindex_signal(make_corpus, fake_embedder, monkeypatch):
    # Review #3: the oversized-delta / degraded signal from convergence must reach the
    # caller rather than being discarded by the read tool.
    from hypermnesic import converge as converge_mod
    repo = make_corpus({"a.md": "# A\n\nMARK alpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)

    def fake_converge(*a, **k):
        return converge_mod.ConvergeResult(status="oversized_delta",
                                           manual_reindex_recommended=True)

    monkeypatch.setattr(converge_mod, "converge", fake_converge)
    out = _call(srv, "search", {"query": "MARK"})
    assert out["manual_reindex_recommended"] is True          # signal surfaced, not dropped


# --- U1: explicit allowlist plumb-through + empty-allowlist startup rejection ---

def test_write_enabled_empty_allowlist_rejected_at_startup(built_index):
    # An empty (or whitespace-only) allowlist on a write-enabled serve narrows writes
    # to NOTHING — refuse at construction so there is no half-open server. (U1)
    for bad in ([], [""], ["  "], ["", "  "]):
        with pytest.raises(ValueError):
            mcp_server.build_server(built_index, host=TAILNET_IP, write_enabled=True,
                                    write_allowlist=bad)


def test_read_only_serve_ignores_allowlist(built_index, fake_embedder):
    # Read-only: --allowlist is inert (no write tool), and an empty list does NOT
    # trigger the write-path startup rejection.
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder,
                                  write_allowlist=[])           # would reject if write_enabled
    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert "commit_note" not in names and names == mcp_server.READ_TOOL_NAMES


def test_explicit_allowlist_permits_only_listed_prefixes(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    srv = _write_server(repo, fake_embedder, write_allowlist=["projects/"])
    permitted = _call(srv, "commit_note", {"path": "projects/p.md", "body": "# P\n\nbody.\n"})
    assert permitted["committed"] and permitted["created"]      # in the explicit list
    refused = _call(srv, "commit_note", {"path": "sources/s.md", "body": "# S\n\nbody.\n"})
    assert refused["committed"] is False and refused["refused"]  # default 'sources/' not listed
    assert not (repo / "sources/s.md").exists()


def test_write_tool_coordination_refusal_maps_to_refused(make_corpus, fake_embedder, tmp_path):
    # U11 over MCP: a push that cannot reach the shared remote surfaces as
    # {committed: False, refused}, not a silent success or an uncaught exception.
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(bare)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "push", "-u", "origin", "main"],
                   check=True, capture_output=True)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    srv = _write_server(repo, fake_embedder, write_allowlist=["sources/"])
    out = _call(srv, "commit_note", {"path": "sources/n.md", "body": "# N\n\nbody.\n"})
    assert out["committed"] is False and out["refused"]         # refusal, not silent success
    audit = repo / ".hypermnesic" / "audit.jsonl"
    assert not audit.exists() or audit.read_text().strip() == ""   # no audit on a non-landed write


# --- U1: resolve entity-resolution read tool --------------------------------

def test_resolve_tool_returns_path_and_slug(make_corpus, fake_embedder):
    repo = make_corpus({"infrastructure/hetzner.md": "# Hetzner\n\nThe homelab box.\n",
                        "net.md": "# net\n\ntopology.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    out = _call(srv, "resolve", {"name": "Hetzner"})
    assert out["resolved"] == "infrastructure/hetzner.md"
    assert out["slug"] == "infrastructure/hetzner"             # caller wikilinks the slug
    assert "manual_reindex_recommended" in out                 # convergence signal surfaced


def test_resolve_tool_ambiguous_and_missing_are_null(make_corpus, fake_embedder):
    repo = make_corpus({"notes/dup.md": "# D1\n\n", "archive/dup.md": "# D2\n\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    assert _call(srv, "resolve", {"name": "dup"})["resolved"] is None      # ambiguous → null
    assert _call(srv, "resolve", {"name": "ghost"})["resolved"] is None    # missing → null


def test_resolve_is_read_tool_and_converges(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    tools = {t.name: t for t in asyncio.run(srv.list_tools())}
    assert "resolve" in tools and "resolve" in mcp_server.READ_TOOL_NAMES
    assert tools["resolve"].annotations.readOnlyHint is True
    # a freshly committed entity page is resolvable after convergence
    _commit(repo, "infrastructure/box.md", "# Box\n\nBOXMARKER body.\n", "add box")
    out = _call(srv, "resolve", {"name": "box"})
    assert out["resolved"] == "infrastructure/box.md"          # converged before resolving


# --- U3: list_folders discovery read tool -----------------------------------

def _folders_by_path(out):
    return {e["path"]: e for e in out["folders"]}


def test_list_folders_returns_taxonomy_and_schema_shape(make_corpus, fake_embedder):
    # AE7: a typed, structured listing — path/writable/protected_reason/note_count per folder,
    # plus truncated/omitted and the convergence signal. Phase-B blocklist default: both notes/
    # and the operator's content folders (projects/) are writable (re-pointed from the Phase-A
    # 4-prefix assertion per the byte-preservation learning — the flip genuinely changes this).
    repo = make_corpus({"notes/n.md": "# N\n\nbody.\n", "projects/acme/a.md": "# A\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    out = _call(srv, "list_folders", {"root": "", "depth": 1})
    assert set(out) >= {"root", "depth", "folders", "truncated", "omitted",
                        "manual_reindex_recommended"}
    by = _folders_by_path(out)
    assert by["notes/"]["writable"] is True and by["notes/"]["protected_reason"] is None
    assert by["notes/"]["note_count"] == 1
    assert by["projects/"]["writable"] is True                 # Phase B: blocklist default
    assert by["projects/"]["protected_reason"] is None


def test_list_folders_returns_root_agents_md_instruction(make_corpus, fake_embedder):
    repo = make_corpus({
        "AGENTS.md": (
            "# Agent rules\n\n"
            "Use repo-local guidance from docs/reference/mcp-tools.md.\n"
            "Do not echo /Volumes/Work/private or http://198.51.100.55:8848/mcp.\n"
        ),
        "notes/n.md": "# N\n\nbody.\n",
    })
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    out = _call(srv, "list_folders", {"root": "", "depth": 1})
    assert "notes/" in _folders_by_path(out)
    assert out["agent_instruction"] == {
        "source": "AGENTS.md",
        "content": (
            "# Agent rules\n\n"
            "Use repo-local guidance from docs/reference/mcp-tools.md.\n"
            "Do not echo <local-path> or <endpoint-url>.\n"
        ),
    }


def test_list_folders_falls_back_to_root_claude_md_instruction(make_corpus, fake_embedder):
    repo = make_corpus({
        "CLAUDE.md": "# Claude rules\n\nFallback guidance.\n",
        "projects/acme/a.md": "# A\n\nbody.\n",
    })
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    out = _call(srv, "list_folders", {"root": "", "depth": 1})
    assert "projects/" in _folders_by_path(out)
    assert out["agent_instruction"] == {
        "source": "CLAUDE.md",
        "content": "# Claude rules\n\nFallback guidance.\n",
    }


def test_list_folders_omits_instruction_payload_when_absent(make_corpus, fake_embedder):
    repo = make_corpus({"people/alice/n.md": "# N\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    out = _call(srv, "list_folders", {"root": "people/", "depth": 1})
    assert "people/alice/" in _folders_by_path(out)
    assert out["agent_instruction"] is None


def test_list_folders_prefers_agents_md_over_claude_md(make_corpus, fake_embedder):
    repo = make_corpus({
        "AGENTS.md": "# Agent rules\n\nPreferred.\n",
        "CLAUDE.md": "# Claude rules\n\nNot preferred.\n",
        "notes/n.md": "# N\n\nbody.\n",
    })
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    out = _call(srv, "list_folders", {"root": "", "depth": 1})
    assert out["agent_instruction"] == {
        "source": "AGENTS.md",
        "content": "# Agent rules\n\nPreferred.\n",
    }


def test_list_folders_reads_only_direct_instruction_file_for_requested_root(make_corpus,
                                                                            fake_embedder):
    repo = make_corpus({
        "projects/acme/AGENTS.md": "# Child rules\n\nDo not bubble up.\n",
        "projects/acme/a.md": "# A\n\nbody.\n",
    })
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    parent = _call(srv, "list_folders", {"root": "projects/", "depth": 1})
    assert "projects/acme/" in _folders_by_path(parent)
    assert parent["agent_instruction"] is None

    child = _call(srv, "list_folders", {"root": "projects/acme/", "depth": 1})
    assert child["agent_instruction"] == {
        "source": "AGENTS.md",
        "content": "# Child rules\n\nDo not bubble up.\n",
    }


def test_list_folders_is_read_tool_and_converges(make_corpus, fake_embedder):
    repo = make_corpus({"notes/a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    tools = {t.name: t for t in asyncio.run(srv.list_tools())}
    assert "list_folders" in tools and "list_folders" in mcp_server.READ_TOOL_NAMES
    assert "list_folders" not in mcp_server.WRITE_TOOL_NAMES
    assert tools["list_folders"].annotations.readOnlyHint is True
    # a folder created by a fresh commit is discoverable after convergence
    _commit(repo, "fresh/box.md", "# Box\n\nFRESHFOLDER body.\n", "add fresh folder")
    out = _call(srv, "list_folders", {"root": "", "depth": 1})
    assert "fresh/" in _folders_by_path(out)                   # converged before listing


def test_list_folders_nested_protected_folder_is_non_writable(make_corpus, fake_embedder):
    # AE4 over MCP: discovery never advertises a path commit_note would refuse. projects/ is
    # writable but projects/scripts/ is NOT — probing a file UNDER the prefix makes the flag agree.
    repo = make_corpus({"projects/scripts/x.md": "# x\n\nbody.\n",
                        "projects/acme/a.md": "# A\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    by = _folders_by_path(_call(srv, "list_folders", {"root": "projects/", "depth": 1}))
    assert by["projects/scripts/"]["writable"] is False
    assert "scripts/" in by["projects/scripts/"]["protected_reason"]


def test_discovery_and_commit_note_agree_on_nested_protected(make_corpus, fake_embedder):
    # G4: the parity-lie guard, both sides in one test. With projects/ allowlisted, projects/acme/
    # is writable but projects/scripts/ is NOT (the protected-dir rule beats the allowlist).
    # list_folders reports projects/scripts/ non-writable AND commit_note refuses
    # projects/scripts/*.md — discovery never advertises a path the write path would refuse.
    repo = make_corpus({"projects/scripts/x.md": "# x\n\nbody.\n",
                        "projects/acme/a.md": "# A\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host="127.0.0.1", embedder=fake_embedder, repo=repo,
                                  write_enabled=True, write_allowlist=["projects/"])
    by = _folders_by_path(_call(srv, "list_folders", {"root": "projects/", "depth": 1}))
    assert by["projects/acme/"]["writable"] is True
    assert by["projects/scripts/"]["writable"] is False        # discovery: non-writable
    refused = _call(srv, "commit_note", {"path": "projects/scripts/n.md", "body": "# n\n\nx.\n"})
    assert refused["committed"] is False and refused["refused"]    # commit_note refuses → agree
    ok = _call(srv, "commit_note", {"path": "projects/acme/n.md", "body": "# n\n\nx.\n"})
    assert ok["committed"] is True                             # the writable sibling commits


def test_list_folders_rejects_traversal_root_without_leak(make_corpus, fake_embedder):
    repo = make_corpus({"notes/n.md": "# N\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    for bad in ("../etc", "/etc/passwd"):
        out = _call(srv, "list_folders", {"root": bad, "depth": 1})
        assert out["folders"] == []                            # no out-of-vault leakage
        assert out["agent_instruction"] is None


def test_list_folders_bounds_payload(make_corpus, fake_embedder, monkeypatch):
    from hypermnesic import config
    monkeypatch.setattr(config, "LIST_FOLDERS_MAX_NODES", 2)    # read at call time by the tool
    repo = make_corpus({f"folder{i}/n.md": f"# F{i}\n\nbody {i}.\n" for i in range(3)})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo)
    out = _call(srv, "list_folders", {"root": "", "depth": 1})
    assert out["truncated"] is True and out["omitted"] == 1
    assert [e["path"] for e in out["folders"]] == ["folder0/", "folder1/"]   # sorted, tail dropped


# --- U2: OAuth2 Resource-Server wiring + write_enabled⇒auth-required invariant -

_RES = "https://example.ts.net/mcp"
_ISS = "https://example.ts.net/honcho/"


def _auth_settings():
    from hypermnesic import auth
    return auth.make_auth_settings(issuer_url=_ISS, resource_server_url=_RES,
                                   required_scopes=["write"])


def _verifier():
    from hypermnesic import auth
    return auth.build_token_verifier(resource_server_url=_RES, verify_raw=lambda t: None)


def test_build_server_no_auth_is_phase1_unauthenticated(built_index, fake_embedder):
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder)
    assert srv.settings.auth is None              # no auth flags → Phase-1 unauthenticated build


def test_build_server_with_auth_sets_resource_server(built_index, fake_embedder):
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder,
                                  token_verifier=_verifier(), auth=_auth_settings())
    assert srv.settings.auth is not None
    assert str(srv.settings.auth.resource_server_url).rstrip("/") == _RES
    assert srv.settings.auth.required_scopes == ["write"]


def test_read_only_serve_with_auth_builds(built_index, fake_embedder):
    # auth is opt-in/additive for a read-only serve too (no write tool)
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, embedder=fake_embedder,
                                  token_verifier=_verifier(), auth=_auth_settings())
    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert "commit_note" not in names


def test_write_enabled_without_auth_refused(built_index):
    # the engine invariant: a write-enabled TAILNET master must NOT start auth-off (mirrors 0.0.0.0)
    with pytest.raises(ValueError, match="(?i)auth"):
        mcp_server.build_server(built_index, host=TAILNET_IP, write_enabled=True)


def test_write_enabled_localhost_without_auth_allowed(make_corpus, fake_embedder):
    # loopback exemption: a single-user localhost write serve does not require auth (only
    # the local user can reach it — the same boundary the CLI write path already has).
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host="127.0.0.1", embedder=fake_embedder, repo=repo,
                                  write_enabled=True)
    assert "commit_note" in {t.name for t in asyncio.run(srv.list_tools())}
    assert srv.settings.auth is None


def test_trust_tailnet_write_allows_auth_off_write_on_a_tailnet_ip(make_corpus, fake_embedder):
    # Explicit operator opt-in: tailnet membership is the write boundary. With trust_tailnet_write,
    # a write-enabled serve on a real Tailscale IP (100.64.0.0/10) may run auth-off — commit_note is
    # registered and no AuthSettings are attached. (The default still refuses; this is opt-in only.)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo,
                                  write_enabled=True, trust_tailnet_write=True)
    assert "commit_note" in {t.name for t in asyncio.run(srv.list_tools())}
    assert srv.settings.auth is None                       # tailnet-trust, no OAuth ceremony


def test_trust_tailnet_write_default_off_still_refuses(built_index):
    # safe-by-default: without the explicit opt-in, the write_enabled⇒auth-required invariant holds.
    with pytest.raises(ValueError, match="(?i)auth"):
        mcp_server.build_server(built_index, host=TAILNET_IP, write_enabled=True)


def test_trust_tailnet_write_rejects_a_non_tailnet_ip(built_index):
    # the opt-in is BOUNDED to the Tailscale CGNAT range — it must not enable an auth-off write on
    # an arbitrary public/LAN IP (that would be a real public write hole, not a tailnet one).
    with pytest.raises(ValueError, match="(?i)tailnet|100\\.64"):
        mcp_server.build_server(built_index, host="203.0.113.5", write_enabled=True,
                                trust_tailnet_write=True)


def test_trust_tailnet_write_never_enables_wildcard(built_index):
    # the wildcard refusal is absolute — trust_tailnet_write cannot open a 0.0.0.0 write.
    with pytest.raises(ValueError, match="(?i)tailnet-only|0\\.0\\.0\\.0|wildcard|bind"):
        mcp_server.build_server(built_index, host="0.0.0.0", write_enabled=True,
                                trust_tailnet_write=True)


def test_write_enabled_verifier_without_auth_settings_refused(built_index):
    # both halves required: a verifier but no AuthSettings is a half-configured auth → refuse
    with pytest.raises(ValueError, match="(?i)auth"):
        mcp_server.build_server(built_index, host=TAILNET_IP, write_enabled=True,
                                token_verifier=_verifier())


def test_write_enabled_with_auth_starts_and_lists_commit_note(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder, repo=repo,
                                  write_enabled=True, token_verifier=_verifier(),
                                  auth=_auth_settings())
    assert "commit_note" in {t.name for t in asyncio.run(srv.list_tools())}
    assert srv.settings.auth is not None


def test_build_server_accepts_auth_server_provider_cloud_lane(built_index):
    # the cloud lane passes an auth_server_provider (AS+RS) instead of a token_verifier
    from mcp.server.auth.settings import AuthSettings

    from hypermnesic import auth_cloud
    prov = auth_cloud.CloudAuthProvider(resource=_RES, public_url="https://h/cloud",
                                        approval_token="x", scopes_supported=["read", "write"])
    auth = AuthSettings(issuer_url="https://h/cloud", resource_server_url=_RES,
                        required_scopes=None)
    srv = mcp_server.build_server(built_index, host=TAILNET_IP, auth_server_provider=prov,
                                  auth=auth)
    assert srv.settings.auth is not None


def test_build_server_rejects_both_verifier_and_provider(built_index):
    from hypermnesic import auth_cloud
    prov = auth_cloud.CloudAuthProvider(resource=_RES, public_url="https://h/cloud",
                                        approval_token="x", scopes_supported=["read"])
    with pytest.raises(ValueError, match="(?i)both|not both|provider"):
        mcp_server.build_server(built_index, host=TAILNET_IP, token_verifier=_verifier(),
                                auth_server_provider=prov, auth=_auth_settings())


def test_auth_with_wildcard_host_refused_bind_first(built_index):
    # the bind invariant is checked FIRST: 0.0.0.0 is refused even with auth configured
    with pytest.raises(ValueError, match="(?i)tailnet|0\\.0\\.0\\.0|bind"):
        mcp_server.build_server(built_index, host="0.0.0.0",
                                token_verifier=_verifier(), auth=_auth_settings())


# --- U2 (security review): the write tool self-enforces the write scope ------

def _set_principal(scopes):
    """Set the authenticated principal in the SDK auth contextvar (what the HTTP auth
    middleware does for a real request). Returns (var, token) so the test can reset it."""
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken
    at = AccessToken(token="t", client_id="agent", scopes=list(scopes), expires_at=None,
                     resource=_RES, claims={"aud": _RES})
    return auth_context_var, auth_context_var.set(AuthenticatedUser(at))


def test_commit_note_rejects_read_scoped_principal(make_corpus, fake_embedder):
    # the V14 inverted-failure case: a read-scoped token reaches the write tool (because the
    # transport's global required_scopes can't separate read from write on one endpoint). The
    # write tool MUST self-enforce the write scope and refuse.
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    srv = _write_server(repo, fake_embedder)                  # auth-on
    var, tok = _set_principal(["read"])                       # read-only principal
    try:
        out = _call(srv, "commit_note", {"path": "notes/n.md", "body": "# N\n\nbody.\n"})
    finally:
        var.reset(tok)
    assert out["committed"] is False and "scope" in out["refused"].lower()
    assert not (repo / "notes/n.md").exists()                 # nothing written


def test_commit_note_read_scope_refusal_is_actionable_and_guard_preserving(make_corpus,
                                                                           fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    srv = _write_server(repo, fake_embedder)
    head_before = _git(repo, "rev-parse", "HEAD")
    var, tok = _set_principal(["read"])
    try:
        out = _call(srv, "commit_note", {"path": "notes/n.md", "body": "# N\n\nbody.\n"})
    finally:
        var.reset(tok)
    assert out["committed"] is False
    refusal = out["refused"]
    assert "write scope is required" in refusal
    assert "reconnect" in refusal or "approve write" in refusal
    assert "does not bypass protected-path" in refusal
    assert "frontmatter" in refusal and "git" in refusal
    assert "token" not in refusal.lower() and "secret" not in refusal.lower()
    assert _git(repo, "rev-parse", "HEAD") == head_before
    assert not (repo / "notes/n.md").exists()


def test_commit_note_allows_write_scoped_principal(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    srv = _write_server(repo, fake_embedder)
    var, tok = _set_principal(["read", "write"])
    try:
        out = _call(srv, "commit_note", {"path": "notes/n.md", "body": "# N\n\nbody.\n"})
    finally:
        var.reset(tok)
    assert out["committed"] is True and out["created"]
