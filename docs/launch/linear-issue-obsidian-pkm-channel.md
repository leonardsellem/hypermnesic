---
title: "Open the Obsidian + PKM channel for the read-only companion"
estimate: 1
priority: High
labels: [launch, distribution, marketing, content]
related_paths:
  - docs/brainstorms/2026-06-25-obsidian-pkm-channel-requirements.md
  - docs/plans/2026-06-25-003-content-obsidian-pkm-channel-plan.md
related_linear:
  - LS-1683
  - LS-1688
  - LS-1689
  - LS-1690
parent: null
sub_issues:
  - title: "U1 — Verify the companion repo is submission-ready on the CURRENT release (0.3.2)"
    estimate: 2
    summary: >-
      Gate before any external action. Prove, against the LIVE companion repo (manifest
      0.3.2, minAppVersion 1.7.2 — NOT the 0.3.0 the prep doc records), that the README
      reviewer disclosures, release-asset hygiene, and naming policy all hold on the
      version the Obsidian bot will actually scan (the latest release). Record a pass/fail
      checklist on LS-1683; no external action fires from this unit.
  - title: "U2 — Open the obsidianmd/obsidian-releases PR and drive it to merge (THE ANCHOR + hard gate)"
    estimate: 5
    summary: >-
      Open the upstream community-plugin PR from the prepared fork branch
      leonardsellem:add-hypermnesic-companion against master (preferred: local gh CLI,
      whose token now carries repo scope — resolving the recorded CreatePullRequest
      blocker; fallback: community.obsidian.md web flow). PR body leads read-only-by-design
      + network-use disclosure. Respond to the per-release security/quality scan + manual
      queue. NOT done at "PR open": done only when the entry is merged into
      community-plugins.json and the companion is installable in Obsidian's in-app browser
      (merge URL + install screenshot captured). This merge HARD-GATES every downstream
      unit. Operator approval required to open.
  - title: "U3 — Obsidian Forum 'Share & showcase' announce (post-merge)"
    estimate: 2
    summary: >-
      Gated on U2 merge. Post one thread to the Obsidian Forum 'Share & showcase' board,
      leading with read-only-by-construction + the network-use disclosure, then the
      vault-as-shared-memory frame, then the companion + engine-quick-start links (adapt
      the approved r/ObsidianMD draft to forum norms). Stay in-thread answering with source
      links only, benchmark answers within the published comparability envelope. Record the
      live thread URL + first substantive reply. Operator approval required to post.
  - title: "U4 — Obsidian Discord developer-channel note (conditional; skip if role not held)"
    estimate: 1
    summary: >-
      Gated on U2 merge. ONLY if the operator confirms they hold the Obsidian Discord
      developer role, post a 2–3 line note to the developer updates channel reusing the U3
      lead. If the role is not held, SKIP entirely and record 'deferred — developer role
      not held' against LS-1683 — do not post from a non-eligible account. Operator
      confirmation + approval required.
  - title: "U5 — PKM feeds: PKM.social Mastodon post + two newsletter emails (the nudge)"
    estimate: 2
    summary: >-
      Gated on U2 merge. Post ONE #obsidian announcement on PKM.social (the instance
      Obsidian Stats + PKM Weekly auto-source), read-only first, vault-as-shared-memory
      frame, companion + engine links — one post, respect feed signal-to-noise. Send one
      short personal email each to Ganessh Kumar R P (Obsidian Stats) and Ed Nico (PKM
      Weekly): merged-directory line + read-only-companion line + the two links; NO pitch
      around the dormant Obsidian Roundup; no private data in the record. Directory merge +
      Mastodon post are the load-bearing path; emails are a courtesy nudge. Operator
      approval required.
  - title: "U6 — Subreddits, last and rules-gated (one venue at a time)"
    estimate: 3
    summary: >-
      Gated on U2 merge. Candidates r/ObsidianMD, r/PKMS, r/Zettelkasten. IMMEDIATELY
      before posting to any subreddit, open its live sidebar/rules/wiki SIGNED IN and
      record three confirmations: (a) self-promo allowed at all / only on a designated day?
      (b) self-promo or showcase flair required? (c) comment-first / account-age / karma
      gate? Post one venue, wait, observe moderation, then the next — honoring the 90/10
      norm. Frame r/Zettelkasten as method/workflow, not a product drop; SKIP any venue
      whose rules forbid tool promotion or where no genuinely-participating account exists.
      Success = at least one rules-verified post live with its rule check recorded; record
      skipped venues with reason. Operator approval per post (one at a time).
