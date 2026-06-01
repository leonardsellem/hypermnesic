---
title: "Surgical scalar-set: edit the line you mean, don't reserialize bytes you didn't touch"
date: 2026-06-01
category: design-patterns
module: frontmatter_gate
problem_type: design_pattern
component: tooling
severity: medium
applies_when:
  - "Editing one field inside a byte-sensitive serialized blob (YAML/TOML/JSON frontmatter) guarded by a diff-or-die equality check"
  - "A full library round-trip (e.g. ruamel.yaml) reflows untouched block-list or nested fields under one pinned style"
  - "A single global indent/style config cannot byte-match every document in a heterogeneous corpus"
  - "The common edit is setting an existing top-level inline scalar to a scalar value"
symptoms:
  - "11.1% gate-abort rate when setting a single top-level scalar field across 2,698 real docs"
  - "Diff-or-die guard correctly aborts on collateral drift in untouched fields (tags, aliases, snapshot_tags, evidence_sources)"
  - "ruamel.yaml dump reflows block-list indentation that differs from the pinned indent(sequence=4, offset=2) style"
root_cause: config_error
resolution_type: code_fix
related_components:
  - commit_note.py
  - gate_audit.py
tags: [frontmatter, yaml, ruamel, byte-preservation, diff-or-die, surgical-edit, round-trip, idempotent-write]
---

# Surgical scalar-set: edit the line you mean, don't reserialize bytes you didn't touch

## Context

`hypermnesic` writes back to an Obsidian-style markdown vault through a single git-native write primitive (`commit_note`), gated by a **byte-preserving "diff-or-die" frontmatter gate** (`src/hypermnesic/frontmatter_gate.py`). The gate's contract: a write may only change the lines it was asked to change, and `assert_only_changed` aborts the whole write if any *unrequested* key drifted. Byte-preservation is the trust foundation that makes review-gated maintenance safe and stops the kind of silent, whole-file frontmatter churn that tools like Basic Memory's `ensure_frontmatter_on_sync` inflict.

A read-only audit (`harness/gate_audit.py::gate_compat`) against the real **2,698-document** vault did a no-op single-scalar field write across every doc and measured an **11.1% abort rate**. More than one in nine documents were un-editable through the gate — not because the edit was wrong, but because the gate's own serializer was contaminating untouched bytes. For a write kernel a live cutover depends on, that's blocking friction.

Root cause: the gate edited frontmatter by a single ruamel.yaml round-trip — `load(fm_inner)` → mutate the mapping → `dump(data)`. ruamel re-serializes the *entire* mapping on dump using one global indent config (`_yaml()` pins `indent(mapping=2, sequence=4, offset=2)`). Any block-list field whose original on-disk indentation differed from that one pinned style (e.g. `tags:` with items at column 0) came back byte-different though its value was unchanged. The guard then *correctly* flagged the collateral drift and aborted. A single global style cannot byte-match every document in a heterogeneous corpus — **the round-trip itself is the contaminator.**

## Guidance

**Surgically edit the line you mean; never reserialize bytes you didn't touch.** When a guarantee is "only these lines change," prefer an in-place line edit over a parse-mutate-reserialize round-trip whose serializer makes *global* formatting decisions about content you never intended to modify.

Concretely, for the dominant case — setting an existing top-level **inline scalar** field to a scalar value — copy the frontmatter line-for-line and rewrite only the target key's value token. Untouched lists are then physically never re-emitted, so they cannot reflow. Keep the full library round-trip strictly as a **fallback** for the structural edits it genuinely must handle (adding a key, deleting a key, list/block values, commented keys, multi-line values). Run the diff-or-die guard on the result of *either* path, unchanged — surgical editing is a cleaner path to the same guarantee, not a relaxation of it.

Two design rules make this safe:

1. **Still serialize the *value* through the library.** Route the scalar value (not the document) through ruamel via a one-key dump, so quoting/escaping of special characters stays correct (`done: really` → `'done: really'`). Only the surrounding document bytes are hand-preserved.
2. **The fallback must remain reachable for every input the fast path declines.** The fast path returns a sentinel (`None`) for anything it can't safely do in place; the dispatch must branch explicitly into the slow path on that sentinel.

## Why This Matters

This eliminates the *cause* rather than masking the symptom. The 11% abort was ruamel re-emitting bytes the caller never asked to touch; the surgical path copies untouched lines verbatim, so a block list is byte-for-byte identical and there is **nothing for the guard to flag**. The guard stays strict — byte-preservation is fully intact — but for the dominant case it now has nothing to reject. Result on the real vault: **abort rate 11.1% → 0.0%** across all 2,698 docs; 147 tests pass; corpus verified untouched.

The two alternatives both fail:

- **Tune the global indent config to match the corpus** — impossible in principle. The vault uses multiple block-list indent styles (offset 0, offset 2, …); one global `indent(...)` matches at most one, and the rest reflow and abort. This is a property of one-global-config serialization, not a tuning gap.
- **Loosen the guard** (ignore whitespace-only or list-reflow diffs) — defeats the entire purpose. It trades a safe abort for silent, unreviewed mutation. Strictly worse.

## When to Apply

