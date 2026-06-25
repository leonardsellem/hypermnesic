---
date: 2026-06-25
topic: low-friction-deploy
title: "Hypermnesic — Kill the install barrier: committed Docker/compose + one-click deploy"
status: draft — awaiting operator sign-off
tags: [hypermnesic, deploy, docker, compose, tailscale-funnel, oauth, one-click, distribution, glama]
---

# Hypermnesic — Kill the install barrier: committed Docker/compose + one-click deploy

## Summary

Ship a committed, blessed Docker/compose path and a one-click deploy template so a stranger can stand up their own hypermnesic endpoint in minutes, not an afternoon of VPS + Tailscale + systemd toil. Keep `hypermnesic local-proof` as the no-account first taste, and keep files-are-truth, the git-first guarded write, and the OAuth endpoint intact across every install lane. This is planning only; the repo gains no Dockerfile or compose in this doc.

## Problem Frame

Self-hosting is the adoption ceiling. The product's whole pitch — your files, your git history, your endpoint — means there is no hosted SaaS to click into; every new user must stand up the engine themselves. Today that means owning a VPS, installing and logging into Tailscale, granting a tailnet `funnel` ACL attribute, supplying an OpenAI key, cloning a vault, and configuring a systemd unit by hand. The runbook (`docs/unified-oauth-mcp-deploy-runbook.md`) is faithful to the operator's homelab but reads as an expert's checklist, not a newcomer's on-ramp. The repo ships **no committed `Dockerfile` and no compose file**: `src/hypermnesic/install.py` `render_docker()` emits them into the state dir only at runtime when `hypermnesic install --service=docker` runs, so nothing container-shaped is inspectable, reviewable, or copy-runnable from the repo tree. That same absence has a second cost: Glama's static inspector builds an MCP server from a committed Docker build, and with no committed Dockerfile (and a `glama.json` that references no build) Glama cannot stand up the running server — the listing rests on metadata alone. A launch that leads with "self-hosted, you own it" while the self-host path is undocumented friction loses the curious-but-busy reader at the worst moment.

## Key Decisions

**Three lanes, one identity.** The deploy story splits by where TLS terminates, and the three lanes are named honestly rather than pretended uniform. Lane 1 is `local-proof` — already shipped, no account, no endpoint, the truly-curious entry that this initiative keeps leading with. Lane 2 is the committed self-host compose (engine + Tailscale sidecar) that preserves the current Tailscale-Funnel public-HTTPS topology verbatim. Lane 3 is a one-click PaaS template where the platform owns TLS at its own edge and Tailscale becomes optional. Files-are-truth, the `commit_note` write guard, and the OAuth endpoint are identical across all three; only the ingress layer changes per target. One product, three doors.

**Tailscale Funnel belongs to the self-host lane, not the PaaS lane — because the two cannot share port 443.** This is the load-bearing technical constraint. Funnel terminates TLS on the node itself, listens only on 443/8443/10000, serves only `*.ts.net` hostnames, and explicitly cannot sit behind another TLS-terminating proxy. Every PaaS already terminates TLS at its edge on 443 and forwards decrypted HTTP to the container, so an in-container Tailscale can never claim the public 443. The honest consequence: the compose lane keeps Funnel (the host owns 443, the node is a real tailnet member); the PaaS lane uses the platform's native HTTPS edge and treats Tailscale as private-only or off. Forcing one ingress story across both would be a lie the first deployer discovers.

**A committed Dockerfile derived from the existing `render_docker()`, not a hand-rolled parallel.** The engine already knows how to build itself — `render_docker()` emits a `FROM python:3.11-slim` image that installs the package and runs `hypermnesic serve … --enable-write`, with `OPENAI_API_KEY` supplied at runtime via `env_file`, never baked in. A committed Dockerfile must be reconciled with that template so the two cannot drift, honoring the native-primitives-first rule: reuse the engine's own render logic as the source, do not invent a second build recipe.

