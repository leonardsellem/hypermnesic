# Consent and clients

Hypermnesic's public `/mcp` endpoint uses browser OAuth consent so a remote client can
read memory, and only write when the owner explicitly grants the `write` scope.

## What the consent page shows

The consent page is intentionally plain, script-free, and no-store. It shows:

- the requesting client identity;
- the redirect origin and full redirect URI;
- the requested scopes;
- plain-language consequences for read and write access;
- reject and cancel actions;
- revocation guidance before approval.

Read access lets a client search, recall, resolve, build context, think, and list writable
folders. Write access lets the client request `commit_note`.

Write access is not a bypass. `commit_note` still runs the protected-path guard,
frontmatter gate, dirty-tree and head-drift checks, audit logging, git coordination, and
any explicit allowlist narrowing.

## Approve, reject, or cancel

Approve only when the client and redirect origin are expected. If the client identity is
generic or missing, treat the warning as a trust signal and verify the app before
continuing.

Reject and cancel both consume the authorization request without issuing a code or grant.
The client receives an OAuth denial response and must start a new authorization request to
try again.

## Inspect clients

On the engine host, use the owner CLI to inspect known grants:

```sh
hypermnesic clients list /path/to/vault
hypermnesic clients list /path/to/vault --json
```

Grant metadata is stored in `.hypermnesic/client-grants.json` when the cloud server is
built with a repo. It contains client id/name, redirect information, scopes, issue/update
times, expiry times, status, and whether write is enabled. It never stores bearer tokens,
refresh tokens, approval credentials, client secrets, or token hashes.

## Revoke a grant

Preview first:

```sh
hypermnesic clients revoke /path/to/vault <grant-id>
```

Apply the revocation marker:

```sh
hypermnesic clients revoke /path/to/vault <grant-id> --apply
```

A running server that shares the same grant metadata store refuses that grant on the next
access or refresh validation. Provider-level revocation also invalidates the whole live
grant path, including the refresh sibling, so a revoked client cannot recover write access
by refreshing.

If a client without write scope calls `commit_note`, the MCP result is
`committed: false` with an actionable `insufficient_scope` refusal. The refusal tells the
client to reconnect and approve write, and repeats that write approval does not bypass
Hypermnesic's write guards.
