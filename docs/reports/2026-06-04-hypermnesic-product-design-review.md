---
date: 2026-06-04
topic: hypermnesic-product-design-review
type: product-design-review
status: current
review_lens:
  - onboarding
  - usability
  - trust-and-control
  - llm-memory-layer-best-practices
  - first-class-product-readiness
sources:
  - README.md
  - docs/guides/getting-started.md
  - docs/reference/cli.md
  - docs/reference/mcp-tools.md
  - docs/why-hypermnesic.md
  - plugin/README.md
  - plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md
  - src/hypermnesic/cli.py
  - src/hypermnesic/install.py
  - src/hypermnesic/mcp_server.py
  - src/hypermnesic/auth_cloud.py
  - src/hypermnesic/capture.py
  - src/hypermnesic/nav_surface.py
  - docs/brainstorms/2026-06-03-first-class-documentation-requirements.md
  - docs/brainstorms/2026-06-03-unified-oauth-endpoint-and-setup-requirements.md
  - docs/brainstorms/2026-06-02-obsidian-companion-first-class-ui-requirements.md
---

# Hypermnesic Product Design Review - Onboarding, Usability, and Memory-Layer Best Practices

## Summary

Hypermnesic has the hard part of a serious LLM memory layer: an unusually credible
architecture for durable, self-owned, inspectable, git-backed agent memory. The core system
already has first-class engineering traits: markdown/git as the source of truth, disposable
indexes, read-time convergence, a structurally separated read/write MCP surface, typed tool
schemas, OAuth consent for write, and a git-first write path with refusal semantics and audit.

The product is not yet first-class because the control, onboarding, and confidence surfaces do
not match the strength of the architecture. A first-time user must understand Tailscale, OAuth,
MCP discovery, resource URLs, scopes, plugin install modes, and vault write surfaces before they
see the product's essential value: "my agent found, used, and safely wrote memory I own." A
production-grade memory layer must make memory understandable, governable, and recoverable, not
only retrievable.

The recommended product direction is to add a first-class product layer over the existing core:
a local "memory works" demo, a guided setup and doctor/status path, an explicit memory manager,
a clearer consent and client-control surface, a taxonomy for what belongs in Hypermnesic, and
end-to-end proof flows that show capture -> retrieve -> connect -> consent -> write -> inspect
-> forget/export/revoke. Once those are shipped, Hypermnesic can credibly claim to be first-class.

---

## Review Method

This review used the Product Design plugin's product-flow audit lens, adapted to a CLI/MCP/docs
product rather than a browser app. There was no web UI flow to capture with screenshots, so the
evidence base is the product's actual user-facing surfaces:

- The README quick start and positioning.
- The getting-started guide.
- CLI help and parser behavior.
- MCP tool reference and MCP server registrations.
- OAuth consent page implementation.
- Plugin README and bundled agent skill.
- Existing brainstorms/plans for unified OAuth, first-class documentation, and first-class
  Obsidian companion UI.
- Memory-layer best-practice baselines from adjacent products and current docs.

The review also used the repo-required knowledge layers:

- Hypermnesic lookup: surfaced the original product vision and the later lesson that Hypermnesic
  should be long-term/project memory while Honcho remains behavioural/session memory.
- Honcho lookup: confirmed the operator's preference for controlled indirection, policy-driven
  configuration, and verification-gated homelab changes.
- ByteRover lookup: no prior product-design review context was found before this audit.
- Product Design context preflight: no saved Product Design context existed, so the repo itself
  was the grounding source.

---

## External Best-Practice Baseline

This review compares Hypermnesic against current patterns in LLM memory products and frameworks.
These are not copied as feature checklists; they define what users and implementers now expect
from a memory layer.

### OpenAI ChatGPT memory controls

