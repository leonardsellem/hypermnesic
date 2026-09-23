---
type: Reference
title: Configuration and Tunables
description: Every knob and the consequence of changing it — environment variables and the gitignored .env, the credential lookup order and its secret-free status shape, the pinned embedding model and dimension, the convergence and folder-discovery bounds, write-zone tiers, and the cloud access-token TTL override.
tags: [configuration, environment-variables, credentials, embeddings, limits, defaults]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T16:18:12.137Z
sources:
  - id: openwiki-source-5f5b95b3d6a215fa02ceb945
    resource: repo://.env.example
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-deb171642843c8fef279b12a
    resource: repo://docs/reference/configuration.md
  - id: openwiki-source-41f901f9f19f630d69b443e1
    resource: repo://harness/parity_harness.py
  - id: openwiki-source-a6ff08c15afa112fd12ab021
    resource: repo://plugin/hermes/__init__.py
  - id: openwiki-source-f945110b610983e29a3ca313
    resource: repo://plugin/plugins/hypermnesic/hooks/scripts/hypermnesic_agent_hook.py
  - id: openwiki-source-040afdd7bd83454d678e4ad2
    resource: repo://plugin/plugins/hypermnesic/hooks/scripts/hypermnesic_hook_status.py
  - id: openwiki-source-12224262a7b33bff0baf3679
    resource: repo://scripts/preflight_public_scan.py
  - id: openwiki-source-e2983cb60d29dab96c31cfed
    resource: repo://src/hypermnesic/auth_cloud.py
  - id: openwiki-source-861fbaa0347100b4d192e5ad
    resource: repo://src/hypermnesic/auth.py
  - id: openwiki-source-9b37eab1bcb7a0dabc8255c1
    resource: repo://src/hypermnesic/cli.py
  - id: openwiki-source-5f17d71d8e2d83b9ea0bc2ae
    resource: repo://src/hypermnesic/config.py
  - id: openwiki-source-c76fa3ae1f9c3796f441ee08
    resource: repo://src/hypermnesic/converge.py
  - id: openwiki-source-1bbdc3310a71beeeab5013ef
    resource: repo://src/hypermnesic/doctor.py
  - id: openwiki-source-eca76e73bbc2749831def863
    resource: repo://src/hypermnesic/embed.py
  - id: openwiki-source-5974acb66f0bfa1a0ca1d95e
    resource: repo://src/hypermnesic/expand.py
  - id: openwiki-source-a549bbb642c1fa61b486d5ae
    resource: repo://src/hypermnesic/folders.py
  - id: openwiki-source-d0c2638cdea3e85ab949dd06
    resource: repo://src/hypermnesic/index.py
  - id: openwiki-source-54a007908deccb21b5ddc567
    resource: repo://src/hypermnesic/install.py
  - id: openwiki-source-37433895d4b7b6af7cd92f4f
    resource: repo://src/hypermnesic/mcp_server.py
  - id: openwiki-source-802c4acce1763f2c8920a3cf
    resource: repo://src/hypermnesic/propose.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-81af13fa7982f0b3becf1286
    resource: repo://tests/test_config.py
  - id: openwiki-source-9241ab90871fd251f3253d0f
    resource: repo://tests/test_mcp_server.py
generated: { by: "openwiki/0.5.0", at: "2026-09-23T16:18:12.137Z" }
---

# Configuration and Tunables

Two kinds of knob exist, and they behave differently:

- **Environment variables** — per-deployment values, read from the process environment (or the one
  key the engine parses itself out of a gitignored repo-root `.env`). Never committed, never echoed.
- **Module constants in `src/hypermnesic/config.py`** — pinned engine tunables. They are the source
  of truth; `docs/reference/configuration.md` and `.env.example` are its mirrors, and `AGENTS.md`
  makes the three move in the same PR (including any `CONVERGE_*` / budget mention in
  `ARCHITECTURE.md`).

Endpoint values in committed configuration are placeholders — `https://YOUR-HOST.ts.net/mcp` style,
never a real operator host, IP, or token; a tracked-file scan enforces that. For what a variable
*means* for the lanes that consume it, see
[Serving and Authentication](../surfaces/serving-and-authentication.md),
[Read-Time Convergence](../architecture/read-time-convergence.md) and
[Retrieval and Indexing](../architecture/retrieval-and-indexing.md).

