---
date: 2026-06-25
origin: docs/brainstorms/2026-06-25-founder-essay-and-crossposts-requirements.md
type: content
---

# Founder Essay and Cross-Posts — Implementation Plan

## Overview

Publish a first-person founder essay — the `gbrain`-drifted → git-first-rebuild origin
story — canonical-first on a domain the author controls, then syndicate to dev.to /
Hashnode / (optionally) Medium with `rel=canonical` pointing home, and seed lobste.rs plus
a second, non-Show-HN Hacker News story. `docs/why-hypermnesic.md` rides along as the
evergreen SEO spine. The win condition is ownership + compounding + reviewable writes — not
benchmark rank — published inside the approved claim set with a hard claims/leak gate before
anything goes live. This is a content/distribution initiative: the units below are concrete
write/build/submit steps, each ending in a captured evidence artifact.

## Goals / Non-goals

**Goals**

- A single canonical essay live on an author-controlled URL, first-person, telling the
  origin story with the three load-bearing ideas (files-are-truth + disposable index;
  reviewable git-commit writes; the Capture → Curate → Recall → Compound flywheel across
  every AI on laptop and phone) and honest limitations intact (R1–R5).
- Every syndicated copy resolves `rel=canonical` to the origin, with the origin published
  and crawled first (R12–R14).
- A second HN presence as a *normal story* (not Show HN, no delete-and-repost), and a
  lobste.rs submission of the canonical essay via a sanctioned invite path with valid tags
  (R15–R16, R19).
- `docs/why-hypermnesic.md` reachable at a public canonical URL and linked from the essay as
  the comparison reference (R6, R11).
- At least one verified-mechanism newsletter tip (Changelog News and/or Console.dev),
  pointing at the canonical essay (R17–R18).
- A claims/leak pass proving zero forbidden claims (R8), zero unverified gated claims (R9),
  zero leaked private values (R10).

