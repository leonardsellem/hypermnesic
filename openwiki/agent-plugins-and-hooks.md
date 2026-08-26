---
type: Reference
title: Agent Plugins and Hooks
description: How hypermnesic reaches agent hosts — the Claude Code/Codex pack and its auto-recall hook, the Hermes CLI pack, and the arm's-length Obsidian companion boundary.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-09160a15c85836458c6d2077
    resource: repo://.claude-plugin/marketplace.json
  - id: openwiki-source-1f366c0f066b53e2ffd37c97
    resource: repo://docs/guides/daily-workflows.md
  - id: openwiki-source-082442cff6ee589b6648d482
    resource: repo://docs/guides/memory-taxonomy.md
  - id: openwiki-source-542368e84795ac7a8f468ea2
    resource: repo://obsidian-plugin/README.md
  - id: openwiki-source-a6ff08c15afa112fd12ab021
    resource: repo://plugin/hermes/__init__.py
  - id: openwiki-source-9f0cd35346c612a7c19a8d43
    resource: repo://plugin/hermes/plugin.yaml
  - id: openwiki-source-78ea31e2438f3de9725a3967
    resource: repo://plugin/hermes/skills/hypermnesic-memory/SKILL.md
  - id: openwiki-source-44959b14c9f7984c34cf9eca
    resource: repo://plugin/plugins/hypermnesic/.claude-plugin/plugin.json
  - id: openwiki-source-ab10374e669f34e59a9e178f
    resource: repo://plugin/plugins/hypermnesic/.mcp.json
  - id: openwiki-source-743e2e4e1166cf9d99f27db5
    resource: repo://plugin/plugins/hypermnesic/hooks/hooks.json
  - id: openwiki-source-f945110b610983e29a3ca313
    resource: repo://plugin/plugins/hypermnesic/hooks/scripts/hypermnesic_agent_hook.py
  - id: openwiki-source-040afdd7bd83454d678e4ad2
    resource: repo://plugin/plugins/hypermnesic/hooks/scripts/hypermnesic_hook_status.py
  - id: openwiki-source-bcf3a4ff129d9883dbfd613f
    resource: repo://plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md
  - id: openwiki-source-0f6af6c5f732c3798e563653
    resource: repo://plugin/README.md
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-9d58473aaf6ce4dff178c003
    resource: repo://tests/test_hermes_plugin_hook.py
  - id: openwiki-source-53609349392bb51a54b863a3
    resource: repo://tests/test_hermes_plugin.py
  - id: openwiki-source-647ad40046580fda69f7163b
    resource: repo://tests/test_plugin_hook.py
  - id: openwiki-source-2711bb7cd9d38c160c128c4b
    resource: repo://tests/test_plugin.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Agent Plugins and Hooks

hypermnesic is a server. Everything on this page is about how *client* agents reach it
without the operator wiring each one by hand. Three integration surfaces exist, and they
are deliberately not one thing:

| Surface | Lives in | Transport | Loaded by |
|---|---|---|---|
| Claude Code + Codex pack | `plugin/plugins/hypermnesic/` | MCP over HTTP (OAuth) | marketplace install |
| Hermes Agent pack | `plugin/hermes/` | the local `hypermnesic` CLI | `register(ctx)` |
| Obsidian companion | a separate repository | read-only MCP wire | Obsidian |

The Hermes pack does not consume the Claude/Codex manifests or their MCP wiring, and the
Obsidian companion is not in this repository at all. Keeping them separate is what lets
the license boundary below hold.

## The Claude Code + Codex pack

```
plugin/plugins/hypermnesic/
  .claude-plugin/plugin.json   # Claude manifest — declares only a skills path
  .codex-plugin/plugin.json    # Codex manifest — skills + an interface block
  .mcp.json                    # OAuth-discovery MCP wiring
  skills/hypermnesic-memory/   # the skill: when and how to use memory
  hooks/hooks.json             # one UserPromptSubmit hook
  hooks/scripts/               # the hook and its status helper
```

The **skill** is the primary surface and carries no per-turn cost: its description is
discoverable, and the agent reaches for `search`, `build_context`, `think`, `resolve`,
`list_folders`, and `commit_note` when memory is actually relevant. See
[MCP Tool Surface](mcp-tool-surface.md) for those tools' contracts.

Two marketplace manifests exist on purpose. Claude Code only discovers `marketplace.json`
at a checkout *root*, so the repository carries one at `.claude-plugin/marketplace.json`
(which enables installing straight from GitHub) alongside `plugin/.claude-plugin/marketplace.json`
(the local-directory source). The root manifest lists only `name` and `source`; the version
and description live solely in the plugin manifest, so a version bump touches one file and
the two manifests cannot drift.

### Why the MCP wiring carries no token

`.mcp.json` declares a `streamable-http` server whose URL is templated from
`HYPERMNESIC_MCP_URL`, with a placeholder default. It contains **no `auth` block and no
static `Authorization` header**, and that omission is the point: a static header would
suppress the OAuth discovery the host needs. From `{type, url}` alone the agent host
discovers the Authorization Server, opens a browser once for the operator to authorize —
read by default, `write` approved explicitly at the consent page to enable `commit_note` —
then stores and silently refreshes the token. See
[Serving Topology and Authentication](serving-and-authentication.md).

The wiring is also distribution-generic: no operator hostname, no token, nothing
machine-specific. A test asserts the whole plugin tree carries no operator-specific values
and no committed secrets.

## The auto-recall hook