OpenAI's memory product language centers user control: users can review saved memories, delete
individual memories, clear all memories, turn memory off, use temporary chats, manage memory
storage, and understand that saved memories are distinct from chat history. The important product
lesson is not OpenAI's exact UI. The lesson is that "memory" is inseparable from a control model:
users need to inspect, remove, disable, and understand provenance. Source:
https://help.openai.com/en/articles/8590148-memory-in-chatgpt-remembering-what-you-chat-about

Hypermnesic has a stronger underlying control substrate because memories are files and commits,
but that strength is not presented as a user-facing memory control center.

### LangGraph / LangChain memory taxonomy

LangGraph frames memory by duration, type, scope, update strategy, storage, and retrieval:
short-term thread state versus long-term cross-session memory; semantic, episodic, and procedural
memory; user/agent/org scopes; hot-path versus background writes; loaded versus on-demand recall.
Source: https://docs.langchain.com/oss/python/concepts/memory

Hypermnesic has enough primitives to map cleanly to this vocabulary, but its onboarding does not
teach the taxonomy. This matters because a durable memory layer becomes dangerous or noisy when
users and agents cannot tell which facts, episodes, behaviours, or project records belong there.

### Zep memory API

Zep's docs emphasize a high-level add/get flow: add messages to memory, retrieve relevant context,
and optionally customize through lower-level graph APIs. Source: https://help.getzep.com/v2/memory

The product lesson is that a memory layer should make the common happy path obvious before
exposing the deeper machinery. Hypermnesic currently exposes the deeper machinery early.

### Mem0 quickstart and memory scopes

Mem0's README emphasizes very fast setup and basic operations: install, initialize, add memory,
search memory, then graduate to self-hosted or platform modes. It also markets multi-level memory
across user, session, and agent state. Source: https://github.com/mem0ai/mem0

Hypermnesic's architecture is more inspectable and owner-controlled, but the first-run experience
does not yet compete with the clarity of "add a memory, search it, see it work."

### Memory consolidation reliability research

The 2026 paper "Useful Memories Become Faulty When Continuously Updated by LLMs" argues that
robust agent memory should treat raw episodes as first-class evidence and gate consolidation
explicitly instead of overwriting evidence after every interaction. Source:
https://arxiv.org/abs/2605.12978

This supports Hypermnesic's git/files posture. Raw markdown and git history are a strong answer
to consolidation drift. The product gap is that the UI/CLI should make the evidence-preserving
model visible and actionable.

---

## What Is Already Strong

### 1. The product thesis is differentiated and defensible

`README.md:10-21` clearly states the core wedge: a git-native memory layer where markdown files
are the source of truth and the index is disposable. `docs/why-hypermnesic.md:12-29` sharpens the
same wedge into four claims: files as truth, git-first writes, one shared endpoint, self-hosted
portability.

This is not cosmetic positioning. It is a real product thesis:

- Users can inspect memory with ordinary tools.
- A reindex cannot lose committed memory.
- Writes are reviewable diffs.
- Memory does not sit in a vendor-owned opaque database.
- Multiple agents can share the same corpus.

That is a meaningful alternative to hosted memory APIs and agent-framework memory stores.

### 2. The read/write capability model is unusually disciplined

`src/hypermnesic/mcp_server.py:1-28` documents the core serving contract: read tools are always
available, while the write tool is structurally separable and only registered when write-enabled.
`src/hypermnesic/mcp_server.py:57-115` defines typed output schemas for tool results, which helps
connectors understand results instead of treating them as opaque blobs.

The registered read tools at `src/hypermnesic/mcp_server.py:361-431` all converge before reading
and are annotated as read-only. The write tool at `src/hypermnesic/mcp_server.py:442-473`
self-enforces the write scope when auth is enabled and returns explicit refusals for guard,
frontmatter, coordination, and dirty-tree failures.

For an LLM memory layer, this is the right safety shape:

- Read and write are not casually mixed.
- Write requires a separate capability.
- Failures are visible refusals, not silent no-ops.
- Tool schemas are explicit.
- The index follows the committed source of truth.

