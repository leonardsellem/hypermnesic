---
date: 2026-06-25
topic: founder-essay-and-crossposts
---

# Founder Essay and Cross-Posts — Requirements

## Summary

A long-form founder essay that turns the authentic origin story — a database-backed
personal brain that drifted from its files, then the git-first rebuild — into the
durable, canonical narrative for hypermnesic. It publishes first on a domain the author
owns, then syndicates to dev.to / Hashnode (and optionally Medium) with `rel=canonical`
pointing home, and seeds lobste.rs and a second Hacker News story. The evergreen
comparison angle from `docs/why-hypermnesic.md` rides along as the SEO spine so the essay
keeps earning attention long after launch week.

## Problem Frame

hypermnesic already has receipts-first launch assets and per-channel announcement drafts,
but those are point-in-time "we launched" artifacts — they convert on the day and then
decay. What is missing is the one piece that compounds: a story that explains *why this
shape exists*, in the author's own voice, on a URL the author controls. The "AI memory"
space is crowded and skeptical (mem0, Letta, Zep, basic-memory, Supermemory all assert
"persistent memory for your agents"), and a launch post cannot win that audience on
features alone — the reflex first question is "is the data actually mine, or is this a
vector DB with a wrapper?". An origin story answers that reflex better than a spec sheet:
the author lived the failure mode the product fixes. There is also a distribution tax
being paid silently — when a high-domain-authority platform (dev.to, Medium, Hashnode)
hosts a version of your writing without a canonical link home, that platform's copy
outranks yours, and the ranking signal and backlinks accrue to them instead of you. And
the announcement channels themselves resist re-drops: Hacker News forbids deleting and
reposting an underperforming Show HN, and lobste.rs polices self-promotion — so there is
no second bite at those audiences unless a genuinely distinct artifact is published.

## Key Decisions

- **Canonical-first publishing is non-negotiable.** The essay's first home is a domain the
  author controls (a `/blog` on the hypermnesic site or a personal `sellem.me`-class
  domain). Every syndicated copy sets `rel=canonical` back to that origin URL. This is the
  whole SEO game: without a canonical, a high-DA platform copy wins the ranking and the
  origin gets nothing; with one, all signal consolidates on the URL the author owns. The
  canonical is published and given time to be crawled *before* any syndication goes out.

- **The essay is an essay, not a second launch post.** It is submitted to Hacker News as a
  normal story (article URL + title), NOT as "Show HN:". This sidesteps HN's
  delete-and-repost prohibition and the Show-HN "must be a major overhaul" bar entirely,
  because an origin essay is a different artifact from the original Show HN — a legitimate
  distinct submission, not a re-drop. Same logic for lobste.rs: the architecture/origin
  writeup clears the bar that a marketing launch page does not.

- **Voice stays first-person, opinionated, and personal — honest limits included.** The
  approved voice ("One brain. Every AI. Yours."; deliberately opinionated; does one thing,
  not a platform) carries straight into the essay. The origin beat — the prior
  database-backed brain that drifted and could not be trusted or moved — is already a
  sanctioned narrative, so the essay introduces *no new claims*; it dramatizes claims the
  repo already proves. Honest limitations (self-hosted not SaaS; dense retrieval degrades
  to lexical-only; the companion is read-only) are kept in, because they are what win the
  skeptical reader, not what to hide from them.

- **Compete on ownership, compounding, and reviewable writes — never on benchmark rank.**
  The essay's argument is files-are-truth + the Capture → Curate → Recall → Compound
  flywheel + every write is a reviewable git commit. Benchmarks appear only as a supporting
  trust signal, strictly inside the published comparability envelope, with the judge axis
  labeled. The essay never claims a rank it cannot defend, and states Hindsight's higher
  number is on a more lenient judge axis plainly rather than burying it.

- **The comparison page is the evergreen SEO spine, reused not duplicated.** `docs/why-
  hypermnesic.md` already draws the architectural-axis comparisons (vs mem0/Letta/basic-
  memory/Obsidian). The essay links to it as the "where does this sit" reference rather than
  re-litigating each competitor inline, keeping the essay a story and the comparison page
  the durable reference both can rank for.

