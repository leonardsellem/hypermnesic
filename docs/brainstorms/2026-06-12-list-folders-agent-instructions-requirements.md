---
date: 2026-06-12
topic: list-folders-agent-instructions
---

# List Folders Agent Instructions

## Summary

`list_folders` should keep returning the vault folder taxonomy, and additionally surface the
agent-instruction file that applies at the requested folder root when one exists. The tool should
prefer `AGENTS.md`, fall back to `CLAUDE.md`, and omit the instruction payload when neither file is
present.

---

## Problem Frame

Agents use `list_folders` before placing durable notes so they can understand the vault's folder
taxonomy and writable locations. The folder list tells an agent where it may write, but it does not
currently expose local operating rules that may live at the same folder boundary. That leaves agents
to discover folder-specific conventions through a separate read/search step, which is easy to miss
when the whole point of `list_folders` is orientation before choosing a destination.

LS-1612 asks for the folder-discovery response to carry the local agent guidance from the requested
root, so an agent gets both the structure and the rules for that location in one read.

---

## Actors

- A1. Agent client: Calls `list_folders` to choose a destination or understand a subtree before
  writing or navigating.
- A2. Vault maintainer: Places `AGENTS.md` or compatibility `CLAUDE.md` files at folder roots to
  define local operating rules.

---

## Requirements

**Instruction discovery**

- R1. When `list_folders` is called for a normalized root, the response includes the content of an
  `AGENTS.md` file located directly at that root when that file exists.
- R2. If no direct `AGENTS.md` exists at the requested root, the response falls back to the content
  of a direct `CLAUDE.md` file at that same root.
- R3. If neither direct instruction file exists at the requested root, the response remains a normal
  folder listing with no instruction content.
- R4. When both files exist at the same requested root, `AGENTS.md` wins and `CLAUDE.md` is not
  returned as the active guidance.
- R5. Instruction discovery is scoped to the requested root itself; child-folder instruction files
  are not bundled into the parent listing.

**Folder-listing behavior**

- R6. The existing folder taxonomy behavior remains intact: normalized root, clamped depth,
  deterministic folder order, bounded output, writability flag, protected reason, recursive note
  count, and convergence signal continue to behave as before.
- R7. Invalid or traversal-style roots continue to avoid leaking out-of-vault paths or file content.
- R8. The instruction payload is structured so clients can distinguish "no instruction file" from
  "instruction file found with this source filename."

**Documentation and compatibility**

- R9. User-facing MCP tool documentation describes the new instruction payload and its precedence
  rule.
- R10. Planning must explicitly decide whether the local `hypermnesic list-folders` CLI mirrors the
  new MCP payload in this change or stays folder-taxonomy-only for now.

---

## Acceptance Examples

- AE1. **Covers R1, R6, R8.** Given `projects/AGENTS.md` exists and `projects/` has child folders,
  when an agent calls `list_folders(root="projects/", depth=1)`, the response includes the usual
  folder entries plus an instruction payload sourced from `AGENTS.md`.
- AE2. **Covers R2, R8.** Given `meetings/CLAUDE.md` exists and `meetings/AGENTS.md` does not, when
  an agent calls `list_folders(root="meetings/", depth=1)`, the response includes the instruction
  payload sourced from `CLAUDE.md`.
- AE3. **Covers R3.** Given neither instruction file exists at `people/`, when an agent calls
  `list_folders(root="people/", depth=1)`, the response includes the folder listing and no
  instruction payload.
- AE4. **Covers R4.** Given both `AGENTS.md` and `CLAUDE.md` exist at the vault root, when an agent
  calls `list_folders(root="", depth=1)`, the active instruction payload comes from `AGENTS.md`.
- AE5. **Covers R5.** Given `projects/hypermnesic/AGENTS.md` exists but `projects/AGENTS.md` does
  not, when an agent calls `list_folders(root="projects/", depth=1)`, the child file is not bundled
  into the parent response.
- AE6. **Covers R7.** Given a caller passes an invalid traversal root, when `list_folders` handles
  the request, the response does not include folder entries or instruction file content from outside
  the vault.

---

## Success Criteria

- Agents calling `list_folders` get the local folder rules at the same time as the folder taxonomy
  when a root-level instruction file exists.
- Existing clients that depend on the folder list, writability signal, truncation behavior, and
  convergence signal continue to work.
- `ce-plan` can proceed without inventing precedence, scoping, empty-state, or documentation
  behavior.

---

## Scope Boundaries

- Do not aggregate every nested `AGENTS.md` / `CLAUDE.md` file in the returned subtree.
- Do not interpret, summarize, rewrite, or validate the instruction file content; return the
  applicable file content as guidance.
- Do not change `commit_note` write permissions, protected-path behavior, or the folder writability
  model.
- Do not introduce a broader agent-instruction discovery tool in this task.

---

## Key Decisions

- Prefer `AGENTS.md` over `CLAUDE.md`: `AGENTS.md` is this repo's canonical agent instruction file,
  while `CLAUDE.md` remains compatibility fallback.
- Scope instructions to the requested root: this keeps `list_folders` bounded and avoids surprising
  payload growth for large subtrees.
- Preserve folder listing as the primary response: instruction content augments orientation but does
  not replace the folder taxonomy contract.

---

## Dependencies / Assumptions

- LS-1612 targets the MCP `list_folders` tool. CLI parity is intentionally left as a planning
  decision because the issue wording names the tool, while the existing product has a CLI mirror.
- Instruction files may contain governance-style guidance; the implementation must preserve the
  repository's existing no-leak behavior for invalid roots.
- The implementation will need to update the MCP tool output schema and user-facing docs if the
  response shape changes.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R8][Technical] What exact structured field shape should represent the optional
  instruction payload while preserving compatibility for existing clients?
- [Affects R10][Product/technical] Should `hypermnesic list-folders` mirror the instruction payload
  in the same change, or should LS-1612 stay MCP-only?
