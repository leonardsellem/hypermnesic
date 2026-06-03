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

There are **16 subcommands**, grouped below by role.

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

## Writing

### `commit-note <repo> <path>`
Preview what a `commit_note` write would do — **dry-run, read-only** (guard + gate run,
zero side effects; prints the diff).
Flags: `--body TEXT`, `--body-file PATH`, `--summary TEXT`, `--json`.

### `capture <repo> <text>`
Frictionless capture: land raw text in `sources/` immediately (free-append zone).
Flags: `--json`.

## Hooks

### `install-hooks <repo>`
Opt-in: install (or uninstall) the post-merge convergence hook. Idempotent,
non-destructive (managed block).
Flags: `--uninstall` (remove only the managed block), `--json`.

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
Flags: `--public-url URL` (required), `--resource URL` (required), `--host` (default
127.0.0.1), `--port N` (default 8850), `--path` (default `/`), `--env-file PATH`,
`--allowlist PREFIX` (repeatable), `--token-ttl N`, `--json`.

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
