---
title: "feat: Surface agent instructions in list_folders"
type: feat
status: active
date: 2026-06-12
origin: docs/brainstorms/2026-06-12-list-folders-agent-instructions-requirements.md
---

# feat: Surface agent instructions in list_folders

## Summary

Extend the existing folder-discovery contract with an optional root-level instruction payload, using
the same additive result shape for MCP and CLI callers. Keep the folder taxonomy and writability
logic unchanged, and thread the new payload through tests and user-facing documentation.

---

## Problem Frame

Agents already use `list_folders` / `hypermnesic list-folders` before choosing where to place
durable notes. The current response orients them to writable folder structure, but not to local
folder rules stored in `AGENTS.md` or compatibility `CLAUDE.md` files (see origin:
`docs/brainstorms/2026-06-12-list-folders-agent-instructions-requirements.md`).

---

## Requirements

- R1. Return root-level `AGENTS.md` content from `list_folders` when it exists.
- R2. Fall back to root-level `CLAUDE.md` content when no `AGENTS.md` exists.
- R3. Return no instruction payload when neither root-level file exists.
- R4. Prefer `AGENTS.md` over `CLAUDE.md` when both exist at the same requested root.
- R5. Do not bundle child-folder instruction files into a parent listing.
- R6. Preserve the existing folder taxonomy behavior: normalized root, clamped depth,
  deterministic ordering, bounded output, writability, protected reason, recursive note count, and
  convergence signal.
- R7. Preserve invalid-root no-leak behavior for traversal and absolute roots.
- R8. Structure the instruction payload so clients can distinguish absence from a found source
  filename with content.
- R9. Update user-facing MCP documentation for the payload and precedence rule.
- R10. Preserve MCP/CLI output-shape parity by updating `hypermnesic list-folders` with the same
  additive payload.

**Origin actors:** A1 Agent client, A2 Vault maintainer.
**Origin acceptance examples:** AE1 `AGENTS.md` at requested root, AE2 `CLAUDE.md` fallback, AE3 no
instruction file, AE4 `AGENTS.md` precedence, AE5 child instructions not bundled, AE6 invalid root
does not leak content.

---

## Scope Boundaries

- Do not aggregate nested instruction files; only the requested root is considered.
- Do not interpret, summarize, rewrite, or validate instruction content.
- Do not change `commit_note`, protected-path rules, write-surface coercion, or folder writability.
- Do not add a separate instruction-discovery tool.
- Do not introduce a new dependency; local path reads are enough for this feature.

---

## Context & Research

### Relevant Code and Patterns

- `src/hypermnesic/mcp_server.py` defines typed MCP output schemas with `TypedDict`, registers
  `list_folders` as a read-only tool, converges before listing, and returns a plain dictionary
  validated against `ListFoldersOutput`.
- `src/hypermnesic/folders.py` owns pure folder taxonomy derivation from indexed markdown paths.
  Preserve this as taxonomy-only logic rather than coupling file-content reads into it.
- `src/hypermnesic/cli.py` implements `hypermnesic list-folders` as the CLI twin of MCP
  `list_folders`, with the same JSON shape and human output.
- `tests/test_mcp_server.py` already covers output schema, read-only registration, convergence,
  nested protected folders, invalid-root no-leak behavior, and bounded payloads.
- `tests/test_cli.py` asserts exact CLI/MCP output-shape parity for `list-folders --json`.
- `docs/reference/mcp-tools.md` and `docs/reference/cli.md` are the primary user-facing contract
  references for MCP and CLI behavior.
- `plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md`,
  `plugin/hermes/skills/hypermnesic-memory/SKILL.md`, and
  `plugin/hermes/flat-skill/hypermnesic-memory/SKILL.md` enumerate `list_folders` /
  `list-folders` as the orientation step before writes.

### Institutional Learnings

- `docs/solutions/design-patterns/surgical-scalar-set-frontmatter-byte-preservation.md` reinforces
  the project habit of keeping changes surgical and preserving untouched behavior. Apply the same
  posture here: add a narrow helper and contract fields without reworking folder derivation.

### External References

- None. Local MCP/CLI contracts and existing typed-schema patterns are sufficient; external
  research would not materially change the approach.

---

## Key Technical Decisions

- Add a structured optional instruction object to `ListFoldersOutput`, rather than adding raw
  top-level content fields. This satisfies absence-vs-found clarity and keeps room for source
  filename plus content without overloading the folder list.
- Keep instruction-file lookup outside `folders.derive_folders`. Folder derivation remains pure and
  index-derived; MCP and CLI entry points can attach root-local file content after root
  normalization succeeds.
