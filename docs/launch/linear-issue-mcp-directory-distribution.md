---
title: "Distribute hypermnesic across the MCP server directories"
estimate: 1
priority: High
labels:
  - launch
  - distribution
  - marketing
related_paths:
  - docs/brainstorms/2026-06-25-mcp-directory-distribution-requirements.md
  - docs/plans/2026-06-25-001-content-mcp-directory-distribution-plan.md
related_linear:
  - LS-1683
  - LS-1689
  - LS-1690
parent: null
sub_issues:
  - title: "Verify-before-claim sweep: registry baseline, awesome PR #8056 state, Glama grade + score-badge path"
    estimate: 2
    summary: >
      Establish ground truth for the three external claims the positioning seed got wrong
      or left unverified, before any copy or badge ships (U1, R14-R16). Capture three
      artifacts: (a) the Official MCP Registry query for io.github.leonardsellem/hypermnesic
      returns EMPTY (baseline for R4); (b) `gh pr view 8056 --repo punkpeye/awesome-mcp-servers
      --json state,merged,mergedAt,url` showing the real merge state (repo evidence says OPEN,
      treat "merged" as unproven); (c) the live Glama listing ak6x81u3rr screenshot showing the
      Tool-Definition-Quality grade, plus `curl -sSI .../badges/score.svg` returning 200 with an
      SVG content-type (and confirming .../badge.svg -> 404 and .../badge -> oversized card).
      These three artifacts decide the awesome-badge sub-issue and all letter-grade wording.
      Read-only; produces no public artifact. Gates everything downstream.
  - title: "Stage + validate root server.json, then operator-gated publish to the Official MCP Registry + live verify"
    estimate: 3
    summary: >
      The cascade trigger and the only human-gated step (U2 + U3; R1-R4). Stage: download the
      mcp-publisher binary, `cp docs/launch/mcp-registry-server.draft.json server.json` WITHOUT
      editing the remotes/{host} template shape, run `./mcp-publisher validate` (passes, including
      the <=100-char description limit), confirm name io.github.leonardsellem/hypermnesic and an
      empty `diff` vs the draft. Then STOP for the operator: the human runs `./mcp-publisher login
      github` (device-code flow, cannot be automated), then `./mcp-publisher publish`. Verify live
      by re-querying the registry for io.github.leonardsellem/hypermnesic and capturing the JSON
      showing the canonical title/description/repo link (R4). Until that query returns the entry,
      the voice rule against claiming an official-registry listing stays in force (R16). Do not
      commit the binary. Hard blocker = operator availability for the device-code login.
  - title: "Submit to Smithery (bring-your-own-hosting) under leonardsellem/hypermnesic with the wedge blurb"
    estimate: 2
    summary: >
      List hypermnesic on Smithery as a remote, self-hosted server pointed at the public /mcp
      OAuth endpoint (U4; R6, R7, R10). Confirm live wizard fields + OAuth specifics (and
      `smithery --help` flags) at submission time before relying on either route. First check for
      an unclaimed crawled entry and CLAIM it rather than duplicating; else submit via smithery.ai/new
      -> URL tab with the operator's real public host (never written to any committed file), org/name
      leonardsellem/hypermnesic, no smithery.yaml (it proxies upstream). Blurb carries the
      ownership-and-compounding wedge (files are truth, index is disposable, writes are reviewable
      commits) + the README quick-start link; no benchmark figure, no SaaS framing. Capture the live
      listing URL + screenshot; record claimed-from-crawl vs created-fresh. Independent of the
      registry publish; runs in parallel once the /mcp endpoint is confirmed reachable.
  - title: "Submit to mcp.so via chatmcp/mcpso Issue #1 with the canonical name + wedge blurb"
    estimate: 1
    summary: >
      List hypermnesic on mcp.so through its confirmed-reliable community path (U5; R8, R10).
      Post a comment on chatmcp/mcpso Issue #1 ("Submit Your MCP Servers here",
      github.com/chatmcp/mcpso/issues/1) linking the server, carrying the ownership-and-compounding
      wedge blurb + the README quick-start link (`gh issue comment 1 --repo chatmcp/mcpso
      --body-file <blurb>`). The web /submit form is an alternate ONLY after its live fields are
      confirmed in an authenticated browser (it 403'd anonymously). Capture the posted comment URL,
      then the live mcp.so listing URL once the maintainer adds it. Independent of the registry
      publish; runs in parallel.
  - title: "README badges: Glama score (always, /badges/score.svg) + awesome-mcp-servers (only if PR #8056 confirmed merged)"
    estimate: 2
    summary: >
      Surface the earned quality signal in the repo without weakening any claim (U6; R11-R13).
      In README.md, after the existing License badge (keep CI, PyPI, License and their order), add
      the Glama score badge using the EXACT working path
      https://glama.ai/mcp/servers/ak6x81u3rr/badges/score.svg (never .../badge.svg [404] nor
      .../badge [oversized card]). Add the awesome-mcp-servers "Mentioned in Awesome" badge ONLY
      if the verify sweep returned `merged: true` for PR #8056; if still open, do NOT add it and
      record the state as "submitted / PR open". No private host/token/path enters the badge row.
      Add a dated [Unreleased] CHANGELOG line for the user-visible README change. Touches only the
      README badge row + CHANGELOG. Depends on the verify sweep; independent of the registry publish.
  - title: "Confirm PulseMCP auto-ingest (~1 week post-publish) + record the conscious mcp-get skip"
    estimate: 2
    summary: >
      Close the cascade loop and durably settle the mcp-get decision (U7; R9). Do NOT hand-submit
      PulseMCP -- it ingests official-registry entries daily and processes weekly. ~1 week after the
      registry publish lands, search pulsemcp.com for hypermnesic; if present, capture the listing
      URL and confirm metadata matches canonical (name, description, links). If absent or wrong after
      the window, email hello@pulsemcp.com with the repo + canonical description for an
      expedite/correction (the lever, not a fresh submission). Record the mcp-get skip WITH its reason
      (package-install-manager registry, npm/PyPI-shaped, largely superseded by the Official Registry,
      poor fit for a remote-only self-hosted server with no installable package shape; revisit only if
      a PyPI-backed `packages` entry is later added) in docs/launch/directory-submission-prep.md, plus
      a dated post-submission state update per target. Depends on the registry publish; time-gated.