---

## Context

hypermnesic's read-only Obsidian companion is its most legible surface for the PKM /
second-brain audience the project is built for, yet it reaches none of them today. The
packaging work is finished — the companion ships from its own GPL-3.0 repo
(`leonardsellem/hypermnesic-companion`) with release assets, `versions.json`, and an
opt-in, empty-by-default endpoint a reviewer wants to see — and the directory branch
`leonardsellem/obsidian-releases @ add-hypermnesic-companion` is pushed. But the upstream
pull request was never opened: the GitHub token in the prior environment lacked
`CreatePullRequest` on `obsidianmd/obsidian-releases`, so the submission stalled one click
short of visible. Until that PR lands and merges, the companion is invisible in
`community-plugins.json` — the surface the whole PKM discovery loop reads from.

This issue opens the channel end to end: land the directory PR (the anchor), then earn
placement in the live PKM feeds — Obsidian Forum, the Obsidian Discord (conditionally),
PKM.social Mastodon, the two surviving weekly newsletters, and rules-checked subreddits.
The merged directory entry is both the credibility anchor and the thing that auto-feeds
the PKM feeds; everything else is participation around it.

This is a distribution / outreach effort, not code: the units are concrete
submit / publish / verify steps. It does **not** restate the companion packaging (that
shipped under the prior companion-directory-publishing effort), and it **corrects three
live facts** the requirements + prep docs predate:

1. The companion is now **`0.3.2`** (manifest `0.3.2`, `minAppVersion` `1.7.2`; tags
   `0.3.0`/`0.3.1`/`0.3.2`; `versions.json` maps all three), **not** the `0.3.0` the prep
   doc records. Obsidian's bot scans the **latest** release, so hygiene must be verified
   on `0.3.2`. The `community-plugins.json` directory entry carries no version field, so
   its text is unchanged — but the scanned release must be the live one.
2. The local `gh` CLI token now carries **`repo`** scope (verified) — sufficient to open a
   cross-fork PR — which resolves the recorded `CreatePullRequest` blocker; the
   `community.obsidian.md` web flow remains the human fallback.
3. The **Obsidian Roundup** newsletter the prep was built to pitch is **dormant** (author
   on hiatus); the live, weekly-publishing feeds are **Obsidian Stats** and **PKM Weekly**,
   both of which auto-source from the community directory and the PKM.social `#obsidian`
   hashtag.

Beyond mechanics, this is a values-gated audience: the Obsidian community and the stricter
PKM subreddits sanction sharing what you built but penalize drop-and-run promotion, and a
plugin that sends note text to a network endpoint is exactly what a reviewer or a skeptical
forum reader scrutinizes first. So **read-only-by-construction and the network-use
disclosure lead every artifact** — the compliance-safest and the most trust-building move,
which here are the same move. The wedge is one line: *your Obsidian vault becomes the
memory every AI you use shares, through a companion that reads the vault and never writes
it* — agent writes come back as reviewable git commits over those same files; the companion
is the read-only window into that loop, not the product.

This is an **epic** (estimate 1) because the work is multi-track and strictly gated across
six externally-visible milestones with a hard merge gate; the tracks are the sub-issues
below, mapped 1:1 to the plan's stable U-IDs (U1–U6).

## Intent

Reach the second-brain / PKM audience hypermnesic is built for by **landing the prepared
Obsidian community-plugin submission for the read-only companion, then earning a place in
the live PKM feeds** — with the directory merge as the load-bearing distribution act and
every other surface as honest, rules-respecting participation around it.

