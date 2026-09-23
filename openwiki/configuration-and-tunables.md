---
type: Reference
title: Configuration and Tunables
description: Every operational knob — environment variables and their readers, the exact credential lookup order, the pinned embedding model, convergence budgets, discovery bounds, and write-zone tiers — with the consequence of changing each.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-5f5b95b3d6a215fa02ceb945
    resource: repo://.env.example
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-deb171642843c8fef279b12a
    resource: repo://docs/reference/configuration.md
  - id: openwiki-source-7e2faff78811ec16a74aaa48
    resource: repo://harness/BENCHMARKS.md
  - id: openwiki-source-040afdd7bd83454d678e4ad2
    resource: repo://plugin/plugins/hypermnesic/hooks/scripts/hypermnesic_hook_status.py
  - id: openwiki-source-12224262a7b33bff0baf3679
    resource: repo://scripts/preflight_public_scan.py
  - id: openwiki-source-e2983cb60d29dab96c31cfed
    resource: repo://src/hypermnesic/auth_cloud.py
  - id: openwiki-source-51d97e561438845ebfc72a76
    resource: repo://src/hypermnesic/capture.py
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
  - id: openwiki-source-a549bbb642c1fa61b486d5ae
    resource: repo://src/hypermnesic/folders.py
  - id: openwiki-source-d0c2638cdea3e85ab949dd06
    resource: repo://src/hypermnesic/index.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-81af13fa7982f0b3becf1286
    resource: repo://tests/test_config.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Configuration and Tunables

Two kinds of knob exist, and they behave differently:

- **Environment variables** — per-deployment values, read from the process environment or a
  gitignored repo-root `.env`. Never committed, never echoed.
- **Module constants in `config.py`** — pinned engine tunables. Changing one changes engine
  behaviour for everyone using that build, which is exactly why they live in one file
  instead of being scattered as defaults.

## Environment variables

| Variable | Read by | Effect if unset |
|---|---|---|
| `OPENAI_API_KEY` | embeddings | Dense retrieval is unavailable; reads degrade to lexical plus graph and say so. This is also how the test suite runs. |
| `HYPERMNESIC_MCP_URL` | the plugin's MCP wiring and the auto-recall hook | The plugin has no endpoint; the hook stays silent with an `unconfigured_endpoint` outcome. |
| `HYPERMNESIC_MCP_TOKEN` | the auto-recall hook only | The hook uses the tailnet read route. On a non-tailnet endpoint it stops at `missing_credential` rather than sending an unauthenticated request. The MCP tool wiring never needs this. |
| `HYPERMNESIC_HOOK_STATUS_FILE` | the hook | Status goes to the user state directory instead. |
| `HYPERMNESIC_HOOK_DISABLE_LOOKUP` | the hook | Proactive recall stays enabled. Set to `1` to disable it for the whole install. |
| `HYPERMNESIC_HOOK_DISABLED_HOSTS` | the hook | Set a comma-separated host list to disable recall per host. |
| `HYPERMNESIC_CLOUD_APPROVAL_TOKEN` | the public cloud lane | The public endpoint cannot start. **Environment only** — never a CLI flag, so it cannot leak through the process table or shell history. A minimum length is enforced. |
| `HYPERMNESIC_DEFAULT_CLIENT_SCOPES` | the public cloud lane | Defaults to `read`. Set `read,write` when new connector approvals should request write access too. This changes only what is *requested*: operator consent is still required and every write guard still applies. |

Endpoint values in your own configuration are your host's — use a placeholder like
`https://<your-host>.ts.net/mcp` in anything you commit or share. A repository-wide scan
enforces that no operator host, IP, or token ships in the public surface; see
[Testing and Release Gates](testing-and-release-gates.md).

The OAuth consent secret is persisted by `setup` to an owner-only env file with restrictive
permissions and is never committed. Diagnostics check only that the file exists and is
owner-only; they never read or print its value. See
[Provisioning and Diagnostics](provisioning-and-diagnostics.md).

## Credential lookup order

For a **repo-addressed** command or server — one that knows which vault it is operating on —
the OpenAI key is resolved in exactly this order:

1. the process environment;
2. the target repository's gitignored `<repo>/.env`;
3. **nothing else.** There is deliberately no working-directory fallback once a repo is known.

