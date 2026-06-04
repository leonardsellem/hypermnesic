---
title: "feat: Memory Taxonomy Agent Guidance"
type: feat
status: active
date: 2026-06-04
origin: docs/brainstorms/2026-06-04-first-class-product-requirements.md
sprint_unit: U6
sequence: 6
depends_on:
  - docs/plans/2026-06-04-001-feat-local-first-value-proof-plan.md
  - docs/plans/2026-06-04-002-feat-setup-doctor-status-plan.md
  - docs/plans/2026-06-04-003-feat-memory-control-center-plan.md
  - docs/plans/2026-06-04-004-feat-consent-client-trust-plan.md
  - docs/plans/2026-06-04-005-feat-plugin-hook-observability-plan.md
---

# feat: Memory Taxonomy Agent Guidance

## Summary

Teach humans and agents what belongs in Hypermnesic: durable long-term/project memory, source
episodes, semantic facts, procedural/policy notes, generated summaries, raw captures, and
current-state mirrors, while explicitly routing short-term session facts and behavioural
preferences to Honcho or another appropriate layer.

---

## Problem Frame

The product gap is category confusion. Hypermnesic's git-backed durable memory is strong, but the
product and bundled skill must prevent over-routing every memory-like fact into it, especially
behavioural/session preferences that belong in Honcho.

---

## Assumptions

*This plan was authored without synchronous user confirmation. The items below are planning-time
inferences that should be reviewed before implementation proceeds.*

- This sprint is mostly docs and agent-skill behavior, with focused tests that check plugin skill
  content and routing guidance rather than new engine behavior.
- The taxonomy should be product-language first and framework-language second.
- Honcho is named as the operator's preferred behavioural/session layer in this environment, while
  docs should also describe the general category for users without Honcho.

---

## Requirements

- R57. Document duration, type, scope, update strategy, and retrieval mode.
- R58. Position Hypermnesic as durable long-term/project memory, not default short-term session or
  behavioural preference memory.
- R59. Explain semantic, episodic/source, procedural/policy, generated summaries, raw captures, and
  current-state mirrors with markdown/git examples.
- R60. Teach preserve-evidence-first behavior.
- R61. Bundled agent skill tells agents when to search, build context, think, resolve, list
  folders, and write.
- R62. Bundled skill tells agents what not to write, including ephemeral session facts,
  behavioural preferences better suited to Honcho, secrets, credentials, and sensitive material.
- R63. Write guidance asks agents to discover writable locations when unclear.
- R64. Write guidance asks agents to preserve raw evidence or cite source paths when consolidating.
- R65. Refusals are useful control signals; agents should not bypass guards.
- R66. README/getting-started include "what belongs in Hypermnesic" before advanced writes.

**Origin actors:** A2 daily operator, A4 agent client, A6 planner/implementer agent, A7 adjacent memory layer.
**Origin flows:** F6 decide whether something belongs in Hypermnesic.
**Origin acceptance examples:** AE6 behavioural preference should not be routed to Hypermnesic by default.

---

## Scope Boundaries

### Deferred for later

- Hosted/cloud Hypermnesic.
- Automatic LLM consolidation of all raw memories.
- Enterprise compliance review workflows.

### Outside this product's identity

- Replacing Honcho or behavioural memory.
- Becoming an agent runtime.
- Hiding memory provenance behind opaque summaries.

### Deferred to Follow-Up Work

- Daily workflow recipes that apply the taxonomy are planned in `docs/plans/2026-06-04-007-feat-daily-human-workflows-plan.md`.
- Product smoke checks for skill guidance are planned in `docs/plans/2026-06-04-008-feat-product-proof-launch-readiness-plan.md`.

---

## Context & Research

### Relevant Code and Patterns

- `plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md` is the primary agent guidance
  surface.
- `plugin/README.md`, `README.md`, and `docs/guides/getting-started.md` carry user education.
- `src/hypermnesic/capture.py` already separates raw capture from later triage.
- `docs/README.md` pins current truth and durable reference docs.

### Institutional Learnings

- Hypermnesic lookup surfaced the durable split: Hypermnesic is long-term/project memory; Honcho is
  short-term/behavioural/preference memory.
- Honcho context confirms routing preferences themselves are behavioural/operational memory and
  should not be confused with durable document ingestion.

### Product Design Lens

- The taxonomy should appear at the moment users and agents decide to write, not buried in an
  architecture document.
- Examples should be concrete enough that an agent can refuse the wrong storage target.

### External References

- LangGraph memory concepts distinguish short-term versus long-term memory and semantic, episodic,
  and procedural types: https://langchain-ai.github.io/langgraph/concepts/memory
