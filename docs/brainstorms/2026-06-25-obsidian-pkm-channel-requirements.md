---
date: 2026-06-25
topic: obsidian-pkm-channel
title: "Open the Obsidian + PKM channel for the read-only companion"
tags: [hypermnesic, obsidian, pkm, companion, distribution, launch]
---

# Open the Obsidian + PKM channel for the read-only companion

## Summary

Reach the second-brain/PKM audience hypermnesic is built for by opening the prepared Obsidian community-plugin submission for the read-only companion, then earning a place in the live PKM feeds (Obsidian Forum, PKM.social Mastodon, the two surviving weekly newsletters, and rules-checked subreddits). The frame is one line: your Obsidian vault becomes the memory every AI shares, through a companion that reads the vault and never writes it.

## Problem Frame

The companion is hypermnesic's most legible surface for PKM people, yet it reaches none of them today. The packaging work is finished — companion `0.3.0` ships from its own GPL-3.0 repo with the release assets, `versions.json`, and an opt-in empty-by-default endpoint a reviewer wants to see — and the directory branch `leonardsellem/obsidian-releases add-hypermnesic-companion` is pushed. But the upstream pull request was never opened: the GitHub token in the prior environment lacked `CreatePullRequest` on `obsidianmd/obsidian-releases`, so the submission stalled one click short of visible. Until that PR lands, the plugin is invisible in the surface — `community-plugins.json` — that the whole PKM discovery loop reads from.

Two facts that the prepared plan predates have since moved, and acting on the stale version would waste the launch. First, Obsidian no longer treats submission as a one-time fork-and-PR: an automated bot now scans every released version for security and code quality, so a network-touching plugin like this one faces a reviewer checkpoint on this release and a re-scan on every future one. Second, the "Obsidian Roundup" newsletter the plan was built to pitch is effectively dormant — its author moved to a general Substack and cited a hiatus — while the live, weekly-publishing feeds are Obsidian Stats and PKM Weekly, both of which auto-source new plugins from the community directory and the PKM.social Mastodon `#obsidian` hashtag. The channel is well-prepped but aimed at last quarter's map.

Beyond mechanics, this is a values-gated audience. The Obsidian community and the stricter PKM subreddits sanction sharing what you built but penalize drop-and-run promotion, and a plugin that sends note text to a network endpoint is exactly the kind a reviewer or a forum reader scrutinizes first. The compounding-flywheel and files-are-truth story is genuinely native to these people — but only if it arrives as participation, with the read-only and network-disclosure facts leading, not buried.

## Key Decisions

**Lead with "your vault becomes the memory every AI shares."** The PKM audience already believes files are truth; that is the shared foundation, not a pitch. The wedge for them is that the same vault they keep in Obsidian becomes the recall layer every AI they use reads from — and that agent writes come back as reviewable git commits over those same files. The companion is the read-only window into that loop, not the product. Frame the channel around the vault and the flywheel, with the companion as the on-ramp.

**Read-only-by-design is the headline, not a footnote.** A plugin that transmits note text to a network endpoint is the highest-risk thing a reviewer or a skeptical forum reader evaluates. The companion's strongest, most honest asset is that it never writes the vault and sends nothing off-device until you set an endpoint. Every artifact in this channel — the PR body, the forum post, the newsletter note, the subreddit copy — leads with read-only-by-construction and the network-use disclosure. This is both the compliance-safest and the most trust-building framing, and they are the same move.

**Land the directory PR before any outreach.** The merged directory entry is the credibility anchor and the thing that auto-feeds the PKM feeds; outreach before it exists is a claim with nothing behind it. Open the PR first, let it merge, and only then announce. This also respects the "participate before you promote" norm: the merge is the artifact that earns the post.

**A directory merge is the primary distribution act; the newsletters are a nudge, not a pitch.** Because Obsidian Stats and PKM Weekly auto-source from the directory and the PKM.social `#obsidian` feed, simply getting merged will likely surface the companion automatically. The deliberate work is therefore a single Mastodon `#obsidian` post on PKM.social plus a short personal email to each author — not a press push. Drop the Obsidian Roundup pitch entirely.

**Treat every external surface as rules-gated and verify before posting.** The plan cannot assume a subreddit's rules, a flair requirement, or whether self-promo is even allowed on a given day — and the strictest PKM venues moderate tool promotion hardest. Each subreddit is checked against its live sidebar/wiki immediately before posting, posted one at a time, and framed as method/workflow where the venue demands it. Reddit is last, and only from an account with genuine prior participation.

**Honest competitor framing, including the unflattering ones.** The differentiation is ownership, compounding, and reviewable writes — not benchmark rank. Where a comparison cuts against us, state it plainly: Hindsight posts a higher LongMemEval number on a more lenient judge axis; Honcho is complementary, not beaten. This audience rewards candor and punishes overclaim, so the honest row is the persuasive one.

