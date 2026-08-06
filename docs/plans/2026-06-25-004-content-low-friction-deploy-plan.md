---
date: 2026-06-25
origin: docs/brainstorms/2026-06-25-low-friction-deploy-requirements.md
type: content
title: "Kill the install barrier — committed Docker/compose + one-click deploy plan"
tags: [hypermnesic, deploy, docker, compose, tailscale-funnel, oauth, railway, glama, distribution]
---

# Kill the install barrier — committed Docker/compose + one-click deploy plan

## Overview

Lower the self-host adoption ceiling by shipping a committed, reviewable container path
and a one-click PaaS template, so a stranger stands up their own public OAuth `/mcp`
endpoint in minutes instead of an afternoon of VPS + Tailscale + systemd toil — without
weakening files-are-truth, the git-first guarded `commit_note` write, or the OAuth
endpoint. The artifacts split by where TLS terminates: a Tailscale-Funnel self-host
compose lane (the host owns 443) and a platform-edge-TLS one-click lane (Railway owns
443, Funnel dropped). `hypermnesic local-proof` stays the no-account lead. This plan
*describes* the files to create during execution (a root `Dockerfile`, `compose.yaml`, a
Railway template, an enriched `glama.json`) and the docs each touches; it creates none of
them now.

## Goals / Non-goals

**Goals**

- Commit a single, reviewable `Dockerfile` reconciled with the engine's existing
  `render_docker()` (one build recipe, no parallel drift) — R1, R2, R3.
- Commit a `compose.yaml` self-host lane that preserves the live Tailscale-Funnel
  public-HTTPS topology verbatim (engine + Tailscale sidecar, shared netns, Funnel
  serving `/mcp` + OAuth well-knowns over HTTPS, no reverse proxy) — R4–R8.
- Ship a one-click Railway template (public repo + committed Dockerfile as source) that
  forms the required secrets, attaches a persistent volume, drops Funnel for the platform
  HTTPS edge, and wires the OAuth issuer/redirect/resource URLs to the platform-assigned
  hostname — R9–R12.
- Preserve files-are-truth, the guarded write, and dense-degrades-to-lexical across every
  lane; persist the vault, the disposable index, and OAuth DCR/token state across restarts
  — R13–R18.
- Make the running HTTP MCP server buildable/inspectable by Glama from the committed
  Dockerfile, referenced from `glama.json`, and verify the live listing (`ak6x81u3rr`) —
  R19.
- Keep `local-proof` the lead and update every doc each artifact touches in the same
  change — R20, R21.

**Non-goals**

- No Fly.io (`fly.toml`) or Render (`render.yaml`) one-click variant — deferred
  alternatives offered only after Railway proves out (`flyctl`-first / disk-on-paid-only).
- No Cloudflare-Tunnel (`cloudflared`) custom-hostname compose profile yet — a second
  blessed profile after the Funnel profile lands.
- No OS packaging (Homebrew tap, `.deb`, Windows) — out of band.
- No managed/operator-run hosted instance, no hosted SaaS, no multi-tenant cloud — the
  product is self-hosted by identity.
- No database-of-record or index-direct write; no secret baked into any image or template;
  no writable Obsidian companion; no "dense always on" framing — all contradict shipped,
  honest behavior.

## Implementation Units

Stable U-IDs. Each maps to requirement IDs (R1–R21) from the origin brainstorm. The
compose lane (U2/U3) ships before the one-click button (U4); Glama (U5) rides on U1.

### U1 — Commit a root Dockerfile reconciled with `render_docker()`

**Goal.** A single committed, reviewable engine image build that installs the published
package and serves the MCP endpoint, with the runtime emitter and the committed file
sharing one source so they cannot drift, and no secret ever baked in. (R1, R2, R3.)

**Steps.**
1. Read the existing emitter: `src/hypermnesic/install.py` `render_docker()` (lines
   199–222). It returns a `FROM python:3.11-slim` Dockerfile —
   `WORKDIR /app` / `COPY . /app` / `RUN pip install --no-cache-dir .` /
   `ENTRYPOINT ["hypermnesic"]` — plus a compose snippet whose `command` is
   `serve --index-db /app/.hypermnesic/index.db --host <bind> --port <port> --path <path>
   --enable-write` with `env_file: .env` (the secret discipline: `OPENAI_API_KEY` supplied
   at runtime, never inlined). This is the native primitive to reuse, not re-invent.
