"""U24 — frictionless capture → deferred thinking-triage. [R6/H6/F5]

Two steps split in time: capture lands raw in ``sources/`` via U18's immutable
free-append fast path (zero friction, no PR in the moment); a later triage reuses
U20's read-only ``think`` to PROPOSE a placement + connections + a grapple prompt
via U18 — and never auto-moves the captured note.
"""

from __future__ import annotations

import subprocess

from hypermnesic import capture
from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


def _branches(repo):
    return _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()


# --- H6: capture is immediate, free-append, no proposal -----------------------

def test_capture_lands_raw_in_sources_immediately(make_corpus, fake_embedder):
    repo = make_corpus({"topics/widgets.md": "# Widgets\n\nwidgets gadgets and more.\n"})
    idx = index_mod.build_index(repo, fake_embedder)
    res = capture.capture(repo, "widgets gadgets — a raw thought", idx=idx,
                          now="20260602T000000")
    assert res.fast_path is True and res.branch is None             # free-append, no PR
    assert len(res.files) == 1 and res.files[0].startswith("sources/")
    assert (repo / res.files[0]).exists()                           # landed immediately
    assert not [b for b in _branches(repo) if b.startswith("hypermnesic/proposals/")]
    # it is committed (not just written) — capture is durable
    assert _git(repo, "ls-files", res.files[0]) == res.files[0]
    idx.close()


# --- triage proposes placement, never auto-moves ------------------------------

def test_triage_proposes_placement_and_connections_without_moving(make_corpus, fake_embedder):
    repo = make_corpus({"topics/widgets.md": "# Widgets\n\nwidgets gadgets and more.\n"})
    idx0 = index_mod.build_index(repo, fake_embedder)
    cap = capture.capture(repo, "widgets gadgets", idx=idx0, now="20260602T000000")
    captured_rel = cap.files[0]
    idx0.close()

    idx = index_mod.build_index(repo, fake_embedder)               # reindex incl. the capture
    g = graph_mod.Graph.from_index(idx)
    head_before = _git(repo, "rev-parse", "HEAD")
    before_bytes = (repo / captured_rel).read_bytes()

    res = capture.triage(repo, idx, g, captured_rel, gh_create=None,
                         now="2026-06-02T00:00:00+00:00")
    assert res.branch is not None and res.branch.startswith("hypermnesic/proposals/")
    assert _git(repo, "rev-parse", "HEAD") == head_before          # not auto-placed on main
    assert (repo / captured_rel).read_bytes() == before_bytes      # not moved/mutated
    note = _git(repo, "show", f"{res.branch}:{res.files[0]}")
    assert res.files[0].startswith("dashboards/")
    assert "placement" in note.lower()
    assert "[[topics/widgets.md]]" in note                         # a found connection
    idx.close()


def test_triage_analysis_is_read_only_then_proposes(make_corpus, fake_embedder):
    repo = make_corpus({"topics/widgets.md": "# Widgets\n\nwidgets gadgets and more.\n"})
    idx0 = index_mod.build_index(repo, fake_embedder)
    cap = capture.capture(repo, "widgets gadgets", idx=idx0, now="20260602T000000")
    captured_rel = cap.files[0]
    idx0.close()

    idx = index_mod.build_index(repo, fake_embedder)
    g = graph_mod.Graph.from_index(idx)
    res = capture.triage(repo, idx, g, captured_rel, gh_create=None,
                         now="2026-06-02T00:00:00+00:00")
    # the only write is the U18 proposal branch; analysis (think) wrote nothing
    assert res.thought_wrote is False
    note = _git(repo, "show", f"{res.branch}:{res.files[0]}")
    assert "grapple" in note.lower()                               # carries a grapple prompt
    idx.close()


def test_cli_capture_is_immediate(make_corpus, fake_embedder, capsys):
    from hypermnesic import cli

    repo = make_corpus({"topics/widgets.md": "# Widgets\n\nwidgets.\n"})
    index_mod.build_index(repo, fake_embedder).close()
    rc = cli.main(["capture", str(repo), "a fleeting idea about widgets", "--json"])
    assert rc == 0
    import json
    out = json.loads(capsys.readouterr().out)
    assert out["fast_path"] is True
    assert out["files"][0].startswith("sources/")