**Secrets stay in the environment; the vault and OAuth state are persistent and sensitive.** The OpenAI key, the OAuth consent secret, and any vault deploy token are read from the environment or an owner-only env file, never inlined into an image, a compose file, or a deploy template — the same discipline the engine already enforces. Two things must persist a restart, not just the cloned vault: the index lives beside it, and the OAuth DCR client registrations plus bearer/refresh state must survive so already-authorized clients are not forced through a fresh browser consent on every redeploy. The volume holding personal notes and a scoped deploy token is the sensitive surface the docs must call out.

**Glama inspectability is a named, separable goal of the committed Dockerfile.** Committing the Dockerfile (and optionally referencing it from `glama.json`) is what could let Glama build and inspect the running HTTP server, strengthening the listing beyond metadata. This is the concrete payoff that ties the deploy work to the launch surface — stated as an explicit target so planning can verify it, not assumed.

**Compose ships first; the one-click button follows.** The compose lane is the primary artifact and lands first: it serves the self-hoster the positioning already targets (someone comfortable with a repo and a VPS) and preserves the exact Funnel topology with zero engine change. The one-click PaaS template is the second wave — it widens reach to people who will not touch a VPS, but it requires dropping Funnel for the platform edge and wiring the OAuth issuer to a platform-assigned hostname, which is more surface to get right. Order by who is served soonest with least new risk.

## Requirements

**Committed container artifacts**

R1. A `Dockerfile` is committed at the repo root, building a runnable hypermnesic engine image that installs the package and serves the MCP endpoint.

R2. The committed Dockerfile is reconciled with the engine's existing `render_docker()` in `src/hypermnesic/install.py` so the committed and runtime-generated builds cannot silently diverge.

R3. The image never bakes in `OPENAI_API_KEY`, the OAuth consent secret, or any vault credential; all secrets are supplied at runtime via environment or an owner-only env file.

R4. A committed `compose.yaml` runs the engine container for self-hosters, mounting a persistent volume for the cloned vault and the disposable `.hypermnesic/` index.

**Self-host public HTTPS (Tailscale Funnel lane)**

R5. The compose lane preserves the current Tailscale-Funnel public-HTTPS topology: a Tailscale sidecar fronts the engine and exposes `/mcp` to the public internet over HTTPS with automatic TLS and no reverse proxy.

R6. The sidecar pattern shares its network namespace with the engine container so the funnel reaches the engine on loopback, matching the deployed two-lane design.

R7. The funnel configuration drives both Serve and Funnel and mounts the OAuth discovery well-knowns alongside `/mcp`, so the OAuth 2.1 discovery chain resolves over HTTPS exactly as the live endpoint does.

R8. The compose docs state plainly that Funnel requires the node to hold the tailnet `funnel` ACL attribute, and that `AllowFunnel` is ignored without it — the top community gotcha.

**One-click PaaS deploy (platform-edge TLS lane)**

R9. A one-click deploy template targets a single PaaS (Railway as the primary candidate) using the public GitHub repo plus the committed Dockerfile as the service source.

R10. The template renders a form for the required inputs — the OpenAI key, the OAuth consent secret, and the vault git URL plus a scoped deploy token — and attaches a persistent volume for the cloned vault and index.

R11. On the PaaS lane the deploy uses the platform's native HTTPS edge for public ingress; Tailscale Funnel is dropped, and any Tailscale use is documented as private-only or off.

R12. The template wires the OAuth 2.1 issuer and the registered redirect/resource URLs to the exact platform-assigned public base URL, since OAuth matching is strict and a hostname mismatch silently breaks client authorization.

**Files-are-truth and guarantees preserved across lanes**

R13. Every deploy lane keeps markdown files in the user's git repo as the single source of truth and the search index as a disposable, rebuildable projection — no lane introduces a database of record.

R14. Every deploy lane preserves the git-first guarded `commit_note` write path (diff-or-die frontmatter gate, blocklist write guard, single-writer locks, append-only audit log) unchanged.

R15. Every deploy lane preserves dense-degrades-to-lexical behavior: an absent or rate-limited OpenAI key drops retrieval to lexical-only as a supported, visible state rather than a failure, so the key may even be optional at deploy time.

**Persistence, secrets, and security**