Concretely: open and **merge** the upstream `obsidianmd/obsidian-releases` PR; once merged,
announce on the sanctioned surfaces in strict order — Obsidian Forum "Share & showcase"
(and Discord only if the operator holds the developer role), then a single PKM.social
`#obsidian` post plus two short personal newsletter emails, then rules-verified subreddits
one at a time. Capture a verification artifact for every externally-visible act, and a
before/after of the companion surfacing in a live PKM feed as the channel's proof.

## Acceptance Criteria

Each criterion is independently verifiable. Sequencing is strict: **U2 merge hard-gates
U3–U6**, and every externally-visible action is **operator-approval-gated** before it fires.

- [ ] **(U1) Submission-readiness verified on the current release.** A checklist is
      recorded (on LS-1683 or the prep doc) naming the exact release tag scanned (`0.3.2`),
      with pass/fail for the four bot-hard-checked hygiene assets, the three reviewer-
      critical README disclosure line references, and the naming + description checks. No
      external action fired from this unit.
- [ ] **(U1) The scanned release is the live one, not `0.3.0`.** The checklist confirms the
      latest GitHub release the directory installs is `0.3.2` (manifest `0.3.2`,
      `minAppVersion` `1.7.2`), and that hygiene was verified against THAT tag.
- [ ] **(U2) Upstream PR opened.** A pull request adding the companion entry to
      `community-plugins.json` is open against `obsidianmd/obsidian-releases` from the
      prepared branch `leonardsellem:add-hypermnesic-companion`; the **PR URL** and the
      **bot's first response** are recorded on LS-1683. The PR body leads with
      read-only-by-construction + the network-use disclosure.
- [ ] **(U2) Directory entry merged — THE ANCHOR.** The entry is **merged** into
      `community-plugins.json` (merge commit/URL recorded) **and** the companion is
      installable from Obsidian's in-app Community plugins browser (**screenshot captured**).
      "PR open" alone does **not** satisfy this criterion.
- [ ] **(U3) Forum showcase post live.** A new "Share & showcase" thread is live on the
      Obsidian Forum, **leading with read-only-by-design + the network-use disclosure**;
      its URL and the first substantive reply are recorded. (Gated on U2 merge.)
- [ ] **(U4) Discord note posted OR explicitly deferred.** Either a developer-channel note
      is posted (message link recorded) **or** the unit is recorded as
      "deferred — developer role not held"; no post is made from a non-eligible account.
      (Gated on U2 merge + operator confirmation of the role.)
- [ ] **(U5) PKM.social post live.** A single `#obsidian` announcement is live on
      PKM.social, read-only-first and framed around vault-as-shared-memory, with the
      companion + engine-quick-start links; its URL is recorded. (Gated on U2 merge.)
- [ ] **(U5) Two newsletter emails sent.** Short personal emails were sent to Ganessh Kumar
      R P (Obsidian Stats) and Ed Nico (PKM Weekly), with timestamps + recipients recorded
      and **no private data in the record**; neither email pitches the dormant Obsidian
      Roundup. (Gated on U2 merge.)
- [ ] **(U6) At least one rules-verified subreddit post live.** For every venue posted to,
      the **per-venue rule check** is recorded — (a) self-promo allowed at all / only on a
      designated day? (b) flair required? (c) comment-first / account-age / karma gate? —
      captured from the live, signed-in sidebar/rules/wiki immediately before posting; the
      post URL and moderation status are recorded. Every **skipped** venue is recorded with
      its reason (rule conflict or no eligible account). r/Zettelkasten, if posted, is
      framed as method/workflow. (Gated on U2 merge; one venue at a time.)
- [ ] **(Proof) Channel proof captured.** A later read of the live PKM feeds shows the
      companion **surfaced** (directly or via auto-sourcing — e.g. an Obsidian Stats weekly
      / a newsletter mention); a **before/after** is captured as the channel's proof
      artifact.