- Research on continuously updated LLM memories supports preserving raw episodes/evidence before
  consolidation: https://arxiv.org/abs/2605.12978

---

## Key Technical Decisions

- Add a dedicated memory taxonomy guide and cross-link it from README, getting-started, plugin
  README, and bundled skill.
- Treat "what not to write" as a first-class skill section, not a footnote.
- Keep examples repository-neutral and secret-free.
- Add lightweight tests that prevent future plugin/doc regressions around Honcho/preference memory,
  secrets, writable-folder discovery, and refusal handling.

---

## Open Questions

### Resolved During Planning

- Should behavioural preferences default to Hypermnesic? No. The origin and memory lookup make
  this an explicit outside-boundary unless deliberately promoted.
- Should consolidated summaries replace raw evidence? No. Evidence preservation is part of the
  product quality bar.

### Deferred to Implementation

- Exact taxonomy labels may be adjusted for readability as long as duration, type, scope, update
  strategy, and retrieval mode are all covered.

---

## Implementation Units

### U1. Memory Taxonomy Guide

**Goal:** Add the durable product guide that explains what belongs in Hypermnesic.

**Requirements:** R57, R58, R59, R60, R66.

**Dependencies:** docs/plans/2026-06-04-005-feat-plugin-hook-observability-plan.md.

**Files:**
- Create: `docs/guides/memory-taxonomy.md`
- Modify: `docs/README.md`
- Test: none

**Approach:**
- Structure the guide around duration, type, scope, update strategy, and retrieval mode.
- Include examples for semantic facts, source episodes, procedural/policy notes, raw captures,
  generated summaries, and current-state mirrors.
- Include "does not belong by default" examples for ephemeral session state, behavioural
  preferences, secrets, and sensitive unreviewed content.

**Test scenarios:**
- Test expectation: none for prose, but run public-surface secret/host scan.

**Verification:**
- A reader can decide whether a candidate memory belongs in Hypermnesic.

### U2. Bundled Agent Skill Routing Rules

**Goal:** Update the bundled skill so agents choose the right read/write tool and storage target.

**Requirements:** R61, R62, R63, R64, R65.

**Dependencies:** U1.

**Files:**
- Modify: `plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md`
- Modify: `plugin/hermes/skills/hypermnesic-memory/SKILL.md`
- Modify: `plugin/hermes/flat-skill/hypermnesic-memory/SKILL.md`
- Test: `tests/test_plugin.py`
- Test: `tests/test_hermes_plugin.py`

**Approach:**
- Add explicit "when to search/build_context/think/resolve/list_folders/commit_note" guidance.
- Add "what not to write" guidance, naming behavioural preference memory as belonging to Honcho or
  an equivalent short-term/preference layer by default.
- Tell agents to discover writable folders before choosing paths when unclear, cite sources when
  consolidating, and treat refusals as control signals.

**Execution note:** Add failing content tests before editing skill files.

**Patterns to follow:**
- Existing skill format and marketplace/plugin tests.

**Test scenarios:**
- Covers AE6. Happy path: skill text instructs that "user likes terse replies" is not written to
  Hypermnesic by default.
- Happy path: skill text requires folder discovery when write location is unclear.
- Happy path: skill text says refusals should not be bypassed.
- Security: skill text forbids storing secrets/credentials/unreviewed sensitive material.

**Verification:**
- Agent guidance no longer routes all memory-like facts to Hypermnesic.

### U3. README and Getting-Started Education

**Goal:** Put "what belongs here" before advanced write features in human onboarding.

**Requirements:** R58, R60, R66.

**Dependencies:** U1.

**Files:**
- Modify: `README.md`
- Modify: `docs/guides/getting-started.md`
- Modify: `plugin/README.md`
- Modify: `CHANGELOG.md`

**Approach:**
- Add a short, concrete section before commit/write setup.
- Link to the full taxonomy guide.
- Explain Honcho as an example adjacent layer where relevant without making it a hard dependency
  for all users.

**Test scenarios:**
- Test expectation: none for prose, but run public-surface secret/host scan.

**Verification:**
- New users see storage boundaries before approving or using write features.

### U4. Evidence Preservation Guidance

**Goal:** Make preserve-evidence-first behavior actionable in docs and skills.

**Requirements:** R60, R64.

**Dependencies:** U1, U2.

**Files:**
- Modify: `docs/guides/memory-taxonomy.md`
- Modify: `plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md`
- Modify: `docs/guides/memory-control.md`
- Test: `tests/test_plugin.py`

**Approach:**
- Explain that raw source episodes should be retained or cited before creating consolidated
  summaries.
- Provide examples of acceptable consolidation notes that link to source paths.
- Warn against overwriting raw captures with generated summaries.

**Patterns to follow:**
- `src/hypermnesic/capture.py` capture/triage split.

