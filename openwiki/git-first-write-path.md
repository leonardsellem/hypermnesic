---
type: Reference
title: Git-First Write Path
description: The single sanctioned write, traced end to end — guard order, the diff-or-die frontmatter gate, multi-host coordination, the refusal contract, degraded-index success, and the append-only audit log.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-362e06c30ccfdafd87339cb0
    resource: repo://ARCHITECTURE.md
  - id: openwiki-source-b71cfd92d11a88500eb68d63
    resource: repo://src/hypermnesic/audit_log.py
  - id: openwiki-source-f103fa2315aae36568406e00
    resource: repo://src/hypermnesic/commit_note.py
  - id: openwiki-source-c76fa3ae1f9c3796f441ee08
    resource: repo://src/hypermnesic/converge.py
  - id: openwiki-source-69bff653ec6e8898c6956b32
    resource: repo://src/hypermnesic/frontmatter_gate.py
  - id: openwiki-source-37433895d4b7b6af7cd92f4f
    resource: repo://src/hypermnesic/mcp_server.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-c1e23b0afbab9875c0484f8b
    resource: repo://tests/test_audit_log.py
  - id: openwiki-source-f30c2de69321a16c4ce3b678
    resource: repo://tests/test_commit_note.py
  - id: openwiki-source-2dd757f2a211bfeced6cd96b
    resource: repo://tests/test_frontmatter_gate.py
  - id: openwiki-source-9241ab90871fd251f3253d0f
    resource: repo://tests/test_mcp_server.py
  - id: openwiki-source-72d58b8d6d14537f15734dec
    resource: repo://tests/test_rename.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Git-First Write Path

`commit_note` is the **one** sanctioned way to change the corpus. Everything else — capture,
triage, sidecars, dashboards — either routes through it or produces a proposal a human
approves. There is no second write lane, and in particular there is no database-first lane
that the index could win.

## The order, and why the order is the security property

```
guard  →  frontmatter gate  →  write file  →  git add/commit  →  push  →  index projection  →  audit
```

Read that left to right and note what each step protects:

1. **The path guard runs first**, before the file is read or the body is touched. A refused
   path is refused *before* any content work happens, so a protected path cannot be reached
   by a clever body or a frontmatter trick. See
   [Write Guard and Security Model](write-guard-and-security-model.md).
2. **The frontmatter gate runs before anything is written.** It computes the new text and
   aborts on drift, so a gate abort leaves the working tree untouched.
3. **Git is the only synchronous layer.** The durable unit is a real commit — not a staged
   change — which is what makes a write recoverable from `HEAD` alone.
4. **The index projection is last and best-effort**, because by then the commit exists and
   cannot be unmade.
5. **The audit entry records the git write**, so it must not depend on whether the index
   projection succeeded.

A single-writer lock is taken around the whole locked section. It is process-local, so it is
not what isolates concurrent committers — see coordination below.

## The frontmatter gate: diff-or-die

**A write may change only the lines it was asked to change.** Frontmatter is parsed with a
round-trip-preserving YAML implementation so untouched keys stay byte-identical: scalar dates
stay scalar, key order survives, underscore-prefixed properties survive. Then the gate
**diffs** the frontmatter before and after and **aborts**, surfacing the offending diff, if
any key changed that the caller did not request.

Change detection is deliberately strict. Keys are compared as line blocks, so an addition, a
removal, or a **reordering** all count as drift — reordering included, because a tool that
silently reorders your frontmatter is a tool that will eventually rewrite it.

There are two edit strategies, and the preferred one exists to avoid false aborts:

- **Surgical line edit** — for a set of pure scalar values on existing top-level keys, only
  those value tokens are replaced in place. Every other byte is untouched, so a block list
  elsewhere in the frontmatter cannot reflow and trip the gate.
- **Structural round-trip** — used when a field is being added or deleted, or when a value is
  a list or block scalar. This is the general path, and its output still goes through the same
  drift assertion.

A document written in a different YAML style will **abort rather than churn**. That is the
intended failure mode: a refusal you can see beats a silent reformat of someone's notes.

A file with no frontmatter is fine — the body is replaced directly — but asking to set
frontmatter fields on a file that has none is an error rather than an implicit creation.

## Multi-host coordination

When the vault has a git remote, the write path converges with it **before** writing:

1. `fetch` the remote and **fast-forward** the local branch. A divergence that cannot be
   fast-forwarded is a refusal — never a merge, because the agent never merges.
