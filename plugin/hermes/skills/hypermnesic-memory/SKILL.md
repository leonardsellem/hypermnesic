---
name: hypermnesic-memory
description: Use when Hermes needs durable project or personal memory through the local hypermnesic CLI: retrieve prior context, think through related notes, resolve entities, inspect writable folders, capture notes, or preview guarded writes.
---

# hypermnesic — Hermes CLI memory

hypermnesic indexes a git-tracked markdown vault. Git is the source of truth; the
index is a disposable, rebuildable projection of the committed tree. Hermes uses the
local `hypermnesic` CLI for this surface.

Use the CLI whenever prior context, a named entity, or a durable note would help.

## Reading

All read commands converge the index before answering and support `--json`.

- `hypermnesic retrieve <repo> <query> --json` — hybrid search over the vault.
  Results include paths, headings, scores, snippets, channels, and recency.
- `hypermnesic think <repo> <topic> --json` — thinking mode: related notes,
  note-grounded questions, and unlinked related pairs. Read-only.
- `hypermnesic resolve <repo> <name> --json` — resolve a name to an existing note
  path and slug, or return null when missing or ambiguous.
- `hypermnesic list-folders <repo> --json` — inspect folder taxonomy and writable
  locations before placing a note.

## Writing

- `hypermnesic capture <repo> <text> --json` — frictionless capture. It writes raw
  text under `sources/` and commits it.
- `hypermnesic commit-note <repo> <path> --body <text> --json` — dry-run preview of
  the guarded write path. In the current CLI it previews the diff and does not commit.

Do not treat plugin enablement or proactive recall as permission to write. Writing
should be an explicit CLI action.

## Model

- Git is source of truth.
- Reads are convergent before answering.
- The index can always be rebuilt from committed markdown.
- `capture` is the simple CLI write path.
- `commit-note` is a preview surface until a later engine change says otherwise.
- Use placeholders such as `<path-to-your-vault>` in examples; never assume a private
  local path.