### 3. The consent and auth primitives are security-aware

`src/hypermnesic/auth_cloud.py:1-17` frames why the public endpoint must not auto-approve
connections. It uses Dynamic Client Registration, PKCE, a consent page, audience-bound tokens,
refresh tokens, and revocation. `src/hypermnesic/auth_cloud.py:152-166` requires the operator
approval token and caps repeated failures for a pending authorization. `src/hypermnesic/mcp_server.py:478-492`
renders a consent page showing client, redirect, and scopes.

This is a serious security foundation. The product issue is not that consent is absent. The
issue is that the consent page is still an engineering form, not a first-class trust surface.

### 4. Setup is closer to one-command provisioning than most self-hosted tools

`src/hypermnesic/install.py:489-530` validates the public URL, repo, OpenAI key, Tailscale state,
and then generates a consent secret, service unit, and funnel routes. `src/hypermnesic/install.py:446-486`
verifies the live OAuth discovery chain and unauthenticated 401 behavior.

This is valuable. It means Hypermnesic already has the technical foundation for a high-confidence
guided setup. The gap is presentation, defaults, and diagnostics.

### 5. The product has a credible human-surface direction

`README.md:124-126` names human surfaces: thinking-mode, salience, serendipity connections,
navigation surfaces, capture/triage, sidecar extraction, and a read-only Obsidian companion.
`src/hypermnesic/capture.py:1-10` explicitly separates frictionless raw capture from later
thinking-triage. `src/hypermnesic/nav_surface.py:1-13` describes generated maps of content and
dashboards as review-gated entry points.

These are the right product instincts. They need to be assembled into a coherent first-run and
daily-use experience.

---

## Product Gaps by Severity

### P0. There is no first-class memory control center

**Evidence**

- `docs/reference/mcp-tools.md` documents `search`, `build_context`, `think`, `resolve`,
  `list_folders`, and `commit_note`.
- `docs/reference/cli.md` documents retrieval, folder discovery, commit-note preview, capture,
  serve, setup, and install.
- The code has token revocation support in `auth_cloud.py`, write refusal semantics in
  `mcp_server.py`, and git history as an underlying edit/delete mechanism.
- There is no user-facing memory management surface that says: show remembered items, show where
  they came from, delete/forget, export, restore, revoke a client, disable write, or audit recent
  writes.

**Why this blocks first-classness**

A memory product is judged on control as much as recall. Users need a place to answer:

- What does Hypermnesic remember?
- Where did this memory come from?
- Which agents can read it?
- Which agents can write?
- What changed recently?
- How do I remove this?
- How do I revoke a client?
- How do I export or back up my memory?
- How do I prove a memory was really removed or reverted?

Hypermnesic can technically answer many of these through git, files, audit logs, and OAuth
metadata, but users should not need to derive a control model from implementation details.

**Product requirement**

Create a memory control center exposed at least through CLI, and eventually through Obsidian or a
small local web/status surface. It should make inspect/delete/export/revoke/audit first-class
verbs, not incidental git operations.

### P0. Onboarding leads with infrastructure instead of a memory "aha"

**Evidence**

- `README.md:29-49` quick start asks for `uv tool install .`, `hypermnesic init`, then
  `hypermnesic setup` with Tailscale Funnel, public URL, and resource URL.
- `docs/guides/getting-started.md:20-43` follows the same path and immediately asks users to
  verify OAuth discovery well-knowns.
- `README.md:57-74` then introduces remote app setup, read versus write, consent secret, plugin
  URL, and Obsidian companion routing.

**Why this blocks first-classness**

The current path is operationally accurate but emotionally backwards. A first-time user has to
configure network reach before seeing whether Hypermnesic solves their problem. The product's
first "aha" should be:

1. I created or pointed at a markdown vault.
2. I captured one durable memory.
3. I asked a natural question.
4. Hypermnesic found the memory.
5. I can open the file and see exactly where it lives.

