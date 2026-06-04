"""Sprint 007 — daily workflow review surface.

The review surface composes existing primitives; it must not mutate source notes or create a
parallel cleanup implementation.
"""

from __future__ import annotations

import json
import subprocess

from hypermnesic import audit_log as al
from hypermnesic import capture, daily_review
from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


def _build(repo, fake_embedder):
    idx = index_mod.build_index(repo, fake_embedder)
    g = graph_mod.Graph.from_index(idx)
    return idx, g


def test_build_daily_review_composes_backlog_recent_writes_and_cleanup(
        make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"projects/atlas.md": "# Atlas\n\nDurable project fact.\n"})
    idx, g = _build(repo, fake_embedder)
    cap = capture.capture(repo, "raw source to triage", idx=idx, now="20260604T000000")
    log = al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test")
    log.append("create", "projects/atlas.md", None, "1" * 40, "decision captured",
               ts="2026-06-04T00:00:00+00:00")

    note = daily_review.build_daily_review(
        repo,
        capture_backlog=capture.backlog(repo),
        audit_log=log,
        generated_surfaces={
            "navigation": "dashboards/MOC.md",
            "salience": "dashboards/salience-digest.md",
            "connections": "dashboards/connections.md",
        },
        degraded=["lexical-only: dense embeddings unavailable"],
        now="2026-06-04T00:00:00+00:00",
    )

    assert "generated_by: hypermnesic" in note
    assert "Capture backlog" in note
    assert cap.files[0] in note
    assert "projects/atlas.md" in note
    assert "dashboards/MOC.md" in note and "dashboards/salience-digest.md" in note
    assert "hypermnesic memory forget" in note
    assert "hypermnesic memory revert" in note
    assert "hypermnesic memory export" in note
    assert "lexical-only" in note
    idx.close()


def test_daily_review_proposal_is_review_gated_and_does_not_mutate_sources(
        make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"projects/atlas.md": "# Atlas\n\nDurable project fact.\n"})
    idx, g = _build(repo, fake_embedder)
    cap = capture.capture(repo, "raw source to triage", idx=idx, now="20260604T000000")
    captured_rel = cap.files[0]
    before = {p: (repo / p).read_bytes() for p in ["projects/atlas.md", captured_rel]}
    log = al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test")

    res = daily_review.review_proposal(repo, idx, g, audit_log=log, gh_create=None,
                                       now="2026-06-04T00:00:00+00:00")

    assert res.branch and res.branch.startswith("hypermnesic/proposals/")
    assert res.files == [daily_review.DAILY_REVIEW_REL]
    assert {p: (repo / p).read_bytes() for p in before} == before
    review = _git(repo, "show", f"{res.branch}:{daily_review.DAILY_REVIEW_REL}")
    assert "Clean up" in review
    idx.close()


def test_daily_review_empty_state_and_cli_json(make_corpus, fake_embedder, capsys):
    from hypermnesic import cli

    repo = make_corpus({"projects/atlas.md": "# Atlas\n\nDurable project fact.\n"})
    index_mod.build_index(repo, fake_embedder).close()

    rc = cli.main(["daily-review", str(repo), "--json"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["files"] == [daily_review.DAILY_REVIEW_REL]
    assert out["generated"] is True
    assert out["cleanup_actions"] == ["inspect", "export", "forget", "revert", "audit"]
