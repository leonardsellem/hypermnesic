"""U23 — always-organized navigation surface (generated MOCs/dashboards + Bases).
[R6/H5/F3/AE4/KD7]

Auto-maintained MOC + Obsidian ``.base`` configs that stay correct as content
changes — proposed via U18, never silent. Generated files are demarcated and land
in a NON-protected dir (``dashboards/``, never the guard-protected ``views/``).
Regeneration is idempotent (no change → no proposal) and never overwrites a
hand-authored note.
"""

from __future__ import annotations

import subprocess

from ruamel.yaml import YAML

from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod
from hypermnesic import nav_surface


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


def _branches(repo):
    return _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()


def _build(repo, fake_embedder):
    idx = index_mod.build_index(repo, fake_embedder)
    g = graph_mod.Graph.from_index(idx)
    return idx, g


# --- H5/AE4: regenerates on change, idempotent on no-change -------------------

def test_nav_proposal_reflects_content_and_is_idempotent(make_corpus, fake_embedder):
    repo = make_corpus({"alpha.md": "# Alpha\n\nfirst note.\n",
                        "beta.md": "# Beta\n\nsecond note.\n"})
    idx, g = _build(repo, fake_embedder)
    res1 = nav_surface.nav_proposal(repo, idx, g, gh_create=None,
                                    now="2026-06-02T00:00:00+00:00")
    assert res1.branch and res1.branch.startswith("hypermnesic/proposals/")
    idx.close()

    # same corpus → identical content → idempotent (no new branch)
    idx2, g2 = _build(repo, fake_embedder)
    res2 = nav_surface.nav_proposal(repo, idx2, g2, gh_create=None,
                                    now="2026-06-02T00:00:00+00:00")
    assert res2.noop is True
    assert res2.branch == res1.branch
    idx2.close()


def test_nav_proposal_regenerates_when_a_note_is_added(make_corpus, fake_embedder):
    repo = make_corpus({"alpha.md": "# Alpha\n\nfirst.\n"})
    idx, g = _build(repo, fake_embedder)
    res1 = nav_surface.nav_proposal(repo, idx, g, gh_create=None,
                                    now="2026-06-02T00:00:00+00:00")
    idx.close()

    (repo / "gamma.md").write_text("# Gamma\n\nthird.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add gamma")
    idx2, g2 = _build(repo, fake_embedder)
    res2 = nav_surface.nav_proposal(repo, idx2, g2, gh_create=None,
                                    now="2026-06-02T00:00:00+00:00")
    assert res2.branch != res1.branch                              # new content → new proposal
    moc = _git(repo, "show", f"{res2.branch}:{nav_surface.MOC_REL}")
    assert "gamma.md" in moc                                       # reflects the new note
    idx2.close()


# --- demarcation + U18, never main directly -----------------------------------

def test_generated_files_are_demarcated_and_on_a_branch(make_corpus, fake_embedder):
    repo = make_corpus({"alpha.md": "# Alpha\n\nfirst.\n"})
    idx, g = _build(repo, fake_embedder)
    head_before = _git(repo, "rev-parse", "HEAD")
    res = nav_surface.nav_proposal(repo, idx, g, gh_create=None,
                                   now="2026-06-02T00:00:00+00:00")
    assert _git(repo, "rev-parse", "HEAD") == head_before          # not committed to main
    assert all(f.startswith("dashboards/") for f in res.files)     # never the protected views/
    moc = _git(repo, "show", f"{res.branch}:{nav_surface.MOC_REL}")
    assert "generated_by: hypermnesic" in moc
    idx.close()


def test_generated_base_is_valid_bases_yaml(make_corpus, fake_embedder):
    repo = make_corpus({"alpha.md": "# Alpha\n\nfirst.\n"})
    idx, g = _build(repo, fake_embedder)
    res = nav_surface.nav_proposal(repo, idx, g, gh_create=None,
                                   now="2026-06-02T00:00:00+00:00")
    base_text = _git(repo, "show", f"{res.branch}:{nav_surface.BASE_REL}")
    data = YAML(typ="safe").load(base_text)
    assert "filters" in data
    # filter root is a single all:/any: group (vault convention)
    assert set(data["filters"].keys()) <= {"all", "any"}
    assert len(data["filters"].keys()) == 1
    assert data.get("generated_by") == "hypermnesic"
    idx.close()


def test_nav_moc_can_link_daily_review_surface(make_corpus, fake_embedder):
    repo = make_corpus({"alpha.md": "# Alpha\n\nfirst.\n"})
    idx, g = _build(repo, fake_embedder)
    res = nav_surface.nav_proposal(
        repo, idx, g, gh_create=None, daily_review_rel="dashboards/daily-review.md",
        now="2026-06-04T00:00:00+00:00")
    moc = _git(repo, "show", f"{res.branch}:{nav_surface.MOC_REL}")
    assert "Daily review" in moc
    assert "[[dashboards/daily-review.md]]" in moc
    idx.close()


# --- KD7: hand-authored notes are never overwritten ---------------------------

def test_hand_authored_notes_untouched(make_corpus, fake_embedder):
    repo = make_corpus({"alpha.md": "# Alpha\n\nfirst.\n", "beta.md": "# Beta\n\nsecond.\n"})
    before = {p: (repo / p).read_bytes() for p in ["alpha.md", "beta.md"]}
    idx, g = _build(repo, fake_embedder)
    nav_surface.nav_proposal(repo, idx, g, gh_create=None, now="2026-06-02T00:00:00+00:00")
    after = {p: (repo / p).read_bytes() for p in before}
    assert after == before
    idx.close()
