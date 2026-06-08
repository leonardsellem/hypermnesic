---
date: 2026-06-08
topic: dense-retrieval-reliability
title: "Hypermnesic Dense Retrieval Reliability Requirements"
type: brainstorm
tags: [hypermnesic, dense-retrieval, embeddings, diagnostics, configuration, reliability]
origin:
  - "live investigation: standing degraded_lexical_only / dense_retrieval failure"
related_to:
  - "src/hypermnesic/config.py"
  - "src/hypermnesic/doctor.py"
  - "src/hypermnesic/embed.py"
  - "src/hypermnesic/retrieve.py"
  - "src/hypermnesic/converge.py"
  - "src/hypermnesic/mcp_server.py"
  - "src/hypermnesic/install.py"
  - "docs/reference/configuration.md"
  - "docs/guides/getting-started.md"
  - "README.md"
---

# Hypermnesic Dense Retrieval Reliability Requirements

## Summary

Hypermnesic can remain in a standing `degraded_lexical_only` state even when an OpenAI key exists
for the operator because dense credential discovery is currently context-sensitive: `config.py`
checks the process environment plus `.env` under the process current working directory, not the
vault/repo passed to CLI and server commands. Any invocation launched from a different working
directory reports `dense_retrieval: fail` and the read path silently degrades to lexical-only.

The fix should make dense retrieval reliable for all repo-addressed entrypoints, improve diagnostics
without leaking secrets, and add tests that reproduce the current failure mode: `doctor /path/to/vault`
started outside the vault must still find `/path/to/vault/.env` and either prove dense retrieval or
report an actionable, precise reason.

---

## Investigation Evidence

The following commands were run during investigation; no secret values were printed.

| Check | Result | Meaning |
|---|---:|---|
| `uv run hypermnesic doctor <home>/dev/hypermnesic --json` from the repo cwd | `dense_retrieval=pass`; `local_index=fail` | The repo `.env` is discoverable only when cwd is the repo. The source checkout has no `.hypermnesic/index.db`, which is a separate local-index issue. |
| Same doctor command launched from `/tmp` with `uv --project <home>/dev/hypermnesic ...` | `dense_retrieval=fail` | Merely changing cwd is enough to reproduce the reported dense failure despite passing the same repo path. |
| Installed `<home>/.local/bin/hypermnesic` launched from `/tmp` | `dense_retrieval=fail` | The installed console script does not currently inject `OPENAI_API_KEY`; ad-hoc invocations outside the repo depend on cwd-sensitive `.env` lookup. |
| Repo cwd environment check | process `OPENAI_API_KEY` absent; repo `.env` present; `.hypermnesic/index.db` absent | The key exists as a repo-local secret file, but not as a global process env var. |
| 1Password field existence check | OpenAI field available in vault `hermes-agent` | The operator has a usable secret source, but Hypermnesic itself does not read 1Password. |
| `uv run python -c 'from hypermnesic.embed import smoke_embed_or_die; smoke_embed_or_die()'` from repo cwd | `smoke_embed=pass` | The configured key is valid and the OpenAI embedding API returns the pinned vector shape from the repo context. |
| `config.get_api_key()` from `/tmp` | fails: checked environment and `.env` | Confirms root cause is lookup scope, not key validity. |
| `uv run pytest tests/test_doctor.py tests/test_index.py::test_smoke_embed_fails_loud_on_missing_key` | `8 passed` | Current tests cover intentional no-key behavior but do not cover repo-scoped `.env` discovery from non-repo cwd. |

---

## Current Behavior Model

### Credential path

`src/hypermnesic/config.py` initializes `_DOTENV_PATHS = [Path.cwd() / ".env"]` at import time.
`config.get_api_key()` then checks:

1. `OPENAI_API_KEY` in the process environment.
2. The import-time cwd `.env` path.

It does **not** check the `repo` argument supplied to `doctor`, `retrieve`, `converge`, `local-proof`,
`serve`, or `serve-cloud`.

### Dense degradation path

- `embed.OpenAIEmbedder()` does not read the key at construction time.
- The MCP backend lazily constructs `OpenAIEmbedder`; a missing key surfaces later during query
  embedding.
- `retrieve.search()` catches `EmbeddingError`, skips dense KNN, and returns `dense_used=False`.
- MCP tools report `degraded_lexical_only` when dense did not contribute.
- `converge.converge()` treats `embedder is None` or embedding failure as graceful dense degradation
  and still serves lexical/graph results.

This graceful degradation is correct for availability, but it means credential-routing mistakes become
standing degraded recall unless diagnostics make the cause obvious and entrypoints route credentials
consistently.

### Index path

The source checkout currently has no `.hypermnesic/index.db`, so `doctor` also reports
`local_index=fail`. That is independent from the dense key failure:

- Missing index means the disposable projection has not been built for this repo.
- Missing/undiscovered dense key means the vector lanes cannot be populated or queried.
- A complete fix must keep these distinct in diagnostics and recovery instructions.

---

## Problem

Dense retrieval is operationally brittle because the key source is tied to the caller's cwd while the
rest of Hypermnesic is repo-addressed. Humans and agents naturally run commands such as
`hypermnesic doctor /path/to/vault`, `hypermnesic retrieve /path/to/vault ...`, or an MCP server with
`--repo /path/to/vault` from arbitrary directories. Those invocations should not lose dense retrieval
when `/path/to/vault/.env` contains the key.

The user-visible symptom is misleading: `dense_retrieval: fail` says "Dense retrieval is not
configured" even when it is configured in the vault's gitignored `.env`; Hypermnesic simply did not
look there from that process context.

---

## Users / Jobs To Be Done

- **Daily operator:** Wants `doctor` and MCP tool outputs to explain why recall is lexical-only and
  how to fix it without exposing secrets.
- **Agent client:** Needs stable dense/vector behavior regardless of the shell cwd or MCP host cwd.
- **Installer/setup flow:** Must produce services whose environment and working directory preserve
  dense retrieval after reboot.
- **Future implementer:** Needs a clear testable target for fixing credential routing and diagnostics
  without weakening secret discipline.

---

## Requirements

### R1. Repo-scoped credential discovery

For every command or server path that accepts a repo/vault path, dense credential lookup MUST check:

1. `OPENAI_API_KEY` from the process environment.
2. `<repo>/.env` for that command/server's repo.
3. Optionally, the historical cwd `.env` fallback only for backward compatibility and only when no
   explicit repo context is available.

The implementation should avoid import-time cwd capture for repo-aware flows. Prefer an explicit API
such as `config.get_api_key(repo: Path | None = None)` or `config.api_key_status(repo: Path | None)`.

### R2. Index-db-derived repo context

For entrypoints that receive only `--index-db`, Hypermnesic MUST derive the repo consistently using
existing server/backend rules and pass that repo into credential lookup. Examples:

- `serve --index-db <repo>/.hypermnesic/index.db`
- `serve-cloud --index-db <repo>/.hypermnesic/index.db`
- read paths that open an index and derive repo from the index database location

If repo derivation is ambiguous, diagnostics must say so and provide the exact flag needed (`--repo`).

### R3. Secret-free, source-aware doctor output

`doctor` MUST report dense configuration in an actionable way without printing secrets:

- Whether a key was discovered.
- Which non-secret source category supplied it: `process_env`, `repo_dotenv`, `cwd_dotenv`, or
  `missing`.
- Whether the live embedding smoke check was skipped, passed, or failed.
- A next action that matches the actual failure: set env, create repo `.env`, run from repo, pass
  `--repo`, repair API key, or rebuild/converge the index.

The output must continue to avoid absolute operator paths where existing secret-free diagnostics avoid
them.

### R4. Distinguish key presence from live dense health

Dense diagnostics SHOULD distinguish these states:

1. `not_configured`: no key found from any approved source.
2. `configured_unverified`: key found, but live API smoke was not requested or could not run in a
   non-network diagnostic mode.
3. `configured_valid`: smoke embed succeeded with `EMBED_MODEL` and `EMBED_DIM`.
4. `configured_invalid`: key found but smoke embed failed, dimension mismatched, or the OpenAI SDK/API
   failed.
5. `index_missing_or_unbuilt`: dense may be configured, but no index exists yet.
6. `vectors_stale_or_absent`: index exists but chunk/doc vector lanes are missing or lagging.

`dense_retrieval: pass/fail` can remain for compatibility, but the structured details should let
clients render the more precise state.

### R5. Preserve graceful read degradation

Read tools must keep returning lexical/graph results when dense is down. The fix must not turn a
missing/invalid embedding key into a hard read outage. The change is to make dense configuration
reliable and observable, not to remove graceful fallback.

### R6. Vector coverage diagnostics

When an index exists, diagnostics SHOULD report secret-free vector coverage:

- total chunks
- embedded chunk vectors
- missing/stale chunk vectors
- total docs
- embedded doc-surface vectors
- missing/stale doc-surface vectors
- whether `manual_reindex_recommended` is set or convergence can catch up incrementally

This keeps "dense key missing" separate from "key exists, but vectors are not populated yet."

### R7. Repair commands must be safe and exact

Docs and `doctor` next actions should offer commands that work from any cwd, for example:

```sh
hypermnesic doctor /path/to/vault --json
hypermnesic local-proof /path/to/vault --dense --json
hypermnesic converge /path/to/vault --now --json
```

If the recommended fix is to write a repo `.env`, docs must show a placeholder and warning, never a
real key. If 1Password integration remains outside Hypermnesic core, docs should say "export
`OPENAI_API_KEY` or place it in gitignored `<repo>/.env`" rather than implying the engine reads
1Password.

