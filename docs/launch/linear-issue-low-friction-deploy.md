---
title: "Kill the install barrier — committed Docker/compose + one-click Railway deploy"
estimate: 1
priority: High
labels: [launch, distribution, docs, devex]
related_paths:
  - docs/brainstorms/2026-06-25-low-friction-deploy-requirements.md
  - docs/plans/2026-06-25-004-content-low-friction-deploy-plan.md
related_linear:
  - LS-1683
  - LS-1684
  - LS-1689
parent: null
sub_issues:
  - title: "Commit a root Dockerfile reconciled with render_docker() + Glama-inspectable (M1)"
    estimate: 3
    summary: >
      U1 + U5. Author a committed repo-root Dockerfile that installs the published
      engine and serves the MCP endpoint, with render_docker() (install.py lines
      199–222) as the single source of record so the runtime emitter and the committed
      file cannot drift — guarded by a failing-if-divergent test. No secret ever baked
      in (test asserts no sk-/consent-token/PAT; .dockerignore keeps .env/.hypermnesic
      out of build context). Enrich glama.json to reference the committed build so the
      static inspector can stand up the running HTTP server, and record the live
      ak6x81u3rr listing state before/after — without asserting any letter grade.
      Foundation milestone that unblocks every other sub-issue.
  - title: "Commit the self-host compose.yaml — engine + Tailscale-Funnel sidecar (M2)"
    estimate: 5
    summary: >
      U2 + U3 + U6 (compose half) + U7 (partial). Commit compose.yaml + funnel.json at
      repo root: a Tailscale sidecar (TS_USERSPACE, TS_STATE_DIR on a named volume,
      TS_SERVE_CONFIG=funnel.json) fronting the engine via network_mode:
      service:tailscale so Funnel reaches it on loopback, exactly mirroring the live
      homelab topology — host owns 443, no reverse proxy. One persistent named volume
      holds the cloned git vault + its disposable .hypermnesic index; funnel.json serves
      the OAuth well-knowns alongside /mcp over HTTPS. Document the Funnel ACL-attribute
      gotcha plainly (AllowFunnel is ignored without the node `funnel` attribute), the
      persistence + scoped-deploy-token contract, and the compose run path in the
      runbook + README three-lane copy — in the same change. This is the primary
      artifact and ships before the one-click button.
  - title: "Ship the one-click Railway template — platform-edge TLS lane (M3)"
    estimate: 5
    summary: >
      U4 + U6 (Railway half) + U7 (remainder). Commit railway.json config-as-code
      (build from the committed Dockerfile, start command mirroring the compose
      serve … --enable-write, health-check path, Volume mount), define template form
      inputs (OPENAI_API_KEY optional with lexical-degrade documented; consent secret
      required; vault git URL + a scoped deploy token, never full-account), attach a
      persistent Volume for vault + index + OAuth DCR/token state, drop Funnel for the
      Railway HTTPS edge, and wire the OAuth issuer/redirect/resource URLs to the exact
      *.up.railway.app hostname (strict matching). Publish the Template, add the "Deploy
      on Railway" button to the README, and finish the runbook/configuration/CHANGELOG/
      ARCHITECTURE updates. Ordered last — most new surface (platform edge + OAuth
      hostname rewiring).
---

## Context

Self-hosting is hypermnesic's adoption ceiling. The whole pitch — your files, your git
history, your OAuth `/mcp` endpoint — means there is no hosted SaaS to click into; every
new user must stand up the engine themselves. Today that is an afternoon of VPS +
Tailscale login + `funnel` ACL grant + OpenAI key + vault clone + a hand-written systemd
unit. The runbook (`docs/unified-oauth-mcp-deploy-runbook.md`) is faithful to the
operator's homelab but reads as an expert's checklist, not a newcomer's on-ramp. The repo
ships **no committed `Dockerfile` and no compose file**: `src/hypermnesic/install.py`
`render_docker()` emits them into the state dir only at runtime under
`hypermnesic install --service=docker`, so nothing container-shaped is inspectable,
reviewable, or copy-runnable from the tree. That same absence blocks Glama: its static
inspector builds an MCP server from a committed Docker build, and with no committed
Dockerfile (and a `glama.json` that references no build — today it holds only `$schema`
and `maintainers`) Glama cannot stand up the running server, so the listing rests on
metadata alone. A launch that leads with "self-hosted, you own it" while the self-host
path is undocumented friction loses the curious-but-busy reader at the worst moment.