- Editing one field inside a byte-sensitive serialized blob (YAML/TOML/JSON frontmatter) guarded by a diff-or-die equality check.
- A full library round-trip reflows untouched block-list or nested fields because it re-serializes the whole structure under one pinned style.
- A single global indent/style config cannot byte-match every document in a heterogeneous corpus.
- The common edit is setting an existing top-level inline scalar to a scalar value — the surgical fast path covers exactly this and hands everything else back to the round-trip.

## Examples

**The fast path declines anything it can't do safely (returns `None` → fall back).** `_serialize_scalar` dumps just `{key: value}` through the configured ruamel and returns the single-line value token, or `None` if it spans more than one line (block scalar / list → "not surgical"):

```python
def _serialize_scalar(key: str, value) -> str | None:
    buf = StringIO()
    _yaml().dump({key: value}, buf)
    lines = buf.getvalue().splitlines()
    if len(lines) != 1:
        return None
    m = re.match(rf"^{re.escape(key)}:\s?(.*)$", lines[0])
    return m.group(1) if m else None
```

`_surgical_set` locates each key's top-level `^key:` line with a non-empty inline value and **no** trailing `#` comment, and replaces only the value token in place — returning `None` (signal: fall back) if *any* requested key isn't surgically replaceable:

```python
def _surgical_set(fm_inner: str, set_fields: dict) -> str | None:
    lines = fm_inner.splitlines(keepends=True)
    out = lines[:]                                   # untouched lines copied verbatim
    for key, val in set_fields.items():
        token = _serialize_scalar(key, val)
        if token is None:
            return None
        keyre = re.compile(rf"^{re.escape(key)}:(.*)$")   # top-level only (col 0)
        idx = None
        for i, line in enumerate(lines):
            m = keyre.match(line.rstrip("\n"))
            if m:
                after = m.group(1)
                if after.strip() == "" or "#" in after:   # block value or comment → not surgical
                    return None
                idx = i
                break
        if idx is None:                              # key absent (an add) → ruamel handles structure
            return None
        nl = "\n" if lines[idx].endswith("\n") else ""
        out[idx] = f"{key}: {token}{nl}"
    return "".join(out)
```

**Dispatch — surgical preferred, ruamel as the explicit fallback (`gated_edit`):**

```python
# BEFORE — every set/delete went through a full mapping round-trip:
#   data = yaml.load(fm_inner)
#   for k, v in (set_fields or {}).items(): data[k] = v
#   yaml.dump(data, buf); new_fm = buf.getvalue()      # reflows untouched lists → abort

# AFTER:
new_fm = fm_inner
if requested:
    surgical = _surgical_set(fm_inner, set_fields) if (set_fields and not delete_fields) else None
    if surgical is not None:
        new_fm = surgical
    else:                                              # add / delete / list / block / comment
        yaml = _yaml()
        data = yaml.load(fm_inner)
        for k, v in (set_fields or {}).items():
            data[k] = v
        for k in (delete_fields or []):
            if k in data:
                del data[k]
        buf = StringIO()
        yaml.dump(data, buf)
        new_fm = buf.getvalue()

assert_only_changed(fm_inner, new_fm, allowed=requested)   # diff-or-die — unchanged safety net
```

**Guardrail learned the hard way — keep the fallback exhaustive.** The first refactor pre-seeded `new_fm = fm_inner` and then *conditionally* ran only the surgical branch. That made **delete-only** edits skip the ruamel branch entirely (surgical doesn't handle deletes, and the slow path was no longer reached) — a silent no-op delete. The fix was to make the fallback explicit: compute `surgical` only when `set_fields and not delete_fields`, then `if surgical is not None: … else: <ruamel>`. **When introducing a fast path, the slow path must remain reachable for every input the fast path declines — assert it with a test per declined category; don't infer it.**

**Tests that lock the behavior in and keep the guard honest** (`tests/test_frontmatter_gate.py`, U17 section):

- `test_surgical_scalar_set_preserves_nonstandard_list` — set `status` on a doc whose `tags:` block list sits at offset 0 (the exact reflow trigger); asserts `tags:\n- homelab\n- infra` stays byte-identical. The regression test for the 11% case.
- `test_surgical_value_with_special_chars_is_quoted` — surgical value still routed through ruamel quoting.
- `test_add_new_key_falls_back_to_ruamel`, `test_delete_field_uses_ruamel`, `test_key_with_comment_falls_back_and_preserves_it` — one per declined category, proving the fallback stays reachable. This trio is what would have caught the delete-only refactor bug.
- `test_abort_error_carries_diff` and the add-on-reflow-prone-doc case — the guard still aborts and surfaces the offending diff when the ruamel path genuinely reflows an untouched key.

**Test relocation, not weakening:** three pre-existing tests asserted that scalar-sets *abort*. Surgical correctly makes those clean now, so rather than delete them they were re-pointed at the ruamel path (an *add* on a reflow-prone doc, or a commented key) to keep exercising the guard's abort + no-partial-effect contract. When a fix legitimately changes an outcome a test pinned, move the test to still cover the invariant — don't flip the assertion or drop it.

## Related

- Plan: `docs/plans/2026-06-01-004-feat-gate-surgical-scalar-set-plan.md` (the U17 work this documents).
- Sibling: `docs/threat-model-commit-note.md` — the gate is the write kernel the threat model gates a live cutover on.
- No prior `docs/solutions/` entries (this is the first); no related GitHub issues.