R16. The persistent volume holds both the cloned vault and the `.hypermnesic/` index, and the deploy survives a restart without losing committed memory.

R17. The OAuth DCR client registrations and bearer/refresh runtime state persist across ordinary redeploys so already-authorized clients are not forced through a fresh browser consent.

R18. The docs document the persistent volume (vault plus cloned deploy token) as sensitive, require owner-only permissions, and require the vault credential to be a scoped deploy token, never a full-account credential.

**Glama inspectability**

R19. The committed Dockerfile makes the running HTTP MCP server buildable and inspectable by Glama's static inspector, optionally referenced from `glama.json`, as a named target of this work.

**Local-proof remains the lead**

R20. `hypermnesic local-proof` remains the no-account, no-endpoint first taste and continues to lead the install story; the new lanes are the step a user takes after the proof convinces them, not a replacement for it.

**Documentation in the same change**

R21. The deploy docs are updated in the same change that introduces each artifact: a committed Dockerfile and compose path are reflected in the deploy runbook and the configuration reference, and the install/deploy narrative names all three lanes and which TLS model each uses.

## Success Criteria

- A new self-hoster brings up a public OAuth `/mcp` endpoint from the committed compose path on their own VPS, reading the repo, without reverse-engineering the operator's homelab runbook.
- The committed and runtime-generated Docker builds stay reconciled — a reviewer can confirm they do not diverge, and neither bakes a secret.
- A one-click Railway deploy stands up a working endpoint whose OAuth discovery chain resolves at the platform-assigned hostname and accepts an authorized client without a redirect-URI mismatch.
- A restart of either hosted lane loses no committed memory and forces no already-authorized client back through browser consent.
- Glama can build and inspect the running HTTP server from the committed Dockerfile, moving the listing past metadata-only.
- The install story still opens on `local-proof`; the deploy lanes are honestly labeled by TLS model, and no doc implies a hosted SaaS, an always-on dense path, or a writable Obsidian companion.

## Scope Boundaries

### Deferred for later

- Fly.io (`fly.toml` + `[http_service]`, `*.fly.dev` with automatic TLS) and Render (`render.yaml` Blueprint) one-click variants — solid alternatives, but `flyctl`-first or disk-on-paid-only; offer after the primary Railway button proves out.
- A Cloudflare Tunnel (`cloudflared`) compose variant for self-hosters who own a Cloudflare domain and want a custom hostname instead of `*.ts.net` — a second blessed compose profile once the Funnel profile lands.
- Universal OS packaging (Homebrew tap, `.deb`, Windows) — out of band with this container/one-click effort.
- A managed, operator-run hosted instance of any kind — never; the product is self-hosted by identity.

### Outside this product identity

- Any hosted SaaS, multi-tenant service, or managed memory cloud — the positioning is files you own on infrastructure you run.
- A database-of-record deploy or an index-direct write that would break files-are-truth — the index stays a disposable projection in every lane.
- Baking secrets into an image or template to make a deploy "easier" — secrets stay in the environment; convenience never overrides the secret discipline.
- A deploy lane that makes the Obsidian companion writable, or that presents dense retrieval as always-on — both contradict shipped, honest behavior.

## Dependencies / Assumptions

- The engine's `render_docker()` in `src/hypermnesic/install.py` is the source the committed Dockerfile reconciles with; the runtime-generated artifacts are the existing native primitive, not a thing to re-invent.
- Tailscale Funnel and PaaS edge-TLS are structurally incompatible on port 443; the compose lane owns Funnel, the PaaS lane owns the platform edge — this split is assumed, not negotiable.
- The Tailscale container image supports `TS_AUTHKEY` (with `?ephemeral=true`), `TS_USERSPACE`, `TS_STATE_DIR`, and `TS_SERVE_CONFIG` (which drives both Serve and Funnel); the sidecar overhead is under ~20 MB RAM.
- The OAuth 2.1 endpoint matches issuer and redirect/resource URLs strictly; the deploy template's first job is wiring the public base URL correctly to the platform-assigned hostname.
- The OpenAI key, OAuth consent secret, and vault deploy token are supplied via environment or an owner-only env file in every lane, consistent with the engine's existing discipline.
- PyPI install is live (`uv tool install hypermnesic`), so the image and templates can install the published package rather than only a local build where appropriate.
- The permissive-dependency license gate (`scripts/license_scan.py`) still applies to anything a new build pulls in.