## Requirements

**Directory submission (the anchor)**

R1. Open the upstream Obsidian community-plugin pull request against `obsidianmd/obsidian-releases` from the prepared, already-pushed branch `add-hypermnesic-companion`, adding the companion's `community-plugins.json` entry (`id` `hypermnesic-companion`, name `Hypermnesic Companion`, author, description, repo `leonardsellem/hypermnesic-companion`).

R2. Resolve the open blocker before the PR can exist: either open it through the Obsidian web flow at `community.obsidian.md` signed in as the human, or use the prepared compare URL with a GitHub token that carries public-repo pull-request scope — the prior token's missing `CreatePullRequest` permission is the recorded reason the submission stalled.

R3. Before opening the PR, re-confirm the companion README still carries, near the top, the three reviewer-critical statements it already contains: it connects only to a user-supplied self-hosted hypermnesic endpoint; exactly what data leaves the vault (the block around the cursor or the current selection, sent for related-note lookup) and that nothing else does; and that the plugin never writes the vault and ships zero client-side telemetry.

R4. Confirm the release-asset hygiene the bot hard-checks is intact on companion `0.3.0`: the GitHub release tag equals the manifest version with no `v` prefix; the release carries `main.js`, `manifest.json`, and `styles.css` as individual assets; the root `manifest.json` matches; `versions.json` maps `0.3.0` to its `minAppVersion`; and a `LICENSE` file is present in the repo.

R5. Verify the naming-policy constraints stay satisfied: the plugin name contains neither "Obsidian" nor "Plugin", and the `id` does not contain the substring "obsidian" — all three already hold for `Hypermnesic Companion` / `hypermnesic-companion` and must not regress.

R6. Record the opened PR URL and the bot's acceptance/feedback as the verification artifact; treat the channel's anchor as unproven until the entry is merged into `community-plugins.json`.

**Forum and Discord announce (post-merge)**

R7. After the directory entry merges, post the companion to the Obsidian Forum "Share & showcase" board — the community's sanctioned announce surface — leading with read-only-by-design and the network-use disclosure, and linking the engine quick start and the companion repo.

R8. If the human holds the Obsidian Discord developer role, post a short companion note to the appropriate updates channel; if not, skip it rather than post from a non-eligible account.

R9. Carry the existing approved r/ObsidianMD framing into the forum and Discord copy for consistency, adapted to each surface's norms; do not invent new claims beyond the approved set.

**PKM feeds and newsletters (the nudge)**

R10. Post a single `#obsidian` announcement on the PKM.social Mastodon instance — the de-facto feed both surviving newsletters watch — once the directory entry is merged, framed around the vault-as-shared-memory line.

R11. Send a short, personal email to Ganessh Kumar R P (Obsidian Stats / Obsidian Plugin Stats) and to Ed Nico (PKM Weekly), each noting the merged directory entry and the read-only companion; do not build any pitch around the dormant Obsidian Roundup.

R12. Rely on the directory merge plus the PKM.social post as the primary mechanism for newsletter surfacing, treating the personal emails as a courtesy nudge rather than the channel's load-bearing step.

**Subreddits (last, rules-gated)**

R13. Post to PKM-relevant subreddits one at a time and only after the directory PR is merged, leading with the read-only / files-are-truth framing and reusing the approved r/ObsidianMD draft as the baseline.

R14. Immediately before posting to any subreddit, open its live sidebar, rules, and wiki signed in, and confirm three things: whether self-promotion is permitted at all or only on a designated day; whether a self-promotion or plugin/showcase flair is required; and whether any comment-first, account-age, or karma gate applies.

R15. For the stricter venues — r/Zettelkasten in particular — frame the post as method and workflow (how a shared file-first memory complements a Zettelkasten) rather than a product drop, and skip the venue entirely rather than post against its rules.

R16. Post to subreddits only from an account with genuine prior participation in that community, honoring the "participate more than you promote" norm; if no such account exists for a venue, defer that venue.

**Claims discipline (applies to every artifact in this channel)**

R17. Every artifact in this channel honors the published claims rules: no hosted SaaS or managed cloud; no claim of an official MCP Registry listing (not published); no "merged into awesome-mcp-servers" until PR #8056's state is verified; no Glama "A" grade until confirmed on the live listing; never imply the companion can write a vault; never imply dense retrieval is always on (lexical-only is a supported, visible state); and no benchmark number outside the published comparability envelope.

R18. No artifact includes a private hostname, token, vault content, or local absolute path; endpoint references use placeholders and the public engine/companion repo URLs only.

## Success Criteria

- The upstream `obsidianmd/obsidian-releases` PR is open, its URL recorded, and the bot's response captured.
- The companion is merged into `community-plugins.json` and is installable from Obsidian's in-app Community plugins browser.
- A "Share & showcase" forum post is live, leading with read-only-by-design, with its URL recorded.
- A PKM.social `#obsidian` post is live and the two newsletter emails are sent.
- At least one rules-verified subreddit post is live, with the per-venue rule check recorded for each venue posted to.
- No artifact in the channel asserts a claim outside the approved set, and a later read of the live PKM feeds shows the companion surfaced (directly or via auto-sourcing).

