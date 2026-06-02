"""U21 — salience scoring + spaced-review digest. [R6/H4/F3/KTD2]

Salience = write-recency (audit log — NO read/access signal exists) + link-degree
+ embedding centrality (the new stored-vector index method). The digest is a
GENERATED note proposed via U18; source notes are NEVER mutated (KTD2).
"""

from __future__ import annotations

import subprocess

from hypermnesic import audit_log as al
from hypermnesic import generated, salience
from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


_HUB = "# Hub\n\nCentral note linking [[a]], [[b]], [[c]].\n"
_A = "# a\n\nalpha, see [[Hub]].\n"
_B = "# b\n\nbeta, see [[Hub]].\n"
_C = "# c\n\ngamma, see [[Hub]].\n"
_ORPHAN = "# Orphan\n\nan isolated stale note about nothing in particular.\n"


def _env(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"hub.md": _HUB, "a.md": _A, "b.md": _B, "c.md": _C,
                        "orphan.md": _ORPHAN})
    idx = index_mod.build_index(repo, fake_embedder)
    g = graph_mod.Graph.from_index(idx)
    log = al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test")
    # write-recency signal: hub written recently, orphan long ago
    log.append("create", "orphan.md", None, "0" * 40, "old", ts="2026-01-01T00:00:00+00:00")
    log.append("create", "hub.md", None, "1" * 40, "recent", ts="2026-06-01T00:00:00+00:00")
    return repo, idx, g, log


# --- deterministic scoring ----------------------------------------------------

def test_scoring_is_deterministic_and_ranks_linked_recent_above_orphan(
        make_corpus, fake_embedder, tmp_path):
    repo, idx, g, log = _env(make_corpus, fake_embedder, tmp_path)
    s1 = salience.score_notes(idx, g, log)
    s2 = salience.score_notes(idx, g, log)
    assert [(s.path, s.score) for s in s1] == [(s.path, s.score) for s in s2]  # deterministic
    by_path = {s.path: s for s in s1}
    assert by_path["hub.md"].score > by_path["orphan.md"].score
    assert by_path["hub.md"].link_degree >= 3
    idx.close()


# --- H4: digest is a U18 proposal, lists dormant-salient notes ----------------

def test_digest_proposal_lists_notes_and_is_u18_proposal(make_corpus, fake_embedder, tmp_path):
    repo, idx, g, log = _env(make_corpus, fake_embedder, tmp_path)
    head_before = _git(repo, "rev-parse", "HEAD")
    res = salience.digest_proposal(repo, idx, g, log, top_n=5, gh_create=None,
                                   now="2026-06-02T00:00:00+00:00")
    assert res.branch is not None and res.branch.startswith("hypermnesic/proposals/")
    assert _git(repo, "rev-parse", "HEAD") == head_before          # not committed to main
    digest = _git(repo, "show", f"{res.branch}:{res.files[0]}")
    assert res.files[0].startswith("dashboards/")                  # NOT guard-protected views/
    # the recently-written hub is NOT dormant; linked-but-dormant notes are surfaced,
    # and rank above the orphan (link_degree 0)
    assert "[[a.md]]" in digest
    assert digest.index("[[a.md]]") < digest.index("[[orphan.md]]")
    idx.close()


def test_digest_carries_generated_marker_and_frontmatter(make_corpus, fake_embedder, tmp_path):
    repo, idx, g, log = _env(make_corpus, fake_embedder, tmp_path)
    res = salience.digest_proposal(repo, idx, g, log, top_n=5, gh_create=None,
                                   now="2026-06-02T00:00:00+00:00")
    digest = _git(repo, "show", f"{res.branch}:{res.files[0]}")
    assert "generated_by: hypermnesic" in digest
    assert generated.MANAGED_BEGIN in digest                       # visible managed-block marker
    idx.close()


# --- KTD2: source notes are never mutated -------------------------------------

def test_digest_does_not_mutate_source_notes(make_corpus, fake_embedder, tmp_path):
    repo, idx, g, log = _env(make_corpus, fake_embedder, tmp_path)
    before = {p: (repo / p).read_bytes() for p in
              ["hub.md", "a.md", "b.md", "c.md", "orphan.md"]}
    salience.digest_proposal(repo, idx, g, log, top_n=5, gh_create=None,
                             now="2026-06-02T00:00:00+00:00")
    after = {p: (repo / p).read_bytes() for p in before}
    assert after == before                                         # byte-identical
    idx.close()


# --- graceful: empty/small vault ----------------------------------------------

def test_empty_scores_digest_says_nothing_dormant():
    note = salience.build_digest_note([], now="2026-06-02T00:00:00+00:00")
    assert "nothing dormant" in note.lower()
    assert "generated_by: hypermnesic" in note