- **The origin beat is a founder essay only — never a competitor row.** The drifted prior
  brain is the author's own history, framed as lived motivation, not a swipe at any named
  competitor. It belongs in the narrative, not in a vs-table.

- **Syndicate only where `rel=canonical` is honored.** dev.to, Hashnode, and Medium all
  support a canonical field; the essay goes to those and skips any platform that cannot set
  one. lobste.rs and Hacker News *link to the canonical origin URL*, not to a syndicated
  copy, so discussion traffic also points home.

## Requirements

**Canonical origin and content**

R1. The essay MUST be published first on a domain the author controls, and that origin URL
is the single canonical target every syndicated copy points to.

R2. The essay MUST tell the origin story in first person: the prior database-backed personal
brain ("gbrain") that drifted from its files and could no longer be trusted or moved, then
the git-first rebuild that makes files the source of truth. This is the only place the gbrain
beat appears; it is framed as motivation, not as a competitor comparison.

R3. The essay MUST land the three load-bearing ideas in the author's voice: (a) files are the
source of truth and the search index is a disposable, rebuildable projection of the git tree
(a reindex can never lose a committed write); (b) every memory write is a reviewable git
commit — visible in history, revertible; (c) the compounding flywheel — Capture → Curate →
Recall → Compound — across every AI on laptop and phone through one shared endpoint.

R4. The essay MAY reference the distinctive mechanics by name where they serve the story —
the guarded `commit_note` write (diff-or-die frontmatter gate + blocklist write guard +
single-writer locks + append-only audit log), hybrid FTS5 + sqlite-vec retrieval via RRF with
graceful lexical-only degradation, read-time convergence, and the one OAuth-secured MCP
endpoint — but MUST NOT introduce any capability beyond what the repo proves.

R5. The essay MUST keep honest limitations visible: hypermnesic is self-hosted and not a
hosted SaaS / managed cloud; dense retrieval can degrade to a supported, visible lexical-only
state; the Obsidian companion is read-only by design.

R6. The essay MUST link to `docs/why-hypermnesic.md` (its public URL) as the evergreen
comparison reference rather than restating each competitor inline, and MAY embed an existing
launch asset from `media/engine/` (e.g. the hero receipt GIF or `flowywheel`/flywheel image)
to show the git-native proof rather than only describe it.

**Claims discipline**

R7. The essay and every cross-post MUST stay inside the approved claims set: git-first memory;
files-are-truth / disposable rebuildable index; reviewable git-commit writes; MCP + CLI +
read-only Obsidian companion; PyPI install is live (`uv tool install hypermnesic`); benchmarks
exist with documented caveats and product readiness tracked separately.

R8. The essay and cross-posts MUST NOT claim, in any form: hosted SaaS / managed cloud; that
the Obsidian companion can write a vault; that dense retrieval is always on; or any benchmark
number outside the published comparability envelope (no GPT-4.1-judged ~95% comparisons).

R9. Three claims are gated on live verification and MUST NOT appear until confirmed: an
official MCP Registry listing (currently unpublished); that the awesome-mcp-servers entry is
*merged* (repo evidence shows PR #8056 open — downgrade to "submitted / PR open" if still
open); and the Glama "A" Tool-Definition-Quality letter grade (confirm on the live listing
`ak6x81u3rr` before quoting the letter; otherwise describe the effort, not the grade).

R10. No post MUST contain private hostnames, tokens, vault contents, or local absolute paths;
host placeholders only, consistent with the repo's preflight discipline.

R11. Any benchmark mention MUST label its judge axis and link `harness/BENCHMARKS.md`; on the
matched GPT-4o-judge axis hypermnesic is on par with Mastra (84.2), +12 over Zep, +23 over the
no-memory floor, with 88.6% overall / 90.2% task-averaged under a GPT-4.1 reader — and any
Hindsight comparison states plainly that its higher number sits on a more lenient judge axis.

**Syndication and sequencing**

R12. The canonical origin MUST be published and given time to be crawled/indexed before any
syndicated copy is posted, so the origin is discovered first.

