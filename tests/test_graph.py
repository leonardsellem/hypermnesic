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