- Apply the new payload to both MCP and CLI. The CLI is documented and tested as the same-output
  twin of `list_folders`, so excluding it would create contract drift.
- Treat invalid roots as a no-content path for MCP, matching the existing no-leak behavior.
  The CLI should continue to fail invalid roots before reading instruction files.

---

## Open Questions

### Resolved During Planning

- Should CLI parity be in scope? Yes. Local docs and tests assert `hypermnesic list-folders` has the
  same output shape as MCP `list_folders`, so the additive payload belongs on both surfaces.
- What should the payload shape communicate? A structured optional object carrying the source
  filename and content is the right planning-level shape; exact field names are implementation
  detail, but tests should prove absence and source identity are distinguishable.

### Deferred to Implementation

- Exact helper and field names: choose names that read naturally beside the existing typed-output
  schema and JSON style.
- Human CLI rendering details: keep it readable and non-disruptive, but final formatting can follow
  what looks clearest once implemented.

---

## Implementation Units

### U1. Add instruction payload tests for MCP list_folders

**Goal:** Lock the new MCP behavior with failing tests before production changes.

**Requirements:** R1, R2, R3, R4, R5, R7, R8.

**Dependencies:** None.

**Files:**
- Modify: `tests/test_mcp_server.py`

**Approach:**
- Add targeted tests around the existing `list_folders` helper path.
- Use fixture repos containing markdown files plus root-level `AGENTS.md` / `CLAUDE.md` files at
  the vault root and nested requested roots.
- Assert the folder list still exists while the optional instruction payload reflects root-local
  precedence.
- Keep invalid-root coverage explicit: a traversal or absolute root must not return instruction
  content from outside the vault.

**Execution note:** Start with these failing MCP contract tests before adding production behavior.

**Patterns to follow:**
- Existing `_call` and `_folders_by_path` helpers in `tests/test_mcp_server.py`.
- Existing invalid-root no-leak test in `tests/test_mcp_server.py`.

**Test scenarios:**
- Covers AE1. Happy path: root has `AGENTS.md`; calling `list_folders` for that root returns the
  usual folder entries and an instruction payload sourced from `AGENTS.md`.
- Covers AE2. Happy path: root has `CLAUDE.md` but no `AGENTS.md`; response payload is sourced from
  `CLAUDE.md`.
- Covers AE3. Empty state: root has neither instruction file; response has no active instruction
  payload while folder entries remain present.
- Covers AE4. Precedence: root has both files; response uses `AGENTS.md`.
- Covers AE5. Scope boundary: only a child folder has `AGENTS.md`; parent-root listing does not
  include the child file.
- Covers AE6. Error path: traversal or absolute root returns no folder entries and no instruction
  content outside the vault.

**Verification:**
- MCP tests fail before implementation and pass after the output payload is implemented.
- Existing list-folder taxonomy tests continue to pass unchanged except for additive shape
  assertions.

---

### U2. Attach root-local instruction metadata in MCP and CLI outputs

**Goal:** Implement the additive payload once and use it from both public list-folder surfaces.

**Requirements:** R1, R2, R3, R4, R5, R6, R7, R8, R10.

**Dependencies:** U1.

**Files:**
- Modify: `src/hypermnesic/mcp_server.py`
- Modify: `src/hypermnesic/cli.py`
- Modify: `tests/test_cli.py`

**Approach:**
- Add a small structured type for instruction metadata in the MCP output schema.
- Normalize the requested root through existing folder-root handling before looking for files, then
  resolve candidates relative to the server's repo path. `build_server` already derives a repo from
  a normal `<repo>/.hypermnesic/index.db` path when one is not passed explicitly.
- Resolve the root-local instruction candidates by precedence: `AGENTS.md`, then `CLAUDE.md`.
- Read only direct files under the normalized root, never descendants.
- On MCP invalid-root handling, return the same empty leak-free listing and omit instruction
  content.
- Reuse the same helper or helper-equivalent behavior from the CLI so JSON parity remains exact.
- Update CLI JSON parity expectations to include the additive payload, and add CLI-specific tests
  for at least one found payload and one absent payload.

**Execution note:** Implement MCP and CLI behavior test-first; keep folder derivation untouched
unless a test proves a shared helper belongs there.

**Patterns to follow:**
- `ListFoldersOutput` and `FolderEntry` in `src/hypermnesic/mcp_server.py`.
- `_cmd_list_folders` in `src/hypermnesic/cli.py`, especially the existing composition of
  `listing` plus `manual_reindex_recommended`.
- Existing exact-shape parity test in `tests/test_cli.py`.

