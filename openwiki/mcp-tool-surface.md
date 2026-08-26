---
type: Reference
title: MCP Tool Surface
description: The client contract — seven read tools and one gated write tool, their typed output schemas, registration conditions, shared read guarantees, and the security boundaries built into each.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-03ee9a9e716fb46eb5e59693
    resource: repo://docs/reference/mcp-tools.md
  - id: openwiki-source-67d6bfc4b44aab1dcbded940
    resource: repo://harness/PARITY_VERDICT.md
  - id: openwiki-source-f103fa2315aae36568406e00
    resource: repo://src/hypermnesic/commit_note.py
  - id: openwiki-source-c76fa3ae1f9c3796f441ee08
    resource: repo://src/hypermnesic/converge.py
  - id: openwiki-source-eca76e73bbc2749831def863
    resource: repo://src/hypermnesic/embed.py
  - id: openwiki-source-a549bbb642c1fa61b486d5ae
    resource: repo://src/hypermnesic/folders.py
  - id: openwiki-source-5bc4d4cc0e683518554afb42
    resource: repo://src/hypermnesic/graph.py
  - id: openwiki-source-37433895d4b7b6af7cd92f4f
    resource: repo://src/hypermnesic/mcp_server.py
  - id: openwiki-source-f2d2daf9ca9b4a326a178c61
    resource: repo://src/hypermnesic/retrieve.py
  - id: openwiki-source-614eabcd0f8a5da6b1127eec
    resource: repo://src/hypermnesic/think.py
  - id: openwiki-source-9241ab90871fd251f3253d0f
    resource: repo://tests/test_mcp_server.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# MCP Tool Surface

This is what a remote client sees. The authority is the tool registration and the typed
output models in the server module — a prose reference can drift, the registrations cannot.

| Tool | Kind | Registered |
|---|---|---|
| `search` | read | always |
| `hypermnesic_search` | read | always |
| `build_context` | read | always |
| `think` | read | always |
| `resolve` | read | always |
| `list_folders` | read | always |
| `read_note` | read | always |
| `commit_note` | write, requires the `write` scope | **only on a write-enabled server** |

Every read tool is annotated `readOnlyHint: true`; the write tool is annotated
`readOnlyHint: false`. Those annotations are what let a client reason about a tool before
calling it.

## Shared guarantees on every read

- **The index converges to `HEAD` before the tool answers.** A note committed a moment ago is
  recall-able without a manual reindex. See [Read-Time Convergence](read-time-convergence.md).
- **Every read result carries `manual_reindex_recommended`.** It is true only when `HEAD` has
  jumped far past the index checkpoint — a signal, not an error, and never something the tool
  acts on by itself.
- **Every tool advertises an `outputSchema`.** The result shapes are declared as typed
  dictionaries so a connector understands the structure rather than receiving an opaque
  object. This is schema-only: the tool functions return plain dictionaries validated against
  those shapes.

## `search(query, k=10)`

Hybrid retrieval: the lexical channel fused with the dense channel by reciprocal-rank fusion,
degrading to lexical-only when embeddings are unavailable. See
[Retrieval and Indexing](retrieval-and-indexing.md).

Returns `query`, `degraded_lexical_only`, `degraded_reason`, `manual_reindex_recommended`, and
`hits`. Each hit carries `path`, `heading`, `score`, `channels` (which retrieval lanes matched),
a bounded `snippet`, and `recency` — the epoch seconds of the most recent commit touching that
path, or null when untracked.

Degradation is *named*, not just flagged: `degraded_reason` is null when the dense channel
contributed, and otherwise identifies the provider or configuration state — a missing embedder,
a configuration problem, a rate limit, the cooldown that follows one, an API error, or an
embedding error. That is the difference between "the index is broken" and "your provider is
throttling you".

## `hypermnesic_search(query, k=10)`

**An alias, not a second implementation.** Same inputs, same output shape; both names call one
shared internal function, so they cannot diverge.

It exists for clients that automatically prefix tool names with the server id — for those, the
bare name is unreachable. Prefer `search` unless your client requires the prefixed form.

## `build_context(path, depth=1)`

