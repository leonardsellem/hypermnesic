---
title: "Founder essay (why-I-built-it) + canonical-first cross-posts"
estimate: 1
priority: Medium
labels:
  - launch
  - content
  - marketing
  - distribution
  - docs
related_paths:
  - docs/brainstorms/2026-06-25-founder-essay-and-crossposts-requirements.md
  - docs/plans/2026-06-25-002-content-founder-essay-and-crossposts-plan.md
related_linear:
  - LS-1683
  - LS-1684
  - LS-1688
  - LS-1689
  - LS-1690
parent: null
sub_issues:
  - title: "Resolve the three blockers: canonical home, gated claims, lobste.rs invite"
    estimate: 2
    summary: >-
      Close the requirements' "resolve before planning" questions (U1). Lock the
      exact author-controlled canonical URL string; verify the three gated claims
      live and record use/omit/downgrade (MCP Registry currently unpublished;
      awesome-mcp-servers PR #8056 open → "submitted/PR open" not "merged"; Glama
      "A" letter only if seen on live listing ak6x81u3rr, else effort-only
      phrasing); confirm or scope-out the lobste.rs invite. Capture a decisions
      record. Blocks every other sub-issue.
  - title: "Stand up the canonical publishing surface (rel=canonical-capable, crawlable)"
    estimate: 3
    summary: >-
      Make the author-controlled origin URL real (U2): a /blog/<slug> route on the
      hypermnesic site or a sellem.me-class path that serves a real <head> with a
      self-referential <link rel="canonical">, title/description/OG tags, returns
      HTTP 200 without auth, and is not noindex/robots-blocked. Reserve the final
      slug and lock the origin URL string.
  - title: "Make docs/why-hypermnesic.md reachable at a public canonical URL (SEO spine)"
    estimate: 2
    summary: >-
      Give the evergreen comparison page a stable public URL the essay links (U7).
      Minimum: link the raw GitHub blob URL (works today). Preferred (if the site
      exists): serve a self-canonical copy on the author domain and pin the
      dual-surface in docs/README.md so the two do not drift. Gap today: the page
      lives only in the repo tree with no author-domain canonical.
  - title: "Draft the canonical founder essay (the load-bearing artifact)"
    estimate: 5
    summary: >-
      Write the first-person ~1,200–1,800-word essay (U3): gbrain-drift →
      git-first-rebuild origin, the three load-bearing ideas (files-are-truth +
      disposable index; reviewable git-commit writes; Capture→Curate→Recall→Compound
      across every AI on laptop and phone), honest limits (self-hosted not SaaS;
      lexical-only degraded mode is visible/supported; companion is read-only),
      one proof asset (media/engine/hero-receipt-loop.gif — NOT a non-existent
      flywheel.jpg), at most one judge-axis-labelled benchmark line, a link to the
      public why-hypermnesic URL, and a soft CTA (uv tool install hypermnesic). No
      gated/forbidden claim. Self-reviewed against the approved claim set.
  - title: "Claims, gated-claims, and leak gate across essay + every cross-post"
    estimate: 3
    summary: >-
      Hard go/no-go gate (U9): prove zero forbidden claims (R8), zero unverified
      gated claims (R9 verdicts honoured verbatim), zero leaked private
      values/hosts/paths (R10 — placeholders only), and that any benchmark mention
      labels its judge axis and links harness/BENCHMARKS.md (R11). Also correct the
      obsolete "do not claim PyPI" line in launch-narrative-drafts.md (LS-1684 is
      Done; PyPI is live). Must be green before publish and before each syndication.
  - title: "Publish canonical essay, request indexing, start the crawl-wait"
    estimate: 2
    summary: >-
      Publish the origin FIRST with operator approval (U4); confirm the
      self-referential canonical + metadata in the published source; request
      indexing (Search Console if available) and start the crawl-wait (a few days).
      Do not syndicate until the origin is discoverable. Record the publish
      timestamp to anchor the window. Hard SEO sequencing rule.
  - title: "Syndicate to dev.to + Hashnode with rel=canonical → origin"
    estimate: 2
    summary: >-
      After the crawl-wait elapses and the claims gate is green for each copy (U5):
      post on dev.to (gear → Canonical URL field, or canonical_url front matter)
      and Hashnode ("Original article URL" set during create). Each copy links the
      canonical origin (never the other copy) plus the why-hypermnesic URL and
      BENCHMARKS.md. Verify each copy's page source resolves rel=canonical to the
      origin. Optional Medium (U6) held by default unless the operator opts in;
      if included, use "Import a story" / "originally published elsewhere".
  - title: "Seed lobste.rs + a normal (non-Show-HN) Hacker News story"
    estimate: 2
    summary: >-
      Submit the essay as a distinct artifact (U8): HN as a NORMAL story (title +
      canonical origin URL, NO "Show HN:" prefix, no delete-and-repost of the old
      Show HN, no vote solicitation); lobste.rs ONLY if an invite was confirmed in
      U1, with valid tags (ai/python/databases/programming/practices; no ml) and
      after substantive prior participation — else record "lobste.rs dropped". Both
      link the canonical origin; both under operator approval.
  - title: "Newsletter tips via verified self-serve mechanisms (essay, not landing page)"
    estimate: 2
    summary: >-
      Land at least one verified-mechanism tip pointing at the canonical essay
      (U10): Changelog News (changelog.com/news/submit; own-work encouraged;
      rejects how-tos/product pages so the essay qualifies) and/or Console.dev
      (hello@console.dev). Every tip links the canonical origin, never a syndicate.
      Explicitly do NOT treat TLDR (paid-only) or Hacker Newsletter (curated from
      HN, no submit form) as free tip channels.