## Environment variables

| Variable | Read by | Default / if unset | Consequence of changing it |
|---|---|---|---|
| `OPENAI_API_KEY` | `config.get_api_key`, embeddings | unset → dense retrieval unavailable | The one secret that turns the dense channel on. Absent, reads keep serving lexical + graph and say so (`degraded_lexical_only`); this is also exactly how the test suite runs (`tests/conftest.py` injects a deterministic `FakeEmbedder`). Never written to the index, the audit log, or any structured output. |
| `HYPERMNESIC_MCP_URL` | the plugin's `.mcp.json` wiring and the auto-recall hook | unset → no endpoint | Templates the MCP URL (`${HYPERMNESIC_MCP_URL:-https://YOUR-HYPERMNESIC-HOST/mcp}`). For the hook, an unset URL means silence, recorded as `unconfigured_endpoint` — never an error, never a blocked turn. |
| `HYPERMNESIC_MCP_TOKEN` | the auto-recall hook, and the `token_env` pointer emitted into an MCP client config by `install` | unset → tailnet read route | A bearer credential for the hook's bounded read on a non-tailnet endpoint. Unset on a non-tailnet endpoint the hook stops at `missing_credential` rather than sending an unauthenticated request. The MCP tool wiring itself needs no token — OAuth discovery handles it. |
| `HYPERMNESIC_HOOK_STATUS_FILE` | hook status writer | `${XDG_STATE_HOME:-~/.local/state}/hypermnesic/hook-status.json` | Redirects the non-secret hook status JSON. The file holds outcome categories, timestamps, endpoint/credential categories, host, enabled state, hit count, and degraded state — never tokens, headers, endpoint URLs, or full prompts. |
| `HYPERMNESIC_HOOK_DISABLE_LOOKUP` | hook | unset → recall enabled | `1` disables proactive recall for the whole plugin install without uninstalling the plugin or removing MCP tools. |
| `HYPERMNESIC_HOOK_DISABLED_HOSTS` | hook | unset → all hosts | Comma-separated host names (`claude`, `codex`) to disable proactive recall per host. |
| `HYPERMNESIC_HOOK_FIXTURE` | hook (test seam) | unset → real network call | Points the hook's search at a JSON fixture instead of the network; test-only. |
| `HYPERMNESIC_CLOUD_APPROVAL_TOKEN` | `serve-cloud` / `setup` | unset → the public lane cannot start | The operator approval token that gates every public connection, read from the environment **only** — never a CLI flag, so it cannot leak via the process table or shell history. `serve-cloud` refuses to start below `auth_cloud.MIN_APPROVAL_TOKEN_LEN` (24) characters. |
| `HYPERMNESIC_DEFAULT_CLIENT_SCOPES` | `serve-cloud` / `setup` (CLI argument resolution) | `read` | Comma- or space-separated OAuth scopes requested by default when a dynamically registered client omits `scope`. `read,write` makes new approvals ask for `commit_note` access too. It changes only what is *requested*: the consent page still requires the approval token and every write guard still applies. |
| `HYPERMNESIC_TOKEN_TTL_SECONDS` | `serve-cloud` / `setup` via `config.cloud_token_ttl_seconds` | `172800` (48 h) | Cloud-lane access-token lifetime. See [The access-token TTL override](#the-access-token-ttl-override). |
| `HYPERMNESIC_RS_CLIENT_ID`, `HYPERMNESIC_RS_CLIENT_SECRET` | `auth.verify_raw_from_discovery` (tailnet AS lane) | unset → an auth-on tailnet serve fails at the first token | RFC 7662 introspection credentials for the resource server. Never committed; a missing pair raises a `ResourceAuthError` naming both variables. |
| `HYPERMNESIC_REPO`, `HYPERMNESIC_INDEX_DB`, `HYPERMNESIC_HERMES_RECALL` | the Hermes plugin's `pre_llm_call` hook | unset → hook silent | Configures the plugin's local-CLI recall path (vault, optional index DB, on/off). No secret, no endpoint; see [Agent Plugins and Hooks](../integrations/agent-plugins-and-hooks.md). |

### The gitignored `.env`

The engine parses exactly one variable out of a `.env` file, by hand, with no dotenv library: a line
that (after stripping) begins `OPENAI_API_KEY=`, with surrounding quotes and whitespace removed
(`config._read_dotenv_key_from`). `export` prefixes and variable interpolation are therefore **not**
supported by that reader. Everything else in the table above must be in the process environment.

In a provisioned deployment that distinction disappears, because systemd loads the files into the
environment before `serve-cloud` starts: the rendered cloud unit carries
`EnvironmentFile=-<repo>/.env` plus `EnvironmentFile=-<owner-only cloud env>`, and references secrets
by name only (`install.render_cloud_systemd_unit`). `.env` is also a governance-protected path in
the write guard, so `commit_note` can never author or modify it (`serialize.protected_reason`).

## Credential lookup order

For a **repo-addressed** command or server — one that knows which vault it is operating on — the
OpenAI key resolves in exactly this order (`config._api_key_from_sources`):

1. the process environment → source category `process_env`;
2. the target repository's gitignored `<repo>/.env` → `repo_dotenv`;
3. **nothing else.** With an explicit repo there is deliberately no working-directory fallback.

Only helper paths with no repo context fall back to `cwd_dotenv`, and that path is captured at
import time (`config._DOTENV_PATHS = [Path.cwd() / ".env"]`), so it reflects the process's starting
directory. The third step is the load-bearing one: `hypermnesic doctor /path/to/vault` and an MCP
serve launched from any directory read the *vault's* `.env`, not an unrelated key from wherever the
process happened to start.

Discovery is reported through `ApiKeyStatus`, a frozen dataclass carrying `configured`, the `source`
category, the ordered tuple of categories `checked`, and an optional error **category**
(`config.ApiKeyStatus`). It contains no filesystem paths and no key material — tests assert a
sentinel key and the temp paths never appear in its `repr`. `get_api_key` raises a `ConfigError`
whose message names the categories checked and how to set one, and adds `repo_dotenv_unreadable`
when the repo `.env` exists but could not be read (`config.get_api_key`).

## A configured key is not a healthy projection

Discovery answers "is a key there", nothing more. `doctor` / `status` are offline-friendly by
default: a discovered key is reported `configured_unverified`, and only an explicit
`--check-dense-live` runs a smoke embedding and distinguishes `configured_valid` from
`configured_invalid` — without ever printing the key (`doctor._dense_retrieval_check`). The reported
states, and the next action each one produces:

| `dense_state` | When | Next action |
|---|---|---|
| `not_configured` | no key found (fail) | set `OPENAI_API_KEY` or add it to the gitignored repo `.env` |
| `configured_unverified` | key found, no `--check-dense-live` | none |
| `configured_valid` / `configured_invalid` | live smoke embed passed / failed (`--check-dense-live`) | none / check the key or the network |
| `index_missing_or_unbuilt` | key configured, no index DB to inspect | build the disposable index (`hypermnesic local-proof`) |
| `vectors_stale_or_absent` | key configured, chunk or doc vectors missing | `hypermnesic converge <repo> --now --json`, or reindex when convergence recommends it |

`repo_dotenv_unreadable` is a `fail`, not a warning: a present but unreadable key file is a
permissions problem someone must fix. `doctor --env-file PATH` inspects the consent secret file
**only** for existence and owner-only (`0600`) permissions and never reads or prints its value
(`doctor._env_file_check`). See
[Provisioning and Diagnostics](provisioning-and-diagnostics.md).

## The pinned embedding model

| Constant | Default | Read by | Consequence of changing it |
|---|---|---|---|
| `EMBED_MODEL` | `text-embedding-3-large` | `embed.OpenAIEmbedder` | Kept equal to the parity baseline's pinned config so a comparison isolates the architecture rather than the model. Changing it invalidates the meaning of every stored vector — rebuild with `reindex`. |
| `EMBED_DIM` | `1536` | `embed.OpenAIEmbedder` (sent explicitly as `dimensions`), `index` | The dimension is baked into the schema (`vec_chunks` / `vec_docs` declare `float[config.EMBED_DIM]`), so a change requires a rebuild, not a migration. `config.assert_embedder_agrees` fails fast at build, reindex, and dense-fill entry when an embedder's `dim` disagrees. |
| `EMBED_FAILURE_COOLDOWN_SECONDS` | `300.0` | `embed.OpenAIEmbedder` | After a 429 the process refuses further embedding attempts for the window, so every read in it keeps serving lexical + graph instead of hammering a throttled provider. The observable reason separates the triggering call (`rate_limited`) from the window that follows (`cooldown`). `0` disables the cooldown. |
| `EXPANSION_MODEL` | `gpt-4o-mini` | `expand.OpenAIExpander` | A small chat model for opt-in multi-query expansion. No engine read path constructs the expander — the harnesses do (`harness/parity_harness.py --expand`) — and expansion returns `[]` on any failure, so retrieval falls back to the un-expanded query. |

## Read-time convergence tunables

These are the knobs to tune against real first-read latency; the mechanism, statuses, and failure
modes are detailed on [Read-Time Convergence](../architecture/read-time-convergence.md).

| Constant | Default | Read by | Consequence of changing it |
|---|---|---|---|
| `CONVERGE_EMBED_BUDGET` | `128` | `converge.converge`, per read | Maximum stale chunks — and at most as many paths whose doc-surface vector is missing — embedded per converging read. The default matches the indexer's embedding batch (`index._BATCH = 128`), keeping a converging read near one API round-trip. Lower it and dense coverage lags longer behind lexical; raise it and the read that pays absorbs several round-trips. |
| `CONVERGE_DEBOUNCE_SECONDS` | `5.0` | `converge.converge` | How long a completed pass suppresses the next one (a stamp in the index state dir). Too low and every read in a burst pays full convergence cost; too high and a just-committed note stays invisible that long. `--now` / `debounce_seconds=0` forces a pass, which is why the window can be generous. |
| `CONVERGE_MAX_DELTA_FILES` | `200` | `converge.converge` | Above this many changed markdown files the delta is not replayed inline: the pass serves the current consistent projection and sets `manual_reindex_recommended`. Too low and ordinary merges nag for reindexes; too high and one read absorbs a very large inline replay. |

All three are read at call time and injectable per call (`debounce_seconds`, `embed_budget`,
`max_delta_files`), which is how tests force a specific path.

## `list_folders` discovery bounds

| Constant | Default | Read by | Consequence of changing it |
|---|---|---|---|
| `LIST_FOLDERS_MAX_NODES` | `200` | the `list_folders` MCP tool, read at call time | Maximum folder entries returned. Entries are sorted **before** the cap, so the dropped tail is deterministic, and the response reports `truncated` plus an `omitted` count; narrowing `root` is how a client sees more. |
| `LIST_FOLDERS_MAX_DEPTH` | `6` | same | Ceiling on requested drill-down depth. A larger request is clamped, and the echoed `depth` reflects the clamp — never rejected. |

`folders.derive_folders` also declares these as default arguments, which are bound at import time,
but the MCP tool passes `config.LIST_FOLDERS_MAX_*` explicitly at call time, so the constants are
re-read per request (`mcp_server.py`, `folders.py`).

## Write-zone tiers, and what is *not* in config

| Constant | Default | Read by | Meaning |
|---|---|---|---|
| `IMMUTABLE_APPEND_ZONES` | `("sources/",)` | `config.is_immutable_append_zone` → `propose` | Free-append zones accept a **new** file directly with no proposal friction — frictionless capture depends on this — but never an overwrite. Every other writable path is curated: changes flow through propose-and-approve. |

It is an explicit path-prefix list, not a heuristic: a path matches only when it equals a zone minus
its trailing slash or starts with the zone prefix. Its one consumer is proposal routing, which takes
the fast path only when *every* requested change is a new file in a free-append zone
(`propose.propose`).

Note what this constant is not. It does not define **which** paths are writable. The write
**surface** is the blocklist guard in the write path (`serialize.protected_reason` plus the
governance-file fence), not a configuration value; the CLI and serve `--allowlist` flag narrows that
surface at runtime through a single coercion site, and an explicitly empty `--allowlist` on a
write-enabled serve is refused at construction rather than silently permitting nothing
(`mcp_server._effective_write_surface`, `mcp_server.build_server`). See
[Write Guard and Security Model](../architecture/write-guard-and-security-model.md).

## The access-token TTL override

`config.cloud_token_ttl_seconds(override)` resolves the cloud-lane access-token lifetime with the
precedence **explicit argument > `HYPERMNESIC_TOKEN_TTL_SECONDS` > `172800`**, and raises
`ConfigError` for a non-integer or non-positive value instead of falling back
(`config.cloud_token_ttl_seconds`).

| Surface | How the value arrives |
|---|---|
| `serve-cloud --token-ttl N` | CLI flag, resolved before the provider is built |
| `setup --token-ttl N` | resolved, then **baked into the rendered unit** as `--token-ttl <resolved>` |
| `HYPERMNESIC_TOKEN_TTL_SECONDS` | read through the same resolver when no explicit override is passed |

The default is 48 h so an overnight idle plus the next morning's digest does not 401 (`mcp-remote`
0.1.38 wipes local credentials on 401 instead of refreshing, which lands a client on a browser hang
path). It applies to the access token only: code TTL stays 300 s, pending TTL 600 s, and refresh
stays 30 days (`auth_cloud.CloudAuthProvider`).