- [ ] **(Claims, R17) No artifact asserts a claim outside the approved set.** In
      particular: no "official MCP Registry listing" (not published); no "merged into
      `awesome-mcp-servers`" (PR #8056 is **open** per repo evidence); no Glama "A" Tool-
      Definition-Quality grade unless confirmed live; never implies the companion can write
      a vault; never implies dense retrieval is always on (lexical-only is a supported,
      visible state); no benchmark number outside the published comparability envelope; no
      hosted/managed-cloud framing.
- [ ] **(Claims, R18) No private data in any artifact.** No artifact (PR body, forum post,
      newsletter email, Mastodon post, subreddit copy, or the Linear record) contains a
      private hostname, token, vault content, or local absolute path; endpoint references
      use placeholders and the public engine/companion repo URLs only.
- [ ] **(Linear hygiene) LS-1683 carries the trail.** LS-1683 carries the PR URL, the bot
      response, the merge proof, and each downstream artifact link, with status moved as
      work progresses and a comment at each milestone (start, PR open, merge, each
      announce, completion).

## Validation Plan

How each criterion is proven, and the evidence artifact captured for it:

- **U1 readiness (both criteria).** Run the four hygiene checks against the **latest**
  release tag (`0.3.2`): tag equals manifest version with **no `v` prefix**; release
  carries `main.js` + `manifest.json` + `styles.css` as individual binary assets; repo-root
  `manifest.json` matches; `versions.json` maps the released version to its `minAppVersion`;
  `LICENSE` present (GPL-3.0). Confirm the three README disclosures near the top
  ("Read-only by construction"; "Network use & privacy" — one remote service, only the
  cursor block / selection transmitted, empty endpoint by default; "no analytics, no
  telemetry, no third party") and note the honest "Clipboard use" disclosure (two explicit
  right-click writes). Confirm naming: `name` "Hypermnesic Companion" contains neither
  "Obsidian" nor "Plugin"; `id` `hypermnesic-companion` has no "obsidian" substring;
  `description` < 250 chars (currently 160), ends with a period, starts with an action verb;
  `isDesktopOnly: true`. **Evidence:** the pass/fail checklist with the scanned tag, on
  LS-1683 / the prep readiness checklist (flip "Obsidian submission PR opened" only after U2).
- **U2 PR opened.** Open via `gh pr create --repo obsidianmd/obsidian-releases --base master
  --head leonardsellem:add-hypermnesic-companion …` (or the web flow). Confirm the branch's
  `community-plugins.json` addition is exactly the prepared entry (`id`
  `hypermnesic-companion`, `name` `Hypermnesic Companion`, `author` `Leonard Sellem`,
  `description` as in the manifest, `repo` `leonardsellem/hypermnesic-companion`), appended
  preserving file ordering/format. **Evidence:** the opened **PR URL** + the bot's first
  response, on LS-1683.
- **U2 merged (anchor).** Drive the PR through the automated per-release security/quality
  scan + manual queue; point the bot at the U1-verified README network-use / telemetry /
  read-only sections if flagged. **Evidence:** the **merge commit/URL** + a **screenshot of
  the companion in Obsidian's in-app Community plugins browser**. Do not treat "PR open" as
  done.
- **U3 forum post.** Post the "Share & showcase" thread; verify it leads with read-only +
  network-use. **Evidence:** the live **forum thread URL** + the first substantive reply
  captured for the response log.
- **U4 Discord.** Confirm the developer-role question with the operator first. **Evidence:**
  either the **message link** (if posted) or an explicit **"deferred — developer role not
  held"** note on LS-1683.
- **U5 PKM feeds.** Post one PKM.social `#obsidian` announcement; send the two emails.
  **Evidence:** the live **Mastodon post URL**; **send timestamps + recipients** for both
  emails (no email bodies with private data). The channel proof artifact (below) is the
  later before/after of the companion surfacing in a feed.