## Scope Boundaries

**Deferred for later**

- The official MCP Registry publication and the awesome-mcp-servers merge are tracked as the separate directory-submission effort; this channel does not block on them.
- The Glama "A" Tool-Definition-Quality grade is verified elsewhere; do not assert the letter grade in this channel until it is confirmed on the live listing.
- Mobile companion recall is a known companion gap and is not part of this outreach.
- Engine-side announce channels (Show HN, r/selfhosted, r/LocalLLaMA, the MCP Discord) are the engine launch sequence, separate from this PKM-audience push.
- The GitHub Discussions welcome/roadmap posts are a separate community-surface effort and are not gated by this channel.

**Outside this product identity**

- No paid placement, sponsorship, or press push; this channel is participation and a directory merge, not advertising.
- No multi-tenant or hosted offering implied to court the PKM audience; hypermnesic stays self-hosted and file-first.
- No claim that the companion can edit or create vault notes; read-only is the identity, not a temporary limitation.
- No benchmark-rank positioning against PKM tools; the competition is ownership, compounding, and reviewable writes.

## Dependencies / Assumptions

- A GitHub identity that can open a PR against `obsidianmd/obsidian-releases` — the human via the web flow, or a token with public-repo pull-request scope.
- The companion `0.3.0` release and its branch remain in the verified state recorded in the directory-submission prep (assets present, `versions.json` populated, naming compliant).
- The companion README's network-use, no-telemetry, and read-only disclosures remain present and accurate at submission time.
- Operator approval before any externally visible action — opening the PR, posting to the forum or Discord, posting on Mastodon, emailing the newsletter authors, or posting to any subreddit.
- A Reddit account (and, for Discord, the developer role) with standing in each target community; absent that standing, the venue is deferred rather than forced.
- Assumed: a directory merge auto-surfaces the companion in Obsidian Stats' weekly update via its directory + PKM.social sourcing, making the newsletter emails a nudge rather than the primary path.

## Outstanding Questions

**Resolve before planning**

- Which path opens the upstream PR — the Obsidian web flow as the human, or a re-scoped GitHub token — and is that identity available now?
- Does the human hold the Obsidian Discord developer role, which decides whether R8 is in or out?
- Which subreddits are genuinely in scope given the prior-participation bar (r/ObsidianMD, r/PKMS, r/Zettelkasten), and does an eligible account exist for each?

**Defer to planning**

- The exact merge-review turnaround for the Obsidian bot plus manual queue, which sets the timing of every downstream post.
- Whether to wait for an organic newsletter mention before sending the personal emails, or send them on merge.
- The order and spacing of the subreddit posts under the 90/10 self-promotion norm.
- Whether to capture a short before/after of the companion surfacing in a PKM feed as the channel's proof artifact.

## Sources / Research

Internal:

- `docs/launch/directory-submission-prep.md` — the prepared Obsidian branch, the `community-plugins.json` and `manifest.json` drafts, the compare URL, and the recorded `CreatePullRequest` token blocker.
- `docs/launch/launch-narrative-drafts.md` — the approved r/ObsidianMD draft and the claims-allowed / claims-avoid lists.
- `docs/launch/promo-grounding-brief.md` — positioning confirmations and the corrected claims state (PyPI live; registry not published; awesome-mcp-servers PR open; Glama grade needs live verification).
- `docs/why-hypermnesic.md` — the ownership/compounding wedge and the vs-plain-Obsidian and complementary-to-Honcho framing.
- `docs/launch/launch-sequencing.md` — the engine launch channel order this PKM push runs alongside.
- `hypermnesic-companion/README.md` (separate GPL-3.0 repo) — the read-only-by-construction, network-use, and no-telemetry disclosures the reviewer checkpoint depends on.

External (this initiative's research):

- Obsidian developer policies and plugin guidelines (docs.obsidian.md) — mandatory network-use README disclosure, the client-telemetry prohibition, the no-"Obsidian"/no-"Plugin" naming rules, and the release-asset hygiene the bot hard-checks.
- obsidian.md/blog — the move to a web submission flow plus an automated per-release security/quality scan.
- Obsidian Stats / Obsidian Plugin Stats (Ganessh Kumar R P) and PKM Weekly (Ed Nico) — the live weekly feeds that auto-source from the community directory and the PKM.social `#obsidian` hashtag; the Obsidian Roundup is dormant.
- Obsidian Community Code of Conduct and Reddit's 90/10 self-promotion norm — the "participate more than you promote" rule and the per-subreddit rule-check requirement, with r/Zettelkasten flagged as stricter on tool promotion.