Only after that should remote MCP, OAuth, Tailscale Funnel, write scopes, and plugin install
enter the story.

**Product requirement**

Add a local-first first-run path that proves value without network setup. Then offer "connect my
agents" as the next milestone.

### P0. Setup leaks avoidable concepts and lacks a single diagnostic narrative

**Evidence**

- `src/hypermnesic/cli.py:632-639` makes both `--public-url` and `--resource` required for
  `setup`, even though the help says the resource is usually the same as `--public-url`.
- `README.md:45-49` and `docs/guides/getting-started.md:27-30` require users to repeat the same
  URL twice.
- `src/hypermnesic/install.py:506-521` performs useful validations, but there is no standalone
  `doctor` or `status` command that summarizes the state outside setup.
- `docs/guides/getting-started.md:48-80` lists failure modes, but they are still prose for a user
  to manually apply.

**Why this blocks first-classness**

Self-hosting can be acceptable for Hypermnesic's target user, but avoidable ambiguity cannot.
The product should own diagnosis. Users should not have to infer whether the problem is:

- Not a git repo.
- Missing or unreadable `OPENAI_API_KEY`.
- Tailscale not installed.
- Tailscale not logged in.
- Funnel not allowed.
- Service not running.
- Well-known routes missing.
- OAuth metadata wrong.
- Unauthenticated call does not 401.
- Plugin URL unset.
- Token expired.
- Write scope missing.
- Index stale or degraded.

**Product requirement**

Add a guided setup/status/doctor experience that checks and explains the whole path from local
index to remote client.

### P0. Memory taxonomy and ownership boundaries are implicit

**Evidence**

- The bundled skill says Hypermnesic is for "durable project or personal memory" at
  `plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md:1-24`.
- The global agent instructions and Hypermnesic lookup surfaced a critical learned boundary:
  Hypermnesic is long-term/project durable memory; Honcho is short-term/behavioural/preference
  memory.
- `README.md:17-21` says Hypermnesic is for durable, portable agent memory, but does not teach
  semantic/episodic/procedural scope or what not to store.

**Why this blocks first-classness**

Agent memory products fail when everything gets routed into one store. The user already hit this
regression operationally: installing a strong long-term memory layer caused behavioural memory to
be over-routed into Hypermnesic and starved Honcho.

Hypermnesic needs a first-class "what belongs here" doctrine:

- Durable project facts and notes belong here.
- Source evidence and raw captures belong here.
- Decisions and current-state mirrors belong here.
- Short-term session state usually does not.
- Behavioural preferences may belong in Honcho or another preference layer.
- Sensitive or temporary material needs an explicit capture decision.
- Consolidated summaries should preserve raw evidence.

**Product requirement**

Add a memory taxonomy guide and have onboarding, skills, and write flows reinforce it.

### P1. Consent is secure but not yet a trust-building UX

**Evidence**

- The consent page implementation at `src/hypermnesic/mcp_server.py:478-492` shows title,
  explanatory text, client, redirect, scopes, token input, and Approve button.
- `_consent_headers` at `src/hypermnesic/mcp_server.py:501-521` has no-script CSP,
  anti-clickjacking, no-store, and redirect-origin handling.
- The page does not provide a Reject button, scope-specific plain-language explanation,
  client trust guidance, "read-only vs write" consequences, last-approved client context, or
  post-approval confirmation.

**Why this matters**

Consent is the front door to a public write-capable memory endpoint. Users should feel they know
exactly what they are granting. Security primitives are not enough; the trust surface has to be
legible.

**Product requirement**

Redesign consent as a small authorization flow: approve read, approve write, reject, show what
each scope can do, and show how to revoke later.

### P1. The plugin experience is agent-readable but not owner-observable

**Evidence**

