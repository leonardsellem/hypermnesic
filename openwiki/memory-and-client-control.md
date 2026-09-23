---
type: Reference
title: Memory and Client Control
description: The owner surfaces over what is remembered and who may connect — listing, inspection, export, git-backed forget, safe revert, audit history, write-scope answering, and secret-free grant revocation.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-b056bdca91307e7c890b5f5b
    resource: repo://docs/guides/consent-and-clients.md
  - id: openwiki-source-c04515f04794611343d64348
    resource: repo://docs/guides/memory-control.md
  - id: openwiki-source-b71cfd92d11a88500eb68d63
    resource: repo://src/hypermnesic/audit_log.py
  - id: openwiki-source-e2983cb60d29dab96c31cfed
    resource: repo://src/hypermnesic/auth_cloud.py
  - id: openwiki-source-d0135879c44e5d0086df3a05
    resource: repo://src/hypermnesic/client_control.py
  - id: openwiki-source-a549bbb642c1fa61b486d5ae
    resource: repo://src/hypermnesic/folders.py
  - id: openwiki-source-3a05a10f6a1dad4ec686dc45
    resource: repo://src/hypermnesic/generated.py
  - id: openwiki-source-37433895d4b7b6af7cd92f4f
    resource: repo://src/hypermnesic/mcp_server.py
  - id: openwiki-source-bf30bdf8a5e94f3f19416f00
    resource: repo://src/hypermnesic/memory_control.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-a6989a1914d75f6aa97d3180
    resource: repo://tests/test_client_control.py
  - id: openwiki-source-b9fde40b8fe71c05bc75b2d9
    resource: repo://tests/test_memory_control.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Memory and Client Control

Two control surfaces answer two owner questions: *what does this system remember about me?*
and *who is allowed to reach it?* Both are built on the objects that make the system
trustworthy in the first place — markdown files, git commits, the disposable index, and the
append-only audit log. Neither introduces a second store of record.

## Memory control

### Seeing what is remembered

`memory list` returns each remembered file with its repo-relative path, title, a bounded
snippet, source type, last commit, the audit actor when one is known, and whether the path is
currently writable **under the same guard `commit_note` uses**. Filters narrow by folder,
source type, writability, protection, and recency.

Source types are **evidence-based**, not guessed:

| Type | Determined by |
|---|---|
| `generated` | The note carries the shared generated-artifact demarcation. |
| `captured` | The note lives under the free-append capture prefix. |
| `authored` | Everything else — ordinary source content. |

Where evidence is missing the surface says so rather than inventing provenance.

`memory inspect` reports one file's provenance in **file and commit terms** and deliberately
carries no raw full-body field: the control surface explains where a memory came from, and
reading the note is a separate, explicit act.

`memory write-scope` answers "what would an agent be allowed to write?" using the same folder
derivation and protected-path guard as folder discovery and the write path — so all three
surfaces agree by construction rather than by convention. See
[Write Guard and Security Model](write-guard-and-security-model.md).

### Export

`memory export` copies the selected markdown files into a destination directory, preserving
their relative structure, and writes a manifest alongside them recording a version, an export
timestamp, the filter that produced the selection, and for each item its path, last commit,
actor, and source type.

This is a **markdown and provenance export, not an index export**. That is the right shape:
the index is disposable and rebuildable from the files, so exporting it would be exporting a
cache.

### Forget: precise about git

`memory forget` **previews by default**. The preview names the target, states that applying
will create a commit, describes the intent, reports the guard verdict, lists a verification
plan, and — importantly — states its own limits.

Applying is deliberately narrow:

- It requires a **clean working tree** before it does anything.
- It takes the single-writer lock, removes the file with `git rm`, and commits that removal
  **scoped to that path**.
- It updates the index projection and advances the checkpoint.
- It appends a `forget` audit entry.

**What forget does:** it removes the current source content as a **new commit**.

**What forget does not do:** it does **not rewrite git history**. Previous content remains
reachable in earlier commits. It does not erase chat contexts or any copy living outside the
vault. And it does not conflate source deletion with index state — the generated and index
state is disposable and rebuildable, which is a separate matter from removing the source.

