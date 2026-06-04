# MCP tool reference

The client contract: every tool the hypermnesic MCP server exposes, with its inputs,
output shape, scope, and read/write annotation. The source of truth is the `@mcp.tool`
registrations in [`src/hypermnesic/mcp_server.py`](../../src/hypermnesic/mcp_server.py)
(`READ_TOOL_NAMES` / `WRITE_TOOL_NAMES` and the typed output models).

Every server advertises an `outputSchema` per tool, so connectors understand result
structure rather than receiving an opaque object. **Read tools always converge the index
to the latest commit before answering** — so a just-pushed note is recall-able without a
manual reindex — and every read result carries `manual_reindex_recommended` (true only
when `HEAD` has jumped far past the index checkpoint).

| Tool | Kind | Scope | Registered |
|---|---|---|---|
| `search` | read (`readOnlyHint: true`) | read | always |
| `build_context` | read (`readOnlyHint: true`) | read | always |
| `think` | read (`readOnlyHint: true`) | read | always |
| `resolve` | read (`readOnlyHint: true`) | read | always |
| `list_folders` | read (`readOnlyHint: true`) | read | always |
| `commit_note` | write (`readOnlyHint: false`) | `write` | only on a write-enabled server |

## Read tools

### `search(query: str, k: int = 10)`

Hybrid (lexical + dense) search over the index.

**Returns** `{ query, degraded_lexical_only, manual_reindex_recommended, hits: [ { path,
heading, score, channels, snippet, recency } ] }`. `channels` records which retrieval
lanes matched (lexical/dense); `recency` is the epoch-seconds of the most recent commit
touching the hit's path (or null if untracked). `degraded_lexical_only` is true when the
dense channel was unavailable.

### `build_context(path: str, depth: int = 1)`

Pages reachable from `path` via body `[[wikilinks]]` (incoming + outgoing edges), to
`depth` hops. Use it to expand around a `search` hit.

**Returns** `{ start, depth, context: [page paths], manual_reindex_recommended }`.

### `think(topic: str, k: int = 8, depth: int = 1)`

Thinking-mode: related notes + Socratic prompts + tensions. **Read-only by construction**
— `wrote` is always `false`; it never writes.

**Returns** `{ topic, wrote: false, related, context, questions, tensions,
degraded_lexical_only, note, manual_reindex_recommended }`.

### `resolve(name: str)`

Entity resolution: resolve a name to an existing page path, or `null` if ambiguous or
missing — **never a wrong guess**. The caller strips `.md` (use `slug`) to form a
wikilink target.

**Returns** `{ name, resolved: path|null, slug: string|null, manual_reindex_recommended }`.

### `list_folders(root: str = "", depth: int = 1)`

Discover the vault's folder taxonomy and writable locations before placing a note: child
folders under `root` (drill-down to `depth` levels). The `writable` flag matches exactly
what `commit_note` accepts (they share one write-surface coercion). Narrow `root` to
drill deeper when `truncated` is true.

**Returns** `{ root, depth, folders: [ { path, writable, protected_reason, note_count } ],
truncated, omitted, manual_reindex_recommended }`. `protected_reason` is null when
writable, else the reason (protected class or allowlist miss); `omitted` counts folders
dropped by the node cap.

## Write tool (gated)

### `commit_note(path: str, body: str | None = None, set_fields: dict | None = None, summary: str | None = None)`

The **one sanctioned write path**. Git-first: writes the file, commits it (and pushes) —
the index follows as a projection; the agent never merges. Registered **only on a
write-enabled server**, and requires the `write` OAuth scope (self-enforced per-tool,
independent of the transport's global scope list). It runs through the blocklist write
guard, the diff-or-die frontmatter gate, single-writer locks, and the append-only audit
log.

**Returns (success)** `{ committed, path, created, noop, new_sha, diff }`.
**Returns (refusal)** `{ committed: false, refused: "<reason>" }` — a protected-path /
governance / allowlist refusal, a frontmatter-drift abort, a head-drift / dirty-tree /
coordination refusal, or an insufficient-scope rejection. When write scope is missing, the
refusal tells the client to reconnect and approve write access, and says that write approval
does not bypass protected-path, frontmatter, dirty-tree, head-drift, audit, or git
coordination guards. A refusal is never a silent success and never produces a partial write
or an audit entry.

See [`docs/reference/cli.md`](cli.md) for the CLI twins of these tools, and
[`SECURITY.md`](../../SECURITY.md) for the write-surface threat model.
