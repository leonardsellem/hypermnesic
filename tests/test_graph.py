"""U3 — body-wikilink graph + build_context traversal.

Edges come from **body** ``[[wikilinks]]`` only; frontmatter ``related_to:`` /
``belongs_to:`` are NOT edges (matches the corpus and gbrain).
"""

from __future__ import annotations

from hypermnesic import graph

# A links to C in the body, and lists B only in frontmatter (must NOT be an edge).
PAGE_A = """---
title: A
related_to: "[[b]]"
---
# A

See [[c]] for details. Also a dead link [[nonexistent-page]].
"""
PAGE_B = "# B\n\nB body, links to [[a]].\n"
PAGE_C = "# C\n\nC body, links back to [[a]] (cycle).\n"


def test_body_wikilink_creates_edge_frontmatter_does_not(make_corpus):
    repo = make_corpus({"a.md": PAGE_A, "b.md": PAGE_B, "c.md": PAGE_C})
    g = graph.Graph.from_repo(repo)
    out = g.out_edges["a.md"]
    assert "c.md" in out          # body wikilink → edge
    assert "b.md" not in out      # frontmatter related_to → NOT an edge


def test_dead_link_tolerated(make_corpus):
    repo = make_corpus({"a.md": PAGE_A, "b.md": PAGE_B, "c.md": PAGE_C})
    g = graph.Graph.from_repo(repo)
    # the [[nonexistent-page]] target is simply absent — no node, no crash
    assert "nonexistent-page.md" not in g.nodes
    assert all("nonexistent" not in t for t in g.out_edges["a.md"])


def test_build_context_walks_in_and_out_edges(make_corpus):
    repo = make_corpus({"a.md": PAGE_A, "b.md": PAGE_B, "c.md": PAGE_C})
    g = graph.Graph.from_repo(repo)
    ctx = graph.build_context(g, "a.md", depth=1)
    # outgoing a→c and incoming b→a are both reachable at depth 1
    assert "c.md" in ctx
    assert "b.md" in ctx
    assert "a.md" not in ctx  # the start page is not its own context


def test_cyclic_links_terminate_at_depth(make_corpus):
    repo = make_corpus({"a.md": PAGE_A, "b.md": PAGE_B, "c.md": PAGE_C})
    g = graph.Graph.from_repo(repo)
    ctx = graph.build_context(g, "a.md", depth=5)  # a↔c cycle must terminate
    assert set(ctx) <= {"b.md", "c.md"}


# --- U1: public name→page resolution (gbrain `get` role) ---------------------

RESOLVE_PAGES = {
    "infrastructure/hetzner.md": "# Hetzner\n\nThe homelab box on Hetzner.\n",
    "people/léa.md": "# Léa\n\nA non-ascii entity name.\n",
    "notes/dup.md": "# Dup one\n\nfirst duplicate stem.\n",
    "archive/dup.md": "# Dup two\n\nsecond duplicate stem.\n",
}


def test_resolve_exact_path_and_md_suffix(make_corpus):
    g = graph.Graph.from_repo(make_corpus(RESOLVE_PAGES))
    # exact `.md`-stripped path and the `.md`-suffixed form both resolve to the page
    assert g.resolve("infrastructure/hetzner") == "infrastructure/hetzner.md"
    assert g.resolve("infrastructure/hetzner.md") == "infrastructure/hetzner.md"


def test_resolve_unambiguous_stem_case_insensitive(make_corpus):
    g = graph.Graph.from_repo(make_corpus(RESOLVE_PAGES))
    # a bare entity name with one matching stem resolves (the wikilink target)
    assert g.resolve("Hetzner") == "infrastructure/hetzner.md"


def test_resolve_ambiguous_stem_returns_none_never_guesses(make_corpus):
    g = graph.Graph.from_repo(make_corpus(RESOLVE_PAGES))
    # two pages share the 'dup' stem → resolve to None, never a wrong guess
    assert g.resolve("dup") is None


def test_resolve_missing_is_none_not_error(make_corpus):
    g = graph.Graph.from_repo(make_corpus(RESOLVE_PAGES))
    assert g.resolve("nonexistent-entity") is None
    assert g.resolve("") is None


def test_resolve_non_ascii_name(make_corpus):
    g = graph.Graph.from_repo(make_corpus(RESOLVE_PAGES))
    assert g.resolve("Léa") == "people/léa.md"


def test_resolve_strips_wikilink_display_and_anchor(make_corpus):
    g = graph.Graph.from_repo(make_corpus(RESOLVE_PAGES))
    # resolution matches body-wikilink semantics: display alias + anchor are stripped
    assert g.resolve("Hetzner|the box") == "infrastructure/hetzner.md"
    assert g.resolve("infrastructure/hetzner#Notes") == "infrastructure/hetzner.md"