Pages reachable from `path` through body wikilinks, following both incoming and outgoing edges
to `depth` hops. This is the expansion move after a `search` hit. Returns `start`, `depth`, and
the reachable `context` paths.

## `resolve(name)`

Entity resolution: a name to an existing page path, or **null when ambiguous or missing** —
never a wrong guess. Returns `name`, `resolved`, and `slug`, where `slug` is the `.md`-stripped
path to use as a wikilink target.

The null-over-guess rule is the whole point of this tool. A wrong link is materially worse than
no link, because it silently connects two unrelated things and both a human and an agent will
believe it.

## `think(topic, k=8, depth=1, path=null)`

Thinking-mode: related notes, a Socratic prompt, graph context, and pairs of notes that surface
together but are not yet linked. **Read-only by construction** — `wrote` is always false, and
the module cannot reach the write path at all. See
[Capture and Thinking Surfaces](capture-and-thinking-surfaces.md).

Pass the active note's `path` to exclude it from its own results; if that removes the only hit,
the tool falls back to the note's graph neighbours rather than returning a blank surface.

## `list_folders(root="", depth=1)`

Folder taxonomy and writable locations, so an agent can discover where a note may land before
attempting to write it. Returns `root` (normalized), the clamped `depth`, `folders`,
`truncated`, `omitted`, and `agent_instruction`.

Each folder entry carries `path`, `writable`, `protected_reason` (null when writable, otherwise
why not), and a recursive `note_count`. **The `writable` flag matches exactly what `commit_note`
accepts**, because both derive it from one shared write-surface coercion — so discovery cannot
promise a write the write path would refuse.

`agent_instruction` is the direct root-local instruction file when one exists — `AGENTS.md`,
falling back to `CLAUDE.md` — with host coordinates redacted, or null. Child instruction files
are not aggregated into a parent listing.

An absolute or traversal `root` does not raise. It returns an **empty, leak-free listing** with
no folders and no instruction, so a malformed request cannot be used to probe for out-of-vault
paths through error messages.

## `read_note(path)`

The full markdown body of one note, typically a `path` returned by another read tool. Returns
`path`, `found`, and `content`.

**Index membership is the security boundary.** Only committed, in-vault markdown notes appear
in the index's path set, so a traversal path, an absolute path, or a non-note file such as a
dotfile or anything under the git directory is simply absent and returns `found: false` with
`content: null` — not an error, and never a read outside the vault. A resolved-within-repo
check adds defence in depth on top of that.

## `commit_note(path, body?, set_fields?, summary?)` — gated

The single sanctioned write, registered **only when the server is started write-enabled**. That
conditional registration is deliberate: on a read-only server the tool does not merely refuse,
it does not exist, so a read lane cannot be talked into a write by any client. See
[Git-First Write Path](git-first-write-path.md).

It additionally **self-enforces the `write` scope per tool**, independently of the transport's
global required-scope list. The SDK middleware applies one scope list to every tool, which
cannot separate read clients from write clients on a single endpoint — so the tool checks the
caller's scopes itself and refuses a read-scoped token before any write is attempted. See
[Serving Topology and Authentication](serving-and-authentication.md).

The result is a **union**, and its two failure-shaped branches mean different things:

| Field set | Meaning |
|---|---|
| `committed: true` with `path`, `created`, `noop`, `new_sha`, `diff` | The write landed. |
| `committed: false` with `refused` | **Nothing was written.** A guard, gate, drift, or scope refusal. |
| `committed: true` with `index_degraded` and `degraded_reason` | **The commit landed**; only its index projection failed. Keep the SHA; do not write the note again. |

Never conflate the last two. A refusal wrote nothing; a degraded success wrote everything and
merely lags in recall. The server returns an explicit structured result for this tool rather
than letting the framework materialize absent union fields as nulls, so a client sees only the
branch that actually applies.

## Guidance carried in the tool descriptions

The descriptions are part of the contract, because for an agent they *are* the documentation.
They state that read tools converge first, that `resolve` returns null rather than guessing,
that `think` never writes, that `list_folders` should be called before a write when the
destination is unclear, and — on the write tool — that a degraded index does not mean the note
should be written again somewhere else.
