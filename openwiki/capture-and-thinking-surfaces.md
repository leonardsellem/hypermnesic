---
type: Reference
title: Capture and Thinking Surfaces
description: The input and pre-write surfaces — frictionless capture, deferred triage, structurally read-only thinking mode, folder discovery, and content-addressed sidecar extraction.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-082442cff6ee589b6648d482
    resource: repo://docs/guides/memory-taxonomy.md
  - id: openwiki-source-03ee9a9e716fb46eb5e59693
    resource: repo://docs/reference/mcp-tools.md
  - id: openwiki-source-d2dbaede6a26ece897033297
    resource: repo://GLOSSARY.md
  - id: openwiki-source-bcf3a4ff129d9883dbfd613f
    resource: repo://plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-51d97e561438845ebfc72a76
    resource: repo://src/hypermnesic/capture.py
  - id: openwiki-source-5f17d71d8e2d83b9ea0bc2ae
    resource: repo://src/hypermnesic/config.py
  - id: openwiki-source-a549bbb642c1fa61b486d5ae
    resource: repo://src/hypermnesic/folders.py
  - id: openwiki-source-b176d8b6149dd2b6fdc03229
    resource: repo://src/hypermnesic/ingest.py
  - id: openwiki-source-bf30bdf8a5e94f3f19416f00
    resource: repo://src/hypermnesic/memory_control.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-842edce8f3d713fbfd277877
    resource: repo://src/hypermnesic/sidecar.py
  - id: openwiki-source-614eabcd0f8a5da6b1127eec
    resource: repo://src/hypermnesic/think.py
  - id: openwiki-source-232e3d28eb24c60863705045
    resource: repo://tests/test_capture.py
  - id: openwiki-source-1e4f106d0ba32441e1843a0a
    resource: repo://tests/test_folders.py
  - id: openwiki-source-5000ba765c9bbfa2c8b762c0
    resource: repo://tests/test_sidecar.py
  - id: openwiki-source-dd637bd8ad88a9aefec117f6
    resource: repo://tests/test_think.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Capture and Thinking Surfaces

These are the surfaces a person or agent touches *before* a curated note exists. They share
one design commitment: **getting something in must be cheap, and turning it into structure
must be a decision someone makes** — never something the system does on its own.

## Capture: separate the two frictions in time

Capture friction and processing friction are different problems, and solving them together
means solving neither. So they are split:

- **Capture** lands raw text under `sources/` immediately, through the free-append fast
  path. It is committed to `HEAD` in the moment, with no proposal branch, no organization
  demanded, and no decision required — a thought is never lost to ceremony.
- **Triage** happens later, reusing the read-only thinking path over the captured item to
  *propose* a placement, connections, and one grapple prompt.

A capture with no name gets a deterministic one: a timestamp plus the first six hex
characters of the body's SHA-256, under `sources/captures/`. The capture write is narrowed
to the `sources/` prefix, so this fast path cannot reach anywhere else in the vault
regardless of what it is handed.

`backlog` lists what is waiting without touching it: for each capture, a path, a bounded
snippet, a byte size, and a stage — `pending_triage`, or `triage_proposed` once a triage
note exists for it.

