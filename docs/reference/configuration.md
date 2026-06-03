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
| `HYPERMNESIC_MCP_TOKEN` | auto-recall hook | optional | Bearer token the per-prompt recall hook uses for its bounded read on a remote (non-tailnet) device. Empty → use the tailnet read route. The MCP tool wiring itself needs no token. |
| `HYPERMNESIC_CLOUD_APPROVAL_TOKEN` | `serve-cloud` / `setup` | for the public lane | The operator approval token that gates every public connection. Read from the environment **only** (never a CLI flag, so it can't leak via the process table / logs). Enforced minimum length. |

The OpenAI key may also be read from a repo-root `.env` (the only file path searched by
default); the OAuth consent secret is persisted by `setup` to an owner-only env file
(`~/.config/hypermnesic-cloud/cloud.env`, `chmod 600`), never committed.

## Embedding model (pinned)

These are pinned in one place so a parity/benchmark result isolates the *architecture*
variable, not the model. A dimension mismatch fails fast at startup.

| Constant | Default | Effect |
|---|---|---|
| `EMBED_MODEL` | `text-embedding-3-large` | The dense embedding model. |
| `EMBED_DIM` | `1536` | Embedding dimensions (sent explicitly to the API; asserted at startup). |
| `EXPANSION_MODEL` | `gpt-4o-mini` | Optional multi-query expansion (a ranking aid); opt-in, degrades gracefully if unavailable. |

## Read-time convergence tunables

Tune against real first-read latency. The budget keeps a converging read near one
embedding round-trip; the debounce coalesces bursts; the delta cap signals (never forces)
a manual reindex when `HEAD` has jumped far past the index checkpoint.

| Constant | Default | Effect |
|---|---|---|
| `CONVERGE_EMBED_BUDGET` | `128` | Max stale chunks embedded per converging read. |
| `CONVERGE_DEBOUNCE_SECONDS` | `5.0` | Skip re-convergence within this window (`--now` overrides). |
| `CONVERGE_MAX_DELTA_FILES` | `200` | Over this many changed markdown files, emit `manual_reindex_recommended` instead of an unbounded inline replay. |

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