**Test scenarios:**
- Integration: CLI `--json` output includes the same top-level keys as the MCP list-folder output,
  including the new instruction payload field.
- Happy path: CLI call at a root with `AGENTS.md` includes source filename and content in JSON.
- Empty state: CLI call at a root without instruction files has the documented absent-payload
  representation.
- Regression: CLI human output remains nonempty and still lists folders when an instruction file is
  present.

**Verification:**
- MCP output schema advertises the new structured instruction field.
- MCP and CLI JSON shapes remain aligned.
- Existing writability, truncation, and convergence behavior is unchanged.

---

### U3. Update user-facing references and plugin guidance

**Goal:** Keep documentation and agent-facing instructions aligned with the changed public contract.

**Requirements:** R6, R8, R9, R10.

**Dependencies:** U2.

**Files:**
- Modify: `docs/reference/mcp-tools.md`
- Modify: `docs/reference/cli.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md`
- Modify: `plugin/hermes/skills/hypermnesic-memory/SKILL.md`
- Modify: `plugin/hermes/flat-skill/hypermnesic-memory/SKILL.md`
- Modify: `tests/test_plugin.py`
- Modify: `tests/test_hermes_plugin.py`

**Approach:**
- Update the MCP tool reference return shape and prose to describe root-local instruction lookup,
  precedence, and absence behavior.
- Update CLI reference prose because CLI parity is in scope.
- Update README mention of folder discovery only if the additional orientation behavior is useful
  at the high-level workflow description.
- Add an `[Unreleased]` changelog entry for the user-visible contract change.
- Update plugin and Hermes skill text so agents know `list_folders` / `list-folders` can also
  return local instruction guidance before writes.
- Strengthen existing plugin/Hermes tests only enough to assert the new guidance appears; avoid
  brittle wording checks.

**Execution note:** Documentation changes are part of this feature, not a follow-up.

**Patterns to follow:**
- Existing `list_folders` sections in `docs/reference/mcp-tools.md` and `docs/reference/cli.md`.
- Existing memory-taxonomy assertions in `tests/test_plugin.py` and `tests/test_hermes_plugin.py`.

**Test scenarios:**
- Documentation assertion: plugin skill text still mentions `list_folders` and now mentions local
  instruction guidance or `AGENTS.md`.
- Documentation assertion: Hermes skill text still mentions `list-folders` and now mentions local
  instruction guidance or `AGENTS.md`.

**Verification:**
- User-facing docs no longer describe the old return shape as complete.
- Agent-facing plugin guidance reflects the new orientation behavior.

---

## System-Wide Impact

- **Interaction graph:** The feature sits on the read-only discovery path. MCP and CLI callers get
  an additive payload; write paths are not invoked or changed.
- **Error propagation:** MCP keeps invalid roots leak-free by returning an empty listing without
  instruction content. CLI keeps its existing invalid-root failure behavior.
- **State lifecycle risks:** None. Instruction files are read from the working tree / repo path at
  request time; no index mutation or write occurs.
- **API surface parity:** MCP `list_folders` and CLI `list-folders --json` must stay aligned because
  docs and tests describe them as twins.
- **Integration coverage:** Contract tests should cover MCP schema, MCP behavior, CLI JSON parity,
  and docs/plugin guidance.
- **Unchanged invariants:** Folder derivation remains index-based; writability still comes from the
  write guard; `commit_note` remains the only sanctioned write path.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Payload grows unexpectedly for large trees | Read only one direct file at the requested root; never aggregate descendants. |
| Invalid roots leak host files | Reuse existing root normalization before any instruction-file read and assert no-content invalid-root behavior. |
| CLI/MCP contract drift | Implement or share one payload helper and update exact-shape parity tests. |
| Existing clients break on output shape change | Make the change additive and keep existing folder fields unchanged. |
| Documentation drift | Update MCP, CLI, README/changelog, and plugin/Hermes guidance in the same change. |

---

## Documentation / Operational Notes

- This is a local read-surface contract change. No deployment migration, data migration, or runtime
  operator action is expected.
- Full completion still requires the repo gate set from `AGENTS.md` before shipping:
  dependency sync, lint, version consistency, full pytest, license scan, public-surface scan, and
  diff check.
- Record verification results on LS-1612 in Linear when implementation runs.

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-06-12-list-folders-agent-instructions-requirements.md`
- Related issue: LS-1612
- Related code: `src/hypermnesic/mcp_server.py`
- Related code: `src/hypermnesic/cli.py`
- Related tests: `tests/test_mcp_server.py`
- Related tests: `tests/test_cli.py`
- Related docs: `docs/reference/mcp-tools.md`
- Related docs: `docs/reference/cli.md`