**Triage never files anything.** It reads the captured note, runs thinking mode over its
text, and emits a *proposal* containing a suggested folder (derived from the nearest
related note's directory), up to five connection wikilinks, and a grapple question. The
capture itself is not moved, renamed, or rewritten. The result carries the thinking step's
own `wrote` value, so a caller can verify from the returned data that the analysis wrote
nothing — the proof travels with the result rather than being a promise in a docstring.

## Thinking mode: a no-write boundary you can check

`think` is the "help me think before you write" surface. It composes read-only retrieval
with wikilink graph context and returns related notes, a Socratic prompt, and pairs of notes
that surface together but are not yet linked — plus an explicit `wrote: false`.

The no-write boundary is **structural, not a flag**: the module imports only read surfaces.
It does not import — and therefore cannot reach — the write path or the proposal queue. The
`wrote: false` field exists so a caller can *observe* the boundary rather than trusting an
implied behavioural difference. See [MCP Tool Surface](mcp-tool-surface.md) for the tool
contract and [Git-First Write Path](git-first-write-path.md) for the surface it deliberately
avoids.

Several choices here are about refusing to generate slop:

- **Notes, not chunks.** Prompts and pairs reason over distinct note paths, so a note with
  two matching chunks does not double-count or produce a duplicate pair.
- **Grounded prompts only.** The generic templated questions were removed because they
  referenced nothing the retrieval found. The surviving prompt names two distinct related
  notes by their resolved titles and fires only when there are at least two; otherwise
  `think` returns no questions rather than padding.
- **Titles are note identity.** A related note is labelled by its own H1, read from the
  file, not by the heading of whichever chunk happened to match.
- **Unlinked pairs claim nothing.** A pair is "these surfaced together and no wikilink joins
  them", offered as a candidate the writer can verify — not an assertion of conceptual
  tension. Adding the link is a proposal, never a write.

Two degradation paths keep the surface honest. Passing the active note's path excludes it
from its own results; if that self-exclusion removes the only hit, `think` falls back to the
note's explicit graph neighbours as low-confidence `graph`-channel results, so a well-linked
note does not produce a blank thinking surface. An empty or meaningless topic returns no
related notes and a plain "nothing relevant yet" note — still `wrote: false`.

## Folder discovery: ask before placing

`list_folders` turns the index's path set into bounded, sorted folder entries so an agent can
discover where a note may land *before* attempting to write it.

The important property is that **writability is single-sourced from the write guard**. A
folder's flag is computed by probing a synthetic markdown file *under* that prefix through
exactly the guard `commit_note` uses. Probing a file under the prefix rather than the bare
prefix matters: the protected-path reason deliberately excludes the leaf, so a bare prefix
would misclassify a folder like `projects/scripts/` as writable. Because the same predicate
answers both questions, the discovery surface and the write surface cannot drift apart.

Results are bounded and deterministic: entries are sorted **before** the node cap is applied,
so truncation always drops the same tail, and the response reports both a `truncated` flag
and an `omitted` count. Depth is clamped. A caller narrows `root` to drill deeper. See
[Configuration and Tunables](configuration-and-tunables.md) for the bounds.

A caller-supplied root is normalized to a repo-relative prefix, and an absolute path or one
containing `..` is rejected outright rather than being normalized into something plausible.

Folder discovery also returns the **root-local agent instruction file** when one exists —
`AGENTS.md` first, falling back to `CLAUDE.md` only when the former is absent at that exact
root. Descendant instruction files are deliberately not aggregated into a parent listing;
narrowing `root` to the child is how you read its guidance. Because this is a remote read
surface, the content is sanitized first: endpoint URLs and host-local absolute paths are
replaced with placeholders while repo-relative paths survive intact, so guidance stays useful
without leaking an operator's coordinates to a connected client.

## Sidecars: making non-markdown sources retrievable

A PDF, DOCX, XLSX, PPTX, or image cannot be indexed directly, so it gets a **markdown
sidecar** that can be. A router keyed on extension and complexity sends complex, scanned,
table-dense, or equation-bearing PDFs and images to one extractor and office formats and
simple native PDFs to another. Both extractors, and the probe libraries behind the
scanned-versus-native heuristic, are permissively licensed by requirement — the copyleft
alternatives are excluded on purpose, and a dependency gate enforces it (see
[Testing and Release Gates](testing-and-release-gates.md)).

The heavy extractors are imported **lazily**, so the routing and hash-gate logic loads and
is testable without them installed.

### The hash gate

Every sidecar is content-addressed. Its frontmatter records the source path, the extraction
timestamp, the source's SHA-256, the extractor and its version, and a quality label.
Re-extraction fires on exactly three conditions: no sidecar exists, the source hash no longer
matches, or the extractor version was bumped. Otherwise the source is skipped — an unchanged
binary never causes churn, and bumping one module-level constant is how you force a corpus-wide
re-extraction deliberately.

### Sidecar writes are proposals

A changed source produces a review-gated re-extraction **proposal**, never a silent overwrite
of the existing sidecar. The one-time cold start over an entire corpus is a *single batched*
proposal rather than one per file, because a pull request per binary is not review, it is
noise. See [Review and Navigation Surfaces](review-and-navigation-surfaces.md).

Sidecar text originates in arbitrary binaries and is read by write-capable agents through the
index, so every sidecar carries a `source: sidecar` trust tag. The current posture accepts
that content, but the tag exists now so a future policy can restrict sidecar-derived chunks
from write-capable tools without re-extracting anything.

## What belongs here at all

Not every memory-like fact belongs in this vault. The taxonomy classifies a candidate on five
dimensions — duration, type, scope, update strategy, and retrieval mode — and routes it
accordingly.

**Write it here** when it is durable project memory: a stable semantic fact, dated
episodic/source evidence, a procedural or policy rule, a generated summary that cites its
sources, a raw capture, or a current-state mirror of an external system.

**Do not write it here by default**: behavioural preferences ("user likes terse replies"),
temporary session state, transient inferences about a person's mood, secrets and credentials
of any kind, and unreviewed sensitive personal material. Behavioural preference and session
state do not become durable project memory merely by being useful; they belong in an adjacent
short-term layer.

Two rules cut across all of it. **Evidence first**: preserve raw captures and cite source
paths rather than replacing evidence with a cleaned summary — triage is allowed, silent source
deletion is not; a removal goes through the memory-control preview/apply flow so it becomes a
new git event with audit context (see [Memory and Client Control](memory-and-client-control.md)).
And **a refusal is a control signal**: a protected-path or consent refusal is product safety,
not an obstacle to route around by changing paths or transports.
