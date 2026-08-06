---
date: 2026-06-25
origin: docs/brainstorms/2026-06-25-obsidian-pkm-channel-requirements.md
type: content
title: "Open the Obsidian + PKM channel for the read-only companion"
---

# Open the Obsidian + PKM channel for the read-only companion

## Overview

Open hypermnesic's Obsidian + PKM distribution channel for the read-only companion by
landing the prepared community-plugin submission, then earning placement in the live PKM
feeds (Obsidian Forum, PKM.social Mastodon, the two surviving weekly newsletters, and
rules-checked subreddits). The merged directory entry is the credibility anchor and the
thing that auto-feeds the PKM feeds; everything else is participation around it. Every
artifact leads with read-only-by-construction and the network-use disclosure, because a
plugin that sends note text to a network endpoint is exactly what a reviewer or a
skeptical forum reader scrutinizes first — and because that framing is both the
compliance-safest and the most trust-building move.

This is a distribution/outreach plan: the Implementation Units are concrete submit /
publish / verify steps, not code modules. It does **not** restate the packaging work
(companion repo, release assets, `versions.json`) — that shipped under the prior
companion-directory-publishing effort. It corrects three live facts the requirements doc
predates (see Risks: companion is now `0.3.2` not `0.3.0`; the local `gh` token already
carries PR-creating `repo` scope; the Obsidian Roundup newsletter is dormant).

## Goals / Non-goals

**Goals**

- Open the upstream `obsidianmd/obsidian-releases` PR from the prepared branch and drive
  it to a merge into `community-plugins.json`, surviving the per-release automated scan.
- Once merged, announce on the sanctioned surfaces in order — Obsidian Forum "Share &
  showcase" (and Discord only if the human holds the developer role), then a single
  PKM.social `#obsidian` post plus two short personal newsletter emails.
- Post to PKM-relevant subreddits last, one at a time, each rules-verified against its
  live sidebar/wiki, only from an account with genuine prior participation.
- Capture a verification artifact for every externally visible act (PR URL + bot
  response, forum/Mastodon URLs, email sends, per-subreddit rule checks) and a
  before/after of the companion surfacing in a PKM feed as the channel's proof.

**Non-goals**

- The official MCP Registry publication and the `awesome-mcp-servers` merge — tracked as
  the separate directory-submission effort (LS-1683); this channel does not block on them
  and must not claim either as done.
- Engine-side announce channels (Show HN, r/selfhosted, r/LocalLLaMA, the MCP Discord) —
  the engine launch sequence in `docs/launch/launch-sequencing.md`, separate from this
  PKM push.
- GitHub Discussions welcome/roadmap posts (separate community-surface effort, LS-1686).
- Mobile companion recall (a known companion gap, out of scope here).
- Any paid placement, sponsorship, or press push; no hosted/multi-tenant offering implied;
  no claim the companion can write a vault; no benchmark-rank positioning against PKM tools.

## Implementation Units

> Sequencing is strict and gated: **U2 (merge) is the gate.** U3–U6 (all outreach) must
> not start until the directory entry is live in `community-plugins.json`. Every
> externally visible action in every unit is **operator-approval-gated** before it fires.

### U1 — Pre-submission verification (companion repo is submission-ready on the CURRENT release)

**Goal.** Prove, against the live companion repo state (not the `0.3.0` snapshot the prep
doc records), that the README disclosures, release-asset hygiene, and naming policy all
hold on the version the Obsidian bot will actually scan — so the PR is not bounced.

**Steps.**
1. Determine the current released version and reconcile the drift: the companion repo is
   now at manifest `version` **`0.3.2`** (`minAppVersion` `1.7.2`), with tags
   `0.3.0`/`0.3.1`/`0.3.2` and `versions.json` mapping all three. Confirm the **latest**
   GitHub release (currently `0.3.2`) is the one the directory will install, and run
   asset hygiene against THAT release, not `0.3.0`.