3. Choose the no-drift mechanism and record it as the resolved answer to the brainstorm's
   "root vs `deploy/`" question: **commit the Dockerfile + compose at the repo root** (so
   Glama and `docker compose up` find them with zero path config), and **make
   `render_docker()` the generator of record** by having it emit the *same* bytes — either
   (a) `render_docker()` reads the committed root files and copies them into the state dir,
   or (b) a tiny test asserts the committed files are byte-identical to `render_docker()`'s
   output. Prefer (a) (single source); fall back to (b) if `install --service=docker` must
   stay self-contained. Either way a `tests/` guard (test-first per AGENTS.md) fails if the
   two diverge.
4. Author the committed `Dockerfile` at repo root: keep `FROM python:3.11-slim`; install
   the engine (prefer `pip install hypermnesic` from PyPI for the deploy image so it does
   not depend on a local checkout, with a build-arg to pin a version; keep the
   `COPY . && pip install .` form available for the Glama/local-build path); `ENTRYPOINT
   ["hypermnesic"]`. Add a comment line stating secrets are runtime-only.
5. Run the full gate set (`uv run ruff check .`,
   `uv run python scripts/check_version_consistency.py`, `uv run pytest`,
   `uv run python scripts/license_scan.py`,
   `uv run python scripts/preflight_public_scan.py`) — the license scan must stay green for
   anything the build pulls in, and the preflight scan must confirm no operator host/token
   shipped.

**Files / Surfaces.** `Dockerfile` (new, repo root); `src/hypermnesic/install.py`
(`render_docker()` reconciliation); `tests/` (new no-drift + no-baked-secret test);
`.dockerignore` (new, to keep `.env` / `.hypermnesic/` out of build context).

**Validation.** `docker build -t hypermnesic .` succeeds locally (capture the build log
tail showing the engine installs and the entrypoint is `hypermnesic`); the no-drift test
passes (paste output); `grep`-style proof in the test that the image/compose contain no
`sk-`, no consent-token value, no PAT; PR link.

**Dependencies.** None (foundation for U2, U4, U5).

### U2 — Commit the self-host `compose.yaml` (engine + Tailscale-Funnel sidecar)

**Goal.** A copy-runnable two-container compose that brings up the public OAuth `/mcp`
endpoint over Tailscale Funnel exactly as the live homelab does — host owns 443, node is a
real tailnet member, no reverse proxy — mounting one persistent volume for the vault and
the disposable index. (R4, R5, R6, R16.)

**Steps.**
1. Author `compose.yaml` at repo root with two services:
   - `tailscale` sidecar (official `tailscale/tailscale` image): env `TS_AUTHKEY`
     (document appending `?ephemeral=true` for auto-cleanup), `TS_USERSPACE=true`
     (required where there is no `/dev/net/tun`), `TS_STATE_DIR=/var/lib/tailscale` on a
     **named volume** (persists node identity across restarts), and
     `TS_SERVE_CONFIG=/config/funnel.json` (the JSON drives both Serve and Funnel).
   - `hypermnesic` engine service built from the U1 Dockerfile, with
     `network_mode: service:tailscale` so the sidecar fronts it and Funnel reaches the
     engine on **loopback** (R6). `command:` mirrors `render_docker()`’s
     `serve --index-db /data/vault/.hypermnesic/index.db ... --enable-write`; secrets via
     `env_file: .env` only (R3).
2. Mount one persistent **named volume** (e.g. `vault:/data/vault`) holding the cloned
   git vault **and** its `.hypermnesic/` index, so a restart loses no committed memory
   (R16). Document a boot step that clones the vault git URL into that volume on first run
   using a scoped deploy token (see U6).