This epic executes the 21 requirements (R1–R21) from the
[low-friction-deploy brainstorm](docs/brainstorms/2026-06-25-low-friction-deploy-requirements.md)
via the seven Implementation Units (U1–U7) of the
[canonical plan](docs/plans/2026-06-25-004-content-low-friction-deploy-plan.md). The
load-bearing constraint is that **Tailscale Funnel and a PaaS edge cannot share port
443** (Funnel terminates TLS on the node, serves only `*.ts.net`, and cannot sit behind
another TLS proxy), which forces a structural lane split rather than one pretend-uniform
ingress story. `hypermnesic local-proof` stays the no-account lead across all of it.

## Intent

Lower the self-host ceiling by shipping a committed, reviewable container path and a
one-click PaaS template so a stranger stands up their own public OAuth `/mcp` endpoint in
minutes — **without weakening files-are-truth, the git-first guarded `commit_note` write,
or the OAuth endpoint**. Deliver three honestly-labeled lanes, named by where TLS
terminates:

- **Lane 1 — `local-proof` (already shipped, the lead):** `uv tool install hypermnesic`
  then `hypermnesic local-proof` — no account, no endpoint, the truly-curious first taste.
- **Lane 2 — committed self-host compose (Tailscale Funnel):** engine + Tailscale sidecar,
  the host owns 443, the live Funnel topology preserved verbatim. Ships first.
- **Lane 3 — one-click Railway template (platform-edge TLS):** Railway owns 443, Funnel
  dropped, OAuth wired to the `*.up.railway.app` hostname. Ships second.

Scope is the plan's three milestones (M1 foundation → M2 compose → M3 button), tracked as
the three sub-issues below. Because it spans seven units across three milestones (well
beyond an estimate of 8), this is an **epic** (estimate 1); the sub-issues carry the
work. Deferred by the plan and out of scope here: Fly.io / Render variants, a
Cloudflare-Tunnel compose profile, OS packaging, and any managed/hosted instance.

## Acceptance Criteria

Each criterion is independently verifiable on the PR(s) for the relevant sub-issue.

- [ ] **AC1 — Committed Dockerfile, no drift (U1, R1/R2).** A `Dockerfile` exists at the
  repo root, builds a runnable engine image (`FROM python:3.11-slim`, installs the engine,
  `ENTRYPOINT ["hypermnesic"]`), and a `tests/` guard fails if it diverges from
  `render_docker()` (`install.py` lines 199–222) — `render_docker()` is the single source
  of record.
- [ ] **AC2 — No baked secrets (U1, R3).** No image, compose file, or template inlines
  `OPENAI_API_KEY`, the OAuth consent secret, or any vault credential; a test asserts the
  build contains no `sk-` / consent-token / PAT, and `.dockerignore` keeps `.env` and
  `.hypermnesic/` out of build context.
- [ ] **AC3 — Glama-inspectable build referenced (U5, R19).** `glama.json` is enriched with
  only schema-valid build/run fields referencing the committed Dockerfile (the
  `maintainers` field preserved), and the live `ak6x81u3rr` listing state is recorded
  before/after. **No letter-grade ("A") claim appears anywhere unless the live page shows
  it.**
- [ ] **AC4 — Self-host compose brings up the Funnel endpoint (U2, R4/R5/R6).** A committed
  root `compose.yaml` runs a Tailscale sidecar + engine with
  `network_mode: service:tailscale`; on a tailnet-member VPS holding the `funnel`
  attribute, `docker compose up -d` brings both containers healthy and exposes `/mcp`
  publicly over HTTPS with no reverse proxy.
