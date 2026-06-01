---
title: "feat: gate surgical scalar-set (cut the list-reflow abort rate)"
type: feat
status: completed
created: 2026-06-01
origin:
  - "docs/plans/2026-06-01-003-feat-phase01-followups-plan.md"
  - "harness/gate_audit.py (real-vault audit: 11.1% abort)"
tags: [hypermnesic, plan, frontmatter-gate, kernel]
---

# feat: gate surgical scalar-set (cut the list-reflow abort rate)

**Target repo:** `hypermnesic`. Builds on U8 (the diff-or-die gate). Lightweight.

## Problem Frame

The real-vault audit (`harness/gate_audit.py`) found an **11.1% gate-abort rate**:
setting one top-level scalar field aborts because ruamel, on dump, reflows an
*untouched* block-list field (`tags`, `aliases`, `snapshot_tags`,
`evidence_sources`) whose original indentation differs from the gate's single
pinned `indent(sequence=4, offset=2)` style. The gate aborts safely (no churn),
but ~1 in 9 field-edits is blocked — real friction. A single global indent config
cannot byte-match every doc's list style.

## Key Technical Decision

**KTD. Don't reserialize untouched keys — edit surgically.** For the common case
(set an existing top-level **inline scalar** field to a scalar value), replace
only that key's value on its own line and leave every other byte of the
frontmatter identical. Untouched list fields are then literally not re-emitted, so
they cannot reflow → no collateral abort. Fall back to the existing ruamel
round-trip path only for structural edits ruamel must handle (adding a key,
deleting a key, changing a list/block value, a key with a multi-line value, or a
value-bearing trailing comment). The `assert_only_changed` guard still runs on the
result, so diff-or-die safety is unchanged — surgical is a *cleaner path to the
same guarantee*, not a relaxation.

## Implementation Units

### U17. Surgical scalar-set in the frontmatter gate

- **Goal:** Make a scalar field-set change only its own line; cut the abort rate.
- **Requirements:** R9 (byte-preservation), closes the audit's 11% friction.
- **Dependencies:** U8.
- **Files:** `src/hypermnesic/frontmatter_gate.py`, `tests/test_frontmatter_gate.py` (extend).
- **Approach:** Add `_serialize_scalar(key, value)` — dump `{key: value}` via the
  configured ruamel and return the single-line value token, or None if it
  serializes multi-line (block scalar / list) → signals "not surgical". Add
  `_surgical_set(fm_inner, set_fields)` — for each key, locate its **top-level**
  (`^key:`) line with a **non-empty inline value and no trailing `#` comment**;
  replace the value token in place; return the rewritten frontmatter, or None if
  ANY key is not surgically replaceable (absent, multi-line value, commented,
  block). In `gated_edit`, when `set_fields` is present and `delete_fields` is not,
  try `_surgical_set` first; on None, fall back to the current ruamel path. Always
  run `assert_only_changed` on the result (unchanged safety net).
- **Execution note:** test-first — preservation of untouched lines is the spec.
- **Patterns to follow:** existing `_yaml()`, `assert_only_changed`, `gated_edit`.
- **Test scenarios:**
  - A doc with a block-list field (`tags:` then `  - a` at non-standard indent) +
    a scalar `status: active`; `set_fields={status: done}` → returns clean, the
    `tags` block is **byte-identical**, only the `status` line changed (the audit's
    abort case, now clean).
  - `Covers AE7.` `status` change still keeps a scalar `created` byte-identical.
  - Adding a new key (`set_fields={updated: ...}` where `updated` is absent) →
    falls back to ruamel (surgical returns None), behavior unchanged.
  - `delete_fields` → ruamel path (surgical not attempted).
  - A key with a trailing `# comment` → falls back to ruamel (no comment mangling).
  - A scalar set whose value contains YAML-special chars is serialized correctly
    (quoted) and round-trips.
  - The guard still aborts if a surgical edit somehow changed another key
    (defensive — `assert_only_changed` on the surgical result).
- **Verification:** re-run `harness/gate_audit.py` against gbrain-brain (read-only)
  → abort rate drops substantially (target: the list-reflow aborts clear).

## Scope Boundaries

- List/block-value edits and key adds/deletes still route through ruamel and may
  still abort (safe) — surgically rewriting block structures is out of scope.
- No change to the guard, the audit harness, or any write path beyond the gate.

## Verification

`uv run pytest` green; `ruff` clean; a fresh read-only `gate_audit` run shows a
materially lower abort rate with the guard's safety unchanged.
