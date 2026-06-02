"""U22 — connection / serendipity proposals. [R6/H3/F3/AE4/KTD3]

"These two notes grapple with the same idea but aren't linked — connect them?":
computed from dense similarity (stored note vectors) AND no existing body-wikilink
edge. High-precision (threshold + near-duplicate exclusion), bounded/batched, and
**never auto-links** — only a review-gated U18 proposal.
"""

from __future__ import annotations

import subprocess

from hypermnesic import connect
from hypermnesic import graph as graph_mod


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


# crafted vectors: a~b high cosine (~0.96), c orthogonal to a
_VEC = {
    "a.md": [1.0, 0.0, 0.0],
    "b.md": [0.96, 0.28, 0.0],
    "c.md": [0.0, 0.0, 1.0],
}


def _graph(pages):
    return graph_mod.Graph.from_pages(pages)


# --- H3: similar-and-unlinked → one proposal; already-linked → none -----------

def test_similar_unlinked_pair_is_a_candidate():
    g = _graph({"a.md": "alpha", "b.md": "beta", "c.md": "gamma"})  # no links
    pairs = connect.candidate_pairs(_VEC, g, threshold=0.8)
    assert [(p[0], p[1]) for p in pairs] == [("a.md", "b.md")]      # only the similar pair


def test_already_linked_pair_is_excluded():
    g = _graph({"a.md": "alpha [[b]]", "b.md": "beta", "c.md": "gamma"})  # a→b edge
    pairs = connect.candidate_pairs(_VEC, g, threshold=0.8)
    assert pairs == []                                             # linked → no suggestion


def test_low_similarity_pairs_excluded():
    g = _graph({"a.md": "alpha", "c.md": "gamma"})
    pairs = connect.candidate_pairs({"a.md": _VEC["a.md"], "c.md": _VEC["c.md"]},
                                    g, threshold=0.8)
    assert pairs == []                                             # orthogonal → none


def test_near_duplicates_excluded():
    g = _graph({"a.md": "alpha", "dup.md": "alpha2"})
    pairs = connect.candidate_pairs({"a.md": [1.0, 0.0], "dup.md": [1.0, 0.0]},
                                    g, threshold=0.8, near_dup=0.999)
    assert pairs == []                                             # boilerplate/dupe → none


# --- proposal is via U18, bounded, and never writes an edge -------------------

def test_connection_proposal_is_u18_and_does_not_mutate_graph(make_corpus):
    repo = make_corpus({"a.md": "# a\n\nalpha\n", "b.md": "# b\n\nbeta\n",
                        "c.md": "# c\n\ngamma\n"})
    g = _graph({"a.md": "alpha", "b.md": "beta", "c.md": "gamma"})
    edges_before = {n: set(g.neighbors(n)) for n in g.nodes}
    head_before = _git(repo, "rev-parse", "HEAD")

    res = connect.connection_proposals(repo, graph=g, vectors=_VEC, threshold=0.8,
                                       gh_create=None, now="2026-06-02T00:00:00+00:00")
    assert res is not None and res.branch.startswith("hypermnesic/proposals/")
    assert _git(repo, "rev-parse", "HEAD") == head_before          # not committed to main
    # no edge was written directly — the graph is unchanged, only a proposal exists
    assert {n: set(g.neighbors(n)) for n in g.nodes} == edges_before
    suggestion = _git(repo, "show", f"{res.branch}:{res.files[0]}")
    assert res.files[0].startswith("dashboards/")
    assert "[[a.md]]" in suggestion and "[[b.md]]" in suggestion


def test_no_candidates_means_no_proposal(make_corpus):
    repo = make_corpus({"a.md": "# a\n\nalpha\n", "c.md": "# c\n\ngamma\n"})
    g = _graph({"a.md": "alpha", "c.md": "gamma"})
    res = connect.connection_proposals(
        repo, graph=g, vectors={"a.md": _VEC["a.md"], "c.md": _VEC["c.md"]},
        threshold=0.8, gh_create=None)
    assert res is None                                             # nothing to suggest


def test_suggestions_are_bounded_by_cap(make_corpus):
    # four mutually-similar notes → many candidate pairs → capped
    vecs = {"a.md": [1.0, 0.0, 0.0], "b.md": [0.97, 0.24, 0.0],
            "c.md": [0.97, 0.0, 0.24], "d.md": [0.95, 0.22, 0.22]}
    g = _graph({k: k for k in vecs})                              # no links among them
    pairs = connect.candidate_pairs(vecs, g, threshold=0.8, cap=2)
    assert len(pairs) == 2                                         # bounded