2. Re-check `HEAD` against the base captured when the file was read. A mismatch is a
   **head-drift refusal**, so an edit computed against a stale base aborts cleanly instead of
   clobbering someone else's change.
3. Write, stage, and commit — then push, retrying on a non-fast-forward by fetching and
   rebasing the single commit onto the advanced tip.

If the push cannot succeed — a conflicting change, an auth or network failure, or exhausted
retries — the local-ahead commit is **dropped** and the write is refused. This matters: an
un-pushed local commit would wedge every fast-forward-only puller on that checkout. The tree
is restored to the remote tip before the refusal is raised.

With no remote configured, coordination is skipped entirely and the write is a local commit.

**Every git operation is path-scoped.** Staging, the "did anything actually stage" check, and
the commit itself all name this note's path explicitly. On a shared checkout another
committer may have unrelated changes staged; the pathspec — not the lock — is what stops
their work from being swept into this commit and pushed. The process-local lock provides no
cross-process exclusion, so this is not an optimization, it is the isolation mechanism.

## Idempotence and no-ops

A write whose result is byte-identical to the existing content is a **no-op**: nothing is
committed and nothing is logged. The same is true if, after staging, git reports nothing
staged for that path. Both return a result with `noop` set rather than a fabricated commit.

## The refusal contract

> **A refusal is never a silent success, and never leaves a partial write.**

Every refusal class — a protected-path or allowlist refusal from the guard, a frontmatter
drift abort, a head-drift or dirty-tree refusal, or a coordination failure — surfaces as an
explicit `{committed: false, refused: "<reason>"}` result. On any of these, no commit reached
the remote and no audit entry was written.

Over MCP there is one more refusal that happens even earlier: **insufficient scope**. The
write tool self-enforces the `write` scope independently of the transport's global scope
configuration, so a read-scoped token that reaches the tool is refused before any write is
attempted. Its message tells the client to reconnect and approve write access, and says
explicitly that write approval only allows the client to *request* `commit_note` — it does
not bypass protected-path, frontmatter, dirty-tree, head-drift, audit, or git coordination
guards. See [Serving Topology and Authentication](serving-and-authentication.md).

## Degraded success: when the commit landed but the index did not

Once the commit is on the remote it **cannot be unmade**. So a failure to project it into the
index is reported as a *degraded success*, not an error: the result carries the real
`new_sha` along with `index_degraded` and a stable reason.

This distinction is not pedantry. Raising here would tell the calling agent that nothing was
written, and a well-behaved agent would then write the same note somewhere else — duplicating
content in response to a purely cosmetic failure. The tool description says it outright: keep
the returned SHA and do not write the note again. The index is disposable and a reindex
restores it. See [Architecture Overview](architecture-overview.md).

Embedding is explicitly **asynchronous** and never blocks a write: a new note is findable
lexically immediately, and its dense vectors catch up later through convergence.

## The audit log

Every write appends one structured JSONL entry: timestamp, actor, verb, path, old SHA, new
SHA, and summary.

- **Summaries only — never page bodies.** This is a deliberate scar: a private-content leak
  through a diagnostic output is exactly what the constraint prevents. Summaries are truncated
  to a bounded length by contract.
- **The actor is server-set.** It is derived from a verified node identity or a fixed
  sentinel, and a caller-supplied actor is *ignored*, never trusted.
- **Refusals are logged too**, as body-free events carrying the attempted verb, path, and a
  refusal category, so an owner or auditor can see what was blocked and not only what
  succeeded. Refusal summaries are additionally scanned for token-shaped strings, which are
  redacted before the entry is written.
- **A reconciler back-fills gaps.** If a process crashes between the commit and the log
  append, `reconcile` walks commits on `HEAD` that carry no entry and records them, so a gap
  is recoverable rather than permanent.

The log is opened in append mode only. See
[Memory and Client Control](memory-and-client-control.md) for the surfaces that read it back.

## Renames

`rename_note` is the atomic move surface: `git mv` plus an index re-key, with no
re-materialization of the old path. The guard runs on **both** ends, so neither the source nor
the destination can escape it. An optional content edit in the same move goes through the
frontmatter gate **first**, so a gate abort means no git operation happens at all.

An optional tombstone sink is invoked with the neutral repo-relative old path just before the
removing git operation — after the gate, so an abort leaves no orphan tombstone, and before
the move, so a crash mid-operation cannot leave an un-tombstoned orphan. It defaults to doing
nothing: the engine owns no external path or format and takes on no dependency on any
companion system that might be restoring files from elsewhere.
