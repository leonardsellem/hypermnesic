# Daily workflows

The daily Hypermnesic loop is:

**capture -> triage -> recall -> write -> review -> clean up**

Use it as an owner workflow, not a hidden automation pipeline. Raw evidence stays in place,
triage is review-gated, recall uses the right primitive for the job, writes go through the
git-first guard, and cleanup uses the memory control center.

## Loop

1. Capture raw source quickly with `hypermnesic capture`.
2. Triage later from the capture backlog and generated suggestions; no raw source is silently moved.
3. Recall during work with `search`, `build_context`, `think`, and `resolve`.
4. Write durable project memory only after applying the memory taxonomy.
5. Review the owner-facing daily surface with `hypermnesic daily-review`.
6. Clean up with memory-control preview/review commands.

## Capture now, triage later

Capture is intentionally low-friction:

```sh
hypermnesic capture /path/to/vault "raw meeting note or fleeting project observation"
```

The raw text lands under `sources/` and is committed. Later, the workflow surfaces the capture
backlog and triage suggestions without moving or rewriting the source. Triage can suggest
placement, connections, and questions, but the owner decides whether to write a durable note.

## Recall modes

- `search` / `hypermnesic retrieve`: direct topic, entity, or project-history recall.
- `build_context`: expand around a known path through wikilinks and neighboring notes.
- `think`: inspect related notes, note-grounded questions, and unlinked pairs.
- `resolve`: map a named entity to an existing note; if it returns null, do not guess.

In degraded or offline operation, lexical recall, capture, backlog review, and cleanup guidance
still work. Dense ranking and embedding centrality may be partial, but the files remain the source
of truth.

## Daily review

Generate one scan-friendly review proposal:

```sh
hypermnesic daily-review /path/to/vault
hypermnesic daily-review /path/to/vault --json
```

The review surface is generated under `dashboards/daily-review.md` through the same review-gated
proposal path as other dashboards. It includes capture backlog, recent audit-log writes, generated
navigation/salience/connection links, recall-mode reminders, cleanup next actions, and degraded
state notes. It does not delete, move, or rewrite source notes.

## Cleanup

Cleanup routes to the memory control center:

- Inspect: `hypermnesic memory inspect /path/to/vault <path>`
- Export: `hypermnesic memory export /path/to/vault --dest <dir>`
- Forget/delete preview: `hypermnesic memory forget /path/to/vault <path>`
- Revert preview: `hypermnesic memory revert /path/to/vault <commit>`
- Audit: `hypermnesic memory audit /path/to/vault`

Archive, forget/delete, revert, and triage completion are different actions. Do not use a generated
review surface as a destructive implementation.

## Obsidian

Obsidian is a read-only review/navigation companion in this architecture. Use it to inspect the
capture backlog, generated dashboards, daily loop notes, and source paths. Writes, cleanup,
revocation, and guarded memory changes stay in the CLI/MCP git-first surfaces unless a separate
approved companion plan changes that boundary. Obsidian cannot bypass consent, write scope,
protected-path refusals, or write guards.

## Recipes

### Recipe: capture now, triage later

1. Run `hypermnesic capture /path/to/vault "raw text"`.
2. Later run `hypermnesic daily-review /path/to/vault`.
3. Follow the capture backlog and triage suggestions.
4. Preserve the raw `sources/` path when writing a summary.

### Recipe: find prior context

1. Start with `hypermnesic retrieve /path/to/vault "topic"`.
2. Use `build_context` from the MCP tool surface when a hit needs graph expansion.
3. Use `hypermnesic think /path/to/vault "topic"` for related notes and questions.

### Recipe: remember a project decision

1. Capture or cite the raw source path.
2. Use `hypermnesic list-folders /path/to/vault` if the destination is unclear.
3. Preview with `hypermnesic commit-note /path/to/vault projects/example/decision.md --body "..."`
   or use the MCP `commit_note` write path from an approved write client.

### Recipe: connect a client

1. Run `hypermnesic doctor /path/to/vault --public-url https://<your-host>.ts.net/mcp`.
2. Add the MCP URL to the client and approve read or write on the consent page.
3. Use `hypermnesic clients list /path/to/vault` to inspect the grant.

### Recipe: revoke a client

1. Run `hypermnesic clients list /path/to/vault --json`.
2. Preview `hypermnesic clients revoke /path/to/vault <grant-id>`.
3. Apply with `--apply` after confirming the grant.

### Recipe: forget a bad memory

1. Inspect first: `hypermnesic memory inspect /path/to/vault <path>`.
2. Preview: `hypermnesic memory forget /path/to/vault <path>`.
3. Apply only when the preview is correct.
4. Run recall again or inspect the audit log to verify post-cleanup state.

### Recipe: recover from stale or degraded recall

1. Run `hypermnesic status /path/to/vault`.
2. If the index is stale, run `hypermnesic converge /path/to/vault --now`.
3. If dense retrieval is unavailable, continue with lexical/offline recall and fix
   `OPENAI_API_KEY` later.
