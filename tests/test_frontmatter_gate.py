"""U8 — frontmatter byte-preservation gate ("diff-or-die"). Abort IS the spec."""

from __future__ import annotations

import pytest

from hypermnesic import frontmatter_gate as fg

DOC = (
    "---\n"
    "title: Hetzner migration\n"
    "status: active\n"
    "created: 2026-05-02\n"
    "tags:\n"
    "  - homelab\n"
    "  - infra\n"
    "_organized: true\n"
    "_icon: rocket\n"
    "---\n"
    "# Hetzner migration\n\nThe original body.\n"
)


def test_body_only_edit_preserves_frontmatter_bytes(make_corpus=None):
    # Covers AE1: editing only the body leaves frontmatter byte-identical.
    new = fg.gated_edit(DOC, body="# Hetzner migration\n\nA rewritten body.\n")
    fm_old, _ = fg.split_frontmatter(DOC)
    fm_new, body_new = fg.split_frontmatter(new)
    assert fm_new == fm_old                      # frontmatter byte-identical
    assert "rewritten body" in body_new
    assert "created: 2026-05-02" in fm_new       # scalar date, not ISO


def test_status_change_keeps_scalar_date():
    # Covers AE7: status active->done must NOT reserialize created (scalar) to ISO.
    new = fg.gated_edit(DOC, set_fields={"status": "done"})
    fm_new, _ = fg.split_frontmatter(new)
    assert "status: done" in fm_new
    assert "created: 2026-05-02" in fm_new       # untouched, still scalar
    assert "2026-05-02T" not in fm_new           # no ISO reserialization


def test_tolaria_underscore_props_preserved():
    new = fg.gated_edit(DOC, body="# Hetzner migration\n\nedited.\n")
    fm_new, _ = fg.split_frontmatter(new)
    assert "_organized: true" in fm_new and "_icon: rocket" in fm_new


def test_guard_detects_unrequested_key_change():
    # Covers AE2 (the guard): a change to an un-allowed key is drift.
    orig_fm = "status: active\ncreated: 2026-05-02\n"
    drifted = "status: done\ncreated: 2026-05-02T00:00:00Z\n"  # created ISO-ified (unrequested)
    changed = fg.changed_keys(orig_fm, drifted)
    assert "created" in changed and "status" in changed
    with pytest.raises(fg.FrontmatterDriftError):
        fg.assert_only_changed(orig_fm, drifted, allowed={"status"})


def test_end_to_end_abort_on_reflow():
    # An untouched key whose serialization would reflow (extra spaces normalized)
    # while editing a different field → abort with the offending diff.
    doc = "---\nstatus:    active\ncreated: 2026-05-02\n---\nbody\n"
    with pytest.raises(fg.FrontmatterDriftError) as ei:
        fg.gated_edit(doc, set_fields={"created": "2026-05-03"})
    assert ei.value.diff and "status" in ei.value.diff


def test_no_frontmatter_body_edit():
    doc = "# Title\n\njust body, no frontmatter.\n"
    new = fg.gated_edit(doc, body="# Title\n\nnew body.\n")
    assert new == "# Title\n\nnew body.\n"
    with pytest.raises(ValueError):
        fg.gated_edit(doc, set_fields={"x": 1})   # no frontmatter to edit


def test_abort_error_carries_diff():
    orig_fm = "a: 1\nb: 2\n"
    drifted = "a: 1\nb: 3\n"
    with pytest.raises(fg.FrontmatterDriftError) as ei:
        fg.assert_only_changed(orig_fm, drifted, allowed=set())
    assert "-b: 2" in ei.value.diff and "+b: 3" in ei.value.diff
