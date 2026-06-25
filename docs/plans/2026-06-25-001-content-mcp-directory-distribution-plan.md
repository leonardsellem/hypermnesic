---
title: "content: Distribute hypermnesic across MCP server directories"
date: 2026-06-25
origin: docs/brainstorms/2026-06-25-mcp-directory-distribution-requirements.md
type: content
---

# content: Distribute hypermnesic across MCP server directories

## Overview

Make hypermnesic findable everywhere an MCP user browses for a server. One publish to the
Official MCP Registry cascades into the directories that ingest from it (PulseMCP); the two
high-traffic directories that do not auto-ingest (Smithery, mcp.so) get hand submissions
carrying the ownership-and-compounding wedge; and the repo closes its own loop by adding the
already-earned Glama score badge (and, only if confirmed merged, an awesome-mcp-servers
badge). Every listing or grade claim is gated on verification at its own source, per the
claims rules — no "live", "merged", or "A grade" assertion ships unproven.

## Goals / Non-goals

**Goals**

- Publish the staged `docs/launch/mcp-registry-server.draft.json` to the Official MCP
  Registry as-is and verify the live entry by registry query (R1–R5).
- Hand-submit hypermnesic to Smithery (bring-your-own-hosting) and mcp.so (GitHub Issue #1),
  each with the canonical name and the ownership-and-compounding blurb (R6–R8, R10).
- Confirm PulseMCP auto-ingests within ~1 week; correct by email only if it does not (R9).
- Add the Glama score badge via the correct `/badges/score.svg` path; add the awesome badge
  only if PR #8056 is confirmed merged (R11–R13).
- Verify every external claim at source before it ships: registry query, Glama listing
  `ak6x81u3rr`, awesome PR #8056 (R14–R16).
- Record the conscious skip of mcp-get with its reason so it is not re-litigated.

**Non-goals**

- No PyPI-package-backed `packages` entry in `server.json` (deferred enrichment; the only
  thing that would also make mcp-get worth revisiting).
- No Obsidian community-plugin submission for the companion — separate repo, separate
  audience, separate distribution track.
- No committed Dockerfile/compose work to make the server Glama-statically-inspectable.
- No hosted-SaaS / managed-cloud listing; every entry is a bring-your-own-host remote.
- No generic "memory server" blurb that drops the wedge; no benchmark figure presented as
  full-product proof or quoted outside the published comparability envelope.
- No chasing the Glama overall coherence letter via tool renames.

## Implementation Units

### U1 — Verify-before-claim sweep (gates every public assertion)

**Goal.** Establish ground truth for the three claims the seed got wrong or left external,
so downstream copy and badges are decided on evidence, not assumption. This unit produces no
public artifact; it produces the facts that license the others.

**Steps.**
1. Query the Official MCP Registry to confirm hypermnesic is **not yet** present (baseline
   for R4 / R16):
   `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.leonardsellem/hypermnesic"`.
   Expect an empty result set; record it.
2. Confirm the awesome-mcp-servers PR state at source:
   `gh pr view 8056 --repo punkpeye/awesome-mcp-servers --json state,merged,mergedAt,url`.
   Record `state` / `merged`. The repo evidence (`docs/launch/directory-submission-prep.md`)
   records it **open**; treat "merged" as unproven until this returns `merged: true`.
3. Open the live Glama listing `https://glama.ai/mcp/servers/ak6x81u3rr` and read the
   Tool-Definition-Quality grade. Capture a screenshot. If it shows **A**, the letter is
   usable in copy (R14); if not confirmable, copy may state only the provable effort (full
   tool descriptions, 100% parameter-description coverage) — never the letter.
4. Confirm the Glama score-badge URL renders inline before it goes in the README:
   `curl -sSI "https://glama.ai/mcp/servers/ak6x81u3rr/badges/score.svg"` returns `200`
   with an SVG content-type. Spot-confirm the two wrong paths are wrong:
   `…/badge.svg` → `404`; `…/badge` → an oversized card, not an inline badge.

**Files / Surfaces.** Read-only against: Official MCP Registry API; GitHub PR #8056;
Glama listing `ak6x81u3rr`. No repo file changes.

**Validation.** Three captured artifacts: (a) the empty registry-query JSON; (b) the
`gh pr view` JSON showing PR #8056 state; (c) the Glama listing screenshot plus the
`curl -I` showing the score-badge `200`. These three decide U6's awesome badge and the
letter-grade wording everywhere.

**Dependencies.** None. Run first — it gates U3 copy, U5, and U6.

---

### U2 — Stage the root `server.json` and validate (no publish)

**Goal.** Get the repository into the exact pre-publish state the registry CLI expects,
deterministically and without touching the human-gated step, so the operator's single
device-code login in U3 is the only remaining action.

**Steps.**
1. Download the `mcp-publisher` binary (pinned to the host arch):
   ```sh
   curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher
   ```
2. Copy the staged draft to the repo-root `server.json` **without editing the `remotes` /
   `{host}` template shape** (R1):
   `cp docs/launch/mcp-registry-server.draft.json server.json`.
3. Validate: `./mcp-publisher validate`. Confirm it passes, including the ≤100-character
   `description` limit (R3) — the staged description is already within it.
4. Confirm the name is `io.github.leonardsellem/hypermnesic` (GitHub-OAuth namespace, so no
   DNS/reverse-DNS verification is needed — that applies only to a `me.sellem/*`-style
   custom-domain name, which hypermnesic does not use).
5. STOP here. Do not run `login` or `publish` — those are U3 (operator-gated).

**Files / Surfaces.** New repo-root `server.json` (a copy of the staged draft);
`docs/launch/mcp-registry-server.draft.json` (source, unchanged); the downloaded
`mcp-publisher` binary (do not commit the binary).

**Validation.** `./mcp-publisher validate` exits success; captured terminal output.
`diff docs/launch/mcp-registry-server.draft.json server.json` is empty (proves no shape
drift).

**Dependencies.** None blocking, but pair it with U3 — this is the no-human half of the
same publish step.

---

### U3 — Operator-gated registry publish + live verification (the cascade trigger)

**Goal.** Publish the validated entry to the Official MCP Registry. This is the single
highest-leverage move: it is the canonical PulseMCP path and the trigger for the downstream
cascade, and it is the only step in the whole initiative that requires a human.

**Steps.**
1. **Operator runs the device-code login** (cannot be automated): `./mcp-publisher login
   github`. Complete the device-code flow in the browser.
2. Publish: `./mcp-publisher publish`.
3. Verify the entry is live (R4 — the gate that unlocks any "listed on the official
   registry" claim):
   `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.leonardsellem/hypermnesic"`.
   Confirm the returned JSON shows `io.github.leonardsellem/hypermnesic` with the canonical
   title, description, and repository link.
4. Record the JSON result as the artifact. Until this returns the entry, the voice rule
   against claiming an official-registry listing stays in force (R16) — do not reference it
   as live anywhere.

**Files / Surfaces.** Official MCP Registry (write via publish). The repo-root `server.json`
from U2 is the published payload.

**Validation.** The R4 registry-query JSON showing the live entry, captured as the artifact
on the tracking issue. (Re-publishing on each future release uses additive `isLatest`
versioning — supersede, never delete-and-replace — and the root `server.json` `version`
tracks the engine version; R5. Out of scope to execute now, recorded for the release loop.)

**Dependencies.** U2 (validated `server.json`). **Hard blocker:** operator availability to
run `mcp-publisher login github`. If the operator cannot run it in this window, the cascade
stalls here — U7 sequences the wait, and U4/U5/U6 that do not depend on the registry can
still proceed.

---

### U4 — Submit to Smithery (bring-your-own-hosting)

**Goal.** List hypermnesic on Smithery as a remote, self-hosted server pointed at the public
`/mcp` OAuth endpoint, under the canonical org/name, without inventing any Smithery-only
hosting config.

**Steps.**
1. Confirm the live wizard fields and OAuth-flow specifics at submission time before relying
   on either route (R7) — Smithery's BYO-hosting requirements (Streamable HTTP transport +
   OAuth) are met by the public `/mcp` endpoint, but the exact field set was not fully
   enumerable from docs.
2. First check whether an **unclaimed crawled entry already exists** (Smithery crawls the
   ecosystem); if so, **claim it** rather than creating a duplicate (R6).
3. Submit via the web flow (preferred, fields visible in-wizard): `smithery.ai/new` → URL
   tab → enter `https://<host>/mcp` (use the operator's real public host at submission time;
   never write the real host into any committed file). Org/name: `leonardsellem/hypermnesic`.
   No `smithery.yaml` — Smithery proxies to the upstream server, so build/runtime config is
   not required for a BYO-hosting remote listing.
   - CLI alternative (verify exact flags first via `smithery --help`; the
     `smithery mcp publish <url> -n <org>/<server>` form is from a third-party guide, not
     Smithery's own docs): `smithery mcp publish https://<host>/mcp -n leonardsellem/hypermnesic`.
4. Set the listing blurb to carry the ownership-and-compounding wedge (R10), reusing the
   canonical line — files are truth, the index is disposable, writes are reviewable commits —
   and link the README quick start `https://github.com/leonardsellem/hypermnesic#quick-start`.
   Suggested blurb (≤ the wedge, no benchmark figure, no SaaS framing):
   > Git-first Markdown memory for AI agents: your files are the source of truth, the search
   > index is disposable and rebuildable, and every write is a reviewable git commit. Remote
   > Streamable HTTP MCP over your own OAuth-secured endpoint.

**Files / Surfaces.** Smithery listing (external). Canonical inputs from
`docs/launch/directory-submission-prep.md` and `README.md`. No repo file changes.

**Validation.** The live Smithery listing URL under `leonardsellem/hypermnesic`, captured
(URL + screenshot), showing the wedge blurb and a working README link (R16). Record whether
the entry was claimed-from-crawl or created fresh.

**Dependencies.** A reachable public `/mcp` OAuth endpoint (the listing points at it).
Independent of U3 — can run in parallel; Smithery does not ingest from the official registry.

---

### U5 — Submit to mcp.so (GitHub Issue #1)

**Goal.** List hypermnesic on mcp.so via its reliable community path, with the canonical name
and the wedge blurb.

**Steps.**
1. Submit via the confirmed-reliable route: post a comment on **`chatmcp/mcpso` Issue #1**
   ("Submit Your MCP Servers here") at `https://github.com/chatmcp/mcpso/issues/1`, linking
   the server and carrying the wedge blurb + README quick-start link (R8, R10). Comment body:
   > Hypermnesic — git-first Markdown memory for AI agents. Markdown files are the source of
   > truth, the search index is disposable and rebuildable, and every write is a reviewable
   > git commit. Remote Streamable HTTP MCP over your own OAuth-secured endpoint.
   > Repo / quick start: https://github.com/leonardsellem/hypermnesic#quick-start
   >
   > `gh issue comment 1 --repo chatmcp/mcpso --body-file <blurb-file>`
2. The web `/submit` form is an acceptable alternate **only after** its live fields are
   confirmed in an authenticated browser (it returned 403/login-gated to anonymous fetch);
   default to the GitHub-issue route (R8).

**Files / Surfaces.** mcp.so directory (external, via `chatmcp/mcpso` Issue #1). No repo file
changes.

**Validation.** The posted GitHub-issue comment URL, then — once the maintainer adds it — the
live mcp.so listing URL, captured (R16). Record both.

**Dependencies.** A reachable public `/mcp` endpoint. Independent of U3 — runs in parallel.

---

### U6 — README badges: Glama score (always) + awesome (conditional)

**Goal.** Surface the earned quality signal in the repo without weakening any claim:
add the Glama score badge unconditionally (the effort is real and the badge path is proven),
and add the awesome badge **only if** U1 confirmed PR #8056 merged.

**Steps.**
1. In `README.md`, after the existing License badge (keep CI, PyPI, License and their order;
   R13), add the Glama score badge using the **exact working path** (R11):
   ```md
   [![Glama score](https://glama.ai/mcp/servers/ak6x81u3rr/badges/score.svg)](https://glama.ai/mcp/servers/ak6x81u3rr)
   ```
   Do **not** use `…/badge.svg` (404) or `…/badge` (oversized 760×400 card).
2. **Conditional on U1 step 2:**
   - If `gh pr view 8056` returned `merged: true`: add an awesome-mcp-servers badge linking
     the merged entry (R12):
     `[![Mentioned in Awesome MCP Servers](https://awesome.re/mentioned-badge.svg)](https://github.com/punkpeye/awesome-mcp-servers)`.
   - If still open: **do not add the badge.** Record the state as "submitted / PR open" in the
     tracking notes (R12). Re-run this step when the PR merges.
3. Confirm no private host, token, or local path enters the badge row (R13) — both badge URLs
   are public Glama / awesome endpoints; the repo links are the public GitHub repo. (This
   change touches only the README badge row; the AGENTS.md anti-drift table does not require
   a further doc update for a badge-row addition, but add a dated `[Unreleased]` CHANGELOG
   line for the user-visible README change.)

**Files / Surfaces.** `README.md` (badge row, lines 3–5 region). `CHANGELOG.md`
(`[Unreleased]` entry). No other docs change.

**Validation.** Rendered README shows the Glama score badge resolving to a real score image
(not a broken-image icon); GitHub preview screenshot. If the awesome badge was added, it
renders and links the merged entry. `git diff` shows CI/PyPI/License untouched and in order.

**Dependencies.** U1 (the awesome-badge decision and the score-badge `200` confirmation).
Independent of U2–U5 — does not need the registry publish.

---

### U7 — PulseMCP auto-ingest check + record the mcp-get skip

**Goal.** Confirm the cascade actually fired (PulseMCP listed hypermnesic from the official
registry) without a redundant hand submission, and durably record the conscious mcp-get skip
so it is not re-opened later.

**Steps.**
1. **Do not hand-submit PulseMCP.** It ingests official-registry entries daily and processes
   them weekly, so the default path is to wait (~1 week after U3) and let it appear (R9).
2. ~1 week after U3 lands, search PulseMCP (`pulsemcp.com`) for hypermnesic. If present,
   capture the listing URL and confirm its metadata matches canonical (name, description,
   links).
3. If absent after the window, or carrying wrong metadata, email `hello@pulsemcp.com` with
   the GitHub repo + canonical description for an expedite/correction (R9) — this is the
   lever, not a fresh submission. (PulseMCP ownership can also be claimed.)
4. Record the **mcp-get skip with its reason** in `docs/launch/directory-submission-prep.md`
   so it is visibly settled: mcp-get is a package-install-manager registry (npm/PyPI shaped),
   largely superseded by the Official MCP Registry, and a poor fit for a remote-only,
   self-hosted server with no installable MCP-server package shape — revisit only if a
   PyPI-package-backed `packages` entry is later added.

**Files / Surfaces.** PulseMCP listing (external); optional email to `hello@pulsemcp.com`.
`docs/launch/directory-submission-prep.md` (append the mcp-get skip rationale + a dated
post-submission state update for each target).

**Validation.** The PulseMCP listing URL captured (or the sent correction-email record); the
mcp-get skip rationale committed to the prep doc (R9, and the success-criterion that the skip
is recorded).

**Dependencies.** U3 (the publish that PulseMCP ingests). Time-gated — the ~1-week wait runs
after the cascade trigger.

---

## Sequencing / Milestones

1. **M0 — Ground truth (U1).** Run the verify-before-claim sweep first. Its three artifacts
   decide the awesome badge (U6) and all letter-grade wording. No public action precedes it.
2. **M1 — Registry publish (U2 → U3).** Stage + validate `server.json` (U2, no human), then
   the operator's single device-code login + publish + live verify (U3). This is the cascade
   trigger and the hard gate; everything registry-dependent waits on the R4 query passing.
3. **M2 — Hand-submitted directories, same day as M1 (U4, U5), in parallel.** Smithery and
   mcp.so do not auto-ingest, so submit them as soon as the public endpoint is confirmed
   reachable — they do not need to wait for U3.
4. **M3 — Repo badges (U6), parallel with M2.** Add the Glama score badge immediately;
   add the awesome badge only on a confirmed-merged result from M0.
5. **M4 — Cascade confirmation (~1 week later, U7).** Confirm PulseMCP auto-listed; correct by
   email if needed. Record the mcp-get skip.

Critical path: M0 → M1 (operator login) → M4. M2 and M3 are off the critical path and can land
on day one regardless of the operator's login timing.

## Risks & Mitigations

- **Operator login never happens in the window (the whole cascade gate).** Mitigation:
  U2 leaves the repo one command from publish; U4/U5/U6 are sequenced to deliver value without
  the registry; M4 is explicitly time-gated so the wait is planned, not a surprise. If login
  slips, the initiative still ships Smithery, mcp.so, and the Glama badge.
- **Claiming a listing before it is live (claims-rule violation).** Mitigation: R16 holds —
  no entry is referenced as live until verified at source (registry R4 query, Smithery/mcp.so
  listing URLs, PulseMCP presence). The voice rule against an official-registry-listing claim
  stays in force until the R4 query returns the entry.
- **Asserting "merged" / "A grade" unverified (the seed's two stale claims).** Mitigation:
  U1 confirms PR #8056 state and the Glama grade at source first; the awesome badge and the
  letter grade are both gated on those confirmations. Absent confirmation, copy states only
  provable effort.
- **Wrong Glama badge path ships a broken image.** Mitigation: U1 `curl -I` proves
  `/badges/score.svg` returns `200` before it enters the README; `…/badge.svg` (404) and
  `…/badge` (oversized card) are explicitly excluded.
- **Smithery field/flag drift (docs not fully enumerable).** Mitigation: R7 — confirm the
  live wizard fields and OAuth specifics, and `smithery --help` flags, at submission time;
  prefer the web wizard (fields visible) over the unverified CLI form.
- **Duplicate Smithery entry from its crawl.** Mitigation: U4 checks for an unclaimed crawled
  entry and claims it rather than creating a second.
- **mcp.so web form is login-gated (fields unread).** Mitigation: default to the
  confirmed-reliable GitHub Issue #1 route; the form is an alternate only after authenticated
  field confirmation.
- **Leaking the operator's real host into a committed file.** Mitigation: the real public
  host is entered only in the external Smithery/mcp.so surfaces at submission time; the
  committed `server.json` keeps the `{host}` template variable and no real host, IP, or token
  appears in any repo file (preflight scan stays green).
- **Stale claims-avoid guard contradicting live reality.** `docs/launch/launch-narrative-drafts.md`
  still says "Do not claim PyPI install until LS-1684 is decided" — PyPI is now live (the
  README installs from it). That line is obsolete; correct it when that doc is next edited so
  it does not block honest copy. (Not in this initiative's critical path; flagged here so it
  is not lost.)

## Validation / Definition of Done

Done when **all** of the following are captured as artifacts on the tracking issue:

- The Official MCP Registry query for `io.github.leonardsellem/hypermnesic` returns the
  published entry, recorded as JSON (R4). Until then, no official-registry-listing claim is
  made (R16).
- hypermnesic is live on Smithery and on mcp.so under the canonical name, each with the
  ownership-and-compounding wedge blurb and a working README quick-start link; both listing
  URLs captured (R6, R8, R10, R16).
- PulseMCP is confirmed present (auto-ingested) within ~1 week of publish, or corrected by
  email; its metadata matches canonical (R9).
- The README shows the Glama score badge via the `/badges/score.svg` path, rendering a real
  score image; CI/PyPI/License badges unchanged and in order; no private host/token/path
  introduced (R11, R13). The awesome badge is present **iff** PR #8056 is confirmed merged,
  else the state is recorded as "submitted / PR open" (R12, R15).
- Every public claim about a listing or grade is backed by a source confirmation: registry
  query, Glama listing `ak6x81u3rr` screenshot, `gh pr view 8056`. No "merged" or "A grade"
  claim ships unverified (R14, R15, R16).
- The mcp-get skip and its reason are recorded in
  `docs/launch/directory-submission-prep.md`, with that doc's post-submission state updated
  for each target (success criterion: skip recorded, not re-litigated).

## References

**Internal**

- `docs/brainstorms/2026-06-25-mcp-directory-distribution-requirements.md` — origin
  requirements (R1–R16).
- `docs/launch/directory-submission-prep.md` — target directories, copy-ready draft entries,
  operator pause points, current submission state.
- `docs/launch/mcp-registry-server.draft.json` — the staged, schema-valid registry entry
  (remote `{host}` template, no `packages`).
- `docs/launch/promo-grounding-brief.md` — positioning confirmations and corrections (PyPI
  live; registry not yet published; awesome + Glama grade need verification).
- `docs/launch/launch-narrative-drafts.md` — claims-allowed / claims-avoid lists and the
  canonical voice (note the obsolete PyPI-avoid line, flagged in Risks).
- `docs/launch/launch-sequencing.md` — where directory updates sit in the launch order.
- `docs/why-hypermnesic.md` — the differentiation framing carried into blurbs.
- `README.md` — current badge row (CI, PyPI, License) and canonical product description.

**External**

- `https://modelcontextprotocol.io/registry` (about · quickstart · remote-servers) — the
  `mcp-publisher` flow, the `remotes` block, URL template variables, the GitHub-OAuth
  namespace, the ≤100-char description limit, additive `isLatest` versioning.
- `https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.leonardsellem/hypermnesic`
  — the verification query (R4).
- `https://pulsemcp.com/submit` — daily ingest / weekly processing from the official
  registry; `hello@pulsemcp.com` for expedite or metadata correction.
- Smithery bring-your-own-hosting docs · `smithery.ai/new` — gateway proxies to upstream;
  Streamable HTTP + OAuth requirements; no `smithery.yaml` for a remote BYO listing.
- `https://github.com/chatmcp/mcpso/issues/1` — the community submission path for mcp.so.
- `https://glama.ai/mcp/servers/ak6x81u3rr` — the live Glama listing; verify the grade and
  the `/badges/score.svg` badge path.
- `https://github.com/punkpeye/awesome-mcp-servers/pull/8056` — the awesome-mcp-servers entry
  whose merge state must be confirmed before any "merged" claim.
- `https://www.truefoundry.com/blog/best-mcp-registries` — the metaregistry / downstream
  ingest landscape.
