---
type: Reference
title: CLI Surface
description: The engine-host-local hypermnesic command line — 22 subcommands by role, the shared conventions, which commands preview by default, and which are CLI twins of MCP tools.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-f9fcdc4150867822e80d6070
    resource: repo://docs/reference/cli.md
  - id: openwiki-source-deb171642843c8fef279b12a
    resource: repo://docs/reference/configuration.md
  - id: openwiki-source-e2983cb60d29dab96c31cfed
    resource: repo://src/hypermnesic/auth_cloud.py
  - id: openwiki-source-9b37eab1bcb7a0dabc8255c1
    resource: repo://src/hypermnesic/cli.py
  - id: openwiki-source-d0135879c44e5d0086df3a05
    resource: repo://src/hypermnesic/client_control.py
  - id: openwiki-source-f103fa2315aae36568406e00
    resource: repo://src/hypermnesic/commit_note.py
  - id: openwiki-source-c76fa3ae1f9c3796f441ee08
    resource: repo://src/hypermnesic/converge.py
  - id: openwiki-source-dc8a4871d5ced7a62fac4926
    resource: repo://src/hypermnesic/daily_review.py
  - id: openwiki-source-1bbdc3310a71beeeab5013ef
    resource: repo://src/hypermnesic/doctor.py
  - id: openwiki-source-eca76e73bbc2749831def863
    resource: repo://src/hypermnesic/embed.py
  - id: openwiki-source-a549bbb642c1fa61b486d5ae
    resource: repo://src/hypermnesic/folders.py
  - id: openwiki-source-d0c2638cdea3e85ab949dd06
    resource: repo://src/hypermnesic/index.py
  - id: openwiki-source-54a007908deccb21b5ddc567
    resource: repo://src/hypermnesic/install.py
  - id: openwiki-source-33b20611aee0ccb46de27828
    resource: repo://src/hypermnesic/local_proof.py
  - id: openwiki-source-37433895d4b7b6af7cd92f4f
    resource: repo://src/hypermnesic/mcp_server.py
  - id: openwiki-source-bf30bdf8a5e94f3f19416f00
    resource: repo://src/hypermnesic/memory_control.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-9ec6473d05fcc2cd40915af2
    resource: repo://tests/test_cli.py
  - id: openwiki-source-f266c4d52f0afb99267b94f3
    resource: repo://tests/test_install.py
  - id: openwiki-source-937978f36359ca361ddca50f
    resource: repo://tests/test_reindex_isolated.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# CLI Surface

The `hypermnesic` CLI is the **engine-host-local** surface. Unlike the MCP lanes it skips
the network entirely and drives the index, retrieval, write, and serve paths directly. It is
the surface you use on the machine that holds the vault; remote clients use
[the MCP tool surface](mcp-tool-surface.md) instead.

The authority for what exists is the parser construction in `cli.py`, not this page or any
prose reference — there are **22 top-level subcommands**, two of which (`memory` and
`clients`) are groups with their own subcommands.

## Shared conventions

- **`--json` everywhere**, emitted with `ensure_ascii=False` so non-ASCII vault content
  survives the round trip rather than being escaped.
- **Every read subcommand converges the index to `HEAD` first.** Several accept `--now` to
  force a non-debounced pass, which is what you need to recall something you committed
  moments ago inside the debounce window. See [Read-Time Convergence](read-time-convergence.md).
- **`--index-db` defaults to `<repo>/.hypermnesic`.** Pass it explicitly to point at a
  non-standard index location.
- **Credential values are never echoed.** Diagnostics report *categories* and file
  permissions, never contents.
- `hypermnesic --version` prints the package version.

## Local proof

**`local-proof [repo]`** — the first command a new user should run, and deliberately the one
that comes *before* any endpoint concept. Against an existing vault it validates that the
repository is a markdown git repo, projects committed files into the index, retrieves an
answer to a natural question, shows the repo-relative source path the answer came from, and
previews a write as a **dry-run diff with no commit**. `--demo-dir` creates a tiny git-backed
demo vault instead. `--dense` opts into the embedding channel; the default proof is lexical
so it works with no API key. The JSON output reports completed milestones, degraded
capabilities, the source path, the retrieval result, the write preview, the index path, a
next action, and any error. See [Provisioning and Diagnostics](provisioning-and-diagnostics.md).

## Indexing

| Command | What it does |
|---|---|
| `index <repo>` | Build the index. `--state-dir` keeps index state outside the corpus; `--no-rebuild` skips deleting an existing index first. |
| `embed <repo>` | Async pass that fills dense vectors lagging the lexical channel. |
| `reindex <repo>` | Rebuild. `--isolated` builds in a git worktree and swaps atomically so writers are never blocked. |
| `init <repo>` | Zero-infrastructure drop-in: index a repo in place with in-repo state. |
| `converge <repo>` | Catch the index up to `HEAD` plus a bounded dense fill — the post-merge hook's entrypoint and a manual warm. `--now` forces a non-debounced pass; `--authoring-host` also refreshes the uncommitted working-tree overlay. |

`reindex` runs an embedding smoke check before rebuilding, so a rebuild does not silently
produce a lexical-only index when the provider is misconfigured.