---

## Context

hypermnesic already has receipts-first launch assets and per-channel announcement
drafts (`docs/launch/launch-narrative-drafts.md`, the `media/engine/` GIFs/SVGs), but
those are point-in-time "we launched" artifacts: they convert on the day and then
decay. What is missing is the one piece that *compounds* — a first-person story that
explains **why this shape exists**, on a URL the author controls. The "AI memory" space
is crowded and skeptical (mem0, Letta, Zep, basic-memory, Supermemory all assert
"persistent memory for your agents"), and the reflex first question is "is the data
actually mine, or is this a vector DB with a wrapper?" An origin story answers that
reflex better than a spec sheet: the author lived the failure mode the product fixes — a
prior database-backed personal brain (`gbrain`) that drifted from its files until it
could no longer be trusted or moved, then the git-first rebuild that makes files the
source of truth and the index a disposable, rebuildable projection.

There is also a distribution tax being paid silently: when a high-domain-authority
platform (dev.to, Medium, Hashnode) hosts a copy of your writing **without** a canonical
link home, that copy outranks the origin and the ranking signal accrues to the platform.
And the announcement channels resist re-drops — Hacker News forbids deleting and
reposting an underperforming Show HN, and lobste.rs polices self-promotion — so there is
no second bite at those audiences unless a genuinely distinct artifact (an origin essay,
not a relaunch page) is published.

This epic implements the canonical plan
(`docs/plans/2026-06-25-002-content-founder-essay-and-crossposts-plan.md`, units
U1–U10) and its requirements (`docs/brainstorms/2026-06-25-founder-essay-and-crossposts-requirements.md`,
R1–R20). It is a **content/distribution** initiative — every sub-issue ends in a captured
evidence artifact — and it spans multiple tracks (surface standup, essay drafting, a
hard claims gate, syndication, discussion seeding, newsletter tips), so it is filed as an
epic (estimate 1) with the nine sub-issues enumerated in frontmatter. It links the
existing LS launch issues as related work, not duplicates: LS-1689 (the per-channel
narrative this essay extends), LS-1683 (directory submissions — the source of the
gated-claim state), LS-1684 (PyPI live — the now-citable install proof), LS-1688 (the
launch-week response SLO the seeded URLs feed), and LS-1690 (channel sequencing).

