# Getting started

This guide expands the [README quick start](../../README.md#quick-start) with
prerequisites, verification, and failure modes for the four ways to run hypermnesic.

- **A. Prove local memory works** — validate the value path before remote setup.
- **B. Self-host the endpoint** — you hold a vault and serve it to your apps.
- **C. Connect a client** — point an app at an existing endpoint.
- **D. Use it locally** — drive the engine directly with the CLI, no network.

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
  --public-url https://<your-host>.ts.net/mcp \
  --resource   https://<your-host>.ts.net/mcp
```

`setup` is idempotent: it renders + starts the cloud service, generates an owner-only
**consent secret** (`~/.config/hypermnesic-cloud/cloud.env`, `chmod 600`), configures the
Tailscale funnel (the `/mcp` mount + the OAuth discovery well-knowns), then **verifies the
live HTTPS discovery chain** before reporting success. Re-running converges to the same
state.

**Verify the discovery chain** (what `setup` checks, and what a client needs):

```sh
curl -fsS https://<your-host>.ts.net/.well-known/oauth-protected-resource | jq .
curl -fsS https://<your-host>.ts.net/.well-known/oauth-authorization-server | jq .
```

Both must return JSON. If they 404 or time out, the funnel or service isn't up — see
failure modes below.

### Failure modes (B)

- **`setup` fails / leaves nothing provisioned.** It is fail-closed: any failure leaves
  no partial state. Re-run after fixing the cause (commonly: Tailscale not logged in, or
  the funnel not permitted for your tailnet).
- **Discovery well-knowns 404.** The funnel mount is wrong or the service isn't running;
  re-run `setup` (it re-converges) and check `tailscale funnel status`.
- **Writes refused with an auth error.** A write-enabled serve requires OAuth
  (`write_enabled ⇒ auth-required`); connect via the OAuth lane, or for a local-only box
  use the CLI (path C).

## C. Connect a client (any remote app)

Point the app's MCP server at your endpoint URL — OAuth is automatic:

- **Claude / ChatGPT connectors, Claude Code plugin, Codex:** add the MCP server URL
  `https://<your-host>.ts.net/mcp`. On first connect the app discovers the OAuth server,
  opens a browser once to authorize, then silently refreshes.
- **Read vs. write:** read is the default. To grant the `commit_note` write tool, approve
  **write** on the consent page (enter your approval token from
  `~/.config/hypermnesic-cloud/cloud.env`). The page shows exactly which scopes you grant.
- **Claude Code / Codex plugin:** install the plugin in `plugin/` and set
  `HYPERMNESIC_MCP_URL` to your endpoint (the bundled `.mcp.json` is discovery-only and
  carries no host or token). See [`plugin/README.md`](../../plugin/README.md).
- **Obsidian companion:** read-only over your tailnet — point it at the tailnet read route
  `http://<tailnet-ip>:8848/mcp` (no OAuth; tailnet membership is the boundary).

### Failure modes (C)

- **Browser login never appears / connection fails:** the app needs OAuth *discovery* —
  confirm the well-knowns (above) resolve. A static `Authorization` header in the wiring
  would suppress discovery; the bundled `.mcp.json` deliberately omits one.
- **401 after a while:** the token expired and refresh failed; reconnect to re-authorize.

## D. Use it locally (on the engine host)

The host that runs the engine skips the network and uses the CLI:

```sh
hypermnesic local-proof /path/to/vault                           # first local value proof
hypermnesic retrieve /path/to/vault "what do we know about X"   # hybrid search
hypermnesic think    /path/to/vault "topic"                     # thinking-mode
hypermnesic resolve  /path/to/vault "Some Entity"               # name → page path
hypermnesic list-folders /path/to/vault                         # writable folder taxonomy
hypermnesic commit-note  /path/to/vault notes/x.md --body "…"   # git-first write (dry-run preview)
```

See the full [CLI reference](../reference/cli.md).

## Offline / degraded operation

Dense retrieval is optional. With no `OPENAI_API_KEY` (or the embedding API
unreachable), every read still answers from **lexical (FTS5) + graph** and flags
`degraded_lexical_only`. Reads also stay fresh without a manual reindex: each one
converges the lexical index up to `HEAD` first (the dense lag fills in the background as
the key/API recover). This is the same mode the test suite runs in.
