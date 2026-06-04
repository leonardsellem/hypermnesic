---
name: hypermnesic-memory
description: Use when Hermes needs durable project or personal memory through the local hypermnesic CLI: retrieve prior context, think through related notes, resolve entities, inspect writable folders, capture notes, or preview guarded writes.
---

# hypermnesic — Hermes CLI memory

hypermnesic indexes a git-tracked markdown vault. Git is the source of truth; the
index is a disposable, rebuildable projection of the committed tree. Hermes uses the
local `hypermnesic` CLI for this surface.

Use the CLI whenever prior context, a named entity, or a durable note would help.

Hypermnesic is durable project memory. Use it for semantic memory, episodic/source
memory, procedural/policy memory, generated summaries, raw captures, and current-state
mirrors that should survive beyond the session as markdown/git truth.

Do not write behavioural preference memory to Hypermnesic by default. Example: "user likes terse replies" belongs in Honcho or an equivalent adjacent behavioural memory
layer, not in durable project memory. Do not write temporary session state, emotional
inferences, secrets, credentials, private keys, bearer tokens, or unreviewed sensitive
material.

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

Tool routing:

- Use `retrieve` for durable topic, entity, and project history.
- Use `think` for note-grounded exploration and related-but-unlinked pairs; it never
  writes.
- Use `resolve` before wikilinking a named entity; do not guess when it returns null.
- Use `list-folders` before writes when the path or writable surface is unclear.

## Writing

- `hypermnesic capture <repo> <text> --json` — frictionless capture. It writes raw
  text under `sources/` and commits it.
- `hypermnesic commit-note <repo> <path> --body <text> --json` — dry-run preview of
  the guarded write path. In the current CLI it previews the diff and does not commit.

Do not treat plugin enablement or proactive recall as permission to write. Writing
should be an explicit CLI action.

Before writing, preserve raw evidence. Cite source paths when consolidating; do not
replace raw captures with generated summaries. If the destination is unclear, call
`list-folders` first and use the returned writable folders. Refusals are control signals: do not bypass protected-path, frontmatter, dirty-tree, head-drift, consent, or
scope refusals.

## Model

- Git is source of truth.
- Reads are convergent before answering.
- The index can always be rebuilt from committed markdown.
- `capture` is the simple CLI write path.
- `commit-note` is a preview surface until a later engine change says otherwise.
- Use placeholders such as `<path-to-your-vault>` in examples; never assume a private
  local path.
