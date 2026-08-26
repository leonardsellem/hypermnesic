---
type: Reference
title: Write Guard and Security Model
description: The blocklist write surface and the protections around it — protected classes, the governance fence, within-repo resolution, allowlist narrowing, locks, body-free auditing, and what never leaves the process.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-5f5b95b3d6a215fa02ceb945
    resource: repo://.env.example
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-bdafb7b3f6e1833bd8499e8b
    resource: repo://docs/2026-06-03-blocklist-write-surface-security-review.md
  - id: openwiki-source-196170e31ff8ec60a116165b
    resource: repo://docs/README.md
  - id: openwiki-source-98f8a82bb4c4fe5df0016f30
    resource: repo://docs/threat-model-commit-note.md
  - id: openwiki-source-040afdd7bd83454d678e4ad2
    resource: repo://plugin/plugins/hypermnesic/hooks/scripts/hypermnesic_hook_status.py
  - id: openwiki-source-12224262a7b33bff0baf3679
    resource: repo://scripts/preflight_public_scan.py
  - id: openwiki-source-3a44815832a872f4778f822b
    resource: repo://SECURITY.md
  - id: openwiki-source-b71cfd92d11a88500eb68d63
    resource: repo://src/hypermnesic/audit_log.py
  - id: openwiki-source-5f17d71d8e2d83b9ea0bc2ae
    resource: repo://src/hypermnesic/config.py
  - id: openwiki-source-1bbdc3310a71beeeab5013ef
    resource: repo://src/hypermnesic/doctor.py
  - id: openwiki-source-a549bbb642c1fa61b486d5ae
    resource: repo://src/hypermnesic/folders.py
  - id: openwiki-source-69bff653ec6e8898c6956b32
    resource: repo://src/hypermnesic/frontmatter_gate.py
  - id: openwiki-source-d0c2638cdea3e85ab949dd06
    resource: repo://src/hypermnesic/index.py
  - id: openwiki-source-33b20611aee0ccb46de27828
    resource: repo://src/hypermnesic/local_proof.py
  - id: openwiki-source-37433895d4b7b6af7cd92f4f
    resource: repo://src/hypermnesic/mcp_server.py
  - id: openwiki-source-802c4acce1763f2c8920a3cf
    resource: repo://src/hypermnesic/propose.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-b5b1810a68834b1277d652e1
    resource: repo://tests/test_blocklist_write_gate.py
  - id: openwiki-source-84bf43836af5a7c7a11cf9f7
    resource: repo://tests/test_preflight_public_scan.py
  - id: openwiki-source-b20923388e0121609cb2fdc7
    resource: repo://tests/test_serialize.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Write Guard and Security Model

The write surface is the highest-value target in this system, and it is bounded by rules
rather than by trust in the caller.

## Blocklist, not allowlist

**The default write surface is a blocklist: write-anywhere-under-guards.** A note may land
anywhere in the vault *except* the protected classes. This is a deliberate posture reversal
from an earlier default that allowed only a handful of prefixes — anything describing an
"allowlist by default" is superseded.

An allowlist still exists, but only as an **opt-in narrowing**. Passing one bounds where a
write may land; it never widens the surface, and it can never re-enable a protected class. The
protected-path refusal is evaluated **first and independently of any allowlist** — that is the
real bound.

Why the reversal matters: the old allowlist blocked dangerous file classes only *by exclusion*,
as a side effect of listing a few content prefixes. Making content folders writable removed
that accidental backstop, so the dangerous classes are now refused **positively** by name and
class. A guard that protects by accident stops protecting the moment its unrelated premise
changes.

## The protected classes

The denylist is a **rule about file classes**, not a fixed list of paths. That distinction is
what lets it hold when the engine is dropped into an arbitrary repository it has never seen.

| Category | Why it is refused |
|---|---|
| Version-control internals and engine state directories | Writing here corrupts the source of truth or the projection itself. |
| CI and workflow directories | A writable workflow is arbitrary code execution on the project's infrastructure. |
| Executable directories — scripts, binaries, hooks, skills | Same reason: a write becomes execution. |
| Agent-instruction files **anywhere in the tree**, nested included | This is privilege escalation: whoever writes the instructions steers every future agent. |
| Editor and agent configuration directories | Configuration is control. |
| Git metadata files that are never a write target | Changing ignore or attribute rules changes what the system can see and do. |
| A governance / build / CI / credential **file class** — container and build files, package manifests and lockfiles, credential dotfiles, and the configuration/lockfile extensions | Closes the residual left when the allowlist stopped being the default. |

Two implementation details carry real weight:

- **Directory matching is case-insensitive.** On a case-insensitive filesystem a differently
  cased directory name lands in the protected directory on disk, so a case-sensitive match
  would report it writable. That hole was inert under the old allowlist and reachable under
  the blocklist, so it was closed when the default flipped.