**Non-goals** (deferred or out of identity — from the requirements' Scope Boundaries)

- A narrated origin video; backdating onto Medium beyond one canonical-respecting cross-post;
  DZone / Hacker Noon and other secondary targets; paid newsletter placement (TLDR
  sponsorship); a measured before/after SEO ranking report; translations.
- Any claim of hosted SaaS / managed cloud / multi-tenant service; that the Obsidian
  companion writes a vault; that dense retrieval is always on; competing on benchmark rank or
  quoting numbers outside the comparability envelope; turning the `gbrain` beat into a
  competitor row; re-dropping the Show HN, soliciting votes, or cold-DMing for invites.

## Implementation Units

### U1 — Resolve the three planning blockers (canonical home, gated claims, lobste.rs invite)

**Goal.** Close the requirements' "Resolve before planning" questions so downstream copy can
state, omit, or downgrade each item with certainty. Nothing else starts until these resolve.

**Steps.**
1. **Canonical home decision.** Confirm with the operator which author-controlled surface
   hosts the essay and produces the canonical URL: a `/blog` path on the hypermnesic site, or
   a `sellem.me`-class personal domain. Record the exact origin URL string (e.g.
   `https://<author-domain>/blog/why-i-built-hypermnesic` — a placeholder until the operator
   fixes it) — every cross-post and seed depends on it.
2. **Gated-claim verification (R9).** Resolve each, capturing the evidence:
   - *Official MCP Registry* — run `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.leonardsellem/hypermnesic"`; per
     `directory-submission-prep.md` it is **not yet published** (blocked on operator
     `mcp-publisher login github`). If still empty → the essay MUST NOT mention a registry
     listing.
   - *awesome-mcp-servers* — check `gh pr view 8056 --repo punkpeye/awesome-mcp-servers --json state,url`.
     Repo evidence (`directory-submission-prep.md`) shows PR #8056 **open**. If open → say
     "submitted (PR open)", NOT "merged".
   - *Glama "A" TDQS grade* — open the live listing `https://glama.ai/mcp/servers/ak6x81u3rr`
     and read the actual Tool-Definition-Quality grade. If the letter is not visibly "A" →
     describe the *effort* ("full self-describing tool descriptions, 100% parameter-description
     coverage"), never quote a letter grade.
3. **lobste.rs invite (R16, R19).** Confirm the author holds, or can obtain via the sanctioned
   path (an existing member who recognizes the author's work — never cold-DMing strangers), a
   lobste.rs invite. If neither → **scope the lobste.rs leg out** (U10) rather than force it.

**Files / Surfaces.** `docs/launch/promo-grounding-brief.md` (gated-claim notes §1);
`docs/launch/directory-submission-prep.md` (PR #8056, registry state); the live Glama listing
`ak6x81u3rr`; operator confirmation for the canonical domain + invite.

**Validation.** A short decisions record (canonical URL string; per-claim verdict
use/omit/downgrade with the command output or screenshot URL; lobste.rs in/out) captured as a
comment on the tracking Linear issue. This is the gate other units cite.

**Dependencies.** None — this is the entry point. Blocks U2–U10.

### U2 — Stand up the canonical publishing surface

**Goal.** Make the author-controlled origin URL real, indexable, and `rel=canonical`-capable,
so it can be the home every copy points to (R1).

**Steps.**
1. On the surface chosen in U1, create the post route (the `/blog/<slug>` page or the
   personal-domain article path). Confirm it serves a real HTML `<head>` you can populate with
   a self-referential `<link rel="canonical" href="<origin-URL>">` and standard
   `<title>` / `<meta name="description">` / Open Graph tags.
2. Verify the surface is crawlable: reachable without auth, returns HTTP 200, and is not
   blocked by `robots.txt` / `noindex`.
3. Reserve the final slug and lock the origin URL string from U1 so U3's body and all
   cross-posts share one canonical target.

**Files / Surfaces.** The author-controlled site/CMS (hypermnesic site `/blog` or
`sellem.me`-class domain) — **external to this repo**; no repo file is created by this unit.

**Validation.** `curl -sSL <origin-URL> -o /dev/null -w '%{http_code}\n'` returns `200`;
`curl -sSL <origin-URL> | grep -i 'rel="canonical"'` shows the self-referential canonical;
capture both outputs. Screenshot of the rendered draft route (unpublished/private is fine at
this stage).

**Dependencies.** U1 (canonical home decided). Blocks U3, U4.

### U3 — Draft the canonical essay (the load-bearing artifact)

**Goal.** Write the first-person essay that carries the whole initiative: the origin story and
the three load-bearing ideas, inside the approved claim set (R2–R7).

**Steps.**
1. **Outline** (length resolved here, a "Deferred to planning" item): a long-form post,
   roughly 1,200–1,800 words, in this arc:
   - *Cold open* — the lived failure: a database-backed personal brain ("gbrain") that drifted
     from its files until it could no longer be trusted or moved (R2). First person, framed as
     motivation, **never** as a competitor swipe.
   - *The turn* — the git-first rebuild: files become the source of truth; the search index is
     a disposable, rebuildable projection of the git tree, so a reindex can never lose a
     committed write (R3a).
   - *What that buys you* — every memory write is a reviewable git commit, visible in history
     and revertible (R3b); then the compounding flywheel: Capture → Curate → Recall → Compound,
     across every AI (ChatGPT, Claude, Claude Code / Codex, your own agents) on laptop **and**
     phone, through one shared OAuth-secured MCP endpoint (R3c).
   - *Under the hood, briefly* (R4, MAY) — name mechanics only where they serve the story and
     only as the repo proves them: the guarded `commit_note` write (diff-or-die frontmatter
     gate + blocklist write guard + single-writer locks + append-only audit log); hybrid FTS5 +
     sqlite-vec retrieval fused via RRF with graceful **lexical-only** degradation; read-time
     convergence; the one OAuth 2.1 `/mcp` endpoint over Tailscale Funnel.
   - *Honest limits* (R5) — self-hosted, **not** a hosted SaaS / managed cloud; dense retrieval
     can degrade to a supported, **visible** lexical-only state; the Obsidian companion is
     **read-only** by design.
   - *Where this sits* — a single link to the public `docs/why-hypermnesic.md` URL (U7) as the
     comparison reference, instead of re-litigating each competitor inline (R6).
   - *Close + soft CTA* — `uv tool install hypermnesic` (PyPI is live, shipped truth) and the
     repo link. No upvote/boost solicitation (R20).
2. **Embed one proof asset** (R6) opening or near the top. Resolve the "which asset" question:
   prefer `media/engine/hero-receipt-loop.gif` (the git-native receipt loop). **Note — there is
   no `flywheel.jpg` in the repo** (the requirements/SEED name one; on disk the real assets are
   `hero-receipt-loop.gif`, `index-recovery.gif`, `claude-code-client.gif`,
   `benchmark-longmemeval.svg`, and `connector-montage/one-endpoint-many-clients.{png,svg}`).
   Use the receipt-loop GIF as the hero, with `connector-montage/one-endpoint-many-clients.svg`
   as the "one endpoint, many clients" visual for the flywheel section if a second image helps.
   Host the chosen asset on the canonical surface or hot-link the raw GitHub URL.
3. **Benchmarks, only as a supporting trust signal** (R11) — at most one line, labelling the
   judge axis: on the matched GPT-4o-judge axis hypermnesic is on par with Mastra (84.2), +12
   over Zep, +23 over the no-memory floor, with 88.6% overall / 90.2% task-averaged under a
   GPT-4.1 reader; link `harness/BENCHMARKS.md`. If Hindsight is mentioned at all, state plainly
   its higher number sits on a *more lenient* judge axis. No GPT-4.1-judged ~95% comparisons.
4. **Self-review against the claim set** before handing to U9: every sentence maps to an
   approved claim in `launch-narrative-drafts.md` / `promo-grounding-brief.md`; no gated claim
   (U1) leaks; no forbidden claim; placeholders only for any host.

**Files / Surfaces.** Draft authored in the canonical CMS (external). Optionally mirror the
Markdown source into the repo for review under `docs/launch/founder-essay.md` (process artifact,
not the published copy). Embeds reference `media/engine/hero-receipt-loop.gif` and
`media/engine/connector-montage/one-endpoint-many-clients.svg`.

**Validation.** The full draft text (operator-reviewable) with a claim-mapping note; a
rendered preview screenshot of the canonical draft showing the embedded asset.

**Dependencies.** U1 (gated-claim verdicts), U2 (canonical surface + URL), U7 (the
`why-hypermnesic` public URL to link). Blocks U5, U6, U8, U9.

### U4 — Publish the canonical essay and confirm indexing

**Goal.** Publish the origin first and let it be discovered before any syndication (R12) — the
core SEO sequencing rule.

**Steps.**
1. With operator approval (required before any external post per the launch docs' posting
   checklist), publish the essay at the locked origin URL.
2. Confirm the self-referential canonical and metadata are present in the *published* page
   source.
3. Request indexing of the origin (submit the URL via the site's Search Console property if
   available) and **start the crawl-wait** — a few days is the common practice (resolves the
   "crawl-wait interval" planning question). Do not syndicate until the origin is discoverable.

**Files / Surfaces.** The canonical surface (external); Search Console for the author domain if
available.

**Validation.** Capture: the live origin URL (HTTP 200); `curl -sSL <origin-URL> | grep -i canonical`
showing the self-canonical; a `site:<origin-domain> <slug>` search result OR a Search Console
"URL is on Google / Crawled" status screenshot once indexed. Record the publish timestamp to
anchor the crawl-wait window.

**Dependencies.** U3 (essay drafted + claim-passed), U9 (claims/leak gate green — see
sequencing; the gate runs on the final copy before this publish). Blocks U5, U6 (syndication
holds until the crawl-wait elapses).

### U5 — Syndicate to dev.to and Hashnode (canonical → origin)

**Goal.** Post the essay on high-DA dev platforms with `rel=canonical` consolidating all signal
onto the origin (R13–R14), only after the origin is crawled (U4).

**Steps.**
1. **dev.to.** New post → set the canonical to the origin URL. In the rich+markdown editor:
   the settings gear next to "Save draft" → **Canonical URL** field. In the basic-markdown
   editor: add `canonical_url: <origin-URL>` to the post front matter. Paste the essay body,
   keep the hero asset, publish.
2. **Hashnode.** Create the post and set **"Original article URL" = the origin URL during the
   create flow** (Hashnode writes `rel=canonical` for you; it must be set before publish, not
   retroactively). Paste body, publish.
3. Each copy links the canonical origin URL (not the other syndicated copy) for its "read the
   original / discuss" affordance, and links the public `why-hypermnesic` URL and
   `harness/BENCHMARKS.md` exactly as the canonical does.

**Files / Surfaces.** dev.to and Hashnode accounts (external). Body reused verbatim from U3.

**Validation.** For each platform capture: the published URL **and** `curl -sSL <copy-URL> | grep -i 'rel="canonical"'`
output showing the canonical resolving to the origin (page-source proof, per the success
criteria). Screenshot of each live post.

**Dependencies.** U4 published + crawl-wait elapsed. Independent of U6; both can run in parallel
once U4 clears.

### U6 — Optional Medium cross-post (held or included per decision)

**Goal.** If Medium is in the first wave (resolves the "Medium in wave one?" planning question),
cross-post with a correct canonical; otherwise hold it for later without blocking (R13–R14).

**Steps.**
1. **Decision.** Default: **hold Medium** for a later wave to keep wave one tight (dev.to +
   Hashnode), unless the operator opts it in. Record the decision.
2. **If included:** use Medium's **"Import a story"** (paste the origin URL) so Medium
   auto-adds `rel=canonical` to the origin and backdates; OR, for a hand-pasted piece, tick
   **"This story was originally published elsewhere"** and enter the origin URL. Never use a
   plain "Write a story" without setting the canonical.

**Files / Surfaces.** Medium account (external), only if included.

**Validation.** If posted: the Medium URL + page-source `rel=canonical` → origin (same proof as
U5). If held: a one-line recorded decision "Medium deferred to later wave."

**Dependencies.** U4. Optional; never blocks U7–U10.

### U7 — Make `docs/why-hypermnesic.md` reachable at a public canonical URL (the SEO spine)

**Goal.** Give the evergreen comparison page a stable public URL the essay links to and that can
rank as the durable reference (R6, R11). **Gap found:** today `docs/why-hypermnesic.md` is only
in the GitHub repo tree (linked from `README.md` and `docs/README.md`); it has no
author-domain canonical URL.

**Steps.**
1. Choose the public URL form for the comparison page and record it:
   - *Minimum:* the existing raw GitHub blob URL
     `https://github.com/leonardsellem/hypermnesic/blob/main/docs/why-hypermnesic.md` (works
     today, zero new surface) — the essay links this.
   - *Preferred (if the canonical site exists):* republish/serve the same content at a
     site path (e.g. `https://<author-domain>/why-hypermnesic`) with its **own** self-canonical,
     so the comparison page accrues ranking signal on the author domain. If republished on the
     site, set its canonical to the site copy and keep the repo file as the source of record
     (update both in lockstep to avoid drift).
2. Verify the chosen URL resolves and link it from the essay (U3) and from each syndicated copy
   (U5/U6).

**Files / Surfaces.** `docs/why-hypermnesic.md` (existing, repo source of record); optionally
the canonical site path. If republished on the site, note the dual-surface in
`docs/README.md`'s positioning pin so the two do not drift.

**Validation.** The resolved public URL (HTTP 200) recorded; confirmation it is linked from the
canonical essay and from each cross-post.

**Dependencies.** U1/U2 (only if the preferred site path is used). Feeds U3, U5, U6.

### U8 — Seed the discussion channels: lobste.rs + a normal (non-Show-HN) Hacker News story

**Goal.** Earn a second, legitimate bite at HN and lobste.rs by submitting the *essay* (a
distinct artifact), each pointing at the canonical origin, respecting both communities' rules
(R15–R17, R19–R20).

**Steps.**
1. **Hacker News (R15, R17, R20).** Submit as a **normal story**: title + the **canonical
   origin URL** (not a dev.to/Medium copy). Title is the essay's, plain — **NOT** prefixed
   "Show HN:". This is a different artifact from the original Show HN, so it sidesteps the
   delete-and-repost prohibition and the Show-HN "major overhaul" bar; do **not** delete/repost
   the old Show HN, and do **not** solicit upvotes/comments. Suggested title (operator-tunable):
   `Why I rebuilt my personal "second brain" to be git-first`.
2. **lobste.rs (R16, R19, R20)** — only if U1 confirmed an invite, else skip (U10 records the
   drop):
   - Submit the **canonical essay URL** (the architecture/origin writeup, not a "we launched"
     page).
   - Tags from the confirmed-existing set: `ai`, `python`, `databases`, `programming`,
     `practices` (use `show` ONLY if ever submitting the project itself, not this essay; `ml`
     does **not** exist as a tag — do not use it).
   - **Etiquette gate:** submit only after the author has participated substantively on others'
     stories first (self-promo a minority of activity); never as a brand-new account's first and
     only post. No vote/comment solicitation.
3. Both submissions get the same operator-approval gate as every external post.

**Files / Surfaces.** Hacker News and lobste.rs accounts (external). Both link the canonical
origin URL from U4.

**Validation.** Capture the HN item URL (and confirm the title carries **no** "Show HN:" prefix
and the link is the origin URL); the lobste.rs story URL with its tags (or a recorded "lobste.rs
dropped — no invite" note). First-reply timestamps for the launch-week response loop.

**Dependencies.** U4 (origin live + crawled), U1 (lobste.rs invite verdict; gated-claim
verdicts). Aligns with `launch-sequencing.md`'s evidence-to-record loop.

### U9 — Claims, gated-claims, and leak gate across the essay + every cross-post

**Goal.** Prove zero forbidden claims (R8), zero unverified gated claims (R9), and zero leaked
private values (R10) before anything is published — the hard go/no-go gate (R7–R11).

**Steps.**
1. **Forbidden-claims scan (R8).** Read the final essay and each cross-post against
   `launch-narrative-drafts.md` "Claims to avoid" + `promo-grounding-brief.md` §4: no hosted
   SaaS / managed cloud; no "companion writes the vault"; no "dense retrieval always on"; no
   benchmark number outside the comparability envelope (no GPT-4.1-judged ~95% comparisons).
2. **Gated-claims enforcement (R9).** Confirm the U1 verdicts are honoured verbatim: MCP
   Registry listing absent unless verified-published; awesome-mcp-servers stated as
   "submitted (PR open)" unless verified-merged; Glama "A" letter quoted only if seen on the live
   listing, else effort-only phrasing.
3. **Leak/secret scan (R10).** Grep the copy for private hostnames, tokens, vault contents, and
   local absolute paths; host **placeholders only** (`<your-host>.ts.net`, the `100.64.0.0/10`
   CGNAT range), consistent with `scripts/preflight_public_scan.py` discipline. The essay copy
   lives off-repo, so this is a manual read plus a grep over any in-repo mirror.
4. **Benchmark-axis check (R11).** Any benchmark mention labels its judge axis and links
   `harness/BENCHMARKS.md`; any Hindsight mention states the lenient-axis caveat plainly.
5. **Correct the known stale guard (Dependencies/Assumptions).** When `launch-narrative-drafts.md`
   is next touched, update its obsolete "Do not claim PyPI install until LS-1684 is decided" line
   — LS-1684 is Done and PyPI is live shipped truth. Bundle this one-line doc fix here.

**Files / Surfaces.** `docs/launch/launch-narrative-drafts.md` (claim lists + the stale-guard
fix), `docs/launch/promo-grounding-brief.md` (gated-claim notes), `harness/BENCHMARKS.md`
(envelope). The essay + every cross-post draft.

**Validation.** A checklist artifact recording PASS for each of (forbidden-claims,
gated-claims, leak-scan, benchmark-axis), with the specific phrasings checked, captured on the
Linear issue. This gate must be green **before** U4 publishes and before each U5/U6/U8
submission.

**Dependencies.** U1 (verdicts), U3 (essay), and each cross-post draft. Blocks U4, U5, U6, U8
go-live.

### U10 — Newsletter tips via verified self-serve mechanisms (essay, not landing page)

**Goal.** Land at least one verified-mechanism newsletter tip pointing at the canonical essay,
using only real submit paths and submitting the **essay** (a story/architecture writeup), not the
landing page (R17–R18).

**Steps.**
1. **Changelog News** — the best direct path. Submit at `https://changelog.com/news/submit`
   (free sign-in required). Fields: **URL** = the canonical origin URL; **Title** = the essay
   title; **"What's interesting about it?"** = a short Markdown note (the gbrain-drift →
   git-first-rebuild angle; files-are-truth; reviewable-commit writes). Submitting your own work
   is explicitly encouraged; they reject how-tos/tutorials and pure product pages — so the essay
   qualifies, the landing page would not.
2. **Console.dev** — email **hello@console.dev** with the tool details and the canonical essay
   link ("we'll happily take a look"); fits the power-user devtool profile (self-serve signup,
   CLI/API, good docs, actively maintained). Beta/pre-1.0 eligible.
3. **Do NOT treat as free tip channels (R18):** **TLDR** is paid-only (no public editorial-tip
   form — out of free scope here); **Hacker Newsletter** is curated *from* HN with no submission
   form — the lever there is the U8 HN story, not a tip. State this explicitly so neither is
   mistakenly "submitted".
4. Every tip links the **canonical origin URL** (R17), never a syndicated copy.

**Files / Surfaces.** Changelog News submit form and `hello@console.dev` (external). Source copy
reused from U3.

**Validation.** Capture: the Changelog News submission confirmation (screenshot/record) and/or
the Console.dev outbound email, each showing the canonical URL. A recorded note that TLDR and
Hacker Newsletter were intentionally **not** used as tip channels.

**Dependencies.** U4 (canonical live), U9 (claims gate green). Independent of U5/U6/U8.

## Sequencing / Milestones

**Milestone A — Unblock & build (gates everything).** U1 (resolve canonical home + gated claims
+ lobste.rs invite) → U2 (stand up canonical surface) → U7 (fix the comparison-page public URL)
→ U3 (draft essay). U7 can run alongside U3 since U3 must link it.

**Milestone B — Gate & publish the origin.** U9 (claims/leak gate on the final essay copy) →
U4 (publish canonical + request indexing + **start the crawl-wait**). The origin MUST be live
and discoverable before any syndication (R12) — this is the hard sequencing rule.

**Milestone C — Syndicate (after crawl-wait).** In parallel once U4's crawl-wait elapses and
U9 is green for each copy: U5 (dev.to + Hashnode), U6 (optional Medium). Each cross-post is
claim-checked (U9) before it posts.

**Milestone D — Seed discussion & newsletters.** U8 (HN normal story + lobste.rs if invited)
and U10 (Changelog News / Console.dev), both pointing at the canonical origin, both after the
origin is live and gated. Fold each posted URL + first-reply timestamp into the
`launch-sequencing.md` evidence loop and the LS-1688 response SLO.

Operator approval is required before every external go-live step (U4, U5, U6, U8, U10),
consistent with the launch docs' posting checklist.

## Risks & Mitigations

- **Syndicating before the origin is indexed → a high-DA copy outranks the origin and the
  ranking signal accrues to the platform.** Mitigation: the U4→U5/U6 ordering is a hard gate;
  do not post any copy until the crawl-wait elapses and `site:` / Search Console confirms the
  origin is discovered (R12).
- **A gated claim leaks (registry "listed", awesome "merged", Glama "A") before it is true →
  overclaim that dies on HN/lobste.rs.** Mitigation: U1 verdicts are enforced verbatim by the
  U9 gate; default to omit/downgrade. (`directory-submission-prep.md` currently shows PR #8056
  open and the registry unpublished.)
- **lobste.rs self-promo / invite missteps → "this isn't your blog's comment section" pushback
  or a frowned-on cold invite ask.** Mitigation: submit only with a sanctioned invite, only the
  architecture/origin essay, only after substantive participation, with valid tags, no vote
  solicitation (R16, R19–R20). If no invite → drop the leg (U1/U10), don't force it.
- **Accidentally re-dropping the Show HN or prefixing "Show HN:" → trips HN's
  delete-and-repost / major-overhaul rules.** Mitigation: U8 submits a **normal story** with the
  origin URL and a plain title; the old Show HN is left untouched (R15).
- **Referencing a non-existent asset (`flywheel.jpg`).** Mitigation: U3 uses the real on-disk
  assets (`hero-receipt-loop.gif`, `connector-montage/one-endpoint-many-clients.svg`, etc.); the
  plan flags that no `flywheel.jpg` exists.
- **Comparison page has no public canonical URL today → essay's evergreen link is just a repo
  blob and signal scatters.** Mitigation: U7 either links the raw GitHub blob (works now) or, if
  the site exists, serves a self-canonical site copy and pins the dual-surface in
  `docs/README.md` to prevent drift.
- **Leaking a private host/path/token in off-repo copy that the repo's preflight scanner can't
  see.** Mitigation: U9's manual leak read + grep over any in-repo mirror; placeholders only
  (R10).
- **Mismatched canonicals across copies (a syndicated copy points at another copy, not the
  origin).** Mitigation: U5/U6 validation greps each copy's page source for `rel=canonical` →
  origin; U8/U10 link the origin, never a syndicate (R17).

## Validation / Definition of Done

The initiative is done only when **all** of the following are captured as evidence (URLs,
screenshots, page-source greps, submission confirmations) on the tracking Linear issue:

- [ ] The essay is live on the author-controlled canonical URL, first-person, telling the
  gbrain-drift → git-first-rebuild story with the three load-bearing ideas (R2, R3) and honest
  limitations intact (R5). *(U3, U4)*
- [ ] Each syndicated copy resolves `rel=canonical` to the origin (verified in page source), and
  the origin was published and crawled **first** (R12–R14). *(U4, U5, U6)*
- [ ] A second HN presence exists as a **normal story**, distinct from the original Show HN, with
  no delete-and-repost and no vote solicitation (R15, R20). *(U8)*
- [ ] If invited: the lobste.rs submission is the canonical essay URL with valid tags, posted by
  an account with prior substantive participation (R16, R19); else a recorded decision to drop
  the leg. *(U8)*
- [ ] A claims pass confirms zero forbidden claims (R8), zero unverified gated claims (R9), and no
  leaked private values (R10) across the essay and all cross-posts; any benchmark mention labels
  its judge axis and links `harness/BENCHMARKS.md` (R11). *(U9)*
- [ ] `docs/why-hypermnesic.md` is reachable at a recorded public URL and linked from the essay
  and each cross-post (R6). *(U7)*
- [ ] At least one verified-mechanism newsletter tip (Changelog News and/or Console.dev) is sent,
  pointing at the canonical essay; TLDR and Hacker Newsletter explicitly not used as free tip
  channels (R17–R18). *(U10)*
- [ ] The obsolete "do not claim PyPI" line in `launch-narrative-drafts.md` is corrected when that
  doc is touched. *(U9)*

## References

**Internal**

- `docs/brainstorms/2026-06-25-founder-essay-and-crossposts-requirements.md` — the requirements
  (R1–R20) this plan implements.
- `docs/why-hypermnesic.md` — the evergreen comparison page / SEO spine and the essay's "where
  this sits" reference (R6, R11).
- `docs/launch/launch-narrative-drafts.md` — approved claims-allowed / claims-to-avoid lists and
  per-channel drafts; holds the now-obsolete PyPI avoid-line to correct.
- `docs/launch/promo-grounding-brief.md` — repo-verified positioning, claims summary, and the
  gated-claim verification notes (MCP Registry, awesome-mcp-servers PR #8056, Glama grade).
- `docs/launch/directory-submission-prep.md` — current state behind the gated claims in R9/U1
  (registry unpublished; PR #8056 open; Obsidian branch prepared).
- `docs/launch/launch-sequencing.md` — the existing channel order, evidence-to-record loop, and
  stop/completion conditions this sequencing aligns with.
- `docs/launch/launch-week-response-slo.md` — the response loop for first-contact items on posted
  channels.
- `harness/BENCHMARKS.md` — LongMemEval methodology and the comparability envelope every benchmark
  mention must respect (R11).
- `ARCHITECTURE.md` / `README.md` — the prime invariant and "How it works" that R3–R4 paraphrase.
- `media/engine/` — reusable assets: `hero-receipt-loop.gif`, `index-recovery.gif`,
  `claude-code-client.gif`, `benchmark-longmemeval.svg`,
  `connector-montage/one-endpoint-many-clients.{png,svg}`. **No `flywheel.jpg` exists** despite
  the requirements naming one.

**External (canonical-first SEO and channel rules, June 2026)**

- Canonical-first cross-posting / `rel=canonical` consolidation: dev.to/nfrankel,
  mikebifulco.com, catalins.tech, townhall.hashnode.com, blog.frankel.ch.
- Per-platform canonical mechanics: dev.to help (dev.to/_hariti, dev.to/leewynne — gear →
  Canonical URL field / `canonical_url:` front matter / RSS "mark source as canonical");
  Hashnode "own your canonical" docs ("Original article URL" set during create); help.medium.com
  "Set a canonical link" + "Importing a post" ("Import a story" / "originally published
  elsewhere").
- lobste.rs norms (invite-only via sanctioned path; <25% self-promo; computing-focused; confirmed
  tag list `ai`/`python`/`databases`/`programming`/`practices`/`show`, no `ml`): lobste.rs/about,
  lobste.rs invite threads, aneeshdurg.me lobsters analysis.
- Hacker News rules (no delete-and-repost; Show-HN "major overhaul" bar; no solicited votes — so
  submit the essay as a normal story): news.ycombinator.com showhn.html and newsguidelines.html.
- Newsletter submit mechanisms: changelog.com/news/submit (free, own-work encouraged, no
  how-tos/product pages); console.dev/selection-criteria + hello@console.dev (power-user devtools,
  pre-1.0 eligible); advertise.tldr.tech (paid-only, no editorial tip form);
  hackernewsletter.com (curated from HN, no submission form).
