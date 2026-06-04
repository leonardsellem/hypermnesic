# Memory taxonomy

Hypermnesic is durable project memory: markdown files in a git repository, retrieved by
search and graph context, and changed through reviewable commits. It is not the default
place for every memory-like fact an agent sees.

Use this guide before creating, consolidating, deleting, or routing memory.

## Decision dimensions

Every candidate memory should be classified by five dimensions:

| Dimension | Question | Hypermnesic answer |
|---|---|---|
| Duration | Should this survive beyond the current session? | Yes, if it remains useful after the conversation ends. |
| Type | Is it semantic, episodic/source, procedural/policy, generated, raw, or current-state? | Store the type explicitly in the note shape or path when helpful. |
| Scope | Is it about a project, entity, source, system, or durable owner decision? | Prefer project/entity/source scopes over vague personal preference scopes. |
| Update strategy | Is this append-only evidence, a curated current state, or a generated summary? | Preserve raw evidence before summarizing or replacing. |
| Retrieval mode | Should agents find it by topic search, entity resolution, graph context, or folder browsing? | Choose paths, headings, and wikilinks that make retrieval predictable. |

## Write to Hypermnesic

Write to Hypermnesic when the fact belongs in durable project memory and future agents should find
it from the markdown/git source of truth.

| Type | Write to Hypermnesic example | Why it belongs |
|---|---|---|
| Semantic memory | Write to Hypermnesic: "Project Atlas uses the blocklist write surface, not an allowlist by default." | Stable project fact that future retrieval should surface. |
| Episodic/source memory | Write to Hypermnesic: a meeting note, imported source excerpt, incident note, or dated observation under `sources/` or a project folder. | Raw evidence or source episode that should remain traceable. |
| Procedural/policy memory | Write to Hypermnesic: "Before adding an adapter, check native upstream primitives." | Durable operating rule tied to project execution. |
| Generated summary | Write to Hypermnesic: a generated design summary that cites source paths and labels itself as generated. | Useful synthesis, as long as raw evidence remains findable. |
| Raw capture | Write to Hypermnesic: unprocessed text landed with `hypermnesic capture` for later triage. | Low-friction evidence intake. |
| Current-state mirror | Write to Hypermnesic: the current deployed topology for a service, updated when reality changes. | Durable mirror of external system state. |

## Do not write to Hypermnesic by default

These examples are memory-like, but they are the wrong default storage target.

| Candidate | Default route | Reason |
|---|---|---|
| Do not write to Hypermnesic: "user likes terse replies." | Honcho or an equivalent adjacent behavioural memory layer. | Behavioural preference, not durable project memory. |
| Do not write to Hypermnesic: "we are halfway through this reply." | Session context only. | Temporary session state. |
| Do not write to Hypermnesic: "the user seems annoyed right now." | Session context or no write. | Transient inference and sensitive behavioural reading. |
| Do not write to Hypermnesic: secrets, credentials, bearer tokens, approval tokens, private keys. | No write; keep in the proper secret store. | Hypermnesic docs, audit logs, and commits must not contain secrets. |
| Do not write to Hypermnesic: unreviewed sensitive personal material. | No write until the owner explicitly chooses a safe destination. | Durable git history is hard to erase fully. |
| Do not write to Hypermnesic: a guard refusal workaround. | Treat the refusal as a control signal. | Protected-path and consent refusals are product safety, not obstacles. |

Honcho is the operator's behavioural/session memory layer in this environment. Users without Honcho
should substitute their own short-term preference/session layer. The important boundary is the type
of memory: behavioural preference and session state do not become durable project memory just
because they are useful.

## Evidence first

Preserve raw evidence before creating a generated summary. A good consolidation note:

- cites source paths such as `sources/meetings/2026-06-04-atlas-review.md`;
- labels generated summaries as generated;
- links durable entities with wikilinks when known;
- keeps raw captures and episodic/source memory traceable;
- explains what changed and why without silently rewriting history.

Do not overwrite raw captures with a cleaned summary. Triage is allowed; silent source deletion is
not. If a raw source is wrong or sensitive, use the memory-control preview/apply flow so the removal
is a new git event with audit context.

## Agent routing checklist

Before writing, an agent should answer:

1. Is this durable project memory, or is it behavioural/session memory for Honcho or another layer?
2. Is there raw evidence to preserve or cite?
3. Is the destination obvious? If not, call `list_folders` before choosing a path.
4. Could this contain secrets, credentials, private keys, or unreviewed sensitive material? If yes,
   do not write it.
5. Did `commit_note` refuse? Treat refusals as control signals; do not bypass guards.

Before reading, an agent should choose the narrowest useful tool:

- `search` for topic/entity/project history;
- `build_context` to expand around a known note path;
- `think` to inspect related notes and unresolved links;
- `resolve` to map a named entity to an existing note;
- `list_folders` to discover taxonomy and writable folders.