3. Ship `funnel.json` (the `TS_SERVE_CONFIG`) committed alongside compose: set
   `TCP.443.HTTPS=true`, a `Web` handler proxying `https://${TS_CERT_DOMAIN}:443` to the
   engine’s loopback `/mcp` port, and `AllowFunnel: {"${TS_CERT_DOMAIN}:443": true}`.
   Ensure the handler also serves the OAuth discovery well-knowns alongside `/mcp` so the
   OAuth 2.1 discovery chain resolves over HTTPS exactly as the live endpoint (R7).
4. Provide a `.env.example` addition (or a compose-scoped example) naming the runtime vars
   without values: `OPENAI_API_KEY`, `HYPERMNESIC_CLOUD_APPROVAL_TOKEN`,
   `HYPERMNESIC_DEFAULT_CLIENT_SCOPES`, the vault git URL, the scoped deploy token, and
   `TS_AUTHKEY` — using placeholders (`<your-host>.ts.net`, `100.64.0.0/10` CGNAT range),
   never real operator values (preflight scan enforces this).
5. Document the run path in the deploy runbook (U7): `docker compose up -d`, granting the
   tailnet `funnel` ACL attribute, and the loopback wiring.

**Files / Surfaces.** `compose.yaml` (new, repo root); `funnel.json` (new — the
`TS_SERVE_CONFIG`); `.env.example` (add compose vars, placeholders only);
`docs/unified-oauth-mcp-deploy-runbook.md` (the compose run path, updated in U7).

**Validation.** On a test VPS that is a tailnet member with the `funnel` attribute:
`docker compose up -d` brings both containers healthy; `curl
https://<your-host>.ts.net/.well-known/oauth-protected-resource` and `.../mcp` resolve
over HTTPS (capture redacted output / status codes); an MCP client completes OAuth and a
read tool round-trips. Capture container `docker compose ps` and a redacted `tailscale
funnel status`. PR link.

**Dependencies.** U1 (the engine image), U6 (secret/volume contract), U7 (docs).

### U3 — Document the Funnel ACL gotcha in the compose lane

**Goal.** State plainly, where a self-hoster will read it, that Funnel requires the node
to hold the tailnet `funnel` ACL attribute and that `AllowFunnel` is silently ignored
without it — the single most common community failure. (R8.)

**Steps.**
1. In the compose section of `docs/unified-oauth-mcp-deploy-runbook.md` (and a short
   call-out comment in `funnel.json` / `compose.yaml`), add: "Funnel requires the
   `funnel` node attribute in your tailnet ACL. `AllowFunnel: true` is **ignored** without
   it — the endpoint will appear up on the tailnet but never reach the public internet."
2. Link the exact Tailscale ACL doc and show the minimal `nodeAttrs` grant snippet
   (placeholder hostnames only).

**Files / Surfaces.** `docs/unified-oauth-mcp-deploy-runbook.md`; inline comments in
`compose.yaml` / `funnel.json`.

**Validation.** Reviewer confirms the ACL-attribute requirement is stated in the runbook
prose and inline; a fresh reader can act on it without external search. PR link.

**Dependencies.** U2.

### U4 — Ship the one-click Railway template (platform-edge TLS lane)

**Goal.** A single-PaaS one-click deploy (Railway, confirmed primary over Fly.io/Render
for its form-input + persistent-Volume support) that uses the public GitHub repo + the U1
Dockerfile as service source, forms the required secrets, attaches a persistent volume,
drops Funnel for Railway’s native HTTPS edge, and wires the OAuth issuer/redirect/resource
URLs to the platform-assigned hostname. (R9, R10, R11, R12.)

**Steps.**
1. Confirm and record **Railway as the single primary target** (resolves the brainstorm's
   "which PaaS" question): Railway renders a Template URL form for required env vars,
   accepts a public GitHub repo + Dockerfile as the service source, and offers an
   attachable persistent **Volume** — the three moving parts the stack needs. Fly.io and
   Render stay deferred (Fly is `flyctl`-first not a literal button; Render free tier
   cannot attach a persistent disk, disqualifying for a stateful git vault).
