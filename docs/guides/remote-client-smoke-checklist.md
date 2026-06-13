# Remote-client smoke checklist

Use this checklist when validating a real remote client against a Hypermnesic endpoint. It
complements the offline contract tests in `tests/test_product_remote_smoke.py` and the local
fixture loop in `scripts/product_smoke.py`; it does not replace either gate.

Run it against a placeholder-shaped endpoint in docs and reports:
`https://<your-host>.ts.net/mcp`. Record real endpoint evidence only in private gate artifacts.

## Required automated gates first

| Gate | Command | Expected evidence |
|---|---|---|
| Local product loop | `uv run python scripts/product_smoke.py --work-dir /tmp/hypermnesic-smoke --json` | JSON status is `pass`; stages include capture, retrieve, write preview, memory inspect, forget preview, recall after change, and doctor status. |
| Offline remote contracts | `uv run pytest tests/test_product_remote_smoke.py -q` | OAuth discovery, read/write scope behavior, write guards, and revocation pass without external services. |
| Full regression suite | `uv run pytest` | All deterministic tests pass. |

## OAuth discovery

1. Configure the client with `https://<your-host>.ts.net/mcp`.
2. Confirm the client discovers the OAuth metadata without a static token or inline auth header.
3. Confirm the browser authorization page appears and names the client, redirect origin, requested
   scopes, and the write-scope consequence when write is requested.
4. Confirm reject/cancel returns the client to an authorization-denied state without granting access.

Evidence to record: client name, redirect origin, requested scopes, pass/fail, reviewer, date.

## Evidence log template

| Client | Step | Expected evidence | Recorded result | Pass/fail | Reviewer | Date |
|---|---|---|---|---|---|---|
| ChatGPT | OAuth discovery | Metadata discovered; consent page appears. | Pending. | Pending. | Pending. | Pending. |
| Claude | Read-scoped client | Read tool succeeds; output is source-grounded and secret-free. | Pending. | Pending. | Pending. | Pending. |
| Claude Code | Write refusal without write scope | `commit_note` refusal names missing write scope. | Pending. | Pending. | Pending. | Pending. |
| Codex | Write-scoped client | Safe write commits; protected path remains refused. | Pending. | Pending. | Pending. | Pending. |
| Obsidian | Read-only companion | Read tools work; no write path is exposed. | Pending. | Pending. | Pending. | Pending. |
| Any client | Revocation | Revoked grant can no longer read or write. | Pending. | Pending. | Pending. | Pending. |

## Read-scoped client

This is the read-scoped client gate.

Run this for ChatGPT, Claude, Claude Code, and Codex when those clients are in scope.

1. Connect with read scope only.
2. Call a read tool such as `search`, `think`, `resolve`, `build_context`, or `list_folders`.
3. Confirm the response includes repo-relative source paths and never includes local absolute paths,
   private or `/mcp` endpoint URLs, endpoint secrets, approval credentials, refresh tokens, or
   credential file bodies. Ordinary public source-of-truth links may appear when they are note
   content rather than host coordinates.
4. Attempt exactly one low-risk memory write and confirm write refusal without write scope.
   If the client aborts before Hypermnesic returns an explicit missing-write-scope refusal, record
   the row as `INCONCLUSIVE/FAIL`, do not retry in the same grant, and preserve the client error.

Required result: read succeeds; write refusal without write scope is explicit and actionable.

## Write-scoped client

This is the write-scoped client gate.

1. Reconnect and approve write scope on the consent page. If the endpoint was started with
   `--default-client-scopes read write` or `HYPERMNESIC_DEFAULT_CLIENT_SCOPES=read,write`, a
   client that omits `scope` should show both scopes on the first consent screen.
2. Write one low-risk test note using `commit_note` into an ordinary writable folder.
3. Confirm a git commit exists, audit metadata exists, and a follow-up `search` can recall the new
   note after convergence.
4. Attempt exactly one protected-path write to `scripts/<smoke-id>-protected-refusal.md` and confirm
   the write guard refuses it. Use `scripts/` rather than an agent instruction file when a hosted
   client applies its own safety layer to `AGENTS.md` / `CLAUDE.md`; the release row must prove the
   MCP refusal, not a client-side preflight refusal. If the client blocks before MCP returns a
   refusal, record `INCONCLUSIVE/FAIL` and preserve the client error.

Required result: write-scoped client can request `commit_note`, but write guards still block
protected paths and unsafe changes.

## Revocation

1. List grants on the engine host with `hypermnesic clients list /path/to/vault --json`.
2. Revoke the tested grant with `hypermnesic clients revoke /path/to/vault <grant-id> --apply`.
3. Confirm the client can no longer read or write until it reconnects and reauthorizes.
4. Confirm grant output remains secret-free.

Required result: revocation invalidates the client grant and does not expose tokens or secrets.

## Obsidian

The Obsidian companion is read-only and uses the tailnet read companion rather than the public OAuth
write lane.

1. Point the companion at the tailnet read route.
2. Confirm `search`, `build_context`, and `think` work from Obsidian.
3. Confirm no write control is exposed by the companion.

Required result: Obsidian can read memory but cannot write.

## Pass criteria

Remote-client smoke passes only when:

- automated local and offline remote gates pass first;
- every in-scope client records OAuth discovery, read success, write refusal without write scope,
  write-scoped success when applicable, write-guard refusal, and revocation evidence;
- all evidence has a pass/fail state, date, and reviewer name;
- public docs and reports use placeholders, not real private endpoints or credentials.