- [ ] **AC5 — OAuth discovery resolves over Funnel (U2, R7).** Committed `funnel.json`
  (`TS_SERVE_CONFIG`) serves the OAuth discovery well-knowns alongside `/mcp`;
  `https://<your-host>.ts.net/.well-known/oauth-protected-resource` and `.../mcp` resolve
  over HTTPS, and an MCP client completes OAuth and round-trips a read tool.
- [ ] **AC6 — Funnel ACL gotcha documented (U3, R8).** The runbook prose **and** an inline
  comment in `compose.yaml`/`funnel.json` state that Funnel requires the node `funnel` ACL
  attribute and that `AllowFunnel` is silently ignored without it, with the minimal
  `nodeAttrs` grant snippet (placeholder hostnames only).
- [ ] **AC7 — One-click Railway deploy stands up an endpoint (U4, R9/R10/R11).** A
  committed root `railway.json` builds from the Dockerfile with a Volume mount; a
  from-scratch deploy via the "Deploy on Railway" button stands up a working endpoint over
  Railway's native HTTPS edge (Funnel dropped), with form inputs for `OPENAI_API_KEY`
  (optional), the consent secret (required), the vault git URL, and a **scoped** deploy
  token.
- [ ] **AC8 — OAuth wired to the platform hostname, no mismatch (U4, R12).** The template
  sets the public base URL to the assigned `https://<app>.up.railway.app` so the issuer and
  registered redirect/resource URIs match exactly; an authorized MCP client reads with
  **no** redirect-URI mismatch.
- [ ] **AC9 — Persistence across restart/redeploy (U6, R16/R17).** Each hosted lane mounts
  one persistent volume holding the cloned vault, its `.hypermnesic/` index, **and** OAuth
  DCR/bearer/refresh state; a restart/redeploy preserves vault git history, keeps a
  previously-recall-able note recall-able, and a previously-authorized client reconnects
  without a fresh browser consent.
- [ ] **AC10 — Sensitive volume + scoped token documented (U6, R18).** `configuration.md`
  and the runbook document the vault+token volume as sensitive, require owner-only perms
  (`chmod 700`/`600`), and require the vault credential to be a scoped deploy token, never
  a full-account credential.
- [ ] **AC11 — Files-are-truth preserved across every lane (U6, R13/R14/R15).** No lane
  introduces a database of record or an index-direct write; the `commit_note` guarded write
  path is unchanged; lexical-only degraded mode remains a supported, visible state so an
  absent `OPENAI_API_KEY` at deploy is supported (a per-lane one-liner reaffirms this).
- [ ] **AC12 — Three honest lanes, `local-proof` leads, docs in the same PR (U7,
  R20/R21).** The README and runbook name all three lanes with their TLS model;
  `local-proof` is still first; the README carries the button + three-lane summary while
  the runbook carries the step-by-step; CHANGELOG has a dated `[Unreleased]` entry; **no
  doc implies a hosted SaaS, always-on dense retrieval, a writable Obsidian companion, an
  official MCP Registry listing, an awesome-mcp-servers *merge*, or a Glama letter grade.**
- [ ] **AC13 — Full gate set green on every artifact PR.** `uv run ruff check .`,
  `uv run python scripts/check_version_consistency.py`, `uv run pytest`,
  `uv run python scripts/license_scan.py`, and
  `uv run python scripts/preflight_public_scan.py` all pass — including no operator
  host/IP/token in any new doc or fixture (placeholders only).

## Validation Plan

How each criterion is proven, and the evidence artifact attached to the PR/issue.