2. Add config-as-code `railway.json` (schema `https://railway.com/railway.schema.json`) at
   the repo root pinning: build from the committed Dockerfile; a start command mirroring
   the compose `serve … --enable-write`; a health-check path; and the Volume mount path
   (e.g. `/data/vault`). Record the resolved answer to "where config-as-code lives" =
   repo root `railway.json`.
3. Define the template form inputs (required env vars): `OPENAI_API_KEY` (decide
   required-vs-optional — default **optional**, since lexical-only degraded mode is a
   supported visible state per R15; document that dense retrieval is off until set),
   `HYPERMNESIC_CLOUD_APPROVAL_TOKEN` (the OAuth consent secret, **required**), the vault
   git URL, and a **scoped deploy token** (not a full-account credential). Attach a
   persistent Volume for the cloned vault + index (R10, R16).
4. Wire OAuth to the platform hostname: the template’s first job is setting the public base
   URL to the Railway-assigned `https://<app>.up.railway.app` so the issuer and the
   registered redirect/resource URIs **exactly** match (strict matching, no normalization
   slack — a mismatch silently breaks client authorization). Use the engine’s existing
   public-URL/resource flags (`serve-cloud … --resource …` per the config reference) driven
   from a Railway variable. Document Funnel is dropped and any Tailscale use is private-only
   or off (R11).
5. Publish the Railway Template and capture the share URL; add a "Deploy on Railway" button
   to the README deploy section (U7) pointing at it.

**Files / Surfaces.** `railway.json` (new, repo root); README deploy section (button +
copy, in U7); the deploy runbook PaaS-lane section. The Railway Template itself is created
in the Railway dashboard (external surface) and referenced by URL.

**Validation.** A from-scratch Railway deploy via the button stands up a working endpoint;
`https://<app>.up.railway.app/.well-known/oauth-protected-resource` and `/mcp` resolve at
the platform hostname; an MCP client completes OAuth with **no** redirect-URI mismatch
(capture the discovery JSON and a successful authorized read); redeploy preserves the vault
and authorized clients (U6). Capture the Template URL and a deploy screenshot. PR link.

**Dependencies.** U1 (image), U6 (persistence/secret contract), U7 (docs/button).

### U5 — Make the HTTP server Glama-inspectable; verify the live listing

**Goal.** Move the Glama listing past metadata-only by giving its static inspector a
committed Docker build to stand up the running HTTP MCP server, referenced from
`glama.json`, and verify what the live listing (`ak6x81u3rr`) actually shows so the
inspectability win is proven, not assumed. (R19.)

**Steps.**
1. Enrich `glama.json` (currently only `$schema` + `maintainers: ["leonardsellem"]`, no
   build) per the Glama server schema to reference the committed U1 Dockerfile / build so
   the inspector can build and run the server. Keep the maintainers field; add only schema-
   valid build/run fields.
2. Resolve the brainstorm's "wire `glama.json` now?" question to **yes** — committing the
   Dockerfile is the native-primitive move that unlocks Glama build, so reference it now
   rather than relying on the runtime-generated artifact.
3. Verify the live listing: load `https://glama.ai/mcp/servers/ak6x81u3rr` and record
   exactly what it shows today (build status, whether a running server is inspectable, and
   whether a Tool-Definition-Quality grade is displayed). **Do not assert an "A" grade in
   any copy** until confirmed on that live page — the repo proves the description/parameter
   effort, not the grade (claims rule).
4. After the Dockerfile + `glama.json` land, re-check the listing for a successful build /
   inspectable server and capture before/after.

**Files / Surfaces.** `glama.json` (enriched); `Dockerfile` (from U1, referenced).

**Validation.** Live `ak6x81u3rr` listing screenshot before and after showing the build /
inspectable-server status change; the recorded current-state note (so the win is evidenced,
not assumed). PR link. No letter-grade claim unless the live page shows it.

**Dependencies.** U1.

### U6 — Persist vault, index, and OAuth DCR/token state across restarts

**Goal.** Guarantee that both hosted lanes survive a restart without losing committed
memory and without forcing already-authorized clients back through browser consent, and
document the persistent volume (vault + cloned deploy token) as the sensitive surface with
owner-only perms and a scoped (never full-account) credential. (R16, R17, R18; preserves
R13/R14.)