That third step is the load-bearing one. It means `hypermnesic doctor /path/to/vault` and an
MCP server launched from any working directory both read the *vault's* `.env`, rather than
picking up an unrelated key from wherever the process happened to start. Only helper paths
with no repo context fall back to the current directory.

Discovery is reported **secret-free**: the status object carries whether a key is configured,
which source category supplied it (`process_env`, `repo_dotenv`, `cwd_dotenv`, or `missing`),
the ordered list of source categories checked, and an error category such as an unreadable
repo `.env`. It contains no filesystem paths and no key material. When no key is found, the
raised error names the categories checked and how to set one — never a value.

## The pinned embedding model

| Constant | Value | Why it is pinned |
|---|---|---|
| `EMBED_MODEL` | `text-embedding-3-large` | Pinning the model in one place is what lets a parity or benchmark result isolate the *architecture* variable rather than measuring a model change. |
| `EMBED_DIM` | `1536` | Sent explicitly to the API and asserted at startup. |
| `EXPANSION_MODEL` | `gpt-4o-mini` | Optional multi-query expansion — a ranking aid only, opt-in, and degrades gracefully when unavailable. |
| `EMBED_FAILURE_COOLDOWN_SECONDS` | `300.0` | After a rate-limit response, the process refuses further embedding attempts for this long. |

A dimension mismatch is a **fail-fast** condition: an embedder whose output dimension
disagrees with the pinned value raises at startup rather than producing a half-populated
vector table that fails confusingly mid-run.

The cooldown exists so provider pressure does not become an outage. After a 429, reads keep
serving lexical and graph results rather than hammering the provider on every request, and
the observable reason distinguishes the triggering call (`rate_limited`) from the window that
follows (`cooldown`) — so an operator can tell provider pressure apart from index corruption.
Setting this to zero disables the cooldown and lets every read retry immediately.

## Read-time convergence tunables

These are the knobs to tune against real first-read latency. See
[Read-Time Convergence](read-time-convergence.md).

| Constant | Default | Consequence of changing it |
|---|---|---|
| `CONVERGE_EMBED_BUDGET` | `128` | Maximum stale chunks or doc surfaces embedded per converging read. The default equals the indexer's embedding batch size, keeping a converging read to roughly one API round-trip. Raising it makes reads catch up faster but adds latency and cost to the read that pays; lowering it makes reads snappier while dense coverage lags longer behind lexical. |
| `CONVERGE_DEBOUNCE_SECONDS` | `5.0` | Re-convergence is skipped inside this window, so a burst of reads pays the cost once. Raising it risks a just-committed note being invisible for longer; `--now` overrides it explicitly, which is why the debounce can be generous. |
| `CONVERGE_MAX_DELTA_FILES` | `200` | Above this many changed markdown files, the read **signals** a manual reindex instead of attempting an unbounded inline replay — the situation after a large merge. Raising it trades a predictable read latency for fewer manual reindex prompts. |

## Folder-discovery bounds

`list_folders` follows the same "cap and emit a signal" precedent rather than truncating
silently. See [Capture and Thinking Surfaces](capture-and-thinking-surfaces.md).

| Constant | Default | Consequence |
|---|---|---|
| `LIST_FOLDERS_MAX_NODES` | `200` | Maximum folder entries returned. Entries are sorted *before* the cap, so the dropped tail is deterministic, and the response reports `truncated` plus an `omitted` count. Narrowing `root` is the intended way to see more. |
| `LIST_FOLDERS_MAX_DEPTH` | `6` | Ceiling on requested drill-down depth; a larger request is clamped, not rejected. |

## Write-zone tiers

| Constant | Default | Meaning |
|---|---|---|
| `IMMUTABLE_APPEND_ZONES` | `("sources/",)` | Free-append zones accept a **new** file directly with no proposal friction — frictionless capture depends on this — but never accept an overwrite. Every other writable path is curated, meaning changes flow through propose-and-approve. |

This is an explicit path-prefix list, not a heuristic: a path is in a free-append zone only
if it matches one of these prefixes exactly.

Note what this constant is *not*. It does not define **which** paths are writable. The write
**surface** is the blocklist guard in the write path, not a configuration value, and the
`--allowlist` flag on the CLI and serve commands narrows that surface at runtime rather than
expanding it. See [Write Guard and Security Model](write-guard-and-security-model.md).