Operational trap: because `setup` bakes the resolved value into the unit, an existing unit that
still carries `--token-ttl 3600` keeps issuing 1-hour tokens after an upgrade. Change that flag to
`172800`, or remove it and set the variable in the owner-only cloud env file, before expecting the
longer lifetime (recorded in `docs/reference/configuration.md`).

## Default client scopes

`normalize_default_client_scopes` defaults to `["read"]`, de-duplicates, accepts either comma- or
space-separated input, and rejects any scope outside `scopes_supported` (`read`, `write`) with a
`ValueError` **before** the authorization server is constructed
(`mcp_server.normalize_default_client_scopes`). The CLI resolves the flag first and falls back to
`HYPERMNESIC_DEFAULT_CLIENT_SCOPES` (`cli._default_client_scopes`); because `setup` resolves it once
and bakes `--default-client-scopes <scopes>` into the rendered unit, an environment variable set at
setup time persists as a flag, while a directly launched `serve-cloud` resolves it at start-up.

## Changing a knob safely

- Keep the three copies together: `config.py` is the source of truth, and
  `docs/reference/configuration.md`, `.env.example`, and any `ARCHITECTURE.md` budget mention are
  mirrors that ship in the same PR.
- An embedding-pinned change (`EMBED_MODEL`, `EMBED_DIM`) is a rebuild, not a flip: the dimension
  lives in the vector-table schema, so an existing index is invalidated rather than migrated.