**Steps.**
1. Confirm the persistence set: (a) the cloned git **vault**, (b) its `.hypermnesic/`
   **index** (disposable but cheaper to keep), and (c) the OAuth **DCR client
   registrations + bearer/refresh runtime state**. The cloud lane already persists DCR/token
   state in an owner-only location; map that path onto the attached volume in both
   `compose.yaml` (U2) and `railway.json` (U4) so a redeploy reuses it.
2. Document the env-var/persistence contract once, shared by both lanes (resolves the
   brainstorm "how the PaaS persists OAuth state alongside the vault" + "env-var contract"
   questions): which dir holds the vault, which holds OAuth state, owner-only `chmod 700`/
   `600`, and that the vault credential must be a **scoped deploy token** (e.g. a
   single-repo deploy key / fine-grained PAT), never a full-account credential (R18).
3. Reassert files-are-truth across lanes (R13) and the unchanged guarded `commit_note`
   write path (R14): no lane introduces a database of record or an index-direct write;
   the volume holds files + a rebuildable projection only. Add a one-line statement to the
   runbook per lane.

**Files / Surfaces.** `compose.yaml`, `railway.json` (volume mounts for vault + OAuth
state); `docs/unified-oauth-mcp-deploy-runbook.md` and
`docs/reference/configuration.md` (persistence + sensitive-volume + scoped-token docs).

**Validation.** Restart/redeploy each lane and show: the vault git history intact, a
previously-recall-able note still recall-able (read-time convergence), and a
previously-authorized MCP client reconnecting **without** a fresh consent flow. Capture
before/after for one client. PR link.

**Dependencies.** U2, U4.

### U7 — Update every doc the artifacts touch; keep `local-proof` the lead

**Goal.** Reflect the committed Dockerfile, compose path, and one-click button in the
deploy runbook, the configuration reference, and the install narrative in the **same
change** as each artifact; name all three lanes and which TLS model each uses; keep
`local-proof` the no-account lead, not a replacement. (R20, R21; AGENTS.md anti-drift
table.)

**Steps.**
1. `docs/unified-oauth-mcp-deploy-runbook.md`: add the committed-compose self-host lane
   (U2/U3 run path, Funnel ACL gotcha) and the Railway one-click lane (U4) beside the
   existing systemd+Funnel path; state the per-lane TLS model (compose = Funnel on the
   node’s 443; Railway = platform edge, Funnel dropped).
2. `docs/reference/configuration.md`: document any new deploy-time env vars / the vault
   git URL + scoped-deploy-token inputs and the persistence locations from U6; reaffirm
   lexical-only degraded mode so an absent `OPENAI_API_KEY` at deploy is a supported state
   (R15).
3. `README.md`: in the existing `## Quick start` / deploy area, keep `local-proof` leading
   (it already does — `uv tool install hypermnesic` then `hypermnesic local-proof`), then
   add the three-lane on-ramp: lane 1 `local-proof` (lead), lane 2 committed compose
   self-host, lane 3 the "Deploy on Railway" button — each honestly labeled by TLS model.
   Resolve the brainstorm "README vs runbook" question: the **button + the three-lane
   summary live in the README**; the full step-by-step lives in the runbook.
4. `CHANGELOG.md`: dated `[Unreleased]` entry for the committed Docker/compose path, the
   Railway button, and the `glama.json` build reference (user-visible).
5. `ARCHITECTURE.md`: if the serving picture gains the committed-container lane, note it in
   the serving section (the OAuth/Funnel topology itself is unchanged).
6. Run `scripts/check_version_consistency.py` and `scripts/preflight_public_scan.py` so no
   version drift and no operator host/token ships in any new doc (placeholders only).

**Files / Surfaces.** `docs/unified-oauth-mcp-deploy-runbook.md`,
`docs/reference/configuration.md`, `README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`;
`docs/launch/directory-submission-prep.md` (note the Glama build/listing change feeding the
awesome-mcp-servers Glama precondition).