## Outstanding Questions

### Resolve before planning

- Which PaaS is the single primary one-click target — confirm Railway over Fly.io/Render given the persistent-volume and form-input needs, or pick another.
- Whether the committed Dockerfile and compose live at the repo root or under a `deploy/` directory, and how `render_docker()` is refactored so the committed file and the runtime emitter share one source without drift.
- Whether `glama.json` should reference the committed Docker build now, and what the live Glama listing (`ak6x81u3rr`) currently shows so the inspectability win is verified, not assumed.

### Deferred to planning

- The exact compose shape for the Tailscale sidecar (`network_mode: service:tailscale`, the `funnel.json` `TS_SERVE_CONFIG`, the `TS_STATE_DIR` named volume) and how the engine's loopback port is wired behind it.
- How the PaaS template persists OAuth DCR/token state on the attached volume alongside the vault, and the precise env-var contract the form exposes.
- Whether the deploy template ships as a Railway Template URL plus a `railway.json`, and where that config-as-code lives in the repo.
- The default for whether `OPENAI_API_KEY` is a required or optional deploy input, given lexical-only degraded mode is supported.
- Where the one-click button and the three-lane install narrative surface in the README versus the deploy runbook.

## Sources / Research

**Internal**

- `docs/launch/promo-grounding-brief.md` — positioning confirmations, the no-committed-Dockerfile/compose state, the runtime-only `render_docker()`, and the Glama inspectability gap.
- `src/hypermnesic/install.py` — `render_docker()` (the existing runtime Docker/compose emitter), the systemd/Funnel/`setup` provisioning, and the secrets-in-env discipline.
- `docs/unified-oauth-mcp-deploy-runbook.md` — the live two-lane topology (public OAuth `/mcp` over Funnel + tailnet read companion on `:8848`) the compose lane must preserve.
- `docs/reference/configuration.md` — the env-var contract (`OPENAI_API_KEY`, `HYPERMNESIC_CLOUD_APPROVAL_TOKEN`, `HYPERMNESIC_DEFAULT_CLIENT_SCOPES`) and the lexical-only degraded-mode behavior.
- `docs/launch/directory-submission-prep.md` — the Glama precondition for awesome-mcp-servers and the MCP Registry remote-template `server.json` draft.
- `docs/launch/launch-narrative-drafts.md` and `README.md` — the voice, the claims-allowed/avoid lists, and `local-proof` as the lead.
- `docs/plans/2026-06-02-006-feat-phase-2-5-engine-deployment-plan.md` — the role-aware installer and the systemd-or-Docker master decision this builds on.

**External**

- Tailscale Funnel docs — TLS terminates on the node; ports 443/8443/10000 only; `*.ts.net` only; cannot sit behind another TLS-terminating proxy; requires the `funnel` ACL attribute.
- Tailscale container docs (`docker-params`, userspace networking) — `TS_AUTHKEY`/`TS_USERSPACE`/`TS_STATE_DIR`/`TS_SERVE_CONFIG`; the sidecar + `network_mode: service:tailscale` self-host pattern (runtimeterror.dev, tailscale-dev/docker-guide-code-examples).
- Railway docs (templates/create, config-as-code, public networking) — Template URL form inputs, GitHub-repo/Dockerfile service source, attachable persistent Volume, platform-edge HTTPS.
- Fly.io and Render docs — `fly.toml` `[http_service]` with `*.fly.dev` auto-TLS; `render.yaml` Blueprint with a disk, and the free-tier no-persistent-disk limitation — both recorded as deferred alternatives.
- MCP authorization spec / DCR guidance (modelcontextprotocol.io, workos.com) — strict issuer and redirect/resource URI matching against the deployed public base URL.
- Cloudflare Tunnel (`cloudflared`) compose pattern — outbound-only, custom-domain, TLS-at-CF-edge alternative for the deferred custom-hostname self-host profile.