2. Re-confirm the three reviewer-critical README statements are present near the top of
   `hypermnesic-companion/README.md` (they are, as of this plan): connects only to a
   user-supplied self-hosted hypermnesic endpoint (the "Network use & privacy" section,
   empty-by-default URL — "transmits nothing off-device until you set the endpoint");
   exactly what data leaves the vault (the block around the cursor or the current
   selection, for related-note lookup) and that nothing else does; never writes the vault
   and ships zero client-side telemetry ("Read-only by construction" + "no analytics, no
   telemetry, no third party"). Note for the reviewer that the only system-clipboard
   writes are the two explicit right-click actions, already disclosed in the "Clipboard
   use" section.
3. Confirm release-asset hygiene the bot hard-checks, on the latest release tag:
   - the GitHub release tag equals the manifest version with **no `v` prefix** (`0.3.2`,
     not `v0.3.2`);
   - the release carries `main.js`, `manifest.json`, and `styles.css` as **individual
     binary assets**;
   - the repo-root `manifest.json` matches the release;
   - `versions.json` maps the released version to its `minAppVersion`;
   - a `LICENSE` file is present in the repo (it is — GPL-3.0).
4. Verify naming-policy constraints stay satisfied and have not regressed: the plugin
   `name` ("Hypermnesic Companion") contains neither "Obsidian" nor "Plugin"; the `id`
   (`hypermnesic-companion`) does not contain the substring "obsidian"; the manifest
   `description` is under 250 chars (currently 160), ends with a period, and starts with
   an action verb ("Surface…"). `isDesktopOnly: true` is set, consistent with a
   network/Node-using plugin.

**Files / Surfaces.** `hypermnesic-companion/` (separate GPL-3.0 repo — `README.md`,
`manifest.json`, `versions.json`, `LICENSE`, the GitHub Releases page); local read-only
checkout at `/Volumes/Dev/hypermnesic-companion`.

**Validation.** A short checklist captured in the directory-submission prep doc (or a
comment on LS-1683) recording: the exact release tag scanned; pass/fail for each of the
four hygiene assets; the three README disclosure line references; the naming + description
check. No external action fires from this unit.

**Dependencies.** None (this is the gate that unblocks U2).

---

### U2 — Open the upstream directory PR and drive it to merge (THE ANCHOR)

**Goal.** Get the companion entry into `obsidianmd/obsidian-releases` →
`community-plugins.json`, opened from the prepared branch, and merged through the bot +
manual queue. Until this merges, the channel has nothing behind it.

**Steps.**
1. **Choose the PR-open path (resolves the recorded blocker).** The prior environment's
   token lacked `CreatePullRequest` on `obsidianmd/obsidian-releases`. Two viable paths
   now, pick one with the operator:
   - **(preferred, lowest-friction) the local `gh` CLI**, whose token carries `repo`
     scope (verified: scopes include `repo`, `workflow`) — sufficient to open a
     cross-fork PR. From the prepared fork branch, open against `master`:
     `gh pr create --repo obsidianmd/obsidian-releases --base master --head leonardsellem:add-hypermnesic-companion --title "Add Hypermnesic Companion" --body-file <body>`;
   - **or the Obsidian web flow as the human** — sign in at `community.obsidian.md`, link
     GitHub, Plugins → New plugin, enter `leonardsellem/hypermnesic-companion`; or open
     the prepared compare URL while signed in:
     `https://github.com/obsidianmd/obsidian-releases/compare/master...leonardsellem:obsidian-releases:add-hypermnesic-companion?expand=1`.
2. Confirm the branch's `community-plugins.json` addition is exactly the prepared entry
   (`id` `hypermnesic-companion`, `name` `Hypermnesic Companion`, `author`
   `Leonard Sellem`, `description` as in the manifest, `repo`
   `leonardsellem/hypermnesic-companion`) and is appended preserving the file's existing
   ordering/format. The directory entry carries **no version field**, so the `0.3.0`→`0.3.2`
   drift does not change the entry text — but the bot scans the **latest release**, which
   is why U1 verifies hygiene on `0.3.2`.
3. Use this PR-body copy (read-only-by-design first, then the demo link), no claims beyond
   the approved set:

   ```md
   Adds **Hypermnesic Companion**, a **read-only** Obsidian plugin that surfaces related
   notes and Socratic prompts from a **self-hosted** hypermnesic index as you write.

   Read-only by construction: it never writes, creates, or deletes vault notes — a static
   allowlist of read tools is verified by the test suite on every push. Network use is
   disclosed in the README: it talks to exactly one remote service, your own hypermnesic
   MCP endpoint on your tailnet, transmitting only the block around your cursor (or your
   selection) for related-note lookup; the endpoint is empty by default, so nothing leaves
   the device until you set it. No analytics, no telemetry, no third party.

   Engine README demo and 5-minute proof: https://github.com/leonardsellem/hypermnesic#quick-start
   Companion repo: https://github.com/leonardsellem/hypermnesic-companion
   ```
4. After opening, respond to bot/maintainer feedback promptly. Expect the **automated
   per-release security/code-quality scan** plus a manual review queue. If the bot flags a
   network-use or telemetry concern, point it at the README sections verified in U1 rather
   than re-arguing from scratch. Treat re-scans on every future companion release as the
   ongoing cost of the channel.

**Files / Surfaces.** `obsidianmd/obsidian-releases` (`community-plugins.json`) via the
pushed fork branch `leonardsellem/obsidian-releases @ add-hypermnesic-companion`;
`community.obsidian.md` web flow as the alternative; PR body drafted from
`docs/launch/directory-submission-prep.md`.

**Validation.** Record the **opened PR URL** and the bot's first response as the
verification artifact on LS-1683 + the prep doc's readiness checklist (flip
"Obsidian submission PR opened; link recorded"). The anchor is **unproven until the entry
is merged into `community-plugins.json`**; capture the merge commit/URL and a screenshot
of the companion appearing in Obsidian's in-app Community plugins browser as the
end-to-end proof. Do not treat "PR open" as done.

