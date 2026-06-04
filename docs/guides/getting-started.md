# Getting started

This guide expands the [README quick start](../../README.md#quick-start) with
prerequisites, verification, and failure modes for the four ways to run hypermnesic.

- **A. Prove local memory works** — validate the value path before remote setup.
- **B. Self-host the endpoint** — you hold a vault and serve it to your apps.
- **C. Connect a client** — point an app at an existing endpoint.
- **D. Use it locally** — drive the engine directly with the CLI, no network.
- **E. Control memory** — inspect, export, forget/delete, revert, and audit from owner
  commands.
- **F. Control clients** — inspect read/write grants and revoke client access.
- **G. Diagnose plugin recall** — inspect hook status, run test recall, and pause auto-recall.

## Prerequisites

- **Python ≥ 3.11** and [**uv**](https://docs.astral.sh/uv/).
- A **git repository of markdown notes** (your vault). Files are the source of truth.
- An **`OPENAI_API_KEY`** for dense retrieval. Without it the engine still works in
  **lexical-only** mode (FTS5), just without the dense channel — see "Offline / degraded".
- For the network surface: **[Tailscale](https://tailscale.com)** installed and logged
  in (`tailscale up`). hypermnesic uses **Tailscale Funnel** for public HTTPS + automatic
  TLS, so there is no reverse proxy or certificate to manage.

## A. Prove local memory works

Run this first on the machine that holds your vault:

```sh
uv tool install .                              # install the `hypermnesic` CLI (from a clone)
hypermnesic local-proof /path/to/your/vault    # no network or client setup required
```

If you want a disposable sample before pointing at your own notes:

```sh
hypermnesic local-proof --demo-dir /tmp/hypermnesic-demo
```

A successful proof prints **Local memory works** and shows:

- the repo-relative markdown source path that answered the question;
- the disposable `.hypermnesic/index.db` projection path;
- whether recall is lexical-only or dense-enabled;
- a `commit_note` dry-run preview destination and diff, with no write commit.

For agents and scripts:

```sh
hypermnesic local-proof /path/to/your/vault --json
```

The JSON contract includes `status`, `completed_milestones`, `degraded_capabilities`,
`source_path`, `retrieval`, `write_preview`, `next_action`, and `error`.

### Failure modes (A)

- **Path is not a git repo.** Initialize the vault with git first, or run with
  `--demo-dir` to create a tiny proof vault.
- **No retrieval hit.** Add a markdown note containing the answer and rerun with
  `--query`, or use `--seed-sample` when you explicitly want the deterministic sample
  note added to an existing repo.
- **Lexical-only degraded state.** Local memory still works from exact text in markdown
  files. Configure `OPENAI_API_KEY` when you want dense ranking and fuzzier recall.

## B. Self-host the endpoint

After the local proof succeeds:

```sh
hypermnesic setup /path/to/your/vault \
  --public-url https://<your-host>.ts.net/mcp

hypermnesic doctor /path/to/your/vault \
  --public-url https://<your-host>.ts.net/mcp
```

`setup` is idempotent: it renders + starts the cloud service, generates an owner-only
**consent secret** (`~/.config/hypermnesic-cloud/cloud.env`, `chmod 600`), configures the
Tailscale funnel (the `/mcp` mount + the OAuth discovery well-knowns), then **verifies the
live HTTPS discovery chain** before reporting success. Re-running converges to the same
state. `--resource` defaults to `--public-url`; pass it only when the OAuth resource
identifier differs.

`doctor` and its alias `status` are non-mutating. They do not start services, rewrite
configuration, create tokens, change funnel routes, modify the vault, or create git commits.
Use `--json` when an agent or CI check needs the structured status contract.

**Verify the discovery chain** (what `setup` checks, and what a client needs):

```sh
curl -fsS https://<your-host>.ts.net/.well-known/oauth-protected-resource | jq .
curl -fsS https://<your-host>.ts.net/.well-known/oauth-authorization-server | jq .
```

Both must return JSON. If they 404 or time out, the funnel or service isn't up — see
failure modes below.

### Failure modes (B)

| Doctor/status code | What it means | Next action |
|---|---|---|
| `initialize_git` | The vault path is not a git repo. | Run `git init`, commit markdown notes, then rerun local proof. |
| `initialize_index` | The disposable `.hypermnesic/index.db` projection is missing or stale. | Run `hypermnesic local-proof /path/to/vault` or `hypermnesic init /path/to/vault`. |
| `configure_key` | Dense retrieval is not configured. Lexical recall still works. | Set `OPENAI_API_KEY` when you want dense ranking and fuzzier recall. |
| `authenticate_tailscale` | Tailscale is missing or not logged in. | Install Tailscale and run `tailscale up`; setup does not manage Tailscale lifecycle. |
| `rerun_setup` | The cloud service unit or consent-secret file is missing. | Re-run `hypermnesic setup /path/to/vault --public-url https://<your-host>.ts.net/mcp`. |
| `repair_funnel` | OAuth well-known metadata did not resolve. | Check `tailscale funnel status`, then rerun setup. |
| `repair_auth` | The endpoint did not challenge unauthenticated requests. | Confirm the public URL points at the OAuth `serve-cloud` lane, then rerun setup. |
| `request_write_scope` | Remote write could not be verified or the client lacks write. | Reconnect the client and approve write scope after discovery is healthy. |
| `provide_public_url` | Only local checks ran. | Add `--public-url https://<your-host>.ts.net/mcp` to run remote checks. |

`setup` is fail-closed: preflight failures leave no service/funnel/secret side effects. If
`setup` fails after applying routes because discovery does not resolve, fix the route or
service cause and rerun; setup converges the same declarative route set.

## C. Connect a client (any remote app)

Point the app's MCP server at your endpoint URL — OAuth is automatic:

- **Claude / ChatGPT connectors, Claude Code plugin, Codex:** add the MCP server URL
  `https://<your-host>.ts.net/mcp`. On first connect the app discovers the OAuth server,
  opens a browser once to authorize, then silently refreshes.
- **Read vs. write:** read is the default. To grant the `commit_note` write tool, approve
  **write** on the consent page (enter your approval token from
  `~/.config/hypermnesic-cloud/cloud.env`). The page shows exactly which scopes you grant,
  explains that write cannot bypass Hypermnesic write guards, and lets you reject or cancel.
- **Claude Code / Codex plugin:** install the plugin in `plugin/` and set
  `HYPERMNESIC_MCP_URL` to your endpoint (the bundled `.mcp.json` is discovery-only and
  carries no host or token). The optional auto-recall hook uses the same URL plus
  `HYPERMNESIC_MCP_TOKEN` only when its own read route requires an HTTP credential. See
  [`plugin/README.md`](../../plugin/README.md).
- **Obsidian companion:** read-only over your tailnet — point it at the tailnet read route
  `http://<tailnet-ip>:8848/mcp` (no OAuth; tailnet membership is the boundary).

### Failure modes (C)

- **Browser login never appears / connection fails:** the app needs OAuth *discovery* —
  confirm the well-knowns (above) resolve. A static `Authorization` header in the wiring
  would suppress discovery; the bundled `.mcp.json` deliberately omits one.
- **401 after a while:** the token expired and refresh failed; reconnect to re-authorize.
- **Write refused with `insufficient_scope`:** reconnect the client and approve write. This
  only allows `commit_note` requests; protected paths, frontmatter, dirty-tree, head-drift,
  audit, and git coordination guards still apply.

## D. Use it locally (on the engine host)

The host that runs the engine skips the network and uses the CLI:

```sh
hypermnesic local-proof /path/to/vault                           # first local value proof
hypermnesic retrieve /path/to/vault "what do we know about X"   # hybrid search
hypermnesic think    /path/to/vault "topic"                     # thinking-mode
hypermnesic resolve  /path/to/vault "Some Entity"               # name → page path
hypermnesic list-folders /path/to/vault                         # writable folder taxonomy
hypermnesic commit-note  /path/to/vault notes/x.md --body "…"   # git-first write (dry-run preview)
hypermnesic memory list /path/to/vault                          # remembered files
hypermnesic memory write-scope /path/to/vault                    # what agents may write
hypermnesic memory forget /path/to/vault notes/bad.md            # preview delete/forget
hypermnesic clients list /path/to/vault                          # known OAuth grants
```

See the full [CLI reference](../reference/cli.md) and the
[memory control guide](memory-control.md). For consent and revocation details, see
[consent and clients](consent-and-clients.md).

## E. Control memory

Use `hypermnesic memory` when you need to answer "what does Hypermnesic remember and
how do I remove it?"

```sh
hypermnesic memory inspect /path/to/vault notes/decision.md
hypermnesic memory export /path/to/vault --folder projects/acme/ --dest ./hypermnesic-export
hypermnesic memory audit /path/to/vault --json
```

Forget/delete is preview-first. Without `--apply`, the command shows the target path,
guard result, git effect, and verification plan. With `--apply`, it removes the current
source file as a new git commit and updates the disposable index projection. It does not
rewrite git history or delete old chat contexts.

## F. Control clients

Use `hypermnesic clients` when you need to answer "which remote clients can read or
write, and how do I revoke them?"

```sh
hypermnesic clients list /path/to/vault --json
hypermnesic clients revoke /path/to/vault <grant-id>      # preview
hypermnesic clients revoke /path/to/vault <grant-id> --apply
```

The grant list is metadata only: client identity, redirect origin, scopes, issue/update
times, expiry times, status, and write-enabled state. It never prints bearer tokens,
refresh tokens, approval credentials, client secrets, or credential file contents.

## G. Diagnose plugin recall

Claude Code / Codex plugin auto-recall is intentionally silent during normal turns unless it has
bounded context to inject. Check it out-of-band from the installed plugin checkout:

```sh
hooks/scripts/hypermnesic_hook_status.py status --json --host claude
hooks/scripts/hypermnesic_hook_status.py test-recall "Project Atlas" --json --host claude
```

Status distinguishes `off_topic`, `disabled_global`, `disabled_host`,
`unconfigured_endpoint`, `missing_credential`, `auth_expired`, `timeout`, `lookup_failed`,
`no_hits`, `degraded_lexical_only`, and `success`. Output includes endpoint and credential
categories, not endpoint URLs, tokens, headers, or full prompts.

Pause proactive recall without uninstalling the plugin:

```sh
export HYPERMNESIC_HOOK_DISABLE_LOOKUP=1
export HYPERMNESIC_HOOK_DISABLED_HOSTS=codex
```

This affects only auto-recall. MCP tools remain available through OAuth discovery, and local CLI
use on the engine host is unchanged.

## Offline / degraded operation

Dense retrieval is optional. With no `OPENAI_API_KEY` (or the embedding API
unreachable), every read still answers from **lexical (FTS5) + graph** and flags
`degraded_lexical_only`. Reads also stay fresh without a manual reindex: each one
converges the lexical index up to `HEAD` first (the dense lag fills in the background as
the key/API recover). This is the same mode the test suite runs in.