Those limits are returned in the result rather than being left for the operator to infer. If
you need history rewritten, that is a different operation with different consequences, and
this surface will not quietly pretend to have done it.

### Revert: refuse rather than guess

`memory revert` also previews by default, and the preview answers one question: **is this
commit supported?**

Support is narrow on purpose. A commit that cannot be found reports `commit_not_found`. A
commit touching more than one markdown file is reported as unsupported with the reason stated
plainly — only single-file markdown commits are handled. Applying an unsupported commit raises
rather than attempting a best-effort partial revert.

When it is supported, apply requires a clean tree, runs `git revert --no-edit`, and **aborts
the revert on conflict** rather than leaving a half-finished state. Afterwards it re-projects
the affected path — re-indexing it if the file now exists, removing it if it does not —
advances the checkpoint, and appends a `revert` audit entry.

The design choice here is that a control surface for someone's memory should refuse an
ambiguous case rather than guess at it. A wrong revert is not recoverable by re-running the
command.

### Audit history

`memory audit` reads back the append-only log described in
[Git-First Write Path](git-first-write-path.md), projecting each entry to a fixed safe shape:
timestamp, actor, verb, attempted verb, path, old and new SHA, category, and a summary passed
through the same redaction used when writing. Refusal entries appear alongside successful
writes, so the history answers "what was blocked" as well as "what changed".

## Client control

### What the grant store is

The live OAuth provider owns bearer tokens, refresh tokens, and revocation semantics. The
grant store deliberately owns **none of that** — only reviewable metadata, so an owner can
inspect and revoke without ever handling a credential.

The stored fields are a fixed allowlist: grant id, client id and name, redirect URI and
origin, scopes, whether write is enabled, issue/update times, access and refresh expiry,
status, active flag, and revocation time. Every read and write of the store passes each grant
through that projection, so **a field outside the allowlist cannot be persisted even if a
caller supplies it**. There are no bearer tokens, refresh tokens, approval credentials, client
secrets, or token hashes anywhere in this file.

Writes are atomic — written to a temporary file and moved into place — and grants are stored
in a stable sort order, so the file stays diffable and a crash mid-write cannot truncate it.

Note the separation of concerns: live OAuth runtime state, including dynamic client
registrations and token material, lives in a **different**, owner-only file so that
browser-login-once clients keep refreshing across a service restart. That file is not the
listing surface, and it is not committed, logged, or shared. See
[Serving Topology and Authentication](serving-and-authentication.md).

### Revoking

`clients revoke` **previews by default**, reporting the grant, client, scopes, and whether
write was enabled, with `would_revoke` set. With apply, it marks the grant revoked and
inactive with a timestamp, and returns the concrete next effect: a running server sharing that
store refuses the grant on its next access or refresh validation.

Two cases are handled explicitly rather than by error: an unknown grant returns `not_found`,
and an already-revoked grant returns `already_revoked` — so revocation is idempotent and a
repeated attempt is not mistaken for a failure.

Marking the metadata is one half. **Provider-level revocation** invalidates the whole live
grant path including its refresh sibling, so a revoked client cannot quietly recover access by
refreshing.

### Consent is where write access is actually granted

A client gets write access only when the owner approves the `write` scope on a plain,
script-free consent page that shows the client identity, the redirect origin and full redirect
URI, the requested scopes, plain-language consequences, and reject and cancel actions. Both
reject and cancel consume the authorization request without issuing a code or grant.

**Write approval is not a bypass.** It only lets a client *request* the write tool; the
protected-path guard, frontmatter gate, dirty-tree and head-drift checks, audit logging, git
coordination, and any allowlist narrowing all still apply. A client without the scope that
calls the write tool gets an explicit `insufficient_scope` refusal that says exactly this.

Changing the default requested scopes changes only what the consent page **asks for**. It does
not auto-approve any client and does not weaken a single write guard. See
[Configuration and Tunables](configuration-and-tunables.md).