R13. Each syndicated copy (dev.to, Hashnode, and optionally Medium) MUST set its canonical
field to the origin URL using that platform's native mechanism (dev.to `canonical_url` front
matter or the editor's Canonical URL field; Hashnode's "Original article URL" set during the
create flow; Medium's "Import a story" / "originally published elsewhere" flow).

R14. Syndication MUST be limited to platforms that honor `rel=canonical`; any platform that
cannot set a canonical is skipped.

R15. The Hacker News submission MUST be a normal story (article URL + title), explicitly NOT a
"Show HN:" post, and MUST NOT be a delete-and-repost of the original Show HN.

R16. The lobste.rs submission MUST be the canonical essay URL (the architecture/origin
writeup, not a "we launched" page), submitted only after substantive participation on others'
stories, using tags confirmed to exist (`ai`, `python`, `databases`, `programming`,
`practices`; `show` only if submitting the project rather than the essay), via an invite
obtained through the sanctioned path (no cold-DMing strangers for invites).

R17. lobste.rs, Hacker News, and any newsletter tip MUST link the canonical origin URL, never
a syndicated dev.to/Medium copy, so discussion traffic points home.

R18. Newsletter outreach MUST use only verified self-serve submit mechanisms and MUST submit
the *essay* (a story/architecture writeup), not the landing page: Changelog News via its
public submit form; Console.dev via hello@console.dev. TLDR is treated as paid-only (no free
editorial tip path) and Hacker Newsletter is curated from HN (no direct submission) — neither
is a free tip channel and MUST NOT be treated as one.

**Self-promotion etiquette**

R19. lobste.rs participation MUST respect the community's self-promotion norm (own
stories+comments kept a minority of activity); the essay arrives after the author has
commented substantively elsewhere, not as a brand-new account's first and only post.

R20. No post MUST solicit upvotes, comments, or coordinated boosting on Hacker News or
lobste.rs.

## Success Criteria

- The essay is live on the author-controlled canonical URL, in first-person voice, telling the
  gbrain-drift → git-first-rebuild story with the three load-bearing ideas (R2, R3) and honest
  limitations intact (R5).
- Every syndicated copy resolves its `rel=canonical` to the origin URL (verifiable in page
  source), and the origin was published first (R12–R14).
- A second Hacker News presence exists as a normal story, distinct from the original Show HN,
  with no delete-and-repost (R15).
- The lobste.rs submission is the canonical essay URL with valid tags, posted by an account
  with prior substantive participation (R16, R19).
- A claims pass confirms zero forbidden claims (R8), zero unverified gated claims (R9), and no
  leaked private values (R10) across the essay and all cross-posts.
- `docs/why-hypermnesic.md` is linked from the essay and is positioned to rank as the evergreen
  comparison reference (R6).
- At least one verified-mechanism newsletter submission (Changelog News and/or Console.dev) is
  sent, pointing at the canonical essay (R17, R18).

## Scope Boundaries

### Deferred for later

- A cinematic narrated origin video — the essay is text-first; video is a separate, later wave.
- Backdating/importing the essay onto Medium beyond a single canonical-respecting cross-post.
- DZone / Hacker Noon and other secondary canonical-respecting syndication targets — allowed in
  principle but not required for this initiative.
- Paid newsletter placement (e.g. TLDR sponsorship) — out of the free-tip scope here.
- A measured before/after SEO ranking report for `docs/why-hypermnesic.md` — worth doing but
  belongs to a later analytics pass, not this writing initiative.
- Translations / localized versions of the essay.

### Outside this product identity

- Any claim of hosted SaaS, managed cloud, or a multi-tenant memory service.
- Any framing that the Obsidian companion writes to a vault, or that dense retrieval is always
  on.
- Competing on benchmark rank, or quoting numbers outside the published comparability envelope.
- Turning the origin beat into a competitor hit-piece — gbrain is the author's own history, not
  a vs-row.
- Re-dropping the original Show HN, soliciting votes, or cold-DMing for lobste.rs invites —
  channel-rule violations are out of bounds regardless of reach.

## Dependencies / Assumptions