`hooks/hooks.json` wires exactly one event — `UserPromptSubmit` — to
`hypermnesic_agent_hook.py --host claude` with a 6-second timeout. There is no
`SessionStart` preamble and no Bash interception; the hook does one thing.

**It can never block a turn.** Every path returns `{"continue": true}`; context is added
only through `hookSpecificOutput.additionalContext`. A malformed payload prints a diagnostic
to stderr and still emits `{"continue": true}`. Any event that is not a prompt-submit
variant is inert.

The order of gates before any network call is: disabled check → relevance → endpoint
configured → credential available → non-empty query. Relevance is deliberately cheap —
memory-ish phrasing (`remember`, `recall`, `what do we know`, …) or a multi-word
proper-noun match — so an off-topic prompt costs nothing.

The lookup itself is bounded: one JSON-RPC `tools/call` to `search` with `k=5` and a
2.5-second timeout, at most five hits rendered, each snippet trimmed to 200 characters
with newlines flattened so a note's content cannot forge structure in the injected block.

### Why the hook has its own credential path

Claude Code exposes no stored MCP OAuth token to hook subprocesses — the prompt payload
carries no credential — so the hook cannot ride the app's OAuth login. Its working remote
path is the tailnet read companion, which needs only a URL. `HYPERMNESIC_MCP_TOKEN` is
therefore **optional**, used only in the `Authorization` header, and never written to
stdout, stderr, or the injected text. When no token is set and the endpoint is not a
tailnet address, the hook stops at `missing_credential` rather than sending an
unauthenticated request.

### Observing a hook that is silent by design

Silence is ambiguous, so the outcome is recorded out of band. Every run writes a small
status record whose `last_outcome` is one of a fixed set: `never_run`, `off_topic`,
`disabled_global`, `disabled_host`, `unconfigured_endpoint`, `missing_credential`,
`auth_expired`, `timeout`, `lookup_failed`, `no_hits`, `degraded_lexical_only`, `success`.
Each maps to a plain-language explanation.

What the record holds is **categories, not values**: the endpoint is reduced to
`local` / `tailnet_read` / `public_https` / `other` / `unset`, and the credential to
`token_present` / `not_required_tailnet` / `missing`. The full prompt, the endpoint URL,
the token, the `Authorization` header, and raw large snippets are never stored.

Status writes are best-effort: the whole write is wrapped so an unwritable path can never
block the hook, and a missing status file reads back as `never_run` rather than an error.

```sh
hooks/scripts/hypermnesic_hook_status.py status --json --host claude
hooks/scripts/hypermnesic_hook_status.py test-recall "Project Atlas" --json --host claude
```

`test-recall` runs the same bounded path for an explicit query and prints sanitized
path/heading/snippet previews, marking the record `test_initiated` so a diagnostic run is
distinguishable from real traffic.

Two environment switches disable proactive recall without uninstalling anything:
`HYPERMNESIC_HOOK_DISABLE_LOOKUP=1` for the whole install, and
`HYPERMNESIC_HOOK_DISABLED_HOSTS=codex` (comma-separated) per host. Both are checked before
relevance, so a disabled hook does no work at all. See
[Configuration and Tunables](configuration-and-tunables.md) for the full variable list.

## The Hermes pack

Hermes talks to the **local CLI**, not to MCP. `plugin/hermes/plugin.yaml` declares the
plugin and the one environment variable it needs, `HYPERMNESIC_REPO` (marked non-secret).
`register(ctx)` always registers the memory skill, and registers a `pre_llm_call` recall
hook **only** when `HYPERMNESIC_HERMES_RECALL` is truthy — proactive recall is opt-in here.

That hook shells out to `hypermnesic retrieve <repo> <query> --k 3 --now --json`, optionally
with `--index-db`, under a 3-second timeout, and returns at most three hits capped at 1400
characters total. Every failure — irrelevant message, unset repo, subprocess error, non-zero
exit, unparseable JSON, no hits — returns `None`, which is silence.

A test asserts the Hermes package carries no MCP transport assumptions and no Claude/Codex
loader assumptions, which is what keeps the two packs independent rather than accidentally
coupled.

## The Obsidian companion boundary

The companion is **not in this repository**. It ships from its own public repository under
**GPL-3.0-or-later**, while the engine here is **AGPL-3.0-only**. The two communicate only
at arm's length over the read-only MCP wire — `search`, `build_context`, `think` — as
separate processes with no shared or statically linked code, so neither is a derivative of
the other. That reasoning is conditional, not permanent: it holds **only while the companion
does not vendor, import, or statically link engine source**. The companion enforces that
with a static read-only invariant scan in its own suite.

In the daily loop Obsidian is a review and navigation surface for capture backlog, generated
dashboards, and source paths. Write, cleanup, revoke, forget, and revert all stay in the
git-first CLI/MCP surfaces; a read-only client cannot bypass consent, write scope,
protected-path refusals, or any server-side guard — see
[Write Guard and Security Model](write-guard-and-security-model.md).

## What the skills teach about what to store

Both skill files carry the same routing rule, so an agent gets it regardless of host.
hypermnesic is **durable project memory**: semantic facts, episodic/source evidence,
procedural policy, generated summaries that cite source paths, raw captures, and
current-state mirrors. Behavioural preferences ("user likes terse replies") and temporary
session state belong in an adjacent behavioural layer, not here. Secrets, credentials,
private keys, and bearer tokens are never written.

The skills also teach agents to preserve raw evidence rather than replacing it with
summaries, to call `list_folders` when the destination is unclear, and to treat a write
refusal as a control signal rather than something to route around by changing paths or
transports.