- **Ordering is chosen so the most informative reason wins.** Directory checks run before the
  governance file-class check, so a workflow file inside a CI directory is reported as a
  protected directory rather than as a generic file class.

The exact enumerated set and its sign-off live in the dated blocklist security review; the
authority is the guard module, and the rule is the file class rather than the list.

## Path resolution

Separately from classification, a write target must actually be inside the repository:

- An **absolute path** is refused outright.
- The path is **resolved** against the repository root, and a result that does not sit under
  that root is refused as escaping. Because this uses real resolution, `..` traversal **and a
  symlink escape** are both caught — a symlink pointing outside the repository resolves
  outside it and is refused like any other escape.

Classification and resolution are deliberately split: resolution needs repository context,
while the class decision is pure and path-clean. That purity is what lets folder discovery
surface the same reason string verbatim, so **discovery and the write path share exactly one
rule** and cannot drift. See [MCP Tool Surface](mcp-tool-surface.md).

## Serialization and preflight

Locks are advisory exclusive file locks that conflict **across descriptors even within one
process**, so concurrent broad writers and reindexers serialize rather than corrupting the
database. There are two granularities: a single-indexer lock for broad writers, and
path-scoped locks so distinct paths proceed concurrently.

Preflight catches two multi-host conditions before a write: **head drift**, where `HEAD` moved
out from under the base a caller read, and — for broad writers — a **dirty tree**. The engine's
own state directory is excluded from git's view, so it never registers as a dirty change.

The proposal path adds an isolated-worktree transaction: a set of files lands as **one atomic
commit on a side branch**, built inside a temporary worktree so the owner's live checkout is
never touched. Any failure rolls back both the worktree and the half-built branch, so no orphan
ref survives. See [Review and Navigation Surfaces](review-and-navigation-surfaces.md).

## What never leaves the process

Credentials — the embedding key, the OAuth consent secret, bearer and refresh tokens — are read
from the environment or gitignored state **only**, and are never written to the index, the audit
log, or any output. Concretely:

- The **audit log** records summaries only, never page bodies, and its refusal entries are
  additionally scanned for token-shaped strings which are redacted before writing.
- **Diagnostics** report categories and file permissions — never values. A consent-secret check
  confirms existence and owner-only permissions without reading the file.
- The **local proof** redacts bearer tokens, key-shaped strings, approval-token assignments, and
  operator home paths from anything it echoes.
- The **hook status** file stores endpoint and credential *categories*, never the URL, the
  token, the header, or the prompt.
- **Folder discovery** sanitizes instruction-file content before returning it, replacing endpoint
  URLs and host-local absolute paths with placeholders.
- A **repository scan gate** enforces that no operator host, address, or credential ships in the
  public surface, and masks any match it reports so the gate itself never re-prints a secret into
  a log. See [Testing and Release Gates](testing-and-release-gates.md).

## The threat model, and what is accepted

The threat model enumerates the vectors against the write surface — protected-path escalation,
prompt injection through ingested content, frontmatter clobbering, actor spoofing, audit-log
leakage, path traversal, ignore-file side effects, concurrent-writer corruption, credential
exposure, and crash recovery — with later dated amendments covering token validation bypass,
audience confusion, authorization-server blast radius, the inverted failure mode where an auth
bug *opens* the write surface, and the bounded tailnet-write opt-in.

Two entries are worth internalizing because they shape how you integrate:

**Prompt injection is bounded, not solved.** The engine treats retrieved content as **data, not
instructions**: it never auto-acts on retrieved text, and every write is an explicit,
authenticated call. Even a successful injection cannot reach governance files, because the path
guard bounds the blast radius. But the engine does **not sanitize content for injection**, and
that is an explicitly accepted risk — a downstream agent harness must treat retrieved content
as untrusted. This is an integration assumption, stated rather than assumed.

**Frontmatter churn is treated as corruption.** Silent reserialization — dates rewritten, keys
reordered, custom properties dropped — is a data-integrity failure, which is why the gate
aborts and surfaces the offending diff instead of writing. See
[Git-First Write Path](git-first-write-path.md).

Other accepted risks are named plainly: no multi-tenant authorization, a malicious operator is
out of scope, and dependency supply chain is covered by the license gate and ordinary hygiene
rather than by anything write-surface specific.

## Working on this surface

Security reviews are **immutable dated deltas** carrying amendment and sign-off frontmatter,
forming an audit chain. A new finding is a **new dated review**, never an edit to an existing
one — a signed-off review that can be rewritten is not evidence of anything.

Changes to the guard, the gate, auth, or the server are security-sensitive: they are routed to
the owner through code-ownership rules and are expected to cite the security policy and the
threat model. Vulnerabilities are reported privately, never in a public issue, and reports must
not contain live tokens, hostnames, or addresses.