## Intent

Publish one first-person founder essay **canonical-first** on an author-controlled URL,
then syndicate it to high-DA dev platforms with `rel=canonical` consolidating all signal
onto the origin, and earn a second legitimate bite at Hacker News and lobste.rs — all
inside the approved claim set, behind a hard claims/leak gate. Win on **ownership +
compounding + reviewable writes**, never on benchmark rank. `docs/why-hypermnesic.md`
rides along as the evergreen SEO spine. Honest limitations stay visible because they are
what win the skeptical reader, not what to hide from them.

## Acceptance Criteria

Each criterion is independently verifiable and maps to plan units / requirements.

- [ ] **AC1 — Blockers resolved & recorded.** A decisions record captures: the exact
  canonical origin URL string; a per-claim verdict (use / omit / downgrade) for each of
  the three gated claims with the command output or screenshot URL; and the lobste.rs
  in/out decision. *(U1; R9)*
- [ ] **AC2 — Canonical surface is live and `rel=canonical`-capable.** The chosen origin
  route returns HTTP 200 without auth, is not `noindex`/`robots.txt`-blocked, and serves
  a `<head>` containing a self-referential `<link rel="canonical">` plus
  `title`/`description`/Open Graph tags. *(U2; R1)*
- [ ] **AC3 — Essay drafted inside the claim set.** A complete first-person draft
  (~1,200–1,800 words) exists telling the `gbrain`-drift → git-first-rebuild story with
  the three load-bearing ideas (R2, R3) and honest limitations intact (R5), embedding one
  real proof asset (`media/engine/hero-receipt-loop.gif`), with at most one
  judge-axis-labelled benchmark line linking `harness/BENCHMARKS.md` (R11), and a
  claim-mapping note where each sentence maps to an approved claim. **No** `flywheel.jpg`
  is referenced (it does not exist in the repo). *(U3; R2–R7, R11)*
- [ ] **AC4 — `why-hypermnesic` reachable at a recorded public URL.** The comparison page
  resolves at a recorded public URL (minimum: the raw GitHub blob; preferred: a
  self-canonical author-domain copy with the dual-surface pinned in `docs/README.md`) and
  is linked from the essay. *(U7; R6, R11)*
- [ ] **AC5 — Claims/gated-claims/leak gate PASS.** A checklist artifact records PASS for
  each of forbidden-claims (R8), gated-claims-honoured-verbatim (R9), leak/secret scan
  (R10, placeholders only), and benchmark-axis labelling (R11), across the essay **and**
  every cross-post, with the specific phrasings checked. *(U9; R7–R11)*
- [ ] **AC6 — Origin published first and crawled.** The essay is live at the locked origin
  URL (HTTP 200) with the self-referential canonical present in the **published** source,
  indexing requested, and discovery confirmed (a `site:` hit or a Search Console
  "crawled/indexed" status) **before** any syndication. Publish timestamp recorded. *(U4;
  R12)*
- [ ] **AC7 — Syndicated copies resolve `rel=canonical` → origin.** Each dev.to and
  Hashnode copy is live and its **page source** resolves `rel=canonical` to the origin
  (not to another copy); each links the public `why-hypermnesic` URL and `BENCHMARKS.md`.
  Medium is either correctly canonicalised the same way or a recorded "deferred" decision.
  *(U5, U6; R13, R14, R17)*
- [ ] **AC8 — Second HN presence as a normal story.** An HN item exists whose title
  carries **no** "Show HN:" prefix and whose link is the canonical origin URL; the
  original Show HN is left untouched and no votes/comments were solicited. *(U8; R15,
  R20)*