---

## Context

hypermnesic is a released `v0.1.0`, self-hosted, git-tracked second brain / memory layer
for AI agents: Markdown files are the single source of truth and the search index is a
disposable, rebuildable projection of the git tree. It already carries its distinctive
proof — a guarded git-first write (`commit_note`), hybrid FTS5 + sqlite-vec retrieval,
read-time convergence, and one OAuth 2.1 MCP endpoint shared by every client — yet a
developer shopping the MCP ecosystem cannot find it. The Official MCP Registry returns no
entry; the staged `docs/launch/mcp-registry-server.draft.json` validates but has never been
published, because publishing requires a human GitHub device-code login no prior session
could complete. Smithery and mcp.so — the two highest-traffic community directories — carry
no hypermnesic listing at all. The awesome-mcp-servers PR `#8056` was opened but its merge
state was never confirmed against the upstream (the prior positioning seed asserted "merged",
which the repo evidence does not support). The Glama listing `ak6x81u3rr` exists and the
engine did the Tool-Definition-Quality work (full tool descriptions, 100% parameter-description
coverage across all seven tools), but the README still shows only CI, PyPI, and License
badges, so a reader never sees the quality signal — and the externally-graded letter has
never been confirmed live. The net is a launch with strong product proof and near-zero
discoverability.