- **U6 subreddits.** For each venue, open the live signed-in sidebar/rules/wiki immediately
  before posting and record the three confirmations (Reddit hard-blocks automated rule
  retrieval — this is a manual check; do not assume the rules). **Evidence, per venue
  posted:** the **post URL**, the **moderation status**, and the **three-point rule check**;
  **per venue skipped:** the recorded reason. At least one rules-verified post must be live.
- **Channel proof.** Re-read the live PKM feeds after merge + posts and capture a
  **before/after** showing the companion surfaced (directly or via auto-sourcing).
- **Claims (R17/R18).** Review every drafted artifact against the approved claims set before
  it fires. **Evidence:** the artifacts themselves (PR body, posts, emails) plus a
  claims-check note; specifically assert the negative on the MCP Registry, `awesome-mcp-
  servers` PR #8056 (open), and the Glama grade.
- **Linear hygiene.** **Evidence:** the LS-1683 comment trail + status transitions
  (In Progress at start → In Review when the PR is open/pending merge → Done only when
  merged + the channel proof is captured), with a comment at each milestone.

## Definition of Done

- **Anchor:** the `obsidianmd/obsidian-releases` PR is open (URL + bot response recorded)
  **and merged** into `community-plugins.json`; the companion is installable from Obsidian's
  in-app Community plugins browser (screenshot captured). **PR-open alone is not done.**
- **Forum:** a "Share & showcase" post is live, leading with read-only-by-design, URL
  recorded.
- **Discord:** posted (message link) **or** explicitly recorded as deferred (developer role
  not held).
- **PKM feeds:** a PKM.social `#obsidian` post is live (URL recorded) and the two newsletter
  emails are sent (timestamps/recipients recorded; no private data).
- **Subreddits:** at least one rules-verified subreddit post is live, with the per-venue
  rule check recorded for every venue posted to; skipped venues recorded with reason.
- **Proof artifact:** a later read of the live PKM feeds shows the companion surfaced; a
  before/after is captured.
- **Claims:** no artifact asserts a claim outside the approved set (R17); no artifact
  includes a private hostname, token, vault content, or local absolute path (R18).
- **Linear hygiene:** LS-1683 carries the PR URL, the bot response, the merge proof, and
  each downstream artifact link, with status moved as work progresses and a comment at each
  milestone (start, PR open, merge, each announce, completion).

> **Closure gate.** This epic is Done only when the **anchor is merged and the channel
> proof is captured** — not when the PR is merely open, not when posts are drafted. A bug
> or a bounce after merge (e.g. a re-scan rejection on a future release) reopens the
> relevant track. Default to OPEN if end-to-end proof is missing.

## Links

- **Canonical plan:** `docs/plans/2026-06-25-003-content-obsidian-pkm-channel-plan.md`
- **Brainstorm (requirements R1–R18):** `docs/brainstorms/2026-06-25-obsidian-pkm-channel-requirements.md`
- **Directory submission prep (LS-1683 artifact):** `docs/launch/directory-submission-prep.md`
- **Approved per-channel drafts + claims-allowed/avoid:** `docs/launch/launch-narrative-drafts.md`
- **Corrected claims state + LS-1683..LS-1690 issue map:** `docs/launch/promo-grounding-brief.md`
- **Ownership / compounding wedge (vs-plain-Obsidian, complementary-to-Honcho):** `docs/why-hypermnesic.md`
- **Engine launch channel order (separate, parallel channel):** `docs/launch/launch-sequencing.md`
- **Companion README disclosures (separate GPL-3.0 repo):** `https://github.com/leonardsellem/hypermnesic-companion#readme`
- **Related Linear:** LS-1683 (Submit to MCP and Obsidian directories — the anchor lives
  here), LS-1689 (launch narrative + per-channel posts — copy source), LS-1690 (launch
  sequencing), LS-1688 (launch-week response SLO — governs in-thread response timing).

<!-- GitHub permalinks for the plan + brainstorm are substituted for the repo-relative
paths above at Linear-issue creation time. -->
