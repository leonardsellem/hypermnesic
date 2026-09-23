---
type: Reference
title: Provisioning and Diagnostics
description: Getting a host working and proving it works — the local-first proof, non-mutating doctor states, fail-closed public setup, role provisioning, the convergence hook, and client next actions.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-b056bdca91307e7c890b5f5b
    resource: repo://docs/guides/consent-and-clients.md
  - id: openwiki-source-3282651cbcc71b7278bcfc5c
    resource: repo://docs/guides/getting-started.md
  - id: openwiki-source-deb171642843c8fef279b12a
    resource: repo://docs/reference/configuration.md
  - id: openwiki-source-9b37eab1bcb7a0dabc8255c1
    resource: repo://src/hypermnesic/cli.py
  - id: openwiki-source-472937341cb047efdecab446
    resource: repo://src/hypermnesic/client_guidance.py
  - id: openwiki-source-c76fa3ae1f9c3796f441ee08
    resource: repo://src/hypermnesic/converge.py
  - id: openwiki-source-1bbdc3310a71beeeab5013ef
    resource: repo://src/hypermnesic/doctor.py
  - id: openwiki-source-54a007908deccb21b5ddc567
    resource: repo://src/hypermnesic/install.py
  - id: openwiki-source-33b20611aee0ccb46de27828
    resource: repo://src/hypermnesic/local_proof.py
  - id: openwiki-source-98c095b66db6365e82c220ad
    resource: repo://tests/test_doctor.py
  - id: openwiki-source-f266c4d52f0afb99267b94f3
    resource: repo://tests/test_install.py
  - id: openwiki-source-420210bcd82ad8b6dc3b5592
    resource: repo://tests/test_local_proof.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Provisioning and Diagnostics

The ordering principle here is that **you prove local memory works before any endpoint
concept enters the conversation.** A remote setup failure is much easier to diagnose when you
already know the vault, the index, and retrieval are fine.

## Local proof: the first thing to run

`local-proof` is a thin orchestration over primitives that already exist — git validation,
index projection, retrieval, and a write-path dry run. It deliberately **provisions nothing**:
no endpoints, no clients, no services.

Against an existing vault it is **read-only by default**. It confirms the vault is a git repo,
projects committed markdown into the index, retrieves an answer to a natural question, shows
the repo-relative path the answer came from, and previews a write as a dry-run diff. It does
not create sample content unless you explicitly ask it to seed one. Demo mode builds a small
dedicated git-backed vault instead.

The result is a **stable contract** rather than prose: a status, an ordered list of completed
milestones (git vault confirmed → markdown memory found → index projected → natural question
retrieved → source path shown → dry-run write previewed), degraded capabilities, the retrieval
hit, the write preview, index information, and a next action.

Failures are equally structured. Passing both a repo and a demo directory, passing neither,
or retrieving nothing all raise an error carrying a stable **code**, a message, and a concrete
**next action** — "add a note containing the answer, rerun with a different query, or use the
demo vault" rather than a stack trace.

Everything the proof echoes back is **sanitized** first: bearer tokens, API-key-shaped strings,
approval-token assignments, and operator home paths are redacted before any heading or snippet
is printed. A diagnostic that leaks a credential is worse than no diagnostic.

The proof is lexical by default, so it works with **no API key at all**; the dense channel is
opt-in.

## Diagnostics: `doctor` and `status`

Both names are one command, built from a single parser definition, and both are strictly
**non-mutating** — they write no files, no services, no secrets, and no commits.

Checks are grouped by category — local, remote, oauth, auth, write — and each returns a
status, a human summary, a stable action code, a next action, an optional command to run, and
a documentation pointer. Skipped checks are *reported as skipped* with the reason, so an
offline run reads as "not evaluated" rather than silently passing.

Without a public URL, every remote check — Tailscale readiness, the endpoint, OAuth discovery,
the auth challenge, write availability — is explicitly skipped. Local diagnosis works with no
network at all.

### A configured credential is not a healthy projection

This distinction is the most useful thing `doctor` reports, and it is easy to get wrong by
hand. The dense check reports a `key_source`, a `dense_state`, and vector coverage — all
secret-free — and separates four situations:

| State | Meaning | What to do |
|---|---|---|
| `not_configured` | No key discovered at all. | Configure one, or accept lexical-only retrieval. |
| `configured_unverified` | A key was found but not exercised. **The default**, so diagnosis stays offline and never spends. | Pass the live-check flag if you need certainty. |
| `configured_valid` / `configured_invalid` | Only reachable with the opt-in live smoke embedding, which distinguishes them **without ever printing the key**. | Fix the credential if invalid. |
| `index_missing_or_unbuilt` | The credential is fine; there is no index yet. | Build the projection. |
| `vectors_stale_or_absent` | The credential is fine and the index exists, but its vectors lag. | Converge first; reindex only if convergence recommends it. |

The last two are the point: a valid key tells you nothing about whether the projection is
healthy, and the remedies are different — convergence, not a full reindex, is usually the
answer. See [Read-Time Convergence](read-time-convergence.md).

The index check likewise distinguishes three states — missing, present but possibly lagging
`HEAD`, and present and current enough — rather than a binary.

### Checking a secret without reading it

Given a consent-secret file path, `doctor` reports only two things: whether it exists, and
whether its permissions are owner-only. Anything broader is a warning with a concrete
remediation command. **The file's contents are never read or printed.** Omitting the path
yields a skipped check explaining what passing it would do.

## Setting up the public endpoint

`setup` brings the unified public endpoint online in one **idempotent** command: render and
install the service unit, persist the operator consent secret to an owner-only env file,
configure the routes for the MCP path and the discovery well-knowns, verify the live HTTPS
discovery chain, and return the URL plus login instructions. Re-running converges to the same
state.

### Fail-closed, and ordered to make that possible

The ordering is the mechanism:

1. **Before any side effect**: validate that the public URL and resource are public HTTPS
   origins, normalize the default client scopes and fail loudly on an unsupported one, confirm
   the target is a git repo, confirm the engine credential is discoverable, and confirm the
   tunnel prerequisite is installed and authenticated. Any of these fails with an actionable
   message and **nothing has been created**.
2. **Side effects, in order**: persist the consent secret, render and start the service,
   apply the routes.
3. **After the routes exist**: verify the real discovery chain over HTTPS. If a well-known
   does not resolve to this service, the command **fails** — explicitly checking real output
   rather than trusting an exit code.

That is what "fail-closed" means here: a failure never leaves you with a half-configured
public endpoint that appears to work.

`setup` never manages the tunnel software itself. If it is missing, you are told to install it
and re-run — the command does not take over a dependency it cannot own.

Secrets stay in owner-only env files and are never inlined into a rendered unit. The result
reports milestones, a plain-language "what this means", client next actions, and next steps —
including that each client opens a browser once on first connect and that the consent page
still requires the operator approval credential.

## Role provisioning

`install` provisions a host into one of three roles — `single`, `master`, or `client` — and is
**pure, offline, and idempotent**. It verifies the environment, renders the service artifacts,
writes the role configuration, and installs the convergence hook.

What it deliberately does *not* do is perform the host-specific side-effectful steps: building
the index and enabling or starting the service come back as `manual_steps` rather than being
run. An unknown role is rejected against the known set instead of being guessed at. The
embedding credential's value is never echoed into any rendered artifact.

## The convergence hook

The post-merge hook keeps the index caught up after a pull, and it is **opt-in, idempotent,
and non-destructive**. Installation manages only a delimited block: an existing hook has its
managed block replaced and any operator content preserved; a missing hook is created with a
shebang; the hook is made executable.

Uninstalling removes **only** the managed block. If what remains is nothing but a bare
shebang, the file is removed entirely rather than left as a stub. The hook file is read once
rather than re-read, avoiding a check-then-act window.

## Client next actions

Both `setup` and `doctor` return **secret-free** per-client guidance, so the answer to "what
do I do now?" is part of the diagnostic rather than something to look up.

Each entry names a client surface — the local CLI, a generic remote MCP client, the coding
agent plugin, and others — with whether it is currently available, a summary, and a concrete
next action. Availability is honest: without a public URL the remote entries report
unavailable and tell you to run setup with one first, instead of printing instructions that
cannot work yet. The local CLI entry is always available, because it needs no remote setup at
all. See [CLI Surface](cli-surface.md) and
[Serving Topology and Authentication](serving-and-authentication.md).