**Dependencies.** U1 (hygiene + disclosures verified on the current release). A GitHub
identity that can open the PR (the local `gh` `repo`-scoped token, or the human via web).
Operator approval to open.

---

### U3 — Obsidian Forum "Share & showcase" announce (post-merge)

**Goal.** Announce the companion on the community's sanctioned showcase surface, leading
with read-only-by-design and the network-use disclosure, only after the directory entry is
live.

**Steps.**
1. Gate on U2 merge. Post a new thread to the Obsidian Forum **"Share & showcase"** board
   (`forum.obsidian.md`).
2. Lead the copy with read-only-by-construction and the network-use disclosure, then the
   vault-as-shared-memory frame, then links. Adapt the approved r/ObsidianMD draft in
   `docs/launch/launch-narrative-drafts.md` to forum norms (a touch more participatory,
   invite feedback). Suggested copy:

   ```md
   I made **Hypermnesic Companion** — a **read-only** Obsidian plugin that surfaces related
   notes and Socratic prompts from a self-hosted **hypermnesic** index while you write. It
   **never writes your vault**: it asks the engine for related notes and shows them; a
   static allowlist of read tools is verified on every push.

   The idea: the same Markdown vault you keep in Obsidian becomes the recall layer the AIs
   you use can read from — and agent writes come back as **reviewable git commits** over
   those same files. The companion is the read-only window into that loop.

   Network use, plainly: it talks to one remote service — your own hypermnesic MCP endpoint
   on your tailnet — sending only the block around your cursor (or your selection) for
   lookup; empty by default, nothing leaves the device until you set the endpoint. No
   telemetry.

   Now installable from Community plugins. Companion: https://github.com/leonardsellem/hypermnesic-companion ·
   Engine + 5-minute proof: https://github.com/leonardsellem/hypermnesic#quick-start
   ```
3. Stay in the thread to answer questions with source links (engine quick start, companion
   README), not speculation; keep all benchmark answers within the published comparability
   envelope.

**Files / Surfaces.** Obsidian Forum → Share & showcase. Copy seeded from
`docs/launch/launch-narrative-drafts.md` (r/ObsidianMD draft) + this plan.

**Validation.** Record the live forum thread URL; note that the post leads with
read-only-by-design. Capture the first substantive reply for the response log.

**Dependencies.** U2 merged. Operator approval to post.

---

### U4 — Obsidian Discord developer-channel note (conditional)

**Goal.** If — and only if — the human holds the Obsidian Discord developer role, post a
short companion note to the appropriate updates channel; otherwise skip entirely rather
than post from a non-eligible account.

**Steps.**
1. Confirm with the operator whether the developer role is held (open question from the
   requirements doc). If not, **skip this unit** and record it as deferred — do not force
   it.
