# Configuration reference

Every user-facing knob, in one place. Environment variables are read from the process
environment or a gitignored repo-root `.env` (see [`.env.example`](../../.env.example)).
Engine tunables live in [`src/hypermnesic/config.py`](../../src/hypermnesic/config.py)
(the source of truth for the values below).

## Environment variables

| Variable | Used by | Required | Effect |
|---|---|---|---|
| `OPENAI_API_KEY` | embeddings | for dense retrieval | The OpenAI key for `text-embedding-3-large`. Absent → retrieval degrades to lexical-only (also how the test suite runs). Never written to the index, audit log, or any output. |
| `HYPERMNESIC_MCP_URL` | plugin `.mcp.json` | per remote client | Your hypermnesic MCP endpoint URL (e.g. `https://YOUR-HOST.ts.net/mcp`). The bundled wiring templates the URL from this var; OAuth is via browser discovery (no token in the wiring). |
| `HYPERMNESIC_MCP_TOKEN` | auto-recall hook | optional | HTTP auth credential the per-prompt recall hook uses for its bounded read on a remote (non-tailnet) device. Empty → use the tailnet read route. The MCP tool wiring itself needs no token. |
| `HYPERMNESIC_HOOK_STATUS_FILE` | auto-recall hook | optional | Override the non-secret hook status JSON location. The file stores outcome categories, timestamps, endpoint/credential categories, host, enabled state, hit count, and degraded state; it never stores tokens, headers, endpoint URLs, or full prompts. |
| `HYPERMNESIC_HOOK_DISABLE_LOOKUP` | auto-recall hook | optional | Set to `1` to disable proactive hook recall for this plugin install without uninstalling the plugin or removing MCP tools. |
| `HYPERMNESIC_HOOK_DISABLED_HOSTS` | auto-recall hook | optional | Comma-separated host names (`claude`, `codex`) to disable proactive recall on specific hosts. |
| `HYPERMNESIC_CLOUD_APPROVAL_TOKEN` | `serve-cloud` / `setup` | for the public lane | The operator approval token that gates every public connection. Read from the environment **only** (never a CLI flag, so it can't leak via the process table / logs). Enforced minimum length. |
| `HYPERMNESIC_DEFAULT_CLIENT_SCOPES` | `serve-cloud` / `setup` | optional | Comma- or space-separated OAuth scopes requested by default when a dynamically registered client omits `scope`. Default is `read`; set `read,write` when new connector approvals should request both read access and `commit_note` write access. The consent page still requires the operator approval token and write guards still apply. |
| `HYPERMNESIC_TOKEN_TTL_SECONDS` | `serve-cloud` / `setup` | optional | Cloud-lane access-token lifetime in seconds. Default is `172800` (48h) so overnight idle does not 401. Refresh stays 30 days. An explicit `--token-ttl` wins over this env var. Code TTL (300s) and pending TTL are unchanged. |
| `HYPERMNESIC_SPEND_ENVELOPE` | embeddings (CLI + both servers) | optional | Absolute path to an **existing** spend-envelope state file. Unset → unchanged behavior. Set → every physical embeddings request must durably reserve its pessimistic cost bound before any provider I/O, and the state's `model`/`expires_at`/`limit_micro_usd` bound the spend. The SDK's own retries are disabled while it is set. See [Spend envelope](#spend-envelope-optional-hard-ceiling-on-embeddings). |

Repo-addressed commands and servers resolve the OpenAI key in this order:

1. process environment `OPENAI_API_KEY`;
2. the target repo's gitignored `<repo>/.env`;
3. no cwd fallback when an explicit repo is known.

Only helper paths with no repo context use the historical cwd `.env` fallback. This means
`hypermnesic doctor /path/to/vault --json` and MCP serves launched from any working
directory still use `/path/to/vault/.env` when process env is absent.

The OAuth consent secret is persisted by `setup` to an owner-only env file
(`~/.config/hypermnesic-cloud/cloud.env`, `chmod 600`), never committed.
`hypermnesic doctor --env-file PATH` checks only whether that file exists and has
owner-only permissions; it never reads or prints the secret value.

`doctor` and `status` are offline-friendly by default: they report a discovered dense key
as `configured_unverified`. Pass `--check-dense-live` to run an explicit OpenAI smoke
embedding and distinguish `configured_valid` from `configured_invalid` without ever
printing the key. A configured key is separate from projection health: `index_missing_or_unbuilt`
means build the disposable index first, while `vectors_stale_or_absent` means run
`hypermnesic converge /path/to/vault --now --json` (or reindex when convergence reports a
manual reindex recommendation).

When the embedding provider returns a rate-limit/quota response, Hypermnesic opens an
in-process cooldown before another embedding attempt. Reads continue in lexical/graph mode and
surface `degraded_reason` (`rate_limited` for the triggering call, `cooldown` during the cooldown)
so operators can distinguish provider pressure from index corruption.

## Spend envelope (optional hard ceiling on embeddings)

`HYPERMNESIC_SPEND_ENVELOPE` points at an **already existing, absolute** JSON file. When it is
unset — the default — nothing changes: no lock, no file, SDK retries untouched. When it is set,
every physical embeddings request (CLI, `serve`, the cloud lane, convergence-driven reads, the
scheduled/manual drain and the startup smoke check) must first append a durable **reservation**
to that file, under one adjacent `<state>.lock` that spans read → validate → append → atomic
fsync'd write. Independent processes therefore cannot oversubscribe the same file, and a crash
can waste allowance but can never overspend it.

The file is a reserve, not an invoice: a reservation is **never refunded**, on success, provider
failure or unknown outcome. Its cost bound is the published rate for the pinned model
(`text-embedding-3-large`: 0.13 USD per 1M tokens) applied to a pessimistic token upper bound —
`ceil((utf8_bytes + inputs) * 13 / 100)` micro-USD per physical request, since every token of the
model's `cl100k_base` encoding covers at least one UTF-8 byte. The file carries counters only;
it never contains note text or a credential.

```json
{
  "schema": "hypermnesic-spend-envelope/v1",
  "envelope_id": "example-outcome-2026-12",
  "expires_at": "2026-12-31T23:00:00Z",
  "model": "text-embedding-3-large",
  "limit_micro_usd": 5000000,
  "reservations": []
}
```

`limit_micro_usd` is the whole-outcome ceiling in micro-USD (`5000000` = 5 USD) and is **not**
renewed per day, per process or per run. The cumulative reserved amount is always derived from
the `reservations` list — there is no separate editable total. Each row is appended by the engine:
`{"request_id", "timestamp", "utf8_bytes", "reserved_micro_usd"}`, with a unique monotonic id.
The file must be owned by the running user and must not be group- or world-writable
(`chmod 600`); symlinks are refused. Nothing auto-creates, resets or repairs the state, and no
CLI command edits it: operators seed it, and a new file is how a new envelope starts.

While the envelope is set, the SDK's own retries are `0` — every attempt, including the adaptive
drain's own 429 retry, reserves separately. Any unusable state refuses **before any provider I/O**
with a `spend_envelope_*` reason that never arms the 429 cooldown and is never reported as rate
limiting:

| `reason` | Meaning |
|---|---|
| `spend_envelope_invalid_path` | The variable is set but is not an absolute path. |
| `spend_envelope_unavailable` | State missing, not a regular file, a symlink, wrong owner, or group/other-writable. |
| `spend_envelope_invalid` | Corrupt JSON, wrong schema/keys, bad type or range, duplicate `request_id`, or reservations already over the limit. |
| `spend_envelope_model` | The state pins a different model, or the embedder is not the pinned `text-embedding-3-large`. |
| `spend_envelope_expired` | `expires_at` (absolute RFC3339 UTC) has passed. |
| `spend_envelope_exhausted` | The next request would push the derived total past `limit_micro_usd`. |
| `spend_envelope_locked` | Another process holds `<state>.lock`; the request is refused, never queued. |
| `spend_envelope_write_failed` | The reservation could not be persisted; no request is sent. |

Read paths stay available: a refused dense slice degrades to lexical/graph (`degraded_reason` =
the `spend_envelope_*` reason), and the CLI reports one honest `failed` record with that reason.

`HYPERMNESIC_DEFAULT_CLIENT_SCOPES` can also be set as an explicit admin flag:
`hypermnesic serve-cloud ... --default-client-scopes read write` or
`hypermnesic setup ... --default-client-scopes read write`. Unsupported scopes fail
loudly before the service starts.

`HYPERMNESIC_TOKEN_TTL_SECONDS` is the same knob as `--token-ttl` on `serve-cloud` /
`setup` (`config.CLOUD_TOKEN_TTL_SECONDS`, default `172800`). After deploying a
build that includes this default, an existing unit that still bakes `--token-ttl
3600` must be updated (change that flag to `172800`, or remove it and set the env
var in `~/.config/hypermnesic-cloud/cloud.env`) before the longer lifetime applies.
New `setup` renders `--token-ttl 172800`.

## Embedding model (pinned)

These are pinned in one place so a parity/benchmark result isolates the *architecture*
variable, not the model. A dimension mismatch fails fast at startup.

| Constant | Default | Effect |
|---|---|---|
| `EMBED_MODEL` | `text-embedding-3-large` | The dense embedding model. |
| `EMBED_DIM` | `1536` | Embedding dimensions (sent explicitly to the API; asserted at startup). |
| `EMBED_FAILURE_COOLDOWN_SECONDS` | `300.0` | In-process cooldown after an embedding 429, preventing every read from hammering the provider while lexical/graph fallback serves. |
| `EXPANSION_MODEL` | `gpt-4o-mini` | Optional multi-query expansion (a ranking aid); opt-in, degrades gracefully if unavailable. |

## Read-time convergence tunables

Tune against real first-read latency. The budget keeps a converging read near one
embedding round-trip; the debounce coalesces bursts; the delta cap signals (never forces)
a manual reindex when `HEAD` has jumped far past the index checkpoint.

| Constant | Default | Effect |
|---|---|---|
| `CONVERGE_EMBED_BUDGET` | `32` | Max stale chunks **and** max missing doc surfaces embedded per converging read (per lane). |
| `CONVERGE_DEBOUNCE_SECONDS` | `5.0` | Skip re-convergence within this window (`--now` overrides). |
| `CONVERGE_MAX_DELTA_FILES` | `200` | Over this many changed markdown files, emit `manual_reindex_recommended` instead of an unbounded inline replay. |

The same 32-per-lane pace is what the scheduled drain uses (`hypermnesic embed --batch 32
--budget 32`). `CONVERGE_EMBED_BUDGET` and `--budget` are **cardinality** caps (inputs per
pass), not financial budgets. A manual `hypermnesic embed` without `--budget`, and the
analytical `ensure_full_coverage` pass used by salience/connections, intentionally stay
unbounded. Bulk dense work is additionally serialized by the non-blocking
`.hypermnesic/dense-maintenance.lock`; that is an internal lock file, not a configuration
knob, and it never blocks narrow `commit_note` writes (which use `index.lock`).

## `list_folders` discovery bounds

A large vault returns a bounded folder payload (sorted before the cap → a deterministic
tail is dropped) with a `truncated` flag + `omitted` count; drill deeper by narrowing
`root`.

| Constant | Default | Effect |
|---|---|---|
| `LIST_FOLDERS_MAX_NODES` | `200` | Max folder entries returned before truncation. |
| `LIST_FOLDERS_MAX_DEPTH` | `6` | Ceiling on the requested drill-down depth (clamped). |

## Write-zone tiers

| Constant | Default | Effect |
|---|---|---|
| `IMMUTABLE_APPEND_ZONES` | `("sources/",)` | Free-append zones accept a NEW file directly (no proposal friction — `capture` depends on this) but never an overwrite. Every other writable path is curated. |

The write **surface** itself (which paths are writable) is the blocklist guard, not a
config constant — see [`ARCHITECTURE.md`](../../ARCHITECTURE.md) and
[`SECURITY.md`](../../SECURITY.md). The CLI/serve `--allowlist` flag narrows it at
runtime.
