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
Async embed pass: fill dense vectors that lag lexical (closes the AE5 dense lag), for both
the chunk lane and the doc-surface lane.
Flags: `--batch N` (requests per embedding call, default 128; the pass halves it adaptively
when the provider answers 429 and keeps the size that works), `--budget N` (at most N stale
chunks **and** N missing doc surfaces this pass — the scheduled tick is
`--batch 32 --budget 32`; omit it to drain the whole backlog), `--index-db PATH`, `--json`.

`--json` emits one validated report on success, clean no-op, deferral or caught failure:
`status` (`complete` | `noop` | `budget_partial` | `lock_busy` | `failed`),
`chunks_embedded` / `docs_embedded` / `rate_limit_retries` (non-negative actual integers),
`effective_batch` (the batch in force at the end — it equals the requested `--batch` when
no 429 occurred), `stale_left` / `docs_stale_left` (actual remaining work; `null` only when
the measurement itself is impossible, e.g. a lock deferral), `reason`, sanitized
`provider_code` / `provider_type` (reported provider metadata, bounded and allowlisted —
never a raw body, input text, header or secret) and `account_state: "unverified"` always.
A `budget_partial` report is exit 0 with real remaining work, never a completion claim.
`lock_busy` is exit 0 with zero paid calls (another dense fill/build owns the maintenance
mutex). An unrecovered one-input 429 — including a quota-coded body — is `failed` exit 1
with the actual partial counters and remaining work; a configuration/auth/API/DB failure is
also nonzero. The CLI validates the report before returning 0: an invalid or missing report
is itself a nonzero failure. Without `--json`, a rate-limited failure keeps the historical
behavior — one plain retryable stderr line, exit 1, no stdout, no traceback and no
credit/billing verdict — and other reasons print their own reason and exit 1. New reports
are an intentional extension to the previous empty-stdout failure behavior.
With `HYPERMNESIC_SPEND_ENVELOPE` set, an unusable/exhausted spend state is one of those other
reasons: `failed`, exit 1, `reason: spend_envelope_*`, zero provider calls and no rate-limit
claim (see the [configuration reference](configuration.md#spend-envelope-optional-hard-ceiling-on-embeddings)).

### `reindex <repo>`
Rebuild the index. `--isolated` builds in a worktree and swaps atomically so narrow
writers never block.
Flags: `--state-dir DIR`, `--isolated`, `--json`.
While another bulk dense operation owns the shared maintenance mutex, `index`, `reindex`
and `init` exit nonzero without starting a build or making a provider call (named
deferral); `commit-note` writes are not blocked by it.

### `init <repo>`
Zero-infra drop-in: index a repo in place (in-repo `.hypermnesic/` state).
Flags: `--no-rebuild`, `--json`.

### `converge <repo>`
Pre-warm: catch the index up to `HEAD` + a bounded dense fill (the post-merge hook's
entrypoint; also a manual warm).
Flags: `--batch N` (chunks per embedding request, default 128; halves adaptively on a
429), `--index-db PATH`, `--authoring-host` (also refresh the uncommitted working-tree
overlay), `--now` (force a non-debounced pass), `--json`.
`--json` additionally reports `effective_batch` (the batch in force at the end — it equals
the requested `--batch` when no 429 occurred, and stays the requested value on a
`debounced`/`lock_busy`/`oversized_delta` result that returns before the dense fill),
`rate_limit_retries` for the bounded dense fill, and `dense_deferred` /
`dense_deferred_reason`: when another bulk dense pass owns the shared maintenance mutex the
lexical catch-up and checkpoint still complete, zero provider calls are made, and the next
read retries the dense slice. The per-lane dense budget is capped at 32 chunk + 32
doc-surface inputs (`CONVERGE_EMBED_BUDGET`), so a public question is never preceded by a
128-input bulk burst. A rate-limited fill degrades to lexical/graph
(`degraded_reason: "rate_limited"`) after the batch ladder is exhausted — converge never
raises on the read path.

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

JSON output includes `root`, `depth`, `folders`, `truncated`, `omitted`,
`manual_reindex_recommended`, and `agent_instruction`. `agent_instruction` is `{source,
content}` when the requested root has a direct `AGENTS.md` file, falls back to direct
`CLAUDE.md` when `AGENTS.md` is absent, and is `null` when neither exists. Child-folder
instruction files are not returned for a parent listing; pass that child path as `--root` to
read its local guidance. The returned content redacts local absolute paths and endpoint URLs
before printing JSON, while preserving repo-relative paths.

Use this before writes when the destination is unclear. Durable project memory belongs in
Hypermnesic; behavioural preference/session memory belongs in Honcho or an equivalent adjacent
layer by default.

## Writing

### `commit-note <repo> <path>`
Guarded note write (guard + diff-or-die gate + single-path git commit). By default it is a
**dry-run, read-only** preview (zero side effects; prints the diff); add `--commit` to land
the write for real (git commit + push, index follows as a projection).
Flags: `--body TEXT`, `--body-file PATH`, `--summary TEXT`, `--commit`, `--json` (`--json`
reports `new_sha` on a real write).

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
(check existence/permissions only; never prints contents), `--check-dense-live` (opt into a
live embedding smoke check; skipped by default), `--json`.

Dense diagnostics use process `OPENAI_API_KEY` first, then the target repo's gitignored
`.env` even when the command is launched from another working directory. JSON output includes
secret-free dense details such as `key_source`, `dense_state`, `live_check`, and vector coverage.
`index_missing_or_unbuilt` points to index initialization; `vectors_stale_or_absent` points to
`hypermnesic converge /path/to/vault --now --json` before resorting to a full reindex.

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
When `--repo` is omitted, `--index-db` must have the standard shape
`<repo>/.hypermnesic/index.db`; pass `--repo /path/to/vault` for any custom index location so
dense credential lookup is not guessed from an unrelated parent directory.

### `serve-cloud`
Run the **public** cloud OAuth MCP — the unified network lane (DCR + PKCE AS + the
operator-consent gate + a write-enabled serve), exposed via Funnel. The operator approval
token is read from `HYPERMNESIC_CLOUD_APPROVAL_TOKEN` (env, never a flag).
Flags: `--index-db PATH` (required), `--host` (default 127.0.0.1), `--port N` (default
8850), `--path /mcp`, `--public-url URL` (required), `--resource URL` (required),
`--repo PATH`, `--token-ttl N` (default `172800` / 48h; env:
`HYPERMNESIC_TOKEN_TTL_SECONDS`), `--default-client-scopes SCOPE ...`
(default: `read`; env: `HYPERMNESIC_DEFAULT_CLIENT_SCOPES=read,write`), `--allowlist
PREFIX` (repeatable). When `--repo` is omitted, `--index-db` must be
`<repo>/.hypermnesic/index.db`; pass `--repo` for custom index locations.

### `setup <repo>`
One idempotent command to bring the unified public OAuth endpoint online: render + start
the service, persist the consent secret, configure the funnel, verify the live HTTPS
discovery chain. Fail-closed (no partial state).
Flags: `--public-url URL` (required), `--resource URL` (defaults to `--public-url`),
`--host` (default 127.0.0.1), `--port N` (default 8850), `--path` (default `/`),
`--env-file PATH`, `--allowlist PREFIX` (repeatable), `--token-ttl N` (default
`172800` / 48h; env: `HYPERMNESIC_TOKEN_TTL_SECONDS`),
`--default-client-scopes SCOPE ...` (default: `read`; env:
`HYPERMNESIC_DEFAULT_CLIENT_SCOPES=read,write`), `--json`.
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
