# CLI reference

The `hypermnesic` CLI is the engine-host-local surface — it skips the network and
operates the index/retrieval/write/serve paths directly. The source of truth is
`build_parser()` in [`src/hypermnesic/cli.py`](../../src/hypermnesic/cli.py). Every read
subcommand converges the index to `HEAD` first; all support `--json`
(`ensure_ascii=False`). Credential values are never echoed.

```
hypermnesic --version
hypermnesic <subcommand> [args] [flags]
```

There are **22 subcommands**, grouped below by role.

## Local proof

### `local-proof [repo]`
Prove local memory works before remote setup. Existing-vault mode validates a markdown
git repo, projects committed files into `.hypermnesic/index.db`, retrieves a natural
question, shows the repo-relative source path, and previews a `commit_note` write as a
dry-run diff with no commit. Demo mode creates a tiny git-backed vault.
Flags: `--demo-dir DIR`, `--query TEXT`, `--seed-sample` (explicitly add the deterministic
sample note to an existing repo), `--preview-path PATH` (default
`memory/local-proof-preview.md`), `--dense` (try the dense embedding channel; default is
lexical local proof), `--json`.

JSON output includes `status`, `completed_milestones`, `degraded_capabilities`,
`source_path`, `retrieval`, `write_preview`, `index`, `next_action`, and `error`.

## Indexing

### `index <repo>`
Build the read-only index over a repo/corpus.
Flags: `--state-dir DIR` (external state dir; keeps the corpus untouched), `--no-rebuild`
(don't delete an existing index first), `--json`.

### `embed <repo>`
Async embed pass: fill dense vectors that lag lexical (closes the AE5 dense lag).
Flags: `--index-db PATH`, `--json`.

### `reindex <repo>`
Rebuild the index. `--isolated` builds in a worktree and swaps atomically so narrow
writers never block.
Flags: `--state-dir DIR`, `--isolated`, `--json`.

### `init <repo>`
Zero-infra drop-in: index a repo in place (in-repo `.hypermnesic/` state).
Flags: `--no-rebuild`, `--json`.

### `converge <repo>`
Pre-warm: catch the index up to `HEAD` + a bounded dense fill (the post-merge hook's
entrypoint; also a manual warm).
Flags: `--index-db PATH`, `--authoring-host` (also refresh the uncommitted working-tree
overlay), `--now` (force a non-debounced pass), `--json`.

## Reading (all read-only; converge first)

### `retrieve <repo> <query>`
Hybrid retrieve — the CLI twin of the MCP `search` tool (same hit shape).
Flags: `--index-db PATH`, `--k N` (default 10), `--now` (catch a self-write committed
within the debounce window), `--json`.

### `think <repo> <topic>`
Thinking-mode: related notes + Socratic prompts; never writes.
Flags: `--index-db PATH`, `--k N` (default 8), `--json`.

### `resolve <repo> <name>`
Entity resolution: name → existing page path, or null. Prints the `slug` to wikilink.
Flags: `--index-db PATH`, `--now`, `--json`.

### `list-folders <repo>`
Folder discovery: the vault's writable folder taxonomy (CLI twin of the MCP
`list_folders` tool, same output shape).
Flags: `--root PREFIX` (default vault root), `--depth N` (default 1), `--index-db PATH`,
`--now`, `--allowlist PREFIX` (repeatable; preview writability under a narrowed surface),
`--json`.

Use this before writes when the destination is unclear. Durable project memory belongs in
Hypermnesic; behavioural preference/session memory belongs in Honcho or an equivalent adjacent
layer by default.

## Writing

### `commit-note <repo> <path>`
Preview what a `commit_note` write would do — **dry-run, read-only** (guard + gate run,
zero side effects; prints the diff).
Flags: `--body TEXT`, `--body-file PATH`, `--summary TEXT`, `--json`.

Use this only for durable project memory. Do not write temporary session state, behavioural
preferences such as "user likes terse replies", secrets, credentials, or unreviewed sensitive
material. Treat refusal output as a control signal, not something to route around.

### `capture <repo> <text>`
Frictionless capture: land raw text in `sources/` immediately (free-append zone).
Flags: `--json`.