The fix is one high-leverage move plus a small, honest fan-out: publish the staged
`server.json` to the Official MCP Registry first and let it cascade into the directories that
ingest from it (PulseMCP ingests official-registry entries daily, processes weekly); hand-submit
only the two that do not auto-ingest (Smithery via bring-your-own-hosting, mcp.so via GitHub
Issue #1), each carrying the ownership-and-compounding wedge; and close the repo loop with the
Glama score badge (correct `/badges/score.svg` path) plus a conditional awesome badge. mcp-get
is consciously skipped (package-install-manager registry, wrong shape for a remote-only server).

This is an EPIC because the work is multi-track and spans a hard human gate plus a ~1-week
time-gate: M0 ground-truth verification → M1 operator-gated registry publish (the cascade
trigger) → M4 cascade confirmation, with the Smithery / mcp.so / badges tracks deliberately
OFF the critical path so they ship even if the operator login slips.

## Intent

Make hypermnesic findable everywhere an MCP user browses for a server, with every listing
and grade claim verified at its own source before it ships in public copy. Concretely:

- Publish the staged registry entry as-is (no `remotes` / `{host}` shape change) and verify
  the live entry by registry query.
- List hypermnesic on Smithery and mcp.so under the canonical `leonardsellem/hypermnesic`,
  each blurb carrying the same wedge (files are truth, the index is disposable, writes are
  reviewable commits) and a working README quick-start link — never a generic "memory server"
  line, never a hosted-SaaS framing, never a benchmark figure outside the published
  comparability envelope.
- Confirm PulseMCP auto-ingests within ~1 week; correct by email only if it does not.
- Add the Glama score badge via the correct `/badges/score.svg` path, and the awesome badge
  **only if** PR `#8056` is confirmed merged.
- Verify every external claim at source first (registry query, Glama listing `ak6x81u3rr`,
  awesome PR `#8056`) so no "live", "merged", or "A grade" assertion ships unproven.
- Durably record the conscious mcp-get skip with its reason so it is not re-litigated.

## Acceptance Criteria

- [ ] A query to the Official MCP Registry for `io.github.leonardsellem/hypermnesic` returns
      the published entry, with the canonical name, title, description, and repository link;
      the JSON is captured as an artifact on this issue.
- [ ] The published description stays within the registry's 100-character limit, and the
      `remotes` / `{host}` template shape of the staged draft was published unchanged
      (`diff docs/launch/mcp-registry-server.draft.json server.json` was empty pre-publish).
- [ ] hypermnesic is live and discoverable on Smithery under `leonardsellem/hypermnesic`,
      showing the ownership-and-compounding wedge blurb and a working README quick-start link;
      the listing URL + screenshot are captured, and whether it was claimed-from-crawl or
      created-fresh is recorded.
- [ ] hypermnesic is submitted to mcp.so via a comment on `chatmcp/mcpso` Issue #1 carrying
      the wedge blurb + README link (comment URL captured), and the live mcp.so listing URL is
      captured once the maintainer adds it.
- [ ] PulseMCP is confirmed present (auto-ingested) within ~1 week of the registry publish —
      or corrected via `hello@pulsemcp.com` — with metadata matching canonical; the listing URL
      (or the sent-email record) is captured.
- [ ] The README shows the Glama score badge via the exact `/badges/score.svg` path, rendering
      a real score image (not a broken-image icon); the CI, PyPI, and License badges are unchanged
      and in their existing order; no private host, token, or local path is introduced.
- [ ] The awesome-mcp-servers badge is present **iff** PR `#8056` is confirmed merged at the
      upstream; if still open, the badge is absent and the state is recorded as "submitted /
      PR open".
- [ ] Every public claim about a listing or grade is backed by a source confirmation captured
      on this issue: the registry query, the Glama listing `ak6x81u3rr` screenshot, and the
      `gh pr view 8056` result. No "official-registry listing", "merged", or "A grade" claim
      appears in any shipped copy without its confirmation.
- [ ] The mcp-get skip and its reason are recorded in
      `docs/launch/directory-submission-prep.md`, with that doc's post-submission state updated
      for each target.

## Validation Plan

| Criterion | How it is proven | Evidence artifact |
|---|---|---|
| Registry entry live | `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.leonardsellem/hypermnesic"` returns the entry with canonical fields (after an EMPTY baseline pre-publish) | Empty baseline JSON + live-entry JSON, both attached to the issue |
| Draft shape unchanged + <=100-char description | `./mcp-publisher validate` exits success; `diff docs/launch/mcp-registry-server.draft.json server.json` is empty | Captured terminal output of validate + diff |
| Smithery listing live | Open the live listing under `leonardsellem/hypermnesic`; confirm the wedge blurb renders and the README quick-start link resolves | Listing URL + screenshot; note of claimed-vs-created |
| mcp.so submitted + listed | The posted comment on `chatmcp/mcpso` Issue #1; then the live mcp.so listing once added | Comment URL + later listing URL |
| PulseMCP auto-ingested | Search `pulsemcp.com` ~1 week post-publish; confirm metadata matches canonical; else email `hello@pulsemcp.com` | Listing URL (or sent-email record) |
| Glama score badge correct | Rendered README GitHub preview shows the score badge resolving to a real image; `curl -sSI ".../badges/score.svg"` returned `200` + SVG content-type in the verify sweep; `git diff` shows CI/PyPI/License untouched and ordered | GitHub README preview screenshot + `curl -I` output + `git diff` |
| Awesome badge gated correctly | `gh pr view 8056 --repo punkpeye/awesome-mcp-servers --json state,merged,mergedAt,url`: badge added iff `merged: true`; else "submitted / PR open" recorded | `gh pr view` JSON + the README diff (or the recorded note) |
| All grade/listing claims source-verified | Cross-check each public claim against its captured confirmation (registry query, Glama screenshot, awesome PR JSON) | The three verify-sweep artifacts referenced by each claim |
| mcp-get skip recorded | Read `docs/launch/directory-submission-prep.md` for the skip rationale + per-target post-submission state | The committed diff to the prep doc |

## Definition of Done

Done when **all** Acceptance Criteria above hold and each is backed by a captured artifact on
this issue, specifically:

- The Official MCP Registry query returns the published `io.github.leonardsellem/hypermnesic`
  entry (JSON captured). Until that query passes, no official-registry-listing claim is made
  anywhere (voice rule held).
- Smithery and mcp.so both show hypermnesic live under the canonical name with the
  ownership-and-compounding wedge blurb and a working README link; both listing URLs captured.
- PulseMCP is confirmed present (auto-ingested) within ~1 week of publish, or corrected by
  email, with canonical metadata.
- The README carries the Glama score badge via `/badges/score.svg` rendering a real image,
  CI/PyPI/License unchanged and ordered, no private host/token/path introduced; the awesome
  badge present iff PR `#8056` is confirmed merged, else recorded as "submitted / PR open".
- Every public listing/grade claim is backed by a source confirmation; no "merged" or
  "A grade" claim shipped unverified.
- The mcp-get skip and its reason are recorded in `docs/launch/directory-submission-prep.md`,
  with per-target post-submission state updated.

The critical path is M0 (verify) → M1 (operator `mcp-publisher login github` + publish + R4
verify) → M4 (PulseMCP cascade confirm). The Smithery, mcp.so, and badge tracks are off the
critical path and may land on day one regardless of the operator login timing; if the operator
login slips its window, the epic still ships those tracks and M1/M4 complete once the login lands.

## Links

- Canonical plan: `docs/plans/2026-06-25-001-content-mcp-directory-distribution-plan.md`
  (GitHub permalink substituted at issue-creation time)
- Origin brainstorm / requirements (R1–R16):
  `docs/brainstorms/2026-06-25-mcp-directory-distribution-requirements.md`
  (GitHub permalink substituted at issue-creation time)
- Target directories + copy-ready drafts + operator pause points:
  `docs/launch/directory-submission-prep.md`
- Staged registry entry (remote `{host}` template, no `packages`):
  `docs/launch/mcp-registry-server.draft.json`
- Positioning confirmations / corrections: `docs/launch/promo-grounding-brief.md`
- Claims-allowed / claims-avoid + canonical voice: `docs/launch/launch-narrative-drafts.md`
- Launch order context: `docs/launch/launch-sequencing.md`
- Differentiation framing carried into blurbs: `docs/why-hypermnesic.md`
- Current badge row + canonical description: `README.md`
- Related LS launch issues: LS-1683 (Submit to MCP and Obsidian directories — the broader
  parent track this epic executes the MCP half of), LS-1689 (launch narrative + per-channel
  posts — source of the canonical voice and claims lists), LS-1690 (launch sequencing — where
  directory updates sit in the launch order).