- An author-controlled canonical domain/path is available to host the essay (a `/blog` on the
  hypermnesic site or a `sellem.me`-class domain); standing up that surface is a precondition,
  not part of the essay copy itself.
- PyPI install being live (`uv tool install hypermnesic`) is shipped truth (LS-1684 Done); the
  stale "do not claim PyPI" line in `docs/launch/launch-narrative-drafts.md` is obsolete and
  should be corrected when that doc is next touched.
- The approved claims/voice lists in `docs/launch/launch-narrative-drafts.md` and the grounding
  in `docs/launch/promo-grounding-brief.md` are authoritative; the essay extends them and
  introduces no new claims.
- Existing media in `media/engine/` (hero receipt GIF, flywheel image, benchmark SVG) is
  reused; no new asset production is assumed here.
- A lobste.rs invite via the sanctioned path is obtainable; if not, the lobste.rs leg is
  dropped rather than forced.
- Operator approval is required before any external post goes live, consistent with the launch
  docs' posting checklist.

## Outstanding Questions

### Resolve before planning

- Which canonical home is it — a `/blog` on the hypermnesic site, or a personal `sellem.me`
  domain? This determines the canonical URL every cross-post depends on.
- Verify the three gated claims now so the essay can use or must omit each: is the official MCP
  Registry listing published, is awesome-mcp-servers PR #8056 merged or still open, and does the
  live Glama listing `ak6x81u3rr` show the "A" grade?
- Does the author hold (or can obtain via the sanctioned path) a lobste.rs invite? If not, scope
  out the lobste.rs leg.

### Deferred to planning

- Exact essay length and section outline (which mechanics to name vs. only link to the
  comparison page).
- Which embedded asset opens the essay — the hero receipt GIF vs. the flywheel image vs. a
  static `git log` excerpt.
- Whether Medium is included in the first syndication wave or held back.
- The crawl-wait interval between origin publication and first syndication (a few days is the
  common practice).
- Cross-linking the essay back into the README / launch docs and whether to add it to any
  public index.

## Sources / Research

Internal:

- `docs/why-hypermnesic.md` — the evergreen architectural-axis comparison page; the SEO spine
  and the essay's "where this sits" reference.
- `docs/launch/launch-narrative-drafts.md` — approved claims-allowed / claims-to-avoid lists and
  per-channel drafts (note the now-obsolete PyPI avoid-line).
- `docs/launch/promo-grounding-brief.md` — repo-verified positioning, the claims-discipline
  summary, and the gated-claim verification notes (MCP Registry, awesome-mcp-servers PR #8056,
  Glama grade).
- `docs/launch/launch-sequencing.md` — the existing channel order, evidence-to-record loop, and
  stop/completion conditions the essay sequencing aligns with.
- `docs/launch/directory-submission-prep.md` — directory-submission state behind the gated
  claims in R9.
- `harness/BENCHMARKS.md` — LongMemEval methodology and the comparability envelope every
  benchmark mention must respect.
- `ARCHITECTURE.md` / `README.md` — the prime invariant and "How it works" that R3–R4 paraphrase.
- `media/engine/` — reusable hero receipt GIF, flywheel image, and benchmark SVG.

External (canonical-first SEO and channel rules, June 2026):

- Canonical-first cross-posting and `rel=canonical` consolidation: dev.to/nfrankel,
  mikebifulco.com, catalins.tech, townhall.hashnode.com, blog.frankel.ch.
- Per-platform canonical mechanics: dev.to help (dev.to/_hariti, dev.to/leewynne), Hashnode
  "own your canonical" docs, help.medium.com "Set a canonical link" + "Importing a post".
- lobste.rs norms (invite-only, <25% self-promo, computing-focused, tag list): lobste.rs/about,
  lobste.rs invite threads, aneeshdurg.me lobsters analysis.
- Hacker News rules (no delete-and-repost; Show-HN "major overhaul" bar; no solicited votes):
  news.ycombinator.com showhn.html and newsguidelines.html.
- Newsletter submit mechanisms: changelog.com/news/submit, console.dev/selection-criteria,
  advertise.tldr.tech, hackernewsletter.com.
