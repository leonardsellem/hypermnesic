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
    # Adding a key forces the ruamel path; an untouched key whose serialization
    # reflows (extra spaces normalized) → abort with the offending diff. (Scalar
    # SETs now take the surgical path and would NOT reflow — see U17 tests below.)
    doc = "---\nstatus:    active\ncreated: 2026-05-02\n---\nbody\n"
    with pytest.raises(fg.FrontmatterDriftError) as ei:
        fg.gated_edit(doc, set_fields={"newkey": "x"})   # add → ruamel → status reflows
    assert ei.value.diff and "status" in ei.value.diff


def test_no_frontmatter_body_edit():
    doc = "# Title\n\njust body, no frontmatter.\n"
    new = fg.gated_edit(doc, body="# Title\n\nnew body.\n")
    assert new == "# Title\n\nnew body.\n"
    with pytest.raises(ValueError):
        fg.gated_edit(doc, set_fields={"x": 1})   # no frontmatter to edit


# --- U17 surgical scalar-set (cut the list-reflow abort rate) ---

# tags list at offset 0 (`- homelab`) — differs from the gate's offset=2 style,
# so the ruamel path would reflow it and ABORT when setting an unrelated field.
_DOC_NONSTD_LIST = ("---\nstatus: active\ntags:\n- homelab\n- infra\n"
                    "created: 2026-05-02\n---\n# T\n\nbody.\n")


def test_surgical_scalar_set_preserves_nonstandard_list():
    new = fg.gated_edit(_DOC_NONSTD_LIST, set_fields={"status": "done"})
    fm, _ = fg.split_frontmatter(new)
    assert "status: done" in fm
    assert "tags:\n- homelab\n- infra" in fm          # block list byte-identical (no reflow)
    assert "created: 2026-05-02" in fm


def test_add_new_key_falls_back_to_ruamel():
    doc = "---\ntitle: T\nstatus: active\n---\nbody\n"
    new = fg.gated_edit(doc, set_fields={"updated": "2026-06-01"})   # 'updated' absent → add
    fm, _ = fg.split_frontmatter(new)
    assert "updated:" in fm and "title: T" in fm and "status: active" in fm


def test_delete_field_uses_ruamel():
    doc = "---\ntitle: T\nstatus: active\ntemp: x\n---\nbody\n"
    new = fg.gated_edit(doc, delete_fields=["temp"])
    fm, _ = fg.split_frontmatter(new)
    assert "temp:" not in fm and "title: T" in fm and "status: active" in fm


def test_key_with_comment_falls_back_and_preserves_it():
    doc = "---\nstatus: active  # current\ntitle: T\n---\nbody\n"
    new = fg.gated_edit(doc, set_fields={"status": "done"})
    fm, _ = fg.split_frontmatter(new)
    assert "status: done" in fm and "# current" in fm    # ruamel RT preserves the comment


def test_surgical_value_with_special_chars_is_quoted():
    new = fg.gated_edit(_DOC_NONSTD_LIST, set_fields={"status": "done: really"})
    fm, _ = fg.split_frontmatter(new)
    assert "tags:\n- homelab\n- infra" in fm              # untouched
    assert "'done: really'" in fm or '"done: really"' in fm   # value safely quoted


def test_abort_error_carries_diff():
    orig_fm = "a: 1\nb: 2\n"
    drifted = "a: 1\nb: 3\n"
    with pytest.raises(fg.FrontmatterDriftError) as ei:
        fg.assert_only_changed(orig_fm, drifted, allowed=set())
    assert "-b: 2" in ei.value.diff and "+b: 3" in ei.value.diff