## Reading — all read-only, all converge first

These four are **CLI twins of MCP tools** and return the same shapes, so a script and a
remote client see the same data:

| CLI | MCP tool | Notes |
|---|---|---|
| `retrieve <repo> <query>` | `search` | Same hit shape. `--k` defaults to 10. |
| `think <repo> <topic>` | `think` | Never writes. `--k` defaults to 8. |
| `resolve <repo> <name>` | `resolve` | Prints the `slug` to wikilink, or null. |
| `list-folders <repo>` | `list_folders` | Same output shape, including `agent_instruction`. `--root`/`--depth` drill down; `--allowlist` previews writability under a narrowed surface. |

## Writing

**`commit-note <repo> <path>` is a preview, not a write.** It runs the real guard and the
real frontmatter gate and prints the diff, with zero side effects — it calls the write path
in dry-run mode. Use `--body`, `--body-file`, and `--summary` to supply content. This is the
safe way to find out whether a write *would* be refused. See
[Git-First Write Path](git-first-write-path.md).

**`capture <repo> <text>`** does commit: it lands raw text under `sources/` through the
free-append zone, immediately and with no organization required. See
[Capture and Thinking Surfaces](capture-and-thinking-surfaces.md).

**`daily-review <repo>`** generates a review-gated dashboard proposal under
`dashboards/daily-review.md` composing capture backlog, recent writes, generated navigation
and salience links, degraded/offline state, and cleanup next actions. It does not move,
delete, or rewrite any source note. See
[Review and Navigation Surfaces](review-and-navigation-surfaces.md).

## Memory control

`memory` is the owner control centre, with seven subcommands. **Every destructive one
previews by default** and requires `--apply` to act:

| Subcommand | Behaviour |
|---|---|
| `memory list` | Remembered files with path, title, snippet, source type, last commit, audit actor when known, and writable/protected state. Filters: `--folder`, `--source-type`, `--writable`, `--protected`, `--recent`. |
| `memory inspect` | One file's provenance in file and commit terms — deliberately without a raw full-body field. |
| `memory write-scope` | Answers "what may an agent write?" using the same guard as `list-folders` and `commit_note`. |
| `memory export` | Copies selected markdown to `--dest` with a provenance manifest. A markdown export, not an index export. |
| `memory forget` | **Preview by default.** `--apply` removes the source file as a new commit, updates the projection, and appends an audit entry. |
| `memory revert` | **Preview by default.** `--apply` reverts a safe recent single-file markdown commit. |
| `memory audit` | Recent writes, forgets, reverts, reconciles, and refusals from the summary-only log. |

## Client control

| Subcommand | Behaviour |
|---|---|
| `clients list` | Known OAuth grants from the secret-free metadata store — ids, client name, redirect origin, scopes, write-enabled state, timestamps, status. Never tokens or secrets. |
| `clients revoke <grant_id>` | **Preview by default.** `--apply` marks the grant revoked; a running server sharing the store refuses it on the next validation. |

See [Memory and Client Control](memory-and-client-control.md).

## Hooks

**`install-hooks <repo>`** installs (or with `--uninstall` removes) the post-merge
convergence hook. It is opt-in, idempotent, and non-destructive: it manages only its own
block inside the hook file, so a hand-written hook survives.

## Diagnostics

**`doctor <repo>`** and **`status <repo>`** are the same command — the parser builds both
names from one definition, so their flags and JSON shape cannot drift apart. Both are
**non-mutating**. They report local git/index/dense state, consent-secret file presence and
permissions when a path is supplied, Tailscale readiness and OAuth discovery when a public
URL is supplied, the unauthenticated auth challenge, write availability, and
client-specific next actions. `--check-dense-live` opts into a live embedding smoke check;
it is skipped by default so diagnosis works offline.

## Serving and provisioning

| Command | Role |
|---|---|
| `serve` | The tailnet MCP server. Requires `--index-db` and `--host` (a specific Tailscale interface IP — it refuses `0.0.0.0`). Read tools always; `--enable-write` adds the gated write tool; `--allow-tailnet-write` accepts tailnet membership as the write boundary on a CGNAT bind; `--allowlist` narrows the write surface. |
| `serve-cloud` | The public cloud OAuth MCP — the unified network lane. Requires `--index-db`, `--public-url`, and `--resource`. The operator approval token comes from the environment, never a flag. |
| `setup <repo>` | One idempotent command to bring the public endpoint online: render and start the service, persist the consent secret, configure the funnel, verify the live HTTPS discovery chain. Fail-closed. |
| `install [repo]` | Provision a host into a role (`single`, `master`, or `client`): render artifacts, write role config, install the convergence hook. Live service start and index build are returned as manual steps. |

Both serve commands take `--repo`. When it is omitted, `--index-db` must have the standard
`<repo>/.hypermnesic/index.db` shape; pass `--repo` explicitly for any custom index location
so credential lookup is not guessed from an unrelated parent directory. See
[Serving Topology and Authentication](serving-and-authentication.md) and
[Configuration and Tunables](configuration-and-tunables.md).