- [ ] **AC9 — lobste.rs submitted-or-dropped, by the rules.** Either the lobste.rs
  submission is the canonical essay URL with valid tags
  (`ai`/`python`/`databases`/`programming`/`practices`; **no** `ml`), posted by an account
  with prior substantive participation; **or** a recorded "lobste.rs dropped — no invite"
  decision. *(U8; R16, R19, R20)*
- [ ] **AC10 — At least one verified-mechanism newsletter tip sent.** A Changelog News
  submission confirmation and/or a Console.dev outbound email exists, each pointing at the
  **canonical** essay URL; with a recorded note that TLDR and Hacker Newsletter were
  intentionally **not** used as free tip channels. *(U10; R17, R18)*
- [ ] **AC11 — Stale PyPI guard corrected.** The obsolete "do not claim PyPI install until
  LS-1684 is decided" line in `docs/launch/launch-narrative-drafts.md` is corrected
  (LS-1684 is Done; PyPI install is live, shipped truth). *(U9; Dependencies/Assumptions)*

## Validation Plan

How each acceptance criterion is proven, and the evidence artifact captured on this issue.

| AC | How it is proven | Evidence artifact |
|----|------------------|-------------------|
| AC1 | Run `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.leonardsellem/hypermnesic"`; `gh pr view 8056 --repo punkpeye/awesome-mcp-servers --json state,url`; open `https://glama.ai/mcp/servers/ak6x81u3rr`. Record each verdict + the canonical URL string + lobste.rs decision. | A decisions comment with the three command outputs/screenshot URLs, the locked canonical URL, and the lobste.rs in/out call. |
| AC2 | `curl -sSL <origin-URL> -o /dev/null -w '%{http_code}\n'` → `200`; `curl -sSL <origin-URL> \| grep -i 'rel="canonical"'` shows the self-referential canonical. | Both command outputs + a screenshot of the rendered (private/draft) route. |
| AC3 | Operator-reviewable read of the full draft against `launch-narrative-drafts.md` / `promo-grounding-brief.md`; confirm word count, the three ideas, honest limits, the `hero-receipt-loop.gif` embed, the single judge-axis-labelled benchmark line. | The draft text + a claim-mapping note + a rendered preview screenshot showing the embedded asset. |
| AC4 | `curl -sSL <why-url> -o /dev/null -w '%{http_code}\n'` → `200`; confirm the essay links it. | The resolved public URL recorded + confirmation of the in-essay link (and the `docs/README.md` dual-surface pin if republished). |
| AC5 | Forbidden-claims scan against the "claims to avoid" list; gated-claims cross-checked against the AC1 verdicts verbatim; `grep` for hostnames/tokens/absolute paths over any in-repo mirror + manual read of off-repo copy; benchmark-axis check. | A PASS/PASS/PASS/PASS checklist artifact naming the specific phrasings checked, for the essay + each cross-post. |
| AC6 | `curl -sSL <origin-URL> -o /dev/null -w '%{http_code}\n'` → `200`; `curl -sSL <origin-URL> \| grep -i canonical`; a `site:<origin-domain> <slug>` result OR a Search Console "URL is on Google / Crawled" screenshot. | The live origin URL, the canonical grep output, the discovery proof, and the recorded publish timestamp. |
| AC7 | For each platform: `curl -sSL <copy-URL> \| grep -i 'rel="canonical"'` shows the canonical resolving to the origin. | Each published copy URL + its canonical grep output + a screenshot; or the recorded Medium "deferred" decision. |
| AC8 | Open the submitted HN item; confirm the title has no "Show HN:" prefix and the link is the origin URL; confirm the old Show HN is untouched. | The HN item URL (+ first-reply timestamp for the LS-1688 SLO loop). |
| AC9 | If invited: open the lobste.rs story; confirm the canonical URL + the valid tag set + prior-participation history. Else: the recorded drop decision. | The lobste.rs story URL with tags, **or** the "dropped — no invite" note. |
| AC10 | Capture the Changelog News submission confirmation and/or the Console.dev outbound email; confirm each carries the canonical URL. | The submission confirmation/screenshot and/or the outbound email, plus the "TLDR + Hacker Newsletter intentionally not used" note. |
| AC11 | `git diff` on `docs/launch/launch-narrative-drafts.md` shows the obsolete PyPI line corrected. | The diff hunk (committed in the same change that touches the doc). |