- `plugin/README.md:36-45` describes the skill as the primary surface and one auto-recall hook.
- `plugin/README.md:47-66` explains endpoint config and OAuth discovery.
- `plugin/plugins/hypermnesic/hooks/hooks.json` describes a silent, non-blocking auto-recall hook.

**Why this matters**

Silent recall is good for agent flow but risky for user trust. The owner should be able to see:

- Whether the hook is installed.
- Whether it is configured.
- Whether it is using local CLI, tailnet read, or OAuth.
- When it last recalled context.
- Whether it timed out, got 401, or found no relevant hits.
- How to disable it per host.

**Product requirement**

Add an observable plugin status and hook diagnostics surface.

### P1. Human surfaces exist as ingredients, not as a coherent daily workflow

**Evidence**

- `README.md:124-126` lists thinking-mode, salience digest, serendipity connections, navigation,
  capture/triage, sidecar extraction, and Obsidian companion.
- `src/hypermnesic/capture.py:1-10` makes capture immediate and triage deferred.
- `src/hypermnesic/nav_surface.py:1-13` proposes generated dashboards.
- Existing companion requirements in `docs/brainstorms/2026-06-02-obsidian-companion-first-class-ui-requirements.md`
  focus the Obsidian UI on first-class read-only interaction.

**Why this matters**

The product has the right pieces, but a first-time or daily user needs flows:

- Capture something now.
- Later triage it.
- Ask what is known.
- Expand context.
- Follow links.
- Approve a write.
- Review recent changes.
- Clean up or forget.

Without named flows, planning can ship disconnected tools instead of a product.

**Product requirement**

Define and implement the daily loops as product flows, not only commands.

### P1. The docs are strong for architecture but weak for first-run comprehension

**Evidence**

- `docs/brainstorms/2026-06-03-first-class-documentation-requirements.md` already covers public
  documentation readiness, reference docs, CLI docs, architecture docs, and positioning.
- `README.md:91-126` explains how the system works, with several security and architecture
  details before the user has seen practical examples.

**Why this matters**

The existing documentation readiness plan makes the repo credible to contributors. It does not
fully solve product onboarding. "First-class documentation" and "first-class product experience"
overlap, but they are not the same.

**Product requirement**

Add product education artifacts: memory taxonomy, lifecycle, recipes, setup checklist, and
control guide.

### P2. Benchmarks are credible but not integrated into product confidence

**Evidence**

- `README.md:130-139` surfaces LongMemEval results honestly.
- `harness/BENCHMARKS.md` is the detailed benchmark artifact.

**Why this matters**

Benchmarks build trust, but first-class product confidence also needs user-facing proof:

- My own memory can be recalled after write.
- A deleted/reverted memory disappears from recall.
- A new client cannot write without consent.
- A stale index catches up.
- Dense retrieval degradation is visible and understandable.
- A setup can be reproduced on a clean machine.

**Product requirement**

Add product proof flows and smoke demos that complement benchmark claims.

---

## First-Class Product Bar

Hypermnesic is first-class when all of the following are true.

### A new user can prove value before infrastructure

- They can run a local demo or wizard with no public endpoint.
- They can capture a memory and retrieve it immediately.
- They can inspect the markdown file and git commit behind the result.
- They understand why files are the source of truth.

### A user can connect agents without becoming an OAuth debugger

- Setup chooses safe defaults and reduces repeated parameters.
- Doctor/status explains the full path in concrete pass/fail checks.
- Client setup instructions are specific to ChatGPT, Claude, Codex, Claude Code, Obsidian, and
  local CLI.
- Token expiry, missing write scope, and connector misconfiguration are recognizable states.

### A user can control memory

- They can list, search, inspect, export, delete/forget, restore/revert, and audit memory.
- They can see recent writes and who/what caused them.
- They can revoke clients and understand read versus write grants.
- They can prove removal or revert through git and recall behavior.

### Agents can use memory without polluting it

- Skills teach when to search, when to build context, when to think, and when to write.
- Skills teach what belongs in Hypermnesic and what belongs in a short-term/preference layer.
- The hook is observable and bounded.
- Consolidation is explicit and preserves raw evidence.

