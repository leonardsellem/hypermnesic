"""U16 — dogfood preview harness: structured, read-only, gate/guard-aware."""

from __future__ import annotations

import subprocess

import dogfood_commit_note as dogfood


def _tracked(repo):
    return subprocess.run(["git", "-C", str(repo), "ls-files", "-s"],
                          capture_output=True, text=True).stdout


def test_preview_is_structured_and_read_only(make_corpus):
    repo = make_corpus({"seed.md": "# Seed\n\nbody.\n"})
    before = _tracked(repo)
    rep = dogfood.preview_inputs(repo, [
        {"path": "notes/new.md", "body": "# N\n\nWORD body.\n", "summary": "add"},
    ])
    assert rep["safe_to_cut_over"] is True
    entry = rep["inputs"][0]
    assert entry["verdict"] == "ok" and entry["planned_verb"] == "create"
    assert entry["diff_lines"] >= 1
    assert _tracked(repo) == before                         # read-only
    assert not (repo / "notes/new.md").exists()             # nothing written


def test_protected_input_reported_refused(make_corpus):
    repo = make_corpus({"a.md": "# A\n\nb.\n"})
    rep = dogfood.preview_inputs(repo, [{"path": "CLAUDE.md", "body": "# x\n"}])
    assert rep["inputs"][0]["verdict"] == "refused"
    assert rep["safe_to_cut_over"] is False


def test_drift_input_reported_gate_abort(make_corpus):
    repo = make_corpus({"doc.md": "---\nstatus:    active\ncreated: 2026-05-02\n---\nbody\n"})
    rep = dogfood.preview_inputs(
        repo, [{"path": "doc.md", "set_fields": {"created": "2026-05-03"}}])
    assert rep["inputs"][0]["verdict"] == "gate-abort" and "diff" in rep["inputs"][0]
    assert rep["safe_to_cut_over"] is False


def test_rollup_safe_when_all_ok(make_corpus):
    repo = make_corpus({"a.md": "# A\n\nb.\n"})
    rep = dogfood.preview_inputs(repo, [
        {"path": "notes/x.md", "body": "# X\n\ny.\n"},
        {"path": "notes/z.md", "body": "# Z\n\nw.\n"},
    ])
    assert rep["safe_to_cut_over"] is True and rep["blocked"] == 0
