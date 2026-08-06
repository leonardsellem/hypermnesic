---
date: 2026-06-25
topic: mcp-directory-distribution
---

# MCP Directory Distribution — Requirements

## Summary

Get hypermnesic listed in every place an MCP user browses for a server, led by one
publish to the Official MCP Registry that cascades into the downstream directories that
ingest from it. Where a directory does not auto-ingest — Smithery, mcp.so — submit it
by hand with the canonical name, description, and tags. Close the loop in the repo by
adding the already-earned Glama and awesome-mcp-servers badges to the README, and verify
every external listing claim before any of it is asserted in public copy.

## Problem Frame

hypermnesic is a public, released `v0.1.0` engine that already carries its distinctive
proof — files-are-truth, a guarded git-first write, hybrid retrieval, one OAuth MCP
endpoint — yet a developer shopping the MCP ecosystem cannot find it. The Official MCP
Registry returns no entry; the staged `server.json` validates but has never been
published because publishing requires a human GitHub device-code login that no prior
session could complete. Smithery and mcp.so, the two highest-traffic community
directories, have no hypermnesic listing at all. The awesome-mcp-servers PR was opened as
`#8056` but its merge state was never confirmed against the upstream, and the prior
positioning seed asserted "merged" — a claim the repo evidence does not support. The
Glama listing exists and the engine did the Tool-Definition-Quality work (full tool
descriptions, 100% parameter-description coverage across all seven tools), but the README
still shows only CI, PyPI, and License badges, so a reader never sees the quality signal,
and the externally-graded letter has never been confirmed on the live listing. The result
is a launch with strong product proof and near-zero discoverability: the audience that
would value the ownership-and-compounding story cannot stumble onto it where it browses.

## Key Decisions

- **Publish to the Official MCP Registry first; let it cascade.** The registry is the
  ecosystem metaregistry, co-maintained by Anthropic, GitHub, PulseMCP, and Microsoft.
  Downstream directories ingest from it — PulseMCP states it ingests official-registry
  entries daily and processes them weekly. One correct `mcp-publisher publish` therefore
  buys several listings without per-directory submission. This is the single
  highest-leverage move and it gates the rest of the fan-out.

- **Ship the staged draft as-is; it is already correct for a remote, self-hosted
  server.** `docs/launch/mcp-registry-server.draft.json` uses a `remotes` block
  (`streamable-http`, a `{host}` URL template variable) with no `packages` entry. For a
  remote, bring-your-own-host server that is schema-valid and complete: remote entries
  need no published package, the `{host}` template variable is the documented
  self-hosted pattern, and the description is already inside the registry's 100-character
  limit. No redesign — the only missing input is the human GitHub login.

- **Use the GitHub-OAuth namespace; no DNS verification is needed.** The name
  `io.github.leonardsellem/hypermnesic` is proven by `mcp-publisher login github`, not by
  the remote host. Reverse-DNS / custom-domain verification applies only to a
  `me.sellem/*`-style name, which hypermnesic deliberately does not use. This keeps the
  one human gate to a single device-code login.

