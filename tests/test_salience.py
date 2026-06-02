"""U21 — salience scoring + spaced-review digest. [R6/H4/F3/KTD2]

Salience = write-recency (audit log — NO read/access signal exists) + link-degree
+ embedding centrality (the new stored-vector index method). The digest is a
GENERATED note proposed via U18; source notes are NEVER mutated (KTD2).
"""

from __future__ import annotations

import subprocess

from hypermnesic import audit_log as al
from hypermnesic import commit_note as cn
from hypermnesic import config, generated, salience
from hypermnesic import embed as embed_mod
from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod


class _DownEmbedder:
    dim = config.EMBED_DIM

    def embed(self, texts):
        raise embed_mod.EmbeddingError("API down")


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


# --- U30: salience forces full convergence before reading note_vectors --------

def test_salience_fully_embeds_before_scoring(make_corpus, fake_embedder, tmp_path):
    # FR-R39: a stale (unembedded) note must be embedded before centrality is
    # computed — otherwise note_vectors() silently omits it.
    repo, idx, g, log = _env(make_corpus, fake_embedder, tmp_path)
    cn.commit_note(repo, "notes/fresh.md", body="# Fresh\n\nfresh unembedded note.\n",
                   idx=idx, log=log)
    assert idx.stale_chunk_ids()                              # lexical-ahead gap exists
    assert "notes/fresh.md" not in idx.note_vectors()         # not embedded yet
    report = salience.score_notes(idx, g, log, embedder=fake_embedder, repo=repo)
    assert report.coverage_complete is True
    assert not idx.stale_chunk_ids()                          # fully embedded now
    assert set(idx.note_vectors()) == set(idx.all_paths())    # every path has a vector
    assert any(s.path == "notes/fresh.md" for s in report.scores)
    idx.close()


def test_salience_partial_coverage_when_embedder_unavailable(make_corpus, fake_embedder, tmp_path):
    # FR-R40: embedder down mid-fill → result flagged coverage_complete: false (still scores).
    repo, idx, g, log = _env(make_corpus, fake_embedder, tmp_path)
    cn.commit_note(repo, "notes/fresh.md", body="# Fresh\n\nfresh unembedded note.\n",
                   idx=idx, log=log)
    assert idx.stale_chunk_ids()
    report = salience.score_notes(idx, g, log, embedder=_DownEmbedder(), repo=repo)
    assert report.coverage_complete is False                  # could not fully embed
    assert report.scores                                      # partial result still produced
    idx.close()


def test_salience_report_is_iterable_and_carries_coverage(make_corpus, fake_embedder, tmp_path):
    repo, idx, g, log = _env(make_corpus, fake_embedder, tmp_path)   # built fully embedded
    report = salience.score_notes(idx, g, log)                # no embedder → already complete
    assert report.coverage_complete is True                   # nothing stale → complete
    assert len(report) == len(list(report)) == len(report.scores)
    assert report[0] is report.scores[0]                      # indexable like the list it wraps
    idx.close()


def test_digest_proposal_forces_full_coverage(make_corpus, fake_embedder, tmp_path):
    # Review #2: digest_proposal must thread embedder/repo into score_notes so the
    # spaced-review digest's centrality is computed over a fully-embedded corpus.
    repo, idx, g, log = _env(make_corpus, fake_embedder, tmp_path)
    cn.commit_note(repo, "notes/fresh.md", body="# Fresh\n\nfresh unembedded note.\n",
                   idx=idx, log=log)
    assert idx.stale_chunk_ids()                              # lexical-ahead gap exists
    salience.digest_proposal(repo, idx, g, log, embedder=fake_embedder, top_n=5,
                             gh_create=None, now="2026-06-02T00:00:00+00:00")
    assert not idx.stale_chunk_ids()                          # digest forced a full embed first
    idx.close()