Capture is for raw evidence. Preserve raw captures or cite their source paths before writing
generated summaries.

### `daily-review <repo>`
Generate a review-gated daily workflow dashboard proposal under
`dashboards/daily-review.md`. The surface composes capture backlog, recent writes,
generated navigation/salience/connection links, recall-mode reminders, degraded/offline
state, and cleanup next actions. It does not move, delete, or rewrite source notes.
Flags: `--index-db PATH`, `--audit-log PATH`, `--nav-rel PATH`, `--digest-rel PATH`,
`--connections-rel PATH`, `--json`.

## Memory control

### `memory list <repo>`
List remembered markdown files with path, title, bounded snippet, source type, last commit,
audit actor when known, and writable/protected state.
Flags: `--index-db PATH`, `--audit-log PATH`, `--folder PREFIX`, `--source-type
{authored|captured|generated}`, `--writable`, `--protected`, `--recent`,
`--allowlist PREFIX` (repeatable), `--now`, `--json`.

### `memory inspect <repo> <path>`
Inspect one remembered file by repo-relative path. Output explains provenance in file and
commit terms; it does not include a raw full-body field.
Flags: `--index-db PATH`, `--audit-log PATH`, `--allowlist PREFIX` (repeatable),
`--now`, `--json`.

### `memory write-scope <repo>`
Answer "what would an agent be allowed to write?" using the same folder derivation and
protected-path guard as `list-folders` and `commit_note`.
Flags: `--index-db PATH`, `--audit-log PATH`, `--root PREFIX`, `--depth N`,
`--allowlist PREFIX` (repeatable), `--now`, `--json`.

### `memory export <repo>`
Copy selected markdown files to a destination directory and write
`hypermnesic-export-manifest.json` with path, last commit, actor when known, and source
type. This is a markdown/provenance export, not an index database export.
Flags: `--dest DIR` (required), `--folder PREFIX`, `--path PATH` (repeatable),
`--index-db PATH`, `--audit-log PATH`, `--allowlist PREFIX` (repeatable), `--now`,
`--json`.

### `memory forget <repo> <path>`
Preview or apply git-backed source removal for one memory. Preview is the default and has
no side effects. `--apply` removes the current source file as a new commit, updates the
index projection, and appends an audit entry. It does not rewrite git history or delete
old chat contexts.
Flags: `--apply`, `--index-db PATH`, `--audit-log PATH`, `--allowlist PREFIX`
(repeatable), `--now`, `--json`.

### `memory revert <repo> <commit>`
Preview or apply a safe recent memory revert. The first implementation supports
single-file markdown commits and refuses complex cases rather than guessing.
Flags: `--apply`, `--index-db PATH`, `--audit-log PATH`, `--now`, `--json`.

### `memory audit <repo>`
Show recent write, forget, revert, reconcile, and refusal entries from the summary-only
audit log.
Flags: `--index-db PATH`, `--audit-log PATH`, `--limit N`, `--now`, `--json`.

## Client control

### `clients list <repo>`
List known OAuth client grants from the secret-free grant metadata store. Output includes
grant id, client id/name, redirect URI/origin, scopes, write-enabled state, issue/update
times, expiry times, status, and active flag. It does not include bearer tokens, refresh
tokens, approval credentials, client secrets, or token hashes.
Flags: `--grant-store PATH` (default `<repo>/.hypermnesic/client-grants.json`), `--json`.

### `clients revoke <repo> <grant_id>`
Preview or apply revocation for a known client grant. Preview is the default. `--apply`
marks the grant revoked in the metadata store; a running server sharing that store refuses
the grant on the next access or refresh validation, and provider-level revocation kills
the live access/refresh pair.
Flags: `--grant-store PATH`, `--apply`, `--json`.

## Hooks

### `install-hooks <repo>`
Opt-in: install (or uninstall) the post-merge convergence hook. Idempotent,
non-destructive (managed block).
Flags: `--uninstall` (remove only the managed block), `--json`.

## Plugin hook helper

The Claude Code / Codex plugin ships a separate helper script, not a `hypermnesic` CLI
subcommand:

