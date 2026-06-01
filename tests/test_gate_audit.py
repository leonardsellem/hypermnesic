"""Read-only gate + guard audit harness (offline)."""

from __future__ import annotations

import gate_audit


def test_gate_compat_buckets_clean_abort_and_no_fm(make_corpus):
    repo = make_corpus({
        "clean.md": "---\ntitle: Clean\nstatus: active\ncreated: 2026-05-02\n---\n# C\n\nbody.\n",
        "reflow.md": "---\ntitle: R\nstatus:    active\n---\n# R\n\nbody.\n",  # extra spaces
        "plain.md": "# No frontmatter\n\njust body.\n",
    })
    rep = gate_audit.gate_compat(repo)
    assert rep["clean"] >= 1 and rep["abort"] >= 1 and rep["no_frontmatter"] == 1
    assert any(a["path"] == "reflow.md" for a in rep["sample_aborts"])
    assert 0.0 < rep["abort_rate"] <= 1.0


def test_guard_audit_flags_governance_not_notes(make_corpus):
    repo = make_corpus({
        "notes/idea.md": "# Idea\n\nbody.\n",
        "people/jane.md": "# Jane\n\nbody.\n",
    })
    rep = gate_audit.guard_audit(repo)
    assert rep["governance_classification"]["CLAUDE.md"].startswith("refused")
    assert rep["governance_classification"][".github/workflows/ci.yml"].startswith("refused")
    assert rep["protected_note_count"] == 0          # ordinary notes are writable