**Test scenarios:**
- Happy path: skill guidance tells agents to cite source paths or preserve raw evidence when
  writing consolidated notes.
- Edge case: generated summaries are labeled as generated and do not erase raw capture guidance.

**Verification:**
- Guidance supports durable trust rather than lossy memory compression.

### U5. Glossary and Reference Alignment

**Goal:** Add stable product terms so docs, CLI output, and plans use the same vocabulary.

**Requirements:** R57, R59, R66.

**Dependencies:** U1.

**Files:**
- Modify: `GLOSSARY.md`
- Modify: `docs/reference/mcp-tools.md`
- Modify: `docs/reference/cli.md`

**Approach:**
- Add or update entries for durable/project memory, semantic memory, episodic/source memory,
  procedural/policy memory, generated summary, raw capture, current-state mirror, and adjacent
  behavioural memory layer.
- Avoid overloading terms that existing docs already pin differently.

**Test scenarios:**
- Test expectation: none for prose, but run public-surface secret/host scan.

**Verification:**
- Terms used across docs and skill guidance match.

---

## System-Wide Impact

- **Interaction graph:** Docs, plugin skills, README, and future write decisions share one storage
  doctrine.
- **Error propagation:** Refusals become expected control signals in agent behavior.
- **State lifecycle risks:** Fewer noisy or inappropriate writes to durable memory.
- **API surface parity:** No engine API changes required unless implementation chooses to expose
  taxonomy labels in future surfaces.
- **Unchanged invariants:** No changes to write guard, OAuth, or index behavior.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Guidance becomes too abstract for agents | Include concrete "write/don't write" examples |
| Honcho-specific language confuses non-Honcho users | Describe Honcho as the operator's layer and name the general category |
| Skill text drifts in plugin variants | Add tests covering each distributed skill surface |
| Taxonomy docs imply automatic consolidation | State that explicit consolidation with raw evidence comes first |

---

## Documentation / Operational Notes

- This sprint is docs/skill-heavy but still user-visible; update `CHANGELOG.md`.
- Run plugin tests and public-surface scan after implementation.

---

## First-Class Validation Gates

This sprint is not complete until every gate below has passing evidence captured in the PR
description, Linear issue comment when available, and final implementation handoff. U1-U5 product
proofs must remain green.

- **AE6 routing gate:** given examples such as "the user likes terse replies", temporary session
  state, behavioural preference, durable project fact, decision rationale, source evidence, and
  cleanup instruction, bundled guidance must route each to Hypermnesic, Honcho, session context, or
  no write with no ambiguity.
- **Negative-example gate:** tests or documented fixtures must include at least three "do not write
  to Hypermnesic" cases and at least three "write to Hypermnesic" cases. Behavioural/preference
  memory must not be routed to Hypermnesic by default.
- **Skill invocation gate:** the bundled skill must instruct agents to query Hypermnesic first for
  durable project/entity/topic history, query Honcho for behavioural/preference/session context
  when available, and preserve evidence before summarizing.
- **Evidence preservation gate:** guidance must require raw captures/source episodes to remain
  traceable and must distinguish cleanup/triage from silent rewriting or source deletion.
- **Glossary/docs coherence gate:** README, getting-started docs, skill docs, glossary, and
  docs index must use the same names for durable memory, behavioural memory, session memory, raw
  capture, triage, recall, write, and cleanup.
- **Agent regression gate:** if a skill invocation or lint fixture exists, it must prove positive
  routing, negative routing, and no accidental preference-memory write path. Otherwise the plan must
  require adding one before implementation completes.
- **Cumulative product gate:** U1-U6 must compose: a reviewer can prove value, diagnose setup,
  control memory, trust/revoke clients, diagnose hooks, and explain what belongs in each memory
  layer without reading source code.
- **Regression gate:** at minimum run targeted docs/skill tests or checks, `git diff --check`,
  `uv run python scripts/preflight_public_scan.py`, and the repo gates required by `AGENTS.md`.

## Sources & References

- Origin document: [docs/brainstorms/2026-06-04-first-class-product-requirements.md](../brainstorms/2026-06-04-first-class-product-requirements.md)
- Product review: [docs/reports/2026-06-04-hypermnesic-product-design-review.md](../reports/2026-06-04-hypermnesic-product-design-review.md)
- Related code/docs: `plugin/plugins/hypermnesic/skills/hypermnesic-memory/SKILL.md`,
  `src/hypermnesic/capture.py`, `README.md`
- Related tests: `tests/test_plugin.py`, `tests/test_hermes_plugin.py`
- External docs: https://langchain-ai.github.io/langgraph/concepts/memory,
  https://arxiv.org/abs/2605.12978
