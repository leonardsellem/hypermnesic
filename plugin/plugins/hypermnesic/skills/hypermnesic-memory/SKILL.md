---
name: hypermnesic-memory
description: Use whenever you need durable project or personal memory — recalling prior context, resolving a named entity to an existing note, or writing a note back. hypermnesic is a self-hosted memory layer (hybrid search/recall + a gated git-first write) served over an OAuth2-authenticated MCP endpoint.
---

# hypermnesic — the memory layer

hypermnesic indexes a git-tracked markdown vault and serves it over a self-hosted,
OAuth2-authenticated **MCP endpoint**. **Git is the source of truth**; the search index is a
disposable projection of the committed tree — a reindex never loses a committed note.

Reach for these tools whenever prior context, a known entity, or a durable note would help. A
relevance-gated recall hook may already surface related notes at prompt time, but call the tools
directly whenever you need more than it offered.

## When to use it

- **Starting or continuing work** that would benefit from prior context → `search` /
  `build_context` / `think`.
- **Wikilinking a named entity** (a person, project, place, system) → `resolve` the name to an
  existing page, then link to it.
- **Capturing a durable note, decision, or summary** → `commit_note` (git-first, gated).

## The tools (MCP)

All read tools converge the index to the latest commit before answering, so a just-pushed note
is recall-able without a manual reindex.

- **`search(query, k=10)`** — hybrid (lexical + dense) search over the vault. Returns ranked hits
  with `path`, `heading`, `score`, `snippet`, `recency`.
- **`build_context(path, depth=1)`** — pages reachable from a note via its body `[[wikilinks]]`
  (incoming + outgoing). Use to expand around a hit.
- **`think(topic, k=8)`** — thinking-mode: related notes + Socratic prompts + tensions. Read-only
  (`wrote: false`); it never writes.
- **`resolve(name)`** — entity resolution: resolve a name to an existing page path, or `null` if
  ambiguous/missing — **never a wrong guess**. The result carries `slug` (the `.md`-stripped
  path); wikilink the slug, e.g. `[[infrastructure/hetzner]]`.

## Writing a note — `commit_note` (git-first, gated)

`commit_note(path, body, set_fields?, summary?)` is the **one sanctioned write path**. It is
**git-first**: it writes the file, commits it, and pushes — the index follows as a projection.
You never merge; the engine coordinates. It is gated:

- **Writable allowlist:** writes must land under a configured set of prefixes (commonly `notes/`,
  `sources/`, `dashboards/`, `captures/`). A path outside the allowlist is **refused**, not
  silently dropped.
- **Protected-path refusal:** governance/execution files — `CLAUDE.md`/`AGENTS.md` anywhere,
  `.github/`, `.git/`, hooks, scripts, `.obsidian/` — are refused unconditionally.
- **Diff-or-die frontmatter gate:** an unintended frontmatter change aborts the write and
  surfaces the diff (no silent reserialization).
- A refusal returns `{committed: false, refused: "<reason>"}` — never a silent success.

For frictionless raw capture, prefer landing text under the free-append zone (commonly `sources/`).

## The disk-first model (why this is safe)

- **Git is the source of truth.** Every note is a committed markdown file; the index is a
  rebuildable projection. There is no separate database of record.
- **Reads are convergent.** The index catches up to `HEAD` before each read, so your own
  just-committed note is recall-able on the next query.
- **Writes are auditable and bounded.** `commit_note` is allowlisted, protected-path-guarded,
  frontmatter-stable, and audit-logged (summaries only, never bodies, never credentials).

## Auth

The MCP endpoint is OAuth2-authenticated. The plugin's MCP wiring presents your token
automatically; you never handle tokens by hand, and a token value never appears in a prompt, a
config file, or a log.