Operator approval is required before every external go-live step (AC6, AC7, AC8, AC10),
consistent with the launch docs' posting checklist.

## Definition of Done

The epic is Done only when **all** of the following hold and are captured as evidence
(URLs, screenshots, page-source greps, submission confirmations) on this issue:

- All eleven acceptance criteria (AC1–AC11) are checked, each with its evidence artifact
  attached.
- The essay is live on the author-controlled canonical URL, first-person, telling the
  `gbrain`-drift → git-first-rebuild story with the three load-bearing ideas and honest
  limitations intact — and the origin was published and crawled **before** any
  syndication.
- Every syndicated copy resolves `rel=canonical` to the origin (verified in page source);
  HN has a second presence as a **normal** story; lobste.rs is submitted by the rules **or**
  a recorded drop; at least one verified-mechanism newsletter tip points at the canonical
  essay.
- The claims/gated-claims/leak gate is green for the essay and every cross-post: **zero**
  forbidden claims, **zero** unverified gated claims (registry listing absent unless
  verified-published; awesome-mcp-servers stated as "submitted/PR open" unless
  verified-merged; Glama "A" letter quoted only if seen live, else effort-only), **zero**
  leaked private values.
- All nine sub-issues are Done with their own captured evidence; their dependency order
  (U1 → U2/U7 → U3 → U9 → U4 → U5/U6/U8/U10) was respected.

**Voice & claims guardrails (binding on every sub-issue):** no acceptance criterion may
require asserting an official MCP Registry listing before it is actually published, that
the awesome-mcp-servers entry is *merged* while PR #8056 is open, or the Glama "A" letter
before it is seen on the live listing. No post may claim hosted SaaS / managed cloud, that
the Obsidian companion writes a vault, or that dense retrieval is always on; no benchmark
number outside the published comparability envelope (no GPT-4.1-judged ~95% comparisons).

## Links

- **Canonical plan:** `docs/plans/2026-06-25-002-content-founder-essay-and-crossposts-plan.md`
  *(GitHub permalink substituted at issue-creation time)*
- **Brainstorm / requirements:** `docs/brainstorms/2026-06-25-founder-essay-and-crossposts-requirements.md`
  *(GitHub permalink substituted at issue-creation time)*
- **SEO spine / comparison page:** `docs/why-hypermnesic.md`
- **Approved claims + per-channel drafts (holds the stale PyPI line to fix):** `docs/launch/launch-narrative-drafts.md`
- **Repo-verified positioning + gated-claim notes:** `docs/launch/promo-grounding-brief.md`
- **Gated-claim source state (registry unpublished; PR #8056 open):** `docs/launch/directory-submission-prep.md`
- **Channel sequencing + evidence loop:** `docs/launch/launch-sequencing.md`
- **Launch-week response SLO (feeds first-reply timestamps):** `docs/launch/launch-week-response-slo.md`
- **Benchmark comparability envelope:** `harness/BENCHMARKS.md`
- **Reusable assets (note: no `flywheel.jpg` exists):** `media/engine/hero-receipt-loop.gif`,
  `media/engine/connector-montage/one-endpoint-many-clients.svg`
- **Related LS launch issues:** LS-1689 (launch narrative — this essay extends it),
  LS-1683 (directory submissions — gated-claim source), LS-1684 (PyPI live — install
  proof), LS-1688 (launch-week response SLO), LS-1690 (channel sequencing).