**Validation.** Reviewer confirms each artifact PR carries its doc update in the same diff
(no "later"); the install narrative names three lanes with TLS models; `local-proof` is
still first; no doc implies hosted SaaS, always-on dense, or a writable companion; both
consistency/preflight scans green. PR link.

**Dependencies.** U2, U4, U5, U6 (docs trail each artifact).

## Sequencing / Milestones

1. **M1 — Foundation (U1, U5).** Commit the reconciled Dockerfile + no-drift test; enrich
   `glama.json` and record the live `ak6x81u3rr` state. Unblocks every other unit and
   delivers the Glama inspectability target first.
2. **M2 — Self-host compose lane ships first (U2, U3, U6, U7-partial).** Committed
   `compose.yaml` + `funnel.json`, Funnel ACL gotcha documented, persistence contract,
   runbook + README three-lane copy. This is the primary artifact and serves the
   self-hoster the positioning already targets with zero engine topology change.
3. **M3 — One-click button second wave (U4, U6, U7-remainder).** Railway template +
   `railway.json`, OAuth-to-platform-hostname wiring, README "Deploy on Railway" button,
   CHANGELOG. Widens reach to non-VPS users; ordered after M2 because it carries the most
   new surface (platform edge + OAuth hostname rewiring).

Hard ordering: compose before the one-click button (brainstorm decision "compose ships
first"); docs land in the same PR as each artifact (R21), never as a follow-up.

## Risks & Mitigations

- **Funnel/PaaS 443 conflict leaks into one story (load-bearing).** Funnel terminates TLS
  on the node (443/8443/10000, `*.ts.net` only, cannot sit behind another TLS proxy); every
  PaaS owns 443 at its edge. *Mitigation:* the lane split is structural, not cosmetic —
  compose owns Funnel, Railway owns the platform edge; never wire Funnel into the Railway
  template. State the constraint in the runbook so the first deployer is not surprised.
- **Committed Dockerfile drifts from `render_docker()`.** Two build recipes silently
  diverge. *Mitigation:* one source of record (U1) — `render_docker()` emits the committed
  bytes, guarded by a failing-if-divergent test (test-first).
- **OAuth redirect/issuer mismatch on Railway silently breaks auth.** Strict matching, no
  normalization. *Mitigation:* the template's #1 job is wiring the public base URL to the
  Railway hostname (U4); validation explicitly asserts a clean authorized read with no
  redirect-URI mismatch.
- **A secret gets baked into an image/compose/template "for convenience".** *Mitigation:*
  the engine's runtime-env discipline is preserved everywhere; a U1 test asserts no
  `sk-`/consent-token/PAT in the build; `preflight_public_scan.py` gates the public surface.
- **OAuth DCR/token state lost on redeploy → users re-consent every deploy.** *Mitigation:*
  U6 persists DCR/bearer/refresh state on the same volume as the vault; validation
  reconnects a prior client without consent.
- **Overclaiming the Glama grade or the awesome-list state.** *Mitigation:* U5 records the
  live `ak6x81u3rr` state and asserts no "A" grade in copy until confirmed; the awesome-mcp
  PR #8056 stays "open" until verified merged (per the grounding brief / claims rules).
- **Vault volume holds sensitive personal notes + a deploy token.** *Mitigation:* U6
  documents owner-only perms and a scoped deploy token (never a full-account credential).
- **A new build dependency trips the copyleft gate.** *Mitigation:* `license_scan.py` runs
  in U1's gate set; keep the image dependency-clean.

## Validation / Definition of Done

Done = each artifact committed **with its docs in the same PR**, the full gate set green
(`ruff`, `check_version_consistency.py`, `pytest`, `license_scan.py`,
`preflight_public_scan.py`), and the following end-to-end evidence captured on the PR(s):

- **U1:** `docker build` log tail (engine installs, entrypoint `hypermnesic`); no-drift
  test output; no-baked-secret assertion.
- **U2/U3:** on a tailnet-member VPS with the `funnel` attribute, `docker compose up -d`
  healthy; `/.well-known/oauth-protected-resource` and `/mcp` resolve over HTTPS at
  `<your-host>.ts.net` (redacted); an MCP client completes OAuth + a read; the Funnel ACL
  gotcha is documented.
- **U4:** Railway button stands up a working endpoint; OAuth discovery resolves at
  `<app>.up.railway.app` and an authorized client reads with no redirect-URI mismatch
  (discovery JSON + screenshot); Template URL recorded.
- **U5:** live `ak6x81u3rr` before/after screenshots showing the build/inspectable-server
  status change; no letter-grade claim unless the page shows it.
- **U6:** restart/redeploy of each lane preserves vault git history, a recall-able note, and
  a previously-authorized client (no fresh consent).
- **U7:** install narrative names three lanes with TLS models; `local-proof` still leads;
  no doc implies hosted SaaS / always-on dense / a writable companion; consistency +
  preflight scans green.

Files are truth and the index disposable in every lane; the guarded `commit_note` write is
unchanged; no database of record is introduced anywhere (R13/R14 reaffirmed).

## References

**Internal**

- `docs/brainstorms/2026-06-25-low-friction-deploy-requirements.md` — the origin
  requirements (R1–R21) and key decisions this plan executes.
- `docs/launch/promo-grounding-brief.md` — positioning confirmations, the
  no-committed-Dockerfile/compose state, the runtime-only `render_docker()`, the Glama gap,
  and the claims-allowed/avoid lists.
- `src/hypermnesic/install.py` — `render_docker()` (lines 199–222), the existing runtime
  Docker/compose emitter and secret-in-env discipline the committed build reconciles with.
- `docs/unified-oauth-mcp-deploy-runbook.md` — the live two-lane topology (public OAuth
  `/mcp` over Funnel + tailnet read companion on `:8848`) the compose lane preserves.
- `docs/reference/configuration.md` — env-var contract (`OPENAI_API_KEY`,
  `HYPERMNESIC_CLOUD_APPROVAL_TOKEN`, `HYPERMNESIC_DEFAULT_CLIENT_SCOPES`) and lexical-only
  degraded-mode behavior.
- `docs/launch/directory-submission-prep.md` — the Glama precondition for the
  awesome-mcp-servers PR (#8056 open) and the MCP Registry remote-template `server.json`.
- `glama.json` — currently `$schema` + `maintainers` only; the build-reference target of U5.
- `docs/plans/2026-06-02-006-feat-phase-2-5-engine-deployment-plan.md` — the role-aware
  installer and the systemd-or-Docker decision this builds on.
- `README.md` — `## Quick start` leading with `local-proof`; where the three-lane on-ramp
  and the Railway button land.

**External**

- Tailscale Funnel docs — TLS terminates on the node; ports 443/8443/10000 only; `*.ts.net`
  only; cannot sit behind another TLS-terminating proxy; requires the `funnel` ACL
  attribute.
- Tailscale container docs (`docker-params`, userspace networking) —
  `TS_AUTHKEY`/`TS_USERSPACE`/`TS_STATE_DIR`/`TS_SERVE_CONFIG`; the sidecar +
  `network_mode: service:tailscale` self-host pattern (runtimeterror.dev,
  tailscale-dev/docker-guide-code-examples).
- Railway docs (templates/create, config-as-code, public networking) — Template URL form
  inputs, GitHub-repo/Dockerfile service source, attachable persistent Volume, platform-edge
  HTTPS; `railway.json` schema at `https://railway.com/railway.schema.json`.
- Fly.io and Render docs — `fly.toml` `[http_service]` `*.fly.dev` auto-TLS; `render.yaml`
  Blueprint disk + the free-tier no-persistent-disk limitation — recorded as deferred
  alternatives.
- MCP authorization spec / DCR guidance (modelcontextprotocol.io, workos.com) — strict
  issuer and redirect/resource URI matching against the deployed public base URL.
- Glama MCP server schema (`https://glama.ai/mcp/schemas/server.json`) and the live listing
  `https://glama.ai/mcp/servers/ak6x81u3rr` — the build-reference target and the
  verification surface.
- Cloudflare Tunnel (`cloudflared`) compose pattern — the deferred custom-hostname
  self-host profile (outbound-only, TLS at the CF edge).