- A new secret belongs in the environment path with a category-only status surface — never in a
  flag, a unit file, a log line, or structured output.

## Focused tests

| Behaviour | Test focus |
|---|---|
| Repo `.env` from a different cwd; process-env precedence; no cwd fallback once a repo is known | `tests/test_config.py` asserts the `source` categories, the resolved key, and that a sentinel key never appears in `repr(status)` |
| Secret-free failure | a missing key and an unreadable repo `.env` both report categories only, the second with `error == "repo_dotenv_unreadable"` |
| Repo context reaches the embedder | `OpenAIEmbedder(repo=...)` and `smoke_embed_or_die(repo=...)` pass the repo into the lazy key lookup |
| Rate-limit cooldown | a 429 raises `reason="rate_limited"`; the next call raises `reason="cooldown"` with exactly one provider call; the retry after the window reaches the provider again |
| TTL precedence | `tests/test_config.py` (default 48 h, env override, explicit override wins, invalid/zero rejected) and `tests/test_auth_cloud.py` (the issued `expires_in` and the grant record match the resolved TTL) |
| TTL and scopes reach the deployment | `tests/test_install.py` asserts `--token-ttl 172800` and `--default-client-scopes read write` land in the rendered unit with no inlined secret; `tests/test_cli.py` covers the flag and env plumbing plus the refusal of a too-weak approval token |
| Discovery bounds | `tests/test_folders.py` (sorted-before-cap, `truncated`/`omitted`, depth clamp, traversal rejection) and `tests/test_mcp_server.py` (the tool honours a patched `LIST_FOLDERS_MAX_NODES`) |
| Convergence budgets and key status | `tests/test_converge.py` / `tests/test_index.py` pass explicit budget and debounce values; `tests/test_doctor.py` covers every `dense_state`, including that a different repo's cwd `.env` is never used |