2. If held, post a 2–3 line note to the developer `#updates` / `#content-update` channel,
   reusing the U3 lead (read-only + network-use), linking the companion repo and the engine
   quick start.

**Files / Surfaces.** Obsidian Discord (developer updates channel), conditional on role.

**Validation.** Either the message link (if posted) or an explicit "deferred — developer
role not held" note recorded against LS-1683/the channel log.

**Dependencies.** U2 merged. Operator confirmation of Discord developer role. Operator
approval to post.

---

### U5 — PKM feeds: PKM.social Mastodon post + two personal newsletter emails (the nudge)

**Goal.** Trigger the auto-sourcing PKM feeds with one `#obsidian` Mastodon post on the
instance both surviving newsletters watch, plus a short personal email to each author —
treating these as a courtesy nudge, not the load-bearing step (the directory merge is).

**Steps.**
1. Gate on U2 merge. Post a single **`#obsidian`** announcement on **PKM.social**
   (the Mastodon instance Obsidian Stats and PKM Weekly auto-source), framed around the
   vault-as-shared-memory line, read-only first, with the companion + engine links. Keep it
   one post (respect the feed's signal-to-noise). Suggested copy:

   ```text
   New: Hypermnesic Companion — a read-only #Obsidian plugin that surfaces related notes
   from a self-hosted hypermnesic index as you write. Your vault becomes the recall layer
   the AIs you use read from; agent writes come back as reviewable git commits. Never writes
   the vault, no telemetry, empty endpoint by default. https://github.com/leonardsellem/hypermnesic-companion
   ```
2. Send a short, personal email to **Ganessh Kumar R P** (Obsidian Stats /
   obsidianstats.com / obsidianpluginstats.substack.com) and to **Ed Nico** (PKM Weekly /
   pkmweekly.com), each: one line on the merged directory entry, one line on the read-only
   companion + the shared-memory frame, the two links. Do **not** build any pitch around
   the dormant Obsidian Roundup. Keep each email 4–6 lines; no press-kit, no asks beyond "in
   case it's a fit for the weekly."
3. Rely on the directory merge + the PKM.social post as the primary surfacing mechanism;
   the emails are the nudge. Optionally hold the emails a few days to let an organic mention
   land first (open timing question — operator's call; default: send on merge).

**Files / Surfaces.** PKM.social (Mastodon, `#obsidian`); email to the two newsletter
authors. Frame seeded from `docs/why-hypermnesic.md` (vs-plain-Obsidian + ownership wedge)
and this plan.

**Validation.** Record the live Mastodon post URL; record that both emails were sent
(timestamps, recipients — no email bodies with private data). As the channel's proof
artifact, capture a before/after of the companion surfacing in a PKM feed
(Obsidian Stats weekly / a newsletter mention) once it auto-sources.

**Dependencies.** U2 merged. Operator approval for the post and the emails.

---

### U6 — Subreddits, last and rules-gated (one venue at a time)

**Goal.** Reach PKM subreddits without tripping the "participate more than you promote"
norm: one venue at a time, each verified against its live rules immediately before posting,
each from an account with genuine standing in that community.

**Steps.**
1. Gate on U2 merge. Candidate venues: **r/ObsidianMD**, **r/PKMS**, **r/Zettelkasten**.
   With the operator, confirm which are genuinely in scope given the prior-participation
   bar and whether an eligible account exists for each (open question from the requirements
   doc). Defer any venue lacking an eligible account.
2. **Immediately before posting to any subreddit**, open its live sidebar, rules, and wiki
   **signed in**, and confirm three things, recording each: (a) whether self-promotion is
   permitted at all or only on a designated day; (b) whether a self-promotion or
   plugin/showcase **flair** is required; (c) any comment-first / account-age / karma gate.
   (Reddit hard-blocks automated rule retrieval, so this is a manual, signed-in check — do
   not assume the rules.)
3. For r/ObsidianMD, post the approved draft from
   `docs/launch/launch-narrative-drafts.md` (already read-only-first), applying any required
   flair. For **r/Zettelkasten** specifically — historically stricter on tool promotion —
   frame as **method/workflow** ("how a shared, file-first memory complements a
   Zettelkasten"), not a product drop; if its rules forbid tool promotion, **skip the venue
   entirely** rather than post against them.
4. Post one venue, wait, observe moderation, then proceed to the next — honoring the
   Reddit-wide 90/10 self-promotion guideline. Answer questions with source links.

**Files / Surfaces.** r/ObsidianMD, r/PKMS, r/Zettelkasten (live sidebars/wikis); approved
r/ObsidianMD draft in `docs/launch/launch-narrative-drafts.md`.

**Validation.** For each venue posted to: record the post URL, the moderation status, and
the **per-venue rule check** (the three confirmations from step 2). For each venue skipped:
record why (rule conflict or no eligible account). Success requires at least one
rules-verified subreddit post live with its rule check recorded.

**Dependencies.** U2 merged. Operator confirmation of eligible accounts per venue. Operator
approval per post (one at a time).

## Sequencing / Milestones

1. **M0 — Ready to submit (U1).** Hygiene, disclosures, and naming verified on the current
   release (`0.3.2`). No external action yet.
2. **M1 — PR open (U2 step 1–3).** Upstream `obsidian-releases` PR opened from the prepared
   branch; URL + bot first response recorded. *Gate gate: nothing downstream proceeds.*
3. **M2 — Merged (U2 step 4 → merge).** Entry live in `community-plugins.json`; companion
   installable in-app. **This is the anchor and the gate for all of U3–U6.** The
   merge-review turnaround (bot + manual queue) sets the timing of every downstream post —
   do not pre-schedule U3–U6 against a date; trigger them off the merge.
4. **M3 — Sanctioned announce (U3, then U4 if eligible).** Forum showcase post live; Discord
   note posted or explicitly deferred.
5. **M4 — PKM feeds nudged (U5).** PKM.social post live; two newsletter emails sent (or held
   a few days by operator choice).
6. **M5 — Subreddits (U6).** One rules-verified venue at a time, spaced; at least one live.
7. **M6 — Proof captured.** A later read of the live PKM feeds shows the companion surfaced
   (directly or via auto-sourcing); before/after captured.

## Risks & Mitigations

- **Stale version assumption (`0.3.0` vs live `0.3.2`).** The requirements + prep docs
  reference companion `0.3.0`; the repo has shipped `0.3.1` and `0.3.2` (manifest
  `0.3.2`, `minAppVersion` `1.7.2`; `versions.json` maps all three). The bot scans the
  **latest** release. *Mitigation:* U1 verifies hygiene against the current release tag, not
  `0.3.0`; the directory entry carries no version field so its text is unchanged, but the
  scanned release must be the live one. Update the prep doc's `0.3.0` references when next
  edited.
- **PR-open blocker recurs.** The prior token lacked `CreatePullRequest`. *Mitigation:* the
  local `gh` token carries `repo` scope (verified) — sufficient for a cross-fork PR — and the
  Obsidian web flow is the human fallback. Pick one with the operator before opening.
- **Per-release automated scan bounces a network plugin.** The bot scans every release for
  security/quality, and a note-text-transmitting plugin is the highest-risk kind.
  *Mitigation:* U1 pre-verifies the README network-use + no-telemetry + read-only
  disclosures; U2 points the bot at those sections; expect re-scans on every future release
  as a standing cost.
- **Pitching a dormant newsletter.** The Obsidian Roundup is dormant (author on hiatus).
  *Mitigation:* drop it entirely; target the live auto-sourcing feeds (Obsidian Stats, PKM
  Weekly) via the directory merge + the PKM.social post, with emails as a nudge.
- **Subreddit norm violation / wrong rule assumption.** Reddit blocks automated rule reads
  and PKM venues moderate tool promotion hardest. *Mitigation:* manual signed-in
  rule/flair/gate check immediately before each post; one venue at a time; method-framing for
  r/Zettelkasten; skip rather than force; post only from accounts with genuine standing.
- **Outreach before the anchor exists.** A post with no merged entry behind it is a claim
  with nothing behind it and burns the "participate before you promote" credibility.
  *Mitigation:* M2 (merge) hard-gates all of U3–U6.
- **Claims drift.** *Mitigation:* every artifact honors R17/R18 (see DoD); no official MCP
  Registry listing, no "merged into awesome-mcp-servers" (PR #8056 is OPEN per repo
  evidence), no Glama "A" grade until live-verified, never imply the companion writes a
  vault, never imply dense retrieval is always on, no number outside the comparability
  envelope, no private host/token/path/vault content. Note the obsolete
  `launch-narrative-drafts.md` PyPI-avoid line (LS-1684 is Done) when that doc is next
  touched — but this channel does not need the PyPI claim.

## Validation / Definition of Done

- **Anchor:** the `obsidianmd/obsidian-releases` PR is open (URL recorded, bot response
  captured) **and merged** into `community-plugins.json`; the companion is installable from
  Obsidian's in-app Community plugins browser (screenshot captured). PR-open alone is **not**
  done.
- **Forum:** a "Share & showcase" post is live, leading with read-only-by-design, URL
  recorded.
- **Discord:** posted with message link, **or** explicitly recorded as deferred (developer
  role not held).
- **PKM feeds:** a PKM.social `#obsidian` post is live (URL recorded) and the two newsletter
  emails are sent (timestamps/recipients recorded; no private data in the record).
- **Subreddits:** at least one rules-verified subreddit post is live, with the per-venue rule
  check (self-promo allowed? flair required? comment/age/karma gate?) recorded for every
  venue posted to; skipped venues recorded with reason.
- **Proof artifact:** a later read of the live PKM feeds shows the companion surfaced
  (directly or via auto-sourcing); a before/after is captured.
- **Claims:** no artifact asserts a claim outside the approved set (R17); no artifact
  includes a private hostname, token, vault content, or local absolute path (R18).
- **Linear hygiene:** LS-1683 carries the PR URL, the bot response, the merge proof, and
  each downstream artifact link, with status moved as work progresses and a comment at each
  milestone (start, PR open, merge, each announce, completion).

## References

**Internal**

- `docs/brainstorms/2026-06-25-obsidian-pkm-channel-requirements.md` — the requirements this
  plan implements (R1–R18).
- `docs/launch/directory-submission-prep.md` — the prepared Obsidian branch, the
  `community-plugins.json` + `manifest.json` drafts, the compare URL, the readiness
  checklist, and the recorded `CreatePullRequest` token blocker (LS-1683).
- `docs/launch/launch-narrative-drafts.md` — the approved r/ObsidianMD draft and the
  claims-allowed / claims-avoid lists (note the obsolete PyPI-avoid line — LS-1684 Done).
- `docs/launch/promo-grounding-brief.md` — positioning confirmations and the corrected
  claims state (PyPI live; registry not published; awesome-mcp-servers PR #8056 open; Glama
  grade needs live verification); the LS-1683..LS-1690 issue map.
- `docs/launch/launch-sequencing.md` — the engine launch channel order this PKM push runs
  alongside (separate channel).
- `docs/why-hypermnesic.md` — the ownership/compounding wedge, the vs-plain-Obsidian and
  complementary-to-Honcho framing.
- `hypermnesic-companion/README.md` (separate GPL-3.0 repo) — the read-only-by-construction,
  network-use & privacy, no-telemetry, and clipboard-use disclosures the reviewer checkpoint
  depends on; manifest `0.3.2`.

**External (this initiative's research)**

- Obsidian Developer policies + Plugin guidelines (docs.obsidian.md) — mandatory
  network-use README disclosure; client-telemetry prohibition; the no-"Obsidian" /
  no-"Plugin" naming + no-"obsidian"-in-`id` rules; the release-asset hygiene the bot
  hard-checks (no `v` prefix, individual `main.js`/`manifest.json`/`styles.css` assets,
  matching root manifest, `versions.json`, `LICENSE`).
- obsidian.md/blog ("future of plugins") — the move to a web submission flow at
  `community.obsidian.md` plus an automated **per-release** security/quality scan.
- Obsidian Stats / Obsidian Plugin Stats (Ganessh Kumar R P — obsidianstats.com /
  obsidianpluginstats.substack.com) and PKM Weekly (Ed Nico — pkmweekly.com) — the live
  weekly feeds that auto-source from the community directory and the PKM.social `#obsidian`
  hashtag; the Obsidian Roundup (Eleanor Konik) is dormant.
- Obsidian Community Code of Conduct + Reddit's 90/10 self-promotion norm — "participate
  more than you promote"; per-subreddit rule/flair/gate checks; r/Zettelkasten flagged as
  stricter on tool promotion.