```sh
plugin/plugins/hypermnesic/hooks/scripts/hypermnesic_hook_status.py status --json --host claude
plugin/plugins/hypermnesic/hooks/scripts/hypermnesic_hook_status.py test-recall "Project Atlas" --json --host claude
```

`status` reports the last proactive auto-recall outcome, host, enabled state, endpoint category,
credential category, hit count, degraded state, and a short explanation. Missing status files return
`never_run`. `test-recall` runs the same bounded hook search path for an explicit query and prints
sanitized path/heading/snippet previews. Neither mode prints endpoint URLs, Authorization headers,
tokens, full prompts, or raw large snippets.

Environment controls:

- `HYPERMNESIC_HOOK_STATUS_FILE` — override the user-state status JSON path.
- `HYPERMNESIC_HOOK_DISABLE_LOOKUP=1` — disable auto-recall for this plugin install.
- `HYPERMNESIC_HOOK_DISABLED_HOSTS=claude,codex` — disable auto-recall for listed hosts only.

## Setup diagnostics

### `doctor <repo>`
Non-mutating setup diagnostics. Reports local git/index/dense state, consent-secret file
presence/permissions when provided, Tailscale readiness when a public URL is provided,
cloud service-unit presence, OAuth discovery, unauthenticated auth challenge, write
availability, and client-specific next actions.
Flags: `--public-url URL`, `--resource URL` (defaults to `--public-url`), `--env-file PATH`
(check existence/permissions only; never prints contents), `--json`.

### `status <repo>`
Alias for `doctor <repo>` with the same flags and JSON shape.

## Serving & provisioning

### `serve`
Run the tailnet MCP server (read tools always; the gated `commit_note` write tool with
`--enable-write`). Binds a specific Tailscale IP (refuses `0.0.0.0`).
Flags: `--index-db PATH` (required), `--host IP` (required; the Tailscale interface IP),
`--port N` (default 8848), `--path /mcp`, `--enable-write`, `--allow-tailnet-write`
(accept tailnet membership as the write boundary — CGNAT bind only), `--allowlist PREFIX`
(repeatable; narrow the write surface — omit for the blocklist default), `--repo PATH`,
`--auth-issuer-url URL`, `--auth-resource-url URL`, `--required-scope SCOPE` (repeatable).

### `serve-cloud`
Run the **public** cloud OAuth MCP — the unified network lane (DCR + PKCE AS + the
operator-consent gate + a write-enabled serve), exposed via Funnel. The operator approval
token is read from `HYPERMNESIC_CLOUD_APPROVAL_TOKEN` (env, never a flag).
Flags: `--index-db PATH` (required), `--host` (default 127.0.0.1), `--port N` (default
8850), `--path /mcp`, `--public-url URL` (required), `--resource URL` (required),
`--repo PATH`, `--token-ttl N` (default 3600), `--allowlist PREFIX` (repeatable).

### `setup <repo>`
One idempotent command to bring the unified public OAuth endpoint online: render + start
the service, persist the consent secret, configure the funnel, verify the live HTTPS
discovery chain. Fail-closed (no partial state).
Flags: `--public-url URL` (required), `--resource URL` (defaults to `--public-url`),
`--host` (default 127.0.0.1), `--port N` (default 8850), `--path` (default `/`),
`--env-file PATH`, `--allowlist PREFIX` (repeatable), `--token-ttl N`, `--json`.
JSON output includes `milestones`, `what_this_means`, and `client_next_actions` in
addition to the rendered service, route, and discovery fields.

### `install [repo]`
Provision a host into a role: render artifacts, write role config, install the
convergence hook. Live service start + index build are returned as manual steps.
Flags: `--role {single|master|client}` (required), `--bind IP`, `--service
{systemd|docker}`, `--master-url URL`, `--mcp-config PATH`, `--port N`, `--path /mcp`,
`--auth-issuer-url URL`, `--auth-resource-url URL`, `--required-scope SCOPE` (repeatable),
`--json`.

---

See [`docs/reference/configuration.md`](configuration.md) for environment variables and
tunables, and [`docs/guides/getting-started.md`](../guides/getting-started.md) for the
end-to-end setup paths.
