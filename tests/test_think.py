"""U20 — thinking-mode: an observable no-write boundary. [R7/H1/KD2/KTD7]

The spec is the *boundary*: ``think`` surfaces related notes + at least one
Socratic/tension prompt, returns an explicit ``wrote: false``, leaves the index
and git HEAD untouched, and is structurally incapable of writing (no
``commit_note``/``propose`` in its import surface). The MCP ``think`` tool is
read-only-hinted and sits beside ``search``/``build_context`` with no write tool.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess

from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod
from hypermnesic import mcp_server
from hypermnesic import think as think_mod

TAILNET_IP = "100.64.0.1"   # CGNAT/Tailscale documentation range — not a real node

_HETZNER = "# Hetzner\n\nHomelab on Hetzner, linked to [[net]]. Backups via restic.\n"
_NET = "# net\n\nNetwork topology and tailnet, see [[Hetzner]].\n"


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


def _built(make_corpus, fake_embedder):
    repo = make_corpus({"hetzner.md": _HETZNER, "net.md": _NET})
    idx = index_mod.build_index(repo, fake_embedder)
    g = graph_mod.Graph.from_index(idx)
    return repo, idx, g


# --- R7: the observable no-write boundary -------------------------------------

def test_think_returns_related_and_wrote_false_no_side_effects(make_corpus, fake_embedder):
    repo, idx, g = _built(make_corpus, fake_embedder)
    head_before = _git(repo, "rev-parse", "HEAD")
    paths_before = set(idx.all_paths())

    r = think_mod.think(idx, "Hetzner homelab", embedder=fake_embedder, graph=g)

    assert r.wrote is False
    assert any(h["path"] == "hetzner.md" for h in r.related)
    assert len(r.questions) >= 1                         # at least one Socratic/tension prompt
    # nothing was written: HEAD and the index are unchanged
    assert _git(repo, "rev-parse", "HEAD") == head_before
    assert set(idx.all_paths()) == paths_before
    idx.close()


def test_think_excludes_active_note(make_corpus, fake_embedder):
    # U42: the note being written must not match itself. With path set, the
    # active note is absent from related (and therefore from questions/pairs,
    # which derive from the same self-excluded hits).
    repo, idx, g = _built(make_corpus, fake_embedder)
    r = think_mod.think(idx, "Hetzner homelab", embedder=fake_embedder, graph=g, path="hetzner.md")
    assert r.wrote is False
    assert r.related, "the other note should still surface"
    assert all(h["path"] != "hetzner.md" for h in r.related)
    idx.close()


def test_think_surfaces_graph_context(make_corpus, fake_embedder):
    repo, idx, g = _built(make_corpus, fake_embedder)
    r = think_mod.think(idx, "Hetzner", embedder=fake_embedder, graph=g)
    # the two notes are mutually linked, so the top hit's neighbour is in context
    top = r.related[0]["path"]
    neighbour = "net.md" if top == "hetzner.md" else "hetzner.md"
    assert neighbour in r.context
    idx.close()


# --- U43: topic normalization (strip a leading ATX heading marker) ------------

def test_think_strips_leading_atx_marker_from_topic(make_corpus, fake_embedder):
    repo, idx, g = _built(make_corpus, fake_embedder)
    r = think_mod.think(idx, "# Hetzner homelab", embedder=fake_embedder, graph=g)
    assert r.topic == "Hetzner homelab"                       # the '# ' never leaks
    assert all("#" not in q for q in r.questions)             # nor into any prompt
    # deeper markers strip too
    assert think_mod.think(idx, "###  Hetzner", embedder=fake_embedder, graph=g).topic == "Hetzner"
    idx.close()


def test_think_topic_normalization_is_idempotent_and_keeps_inline_hash(make_corpus, fake_embedder):
    repo, idx, g = _built(make_corpus, fake_embedder)
    # a clean topic is unchanged (preserves the CLI-shape / round-trip contract)
    assert think_mod.think(idx, "Hetzner", embedder=fake_embedder, graph=g).topic == "Hetzner"
    # only a LEADING heading marker is stripped; an inline #tag survives
    assert think_mod.think(idx, "see #homelab", embedder=fake_embedder,
                           graph=g).topic == "see #homelab"
    idx.close()


# --- U44: note-title resolution (H1-level, not the chunk section heading) -----

def test_think_title_is_h1_not_section_heading(make_corpus, fake_embedder):
    # A structural note that opens with an H2 (no H1) must NOT surface its section
    # label ("Now") as its identity — it falls through to the de-kebabbed stem.
    repo = make_corpus({
        "backlog.md": "## Now\n\nGRDN urban project working set.\n",   # H2-first, no H1
        "seed.md": "# Seed note\n\nGRDN other material.\n",            # real H1
    })
    idx = index_mod.build_index(repo, fake_embedder)
    g = graph_mod.Graph.from_index(idx)
    r = think_mod.think(idx, "GRDN urban", embedder=fake_embedder, graph=g, repo=repo)
    titles = {h["path"]: h["title"] for h in r.related}
    assert titles.get("backlog.md") == "backlog"        # stem fallback, NOT "Now"
    assert titles.get("seed.md") == "Seed note"         # real level-1 H1
    assert all(h["title"] for h in r.related)           # every related entry has a title
    idx.close()


def test_think_title_stem_fallback_strips_leading_date(make_corpus, fake_embedder):
    repo = make_corpus({"2026-06-03-foo-bar.md": "## Section\n\nZQX content only.\n"})  # no H1
    idx = index_mod.build_index(repo, fake_embedder)
    g = graph_mod.Graph.from_index(idx)
    r = think_mod.think(idx, "ZQX content", embedder=fake_embedder, graph=g, repo=repo)
    titles = {h["path"]: h["title"] for h in r.related}
    assert titles.get("2026-06-03-foo-bar.md") == "foo bar"   # date stripped, de-kebabbed
    idx.close()


# --- KTD7: structurally incapable of writing ----------------------------------

def test_think_module_has_no_write_surface():
    # scan the IMPORT surface only — the docstring legitimately names the modules
    # it deliberately does not import.
    src = inspect.getsource(think_mod)
    imports = "\n".join(ln for ln in src.splitlines()
                        if ln.strip().startswith(("import ", "from ")))
    assert "commit_note" not in imports
    assert "propose" not in imports


# --- graceful degradation -----------------------------------------------------

def test_think_no_match_degrades_gracefully(make_corpus, fake_embedder):
    # lexical-only (no embedder) + a term absent from the corpus → genuinely empty
    repo, idx, g = _built(make_corpus, fake_embedder)
    r = think_mod.think(idx, "zzzqxnonexistentterm", embedder=None, graph=g)
    assert r.wrote is False
    assert r.related == []
    assert "nothing" in r.note.lower()
    idx.close()


def test_think_as_dict_round_trips():
    r = think_mod.ThinkResult(topic="t", wrote=False, related=[], context=[],
                              questions=["q?"], tensions=[], degraded=False, note="")
    d = r.as_dict()
    assert d["wrote"] is False and d["topic"] == "t" and d["questions"] == ["q?"]
    json.dumps(d)                                        # must be JSON-serialisable


# --- the MCP think tool is read-only, beside search/build_context -------------

def test_think_mcp_tool_is_read_only_and_no_write_tool(make_corpus, fake_embedder):
    repo, idx, g = _built(make_corpus, fake_embedder)
    db = index_mod.state_dir_for(repo) / "index.db"
    idx.close()
    srv = mcp_server.build_server(db, host=TAILNET_IP, embedder=fake_embedder)
    tools = asyncio.run(srv.list_tools())
    names = {t.name for t in tools}
    assert "think" in names
    assert names <= {"search", "build_context", "think"}
    assert not any(kw in n for t in tools for n in [t.name]
                   for kw in ("write", "commit", "delete", "put", "update", "create"))
    for t in tools:
        assert t.annotations is not None and t.annotations.readOnlyHint is True


# --- CLI think mirrors the tool shape -----------------------------------------

def test_cli_think_matches_tool_shape(make_corpus, fake_embedder, capsys):
    from hypermnesic import cli

    repo, idx, g = _built(make_corpus, fake_embedder)
    idx.close()
    rc = cli.main(["think", str(repo), "Hetzner", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["wrote"] is False
    assert out["topic"] == "Hetzner"
    assert any(h["path"] == "hetzner.md" for h in out["related"])