| AC | How it is proven | Evidence artifact |
|---|---|---|
| AC1 | Run `docker build -t hypermnesic .`; run the no-drift test | Build-log tail (engine installs; entrypoint `hypermnesic`) + no-drift test output |
| AC2 | Run the no-baked-secret test; inspect `.dockerignore` | Test output asserting no `sk-`/consent-token/PAT; `.dockerignore` diff |
| AC3 | Load `https://glama.ai/mcp/servers/ak6x81u3rr` before and after the build lands | Before/after screenshots + recorded current-state note; `glama.json` diff |
| AC4 | On a tailnet-member VPS with the `funnel` attribute, `docker compose up -d`; `docker compose ps` | `docker compose ps` showing both healthy + redacted `tailscale funnel status` |
| AC5 | `curl` the two well-known/`/mcp` URLs; run an MCP client OAuth + read | Redacted `curl` output / status codes + a successful authorized read transcript |
| AC6 | Reviewer reads the runbook + inline comments cold | Reviewer confirmation + the `nodeAttrs` snippet in the diff |
| AC7 | Deploy from scratch via the Railway button | Template URL + deploy screenshot + reachable-endpoint check |
| AC8 | Complete OAuth from an MCP client against the Railway host | Discovery JSON at `<app>.up.railway.app` + authorized-read transcript with no mismatch |
| AC9 | Restart compose / redeploy Railway; re-run a recall + reconnect a prior client | Before/after: vault `git log` intact, note still recall-able, client reconnects sans consent |
| AC10 | Reviewer confirms the sensitive-volume + scoped-token prose | Diff of `configuration.md` + runbook persistence/security sections |
| AC11 | Reviewer confirms no DB-of-record / index-direct write; lexical-degrade reaffirmed | Per-lane one-liner in the diff; degraded-mode note in `configuration.md` |
| AC12 | Reviewer confirms three lanes + TLS models, `local-proof` first, claims clean | README + runbook diffs; CHANGELOG `[Unreleased]` entry; claims read-through |
| AC13 | Run the six-command gate set locally and in CI | CI `lint-test-license` green + local run output on the PR |

## Definition of Done

- All three sub-issues are **Done** (deployed + verified), each artifact committed **with
  its docs in the same PR** (no "later").
- Every acceptance criterion AC1–AC13 has its evidence artifact captured on the relevant
  PR/issue.
- The full gate set passes on every artifact PR (AC13).
- End-to-end proof captured for the load-bearing behaviors: a working Funnel endpoint from
  compose on a real tailnet-member VPS (AC4/AC5); a working Railway button deploy with a
  clean authorized read (AC7/AC8); and a restart/redeploy of each lane that loses no
  committed memory and forces no re-consent (AC9).
- Files-are-truth and the disposable index hold in every lane; the guarded `commit_note`
  write is unchanged; no database of record is introduced anywhere (AC11).
- The install narrative leads with `local-proof` and names three lanes by TLS model; no
  doc overclaims (no hosted SaaS, no always-on dense, no writable companion, no MCP
  Registry listing, no awesome-mcp-servers merge, no Glama letter grade) (AC12).
- Related launch issues are linked as `related` (LS-1683 directory submissions —
  Glama/awesome-mcp precondition feeds it; LS-1684 PyPI install the deploy image relies on;
  LS-1689 launch narrative whose three-lane copy this realizes).

## Links

- Canonical plan: [`docs/plans/2026-06-25-004-content-low-friction-deploy-plan.md`](docs/plans/2026-06-25-004-content-low-friction-deploy-plan.md)
- Origin brainstorm: [`docs/brainstorms/2026-06-25-low-friction-deploy-requirements.md`](docs/brainstorms/2026-06-25-low-friction-deploy-requirements.md)
- Positioning + claims grounding: [`docs/launch/promo-grounding-brief.md`](docs/launch/promo-grounding-brief.md)
- Runtime Docker emitter (source of record): `src/hypermnesic/install.py` — `render_docker()` (lines 199–222)
- Live deploy runbook (compose lane preserves this topology): [`docs/unified-oauth-mcp-deploy-runbook.md`](docs/unified-oauth-mcp-deploy-runbook.md)
- Env-var / degraded-mode contract: [`docs/reference/configuration.md`](docs/reference/configuration.md)
- Glama precondition for awesome-mcp-servers: [`docs/launch/directory-submission-prep.md`](docs/launch/directory-submission-prep.md)
- Glama listing (verification surface): `https://glama.ai/mcp/servers/ak6x81u3rr`
- Related Linear: LS-1683 (Submit to MCP and Obsidian directories), LS-1684 (PyPI publication), LS-1689 (launch narrative + per-channel posts)

> GitHub permalinks for the plan and brainstorm are substituted for the repo-relative
> paths above at Linear-issue creation time.
