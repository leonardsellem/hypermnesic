# Plan — dream mode (review-gated wikilink proposals)

- **Date:** 2026-08-15
- **Status:** Planned
- **Type:** feat
- **Workspace/Project:** LS Ventures · hypermnesic
- **Relations:** implements [LS-2612](https://linear.app/ls-ventures/issue/LS-2612); consumes LS-2613…LS-2618
- **Branch off:** `dev` · PR into `dev` · DCO `Signed-off-by`
- **ADR:** write `docs/adr/YYYY-MM-DD-dream-cursor-and-per-pair-commits.md` in the implementing PR (hard to reverse: SHA-as-cursor + one-commit-per-pair)

## Context & motivation

`connect.py` already finds similar-but-unlinked note pairs (cosine + no existing
body-wikilink edge, cap 20) and emits a generated dashboard note. It never writes
an edge into a curated note (KTD2/R10 docstring). Léonard wants the opposite
review vehicle: **one PR per dream run** that inserts real Obsidian wikilinks,
scannable in one approval.

Ideation (`docs/ideation/2026-06-05-dreaming-mode-ideation.md`) recommended
deterministic-only v0. Charting **overrode** that: v0 includes a cheap
user-chosen LLM that only keep/drops deterministic candidates.

## Goal

A scheduler-agnostic `hypermnesic dream <repo>` CLI that, for one run:

1. Finds deterministic candidate pairs (`connect.candidate_pairs`).
2. Asks an injectable LLM judge: keep or drop + one-line reason.
3. Places kept pairs by **deterministic tier** (not LLM):
   - **obvious** → wrap the first body mention
   - **vaporous** → append one clean `[[target]]` under `## Related`
4. Commits a journal note to HEAD (fast-append) whose SHA is the incremental cursor.
5. Opens one review-gated PR (`propose.py`) with **one commit per pair**.
6. Never auto-merges. Never edits `sources/` or `captures/`.

On-demand first. A systemd timer wraps the same CLI later (opt-in install).

## Decisions (do not re-litigate)

Each line is closed. Ticket is the authority.

| ID | Decision | Ticket |
|---|---|---|
| D0 | Destination is this plan; implementation is a later effort executing it | LS-2612 charting |
| D1 | Inline for obvious, `## Related` for vaporous; nothing auto-applies | charting |
| D2 | One PR per run; review = one diff | charting |
| D3 | On-demand CLI/MCP core first; scheduler wraps it | charting + LS-2613 |
| D4 | v1 links existing notes only — no entity-page birthing | charting |
| D5 | Incremental runs + occasional full sweeps | charting + LS-2615 |
| D6 | Reviewed PRs MAY edit curated notes; KTD2 salience-frontmatter core stays; wikilink corollary retired | charting + LS-2614 |
| D7 | LLM in v0; model configurable; default `gpt-5.6-terra` / medium thinking | charting + LS-2617 |
| D8 | All correctness in `hypermnesic dream` CLI; watermark SHA makes any trigger safe | LS-2613 |
| D9 | Blessed trigger: systemd timer + oneshot rendered by `install.py` (opt-in). Cron = documented fallback. In-server opportunistic trigger **rejected** | LS-2613 |
| D10 | Journal = NEW file in immutable free-append zone, committed to HEAD; SHA = cursor + health beacon. Watermark advances even when a PR is rejected | LS-2615 |
| D11 | Reuse `propose.py` as-is: branch `hypermnesic/proposals/dream-<run-id>`, shared `ProposalBudget` (dream charges 1), existing ledger, gate-before-branch | LS-2615 |
| D12 | Stack PRs (don't skip-while-open). Journal proposed-pair memory prevents re-proposing pairs sitting in an open PR | LS-2615 |
| D13 | One commit per pair. Verdicts from **content**: merged = accepted; pruned-from-merged = rejected forever (`--include-rejected` overrides); closed-unmerged = no verdict, pairs return | LS-2615 |
| D14 | PR body = journal: one line per pair (source → target, tier, score, reason) | LS-2615 |
| D15 | Obvious = unique title / filename stem / frontmatter `aliases:` match. Ambiguous → skip (same as `graph.py:70-82`) | LS-2616 |
| D16 | Wrap **first body mention only**. Never heading / quote / code / frontmatter. Never reword — only wrap (`[[path\|mention]]` when mention ≠ title) | LS-2616 |
| D17 | Vaporous = one clean `[[target]]` under `## Related`. No score in-note. Skip if that wikilink already exists anywhere. No `## Dream` heading | LS-2616 |
| D18 | True source notes = existing files under `sources/` or `captures/` — path-prefix **refusal** (not routing). `projects/.../meetings/` may be edited | LS-2616 |
| D19 | LLM role = keep/drop + one-line reason. Tier is **not** an LLM decision | LS-2617 |
| D20 | Pin via env (`DREAM_MODEL` + thinking) through the existing OpenAI-compatible client. No new provider SDK | LS-2617 |
| D21 | Cap 20 pairs/run. Model down / junk output → no link PR, record skip, **do not advance watermark**, next trigger retries. Exit 0 with visible reason (lock_busy posture) | LS-2617 |
| D22 | LS-2614 security package: dated review + operator sign-off **before enablement**; LLM filters only; engine-chosen paths; schema-bound output; no prompt/completion bodies in audit log; reuse `openai` | LS-2617 Q4 (timeout default, operator later restated “reuse the lib”) |
| D23 | Prototype shape accepted (timeout default): 3-pair mixed-tier PR is reviewable at one approval. Reject-in-place = drop that commit | LS-2618 |
| D24 | v1 surface = the review PR only. Do **not** wire `connections_rel` / `nav_surface.build_moc` / `daily_review` | plan default (map leftover) |
| D25 | O(n²) `candidate_pairs` stays as-is in v1 (cap 20). Scaling is a later ticket | plan default |

Provisional locks (reopen before treating as frozen): D22, D23.

## Scope & non-goals

**In scope (this implementation effort):**

- `hypermnesic dream` CLI + optional MCP tool wrapping the same function
- Journal + watermark + incremental / `--full` sweep
- LLM judge (injectable, offline tests)
- Deterministic placement (wrap / Related)
- `sources/` + `captures/` refusal guard
- `propose.py` multi-commit variant (one commit per pair) — CODEOWNERS
- Opt-in systemd timer render in `install.py`
- Security review + sign-off gate + threat-model amendment + doctrine pin
- Docs listed below, same PR as the behavior they describe

**Out of scope:**

- Building this plan is the *next* effort; this file is the spec
- Entity-page birthing
- Full LLM knowledge-graph extraction (Phase 3, `connect.py:5`)
- In-process / MCP-server opportunistic dreaming
- New LLM provider SDKs
- Wiring dream output into MOC / daily-review `connections_rel`
- Rewriting `candidate_pairs` for large-vault O(n²)
- Auto-merge, silent writes, editing `sources/` or `captures/`

## Design / approach

### Run anatomy

```
hypermnesic dream <repo> [--full] [--include-rejected]
  1. non-blocking serialize.index_write_lock (busy → exit 0, reason=lock_busy)
  2. read watermark = SHA of latest dream-journal commit (or genesis)
  3. unless --full: candidate notes = git log <watermark>..HEAD (md only)
  4. connect.candidate_pairs(vectors, graph, cap=20)
     minus pairs in open dream PRs (journal memory)
     minus pairs rejected-forever (pruned-from-merged) unless --include-rejected
     minus any pair whose edit target is sources/ or captures/
  5. LLM judge each remaining pair → keep|drop + reason
     unreachable/unparseable → no link PR, do not advance watermark, exit 0
  6. for each keep: assign tier from D15–D17 (engine, not model)
     skip if placement is a no-op (already linked / no legal wrap site and
     Related would duplicate)
  7. journal NEW file under sources/dreams/<run-id>.md via propose() fast path
     (HEAD). Frontmatter: run-id, watermark_prev, pair list. Body = PR body.
     This commit SHA is the new watermark — only if step 5 succeeded.
  8. if any placeable keeps: propose() on branch
     hypermnesic/proposals/dream-<run-id>
     one commit per pair (needs multi-commit branch_commit_transaction)
     charge ProposalBudget 1
  9. PR body = journal body
```

Empty delta after step 3 → exit 0, no journal, no watermark move.
Lock busy → exit 0, no journal.
LLM fail → exit 0, no journal, no watermark move.

### Placement (engine)

- Resolve mention against title, stem, and `aliases:` YAML list. >1 page → not obvious.
- Scan body after frontmatter. Skip ATX/setext headings, fenced/indented code,
  inline `` ` ``, markdown quotes (`>`), wikilink interiors.
  First remaining case-insensitive whole-word (or alias) hit → wrap.
- Else vaporous: ensure one `## Related` (create at EOF if missing); append
  `- [[target-path-without-md]]` if that target is not already wikilinked
  anywhere in the note.
- Frontmatter: never touched (`frontmatter_gate` still runs).

### Security (must exist before the path can be *enabled*)

Do these **before** flipping any enablement flag / merging a path that can
call a live model against a real vault:

1. New dated review `docs/YYYY-MM-DD-dream-generative-proposer-security-review.md`
   with `amends:` / `signed_off:` (precedent: `docs/2026-06-03-blocklist-write-surface-security-review.md`).
2. Operator sign-off recorded; enforce with a gate test (precedent
   `tests/test_blocklist_write_gate.py`).
3. Dated amendment block on `docs/threat-model-commit-note.md` restating V2
   for an *internal* generative consumer.
4. `docs/README.md` current-truth pin (KTD2 wikilink corollary retired;
   salience core kept; `sources/`+`captures/` refused; nothing auto-applies).
5. CODEOWNERS: add `propose.py` + new dream module to the security-sensitive block.

In the implementing PR (same change as the code):

- LLM may only filter `connect.candidate_pairs`; never add a pair
- Target paths engine-chosen, never parsed from model text
- Output schema: `{keep: bool, reason: str}` only
- `sources/` + `captures/` refused in candidate filter **and** `propose()`/`serialize`
- All writes through `propose()` (guard first, in-memory gate, budget, ledger)
- No prompt/completion bodies in the audit log
- Fake judge in tests; `monkeypatch.delenv("OPENAI_API_KEY")`
- Reuse `openai` — no new dependency

### Config

| Knob | Default | Where |
|---|---|---|
| `DREAM_MODEL` | `gpt-5.6-terra` | `config.py`, `.env.example`, `docs/reference/configuration.md` |
| `DREAM_THINKING` | `medium` | same |
| pair cap | 20 (`connect._DEFAULT_CAP`) | reuse; do not add a second cap unless tests need it |
| timer cadence | documented `OnCalendar=` (daily, `Persistent=true`, `RandomizedDelaySec`) | `install.py` render + configuration.md |

Optional OpenAI-compatible `base_url` follows whatever embed/expand already
use; do not invent a second client.

## Implementation outline (TDD-first)

No production code without a failing test. Slices in this order.

1. **U0 — security artifacts (docs + failing enablement gate).**
   Dated review (unsigned), threat-model amendment stub, CODEOWNERS lines,
   `tests/test_dream_write_gate.py` that fails until `signed_off` is present.
   Path is not enableable.

2. **U1 — `sources/` + `captures/` refusal.**
   Failing tests: `propose()` / dream candidate filter refuse an edit to an
   existing `sources/x.md` and `captures/y.md`; a *new* file under `sources/dreams/`
   still takes the free-append fast path. Implement path-prefix refusal
   (`serialize.protected_reason` or a dream/propose allowlist — prefer extending
   the existing guard style). Cite `SECURITY.md` + threat model.

3. **U2 — mention resolver + wrap / Related placement (pure, no LLM).**
   Failing tests covering D15–D17:
   - unique alias `karpathy` wraps first body hit as `[[people/andrej-karpathy|Karpathy]]`
   - two pages named Acme → no wrap
   - heading / quote / code / frontmatter never wrapped
   - second body mention left plain
   - existing wikilink → no-op
   - missing `## Related` → created; existing → append; duplicate skipped
   Implement in a new `src/hypermnesic/dream_place.py` (name bikeshed OK).

4. **U3 — injectable judge.**
   Failing tests: fake keep/drop; unreachable judge returns a typed skip
   (no exception to CLI); malformed output = skip; never adds a pair not in
   the input list. Implement `dream_judge.py` using `openai` like `expand.py`.

5. **U4 — journal + watermark.**
   Failing tests: first run with no journal processes the full candidate set
   (or `--full`); second run with empty `watermark..HEAD` is a no-op; rejected
   PR still advances watermark (journal already on HEAD); LLM skip does **not**
   write a journal. Fast-path new file `sources/dreams/<run-id>.md`.

6. **U5 — multi-commit `propose` + stacked PRs.**
   Failing tests: one `Change` per pair becomes one commit on
   `hypermnesic/proposals/dream-<run-id>`; budget charges 1; second run while
   first PR is open does not re-propose those pairs; prune-then-merge records
   rejected-forever. Small variant of `serialize.branch_commit_transaction`
   (CODEOWNERS). Verdict inference is content-based (diff of merged tree vs
   proposed), not commit SHA.

7. **U6 — `hypermnesic dream` CLI (+ optional MCP tool).**
   Failing tests: parses; `--full` / `--include-rejected`; lock_busy / llm_skip /
   empty_delta exit 0 with a stable `--json` reason. Wire `cli.py`. MCP tool
   only if it is a thin wrapper of the same function (do not put the job inside
   the server read path).

8. **U7 — opt-in timer render.**
   Failing tests: `render_dream_timer_unit` / `render_dream_service_unit` are
   pure strings (absolute exe, `EnvironmentFile=-{repo}/.env`, no secrets,
   `Persistent=true`). `--with-dream-timer` opt-in; default install unchanged.
   Docker role: documented `docker compose run … dream` line, no unit.

9. **U8 — docs anti-drift (same implementing PR as the behavior).**
   See checklist below. Includes GLOSSARY terms and the KTD2 docstring fix
   in `connect.py` (and a scope-clarify on `salience.py`).

10. **U9 — enablement.**
    Operator signs the dated review. Gate test goes green. Only then is a
    live-model dream against a real vault allowed.

## Docs-anti-drift checklist (implementing PR)

| Doc | What to add/change |
|---|---|
| `docs/reference/cli.md` | `dream` subcommand, flags, exit reasons |
| `docs/reference/mcp-tools.md` | only if a tool is added |
| `README.md` | tool/CLI list + one How-it-works bullet |
| `ARCHITECTURE.md` | new proposal/dream section (layer is absent today) |
| `SECURITY.md` | posture line + deltas index |
| `docs/threat-model-commit-note.md` | dated amendment (U0) |
| `docs/YYYY-MM-DD-dream-generative-proposer-security-review.md` | new (U0) |
| `docs/README.md` | current-truth pin + security-reviews row |
| `GLOSSARY.md` | **dream**, **obvious**, **vaporous**, **true source note**; extend serendipity line |
| `docs/reference/configuration.md` + `.env.example` | `DREAM_MODEL`, `DREAM_THINKING`, timer cadence |
| `docs/unified-oauth-mcp-deploy-runbook.md` | unit-topology row if timer ships |
| `CHANGELOG.md` | `[Unreleased]` |
| `src/hypermnesic/connect.py` docstring | retire “never written directly into a source note” |
| `src/hypermnesic/salience.py` docstring | keep no-`salience:` core; clarify KTD2 scope |
| `.github/CODEOWNERS` | `propose.py` + dream module |
| ADR | cursor + per-pair-commit |

## Test & verification plan

- New tests under `tests/` (`--import-mode=importlib`), offline, key neutralized.
- Fake embedder + fake judge; no network.
- Fixture vault with: unique alias page, two-Acme collision, `sources/` transcript,
  a note that already contains the link, a heading/quote/code mention.
- Full gate set: `ruff` · `check_version_consistency.py` · `pytest` ·
  `license_scan.py` · `preflight_public_scan.py`.
- Placeholders only (`<your-host>.ts.net`, `100.64.0.0/10`).
- Cold-read: a builder who never saw LS-2612 can execute U0–U9 without asking
  a question this plan already answered.

## Acceptance criteria

- `hypermnesic dream <fixture-repo>` produces a journal on HEAD and a stacked
  proposal branch with one commit per kept pair, or a documented skip reason.
- `sources/` and `captures/` edits are refused by test.
- Suite stays offline; `license_scan.py` green with no new dependency.
- Enablement gate is red until operator `signed_off`.
- Every doc in the checklist is updated in the same PR as the code it describes.
- Prototype review shape (LS-2618) is preserved: PR body is a table/list of
  pairs, not a buried CSV.

## Risks / open only if a builder is stuck

- Multi-commit `branch_commit_transaction` is the only CODEOWNERS-heavy code
  change besides the `sources/` refusal. Keep the diff small; do not rewrite
  `propose.py`.
- `aliases:` parsing must use the same YAML/frontmatter split as the rest of
  the engine (`frontmatter_gate.split_frontmatter`) so display aliases and
  list-style aliases both work.
- Journal lives under `sources/dreams/` as a *new* file (allowed) while *edits*
  to other `sources/` files stay refused. Tests must pin that distinction.
- D22/D23 were timeout defaults. If Léonard reopens them, stop and amend this
  plan before enablement — do not silently keep a rejected default.

## Handoff

Map LS-2612 is done when this file is on `dev` via PR. Implementation is a
fresh Linear effort executing U0–U9. Do not start U9 against the live vault
without the signed review.