### R8. Service/unit behavior remains explicit

The systemd unit generation already sets `WorkingDirectory=<repo>` and `EnvironmentFile=-<repo>/.env`.
Regression tests should preserve that. The dense reliability fix should also cover ad-hoc CLI and MCP
invocations that are not launched by that unit.

### R9. Documentation updates ship with the fix

A code fix affects configuration and diagnostics, so the implementation PR must update:

- `docs/reference/configuration.md` for repo-scoped `.env` lookup and any new doctor fields.
- `docs/reference/cli.md` for dense health / convergence commands if output or flags change.
- `README.md` if quick-start or "How it works" dense behavior changes.
- `CHANGELOG.md` under `[Unreleased]` for user-visible diagnostic/config behavior.

---

## Non-Goals

- Do not store OpenAI keys in the index, audit log, MCP outputs, git history, or generated docs.
- Do not require dense retrieval for basic lexical recall.
- Do not make Hypermnesic core depend on 1Password or any specific operator secret manager.
- Do not replace sqlite-vec or change the pinned embedding model/dimension as part of this fix.
- Do not paper over a missing local index by reporting dense as healthy; index and credential states
  should remain separate.

---

## Edge Cases

- Command launched from `/tmp` with `hypermnesic doctor /path/to/vault` and `/path/to/vault/.env`
  present.
- Command launched from inside one vault while diagnosing a different vault.
- `OPENAI_API_KEY` present in process env and a different key present in repo `.env`; process env
  should keep precedence, but diagnostics should reveal only the source category, not values.
- `.env` exists but is unreadable.
- `.env` has quotes, whitespace, comments, or multiple lines; preserve current accepted syntax or
  document any stricter parser.
- MCP server receives `--index-db` without `--repo`; repo derivation must be deterministic or fail
  actionably.
- Index exists with lexical rows but zero vector rows because previous reads ran while dense was down.
- Doc-lane vectors are missing while chunk vectors exist, or vice versa.
- Network is unavailable during an optional smoke check; diagnose as live check failed/skipped without
  losing lexical availability.

---

## Acceptance Criteria

- A regression test creates a repo with `.env`, runs `doctor(repo)` while `cwd` is a different temp
  directory and no process `OPENAI_API_KEY` is set, and expects `dense_retrieval` not to fail due to
  missing configuration.
- A regression test verifies repo `.env` does not leak in doctor JSON or human output.
- A regression test verifies process env precedence over repo `.env` using source-category metadata,
  without exposing either value.
- A regression test covers an MCP/serve backend or CLI path where only `--index-db` is supplied and
  repo-scoped credential lookup still works.
- A diagnostic test distinguishes missing index from missing dense key.
- Existing tests in `tests/test_doctor.py`, `tests/test_index.py`, and install/unit rendering remain
  green.
- Manual verification from outside the repo succeeds:

```sh
cd /tmp
hypermnesic doctor /path/to/vault --json
```

  The output must not say `dense_retrieval: fail` when `/path/to/vault/.env` contains a valid key.

- Manual verification from the repo cwd still succeeds:

```sh
cd /path/to/vault
hypermnesic doctor . --json
```

- If `--check-dense-live` or equivalent live smoke behavior is added, a valid key produces a
  successful `text-embedding-3-large` 1536-dimensional smoke embed and an invalid key produces an
  actionable dense diagnostic without leaking the key.

---

## Suggested Implementation Shape

1. Add a repo-aware credential status helper in `config.py` that returns structured metadata, not just
   a string key. Keep the actual key value private to callers that need to instantiate the OpenAI SDK.
2. Thread `repo` into `embed.OpenAIEmbedder` or into the `config.get_api_key(repo=...)` call it uses.
3. Update CLI commands and MCP backend construction so every repo-addressed path passes repo context
   to the embedder.
4. Update `doctor.run_doctor(repo=...)` to use repo-aware key status and add vector coverage when the
   index exists.
5. Add tests before production changes for the cwd mismatch reproduced above.
6. Update docs and changelog in the same PR.

---

## Open Questions

- Should live API smoke checks run by default in `doctor`, or behind an explicit flag to keep doctor
  fast/offline-friendly?
- Should cwd `.env` remain a fallback for repo-aware commands, or should repo `.env` plus process env
  be the only documented behavior?
- Should a successful `setup` or `local-proof --dense` also prebuild/converge enough vectors to avoid
  an initial `degraded_lexical_only` result immediately after configuration?
- Should the installed console script remain plain, or should deployment guidance recommend a shell
  wrapper/export strategy for non-service ad-hoc invocations?

---

## Next Step

Write a test-first implementation plan focused on repo-scoped credential lookup and doctor output.
Start with the cwd-mismatch regression because it reproduces the observed `dense_retrieval: fail`
without requiring a real API call or secret value.