### Trust is visible

- Consent is clear and reversible.
- Write scope consequences are plain.
- The user always knows what changed and how to undo it.
- Degraded retrieval is surfaced honestly.
- Security posture is understandable without reading source.

### The daily loop is coherent

- Capture now.
- Triage later.
- Recall during work.
- Expand around a hit.
- Write a durable note.
- Review changes.
- Clean up or forget.
- Export or back up.

---

## Recommended Sprint Units

This report's companion requirements document captures these as sprint-sized units. The high-level
sequence is:

1. Local first-run and value proof.
2. Setup/doctor/status.
3. Memory management and control.
4. Consent and client trust.
5. Plugin/hook observability.
6. Memory taxonomy and agent guidance.
7. Daily human workflows.
8. Product proof, examples, and launch readiness.

The sequence is intentional. A memory product should first prove it works, then prove it is
connected, then prove the user controls it, then prove agents can use it responsibly.

---

## Evidence Matrix

| Claim | Evidence |
|---|---|
| Files-as-truth is already central | `README.md:10-21`, `docs/why-hypermnesic.md:12-29` |
| Quick start begins with infra setup | `README.md:29-49`, `docs/guides/getting-started.md:20-43` |
| Client setup is OAuth/MCP-centric | `README.md:57-74`, `plugin/README.md:47-66` |
| `setup` requires duplicated URL concepts | `src/hypermnesic/cli.py:632-639` |
| Setup validates important operational state | `src/hypermnesic/install.py:489-530` |
| Discovery verification exists in code | `src/hypermnesic/install.py:446-486` |
| Read tools converge and return typed shapes | `src/hypermnesic/mcp_server.py:57-115`, `src/hypermnesic/mcp_server.py:361-431` |
| Write is scope-gated and refusal-based | `src/hypermnesic/mcp_server.py:442-473` |
| Consent exists but is basic | `src/hypermnesic/mcp_server.py:478-492` |
| Raw capture and deferred triage exist | `src/hypermnesic/capture.py:1-10` |
| Navigation surfaces exist as generated artifacts | `src/hypermnesic/nav_surface.py:1-13` |
| Product docs already cover public documentation readiness | `docs/brainstorms/2026-06-03-first-class-documentation-requirements.md` |
| Unified OAuth is already scoped elsewhere | `docs/brainstorms/2026-06-03-unified-oauth-endpoint-and-setup-requirements.md` |
| Companion UI first-classness is already scoped elsewhere | `docs/brainstorms/2026-06-02-obsidian-companion-first-class-ui-requirements.md` |

---

## Risks If Not Addressed

- Hypermnesic remains impressive to its author but hard to adopt for a new power user.
- Users treat memory as a black box despite the architecture being intentionally inspectable.
- Agents over-write or over-route memory because taxonomy is not taught at the point of use.
- OAuth or Tailscale setup failures become support/debugging sessions instead of diagnosed states.
- Consent remains technically secure but psychologically weak.
- The product is compared against Mem0/Zep quickstarts before users experience Hypermnesic's
  stronger ownership model.
- The Obsidian companion and documentation work ship polish around a product core that still
  lacks control and proof loops.

---

## Review Conclusion

Hypermnesic should not try to become a hosted memory API or an agent framework. Its identity is
strongest when it stays a self-owned, file-backed, git-first memory layer shared by many agents.
The first-class gap is not the kernel. The gap is that the kernel's guarantees are not yet
translated into user experience:

- Own your memory.
- See what is remembered.
- Know what each agent can do.
- Prove recall works.
- Remove or revert what should not persist.
- Preserve evidence before summarizing it.
- Connect clients without learning the entire auth stack.

If the recommended requirements are met, Hypermnesic will not merely be well engineered. It will
feel like a coherent product for people who care about durable, portable agent memory.