- **Hand-submit only the directories that do not auto-ingest.** Smithery (bring-your-own
  hosting, no `smithery.yaml` required because it proxies to an upstream server) and
  mcp.so (community-submitted via its GitHub Issue #1) do not pull from the official
  registry, so they get explicit submissions. PulseMCP gets nothing by hand unless it
  fails to auto-list — then a metadata-correction email is the lever, not a fresh
  submission.

- **Skip mcp-get.** It is a package-install-manager registry (npm / PyPI shaped) and is
  largely superseded by the Official MCP Registry as the canonical source. hypermnesic is
  a remote-only server with no installable MCP-server package shape, so the fit is poor
  and the incremental traffic is low. Listing it would be effort spent against the wrong
  surface.

- **Treat Glama and awesome-mcp-servers as done submissions, not open work — but verify
  both before claiming either.** The remaining repo-side action for both is README
  badges. Per the claims rules, the Glama "A" Tool-Definition-Quality letter is an
  external Glama-side result and the awesome-mcp-servers "merged" state is contradicted by
  repo evidence (PR `#8056` recorded open). Neither is asserted in public copy until
  confirmed at its source.

- **Compete on ownership, compounding, and reviewable writes — even in a directory
  blurb.** Every listing carries the same one-line wedge: Markdown files are truth, the
  index is disposable, writes are reviewable commits. The directory entries are a
  distribution surface for the positioning, not a generic "memory server" line that blends
  into the crowd.

## Requirements

**Official MCP Registry publication**

R1. The staged `docs/launch/mcp-registry-server.draft.json` MUST be published to the
Official MCP Registry under the name `io.github.leonardsellem/hypermnesic`, via the
`mcp-publisher` CLI, without altering the `remotes` / `{host}` template shape.

R2. Publication MUST follow the verified command sequence: download the `mcp-publisher`
binary, copy the draft to a root `server.json`, run `mcp-publisher validate`, run
`mcp-publisher login github`, run `mcp-publisher publish`. The `mcp-publisher login
github` device-code step is operator-gated and MUST be performed by the human operator.

R3. The published name, title, description, and repository link MUST match the canonical
values in the draft; the description MUST stay within the registry's 100-character limit.

R4. Publication MUST be verified by querying the registry for
`io.github.leonardsellem/hypermnesic` and recording the JSON result, before the listing is
referenced anywhere as live.

R5. Re-publishing on each future release MUST use the additive `isLatest` versioning the
registry already supports (supersede, never delete-and-replace); the root `server.json`
version MUST track the engine version on each release.

**Hand-submitted directories**

R6. hypermnesic MUST be submitted to Smithery via its bring-your-own-hosting path, by the
public `/mcp` endpoint URL, under the canonical `leonardsellem/hypermnesic` org/name; no
`smithery.yaml` is required because Smithery proxies to the upstream server. If an
unclaimed crawled entry already exists, it MUST be claimed rather than duplicated.

R7. The exact Smithery bring-your-own-hosting wizard fields and OAuth-flow specifics, and
the CLI `smithery mcp publish` flags, MUST be confirmed at submission time against
Smithery's own surface before relying on either route.

R8. hypermnesic MUST be submitted to mcp.so via the reliable GitHub-issue path — a comment
linking the server on `chatmcp/mcpso` Issue #1 ("Submit Your MCP Servers here"). The web
`/submit` form is an acceptable alternate only after its live fields are confirmed in an
authenticated browser.

R9. PulseMCP MUST NOT be hand-submitted on the assumption it will not auto-ingest; the
default path is to let it ingest from the Official MCP Registry. About one week after R1,
the PulseMCP listing MUST be checked; if absent or carrying wrong metadata, a correction
email to `hello@pulsemcp.com` is the remedy.

R10. Every hand-submitted entry's blurb MUST carry the ownership-and-compounding wedge
(files are truth, the index is disposable, writes are reviewable commits) and link the
README quick start, consistent with the canonical name and description.

**Repo-side badges and listing hygiene**

R11. The README badge row MUST add the Glama score badge using the exact working path
`https://glama.ai/mcp/servers/ak6x81u3rr/badges/score.svg`; the `…/badge.svg` path (404)
and the `…/badge` oversized card MUST NOT be used.

R12. The README SHOULD add an awesome-mcp-servers "Mentioned in Awesome" badge, gated on
R15 confirming the entry is actually merged; if the PR is still open, the badge MUST NOT be
added and the state MUST be recorded as "submitted / PR open".

R13. The README badge additions MUST keep the existing CI, PyPI, and License badges and
their order, and MUST NOT introduce any private host, token, or local path into the public
surface.

**Claim verification (gates public assertions)**

R14. The Glama "A" Tool-Definition-Quality grade MUST be confirmed on the live listing
`ak6x81u3rr` before the letter grade appears in any public copy; absent confirmation, copy
MAY state only the provable effort (full tool descriptions, 100% parameter-description
coverage), not the grade.

R15. The awesome-mcp-servers PR `#8056` merge state MUST be confirmed against the upstream
`punkpeye/awesome-mcp-servers` before "merged" is claimed anywhere; if open, the claim MUST
be downgraded to "submitted / PR open".

R16. No directory listing MAY be referenced as live until verified at its own source — the
Official MCP Registry via R4, Smithery / mcp.so via their listing URLs, PulseMCP via R9.
The voice rule against claiming an official-registry listing before publication MUST hold
until R4 passes.

## Success Criteria

- A query to the Official MCP Registry for `io.github.leonardsellem/hypermnesic` returns
  the published entry, recorded as an artifact.
- hypermnesic is live and discoverable on Smithery and mcp.so under the canonical name,
  each with the ownership-and-compounding blurb and a working README link.
- The PulseMCP listing is confirmed present (auto-ingested) within roughly one week of
  R1, or corrected by email; its metadata matches canonical.
- The README shows the Glama score badge via the correct `/badges/score.svg` path, and the
  awesome badge if and only if the entry is confirmed merged.
- Every public claim about a listing or grade is backed by a confirmation at its source;
  no "merged" or "A grade" claim ships unverified.
- The mcp-get registry is consciously and visibly skipped, with the reason recorded so it
  is not re-litigated later.

## Scope Boundaries

### Deferred for later

- Adding a PyPI-package-backed `packages` entry to the registry `server.json`. PyPI install
  is live, but the registry remote entry stands on its own; a `packages` entry (and the
  `mcp-name` README verification string it requires) is a later enrichment, and is the only
  thing that would also make mcp-get worth revisiting.
- The Obsidian community-plugin directory submission for the companion. The branch is
  prepared, but it is a separate repo and a distinct audience; it belongs to the companion's
  own distribution track, not this MCP-server fan-out.
- Any committed Dockerfile work to make the HTTP server Glama-buildable. Glama already
  lists hypermnesic on metadata plus the TDQS push; making the server statically
  inspectable is a separate deploy-surface concern.
- Listing on additional or future MCP directories beyond the named set, and any paid or
  sponsored placement.

### Outside this product identity

- A hosted-SaaS, multi-tenant, or managed-cloud listing. hypermnesic is self-hosted; every
  entry is a bring-your-own-host remote server, never a hosted service.
- Generic "memory server" blurbs that drop the ownership-and-compounding wedge to blend in.
- Any benchmark figure in a directory entry presented as full-product proof or quoted
  outside the published comparability envelope.
- Chasing the Glama overall coherence letter via tool renames; the engine intentionally
  does not break tool names for a higher overall grade.

## Dependencies / Assumptions

- The single human-gated step is `mcp-publisher login github` (device-code flow); the
  operator must run it for R1–R4 to complete. Everything downstream of publication is
  unblocked once it lands.
- The public `/mcp` OAuth 2.1 endpoint is reachable and stable, since the registry, Smithery,
  and mcp.so entries all point at it; the registry performs no publish-time reachability
  check, but a live endpoint is assumed for the listings to be useful.
- The Glama listing `ak6x81u3rr` and the awesome-mcp-servers PR `#8056` remain the correct
  identifiers to verify against.
- Downstream auto-ingest behaviour (PulseMCP daily ingest / weekly processing from the
  official registry) holds as documented; R9 exists precisely to catch the case where it
  does not.
- The canonical name, title, description, and tags are those in the seed and the staged
  draft; no new naming is invented for any directory.

## Outstanding Questions

### Resolve before planning

- Will the operator run `mcp-publisher login github` in the planning/execution window? The
  entire cascade is gated on it; if not, the initiative stalls at R1 and the plan must
  sequence around the wait.
- What is the actual merge state of awesome-mcp-servers PR `#8056` right now? It decides
  whether R12 adds the awesome badge or the copy says "PR open", and it must be checked
  before any "merged" claim (R15).
- Does the live Glama listing `ak6x81u3rr` currently show the "A" Tool-Definition-Quality
  grade? It gates whether public copy may use the letter or only the effort (R14).

### Deferred to planning

- Smithery web wizard versus CLI (`smithery mcp publish <url> -n <org>/<server>`): which
  route to use, and confirming the exact fields and flags at submission time (R7).
- Whether a hypermnesic entry already exists to claim on Smithery (from its crawl) or must
  be created fresh (R6).
- The mcp.so route choice — GitHub Issue #1 comment (confirmed reliable) versus the
  login-gated web form (fields unread) (R8).
- The precise PulseMCP check date and the metadata-correction email contents, if the
  auto-listing is wrong (R9).

## Sources / Research

Internal:

- `docs/launch/directory-submission-prep.md` — target directories, copy-ready draft
  entries, current submission state, and the operator pause points.
- `docs/launch/mcp-registry-server.draft.json` — the staged, schema-valid registry entry.
- `docs/launch/promo-grounding-brief.md` — positioning confirmations and the
  corrections/enrichments (PyPI live; registry not yet published; awesome-mcp-servers and
  Glama grade need verification).
- `docs/launch/launch-narrative-drafts.md` — approved claims-allowed / claims-avoid lists
  and the canonical story voice.
- `docs/launch/launch-sequencing.md` — where directory updates sit in the launch order.
- `docs/why-hypermnesic.md` — the canonical differentiation framing carried into blurbs.
- `README.md` — current badge row (CI, PyPI, License; Glama and awesome badges absent) and
  canonical product description.

External:

- modelcontextprotocol.io/registry (about, quickstart, remote-servers) — the
  `mcp-publisher` flow, the remote-server `remotes` block, URL template variables, the
  GitHub-OAuth namespace, the 100-character description limit, and additive `isLatest`
  versioning.
- pulsemcp.com/submit — PulseMCP ingests official-registry entries daily and processes them
  weekly; `hello@pulsemcp.com` for expedite or metadata correction.
- Smithery bring-your-own-hosting docs — gateway proxies to an upstream server; Streamable
  HTTP + OAuth requirements; no `smithery.yaml` for a remote BYO-hosting listing.
- `github.com/chatmcp/mcpso` Issue #1 — the community submission path for mcp.so.
- glama.ai/mcp/servers/ak6x81u3rr — the live Glama listing to verify the grade and the
  correct `/badges/score.svg` badge path.
- `github.com/punkpeye/awesome-mcp-servers` PR `#8056` — the awesome-mcp-servers entry whose
  merge state must be confirmed.
- truefoundry.com/blog/best-mcp-registries — the metaregistry / downstream-ingest landscape.
