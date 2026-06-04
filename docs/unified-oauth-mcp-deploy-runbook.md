# Unified OAuth MCP — cutover runbook (U8)

> Supersedes `docs/cloud-oauth-mcp-deploy-runbook.md` (the `/cloud`→`:8850` lane). This takes the
> live homelab from the four-lane state to the **two-lane** end state: one public Tailscale-funnel'd
> OAuth endpoint at `/mcp` (read+write by scope, write-anywhere-under-guards) + the retained
> tailnet read companion (`:8848`). honcho is untouched. Plan:
> `docs/plans/2026-06-03-001-feat-unified-oauth-endpoint-and-setup-plan.md`. Security sign-off (G3):
> `docs/2026-06-03-unified-write-anywhere-security-review.md`.

## G4 — this is a HALT gate

The steps below change **public** funnel routes and stop running services. They are presented for
operator approval and are **not executed** until G4 is signed off. Privileged funnel commands use
`tailscale funnel` (NEVER `serve` — `serve --set-path` silently clears `AllowFunnel[:443]` and would
drop `/cloud` + `/honcho`).

## Live start state (2026-06-03, verified)

| Funnel path (:443) | → backend | Service | Disposition |
| --- | --- | --- | --- |
| `/mcp` | `100.64.0.55:8851/mcp` | `hypermnesic-master-auth` (write master) | **repoint → unified; retire service** |
| `/cloud` (+ `/cloud` well-knowns) | `127.0.0.1:8850` | `hypermnesic-cloud` (cloud OAuth) | **becomes the unified endpoint** |
| `/honcho` (+ `/honcho` well-knowns), `:8443` | `127.0.0.1:8788` | honcho | **untouched** |
| `/`, `:3131` | `127.0.0.1:3131` | gbrain | unaffected (decommission owns it) |
| (tailnet) | `100.64.0.55:8848` | `hypermnesic` (read master) | **retain (read companion)** |
| (tailnet) | `100.64.0.55:8849` | `hypermnesic-as` (client_credentials AS) | **retire (U7)** |
| — | — | `hypermnesic-token.timer/.service` | **retire (minted :8851 RS tokens)** |

`inet gbrain_watch` nft counter: **preserve** (still the gbrain Gate-B signal).

## Pre-req — engine must carry the unified code (operator: merge to `main`)

The unified endpoint requires this branch's engine (U1 write-anywhere default + U2 R2 HTTPS-origin
guard + U3 `setup`). The live `:8850` service runs the OLD installed engine (`captures/` default).
`main`/`dev` are read-only to the agent, so the operator merges
`claude/condescending-sutherland-4d9b29` → `main` (PR), then re-pins the engine:

```
git -C <master-main-worktree> fetch && git -C <master-main-worktree> checkout --detach origin/main
# bump the wheel version or uv reuses the stale name+version wheel (memory: uv-tool-install-wheel-cache)
uv tool install --force <master-main-worktree>
```

## The cutover decision — ✅ Option A SELECTED (operator, G4, 2026-06-03)

The existing ChatGPT/Claude Cloud connectors are bound to `https://…/cloud/mcp` (audience
`/cloud/mcp`). The unified endpoint's canonical audience is `/mcp`. The operator chose **Option A**
at G4 — one endpoint now, existing connectors re-authorize once. Option B is recorded as the
not-taken alternative.

### Option A — one endpoint now, existing connectors re-auth once ✅ SELECTED

Reconfigure the `:8850` service to the unified `/mcp` identity; route both `/mcp` and (transitional)
`/cloud` to it. Existing connectors' `/cloud/mcp`-audience tokens stop validating → they rediscover
and re-authorize **once** → `/mcp`-audience tokens. New clients use `/mcp` directly.

```
# 1. reconfigure + restart the service to the unified identity (write-anywhere, new engine)
#    ExecStart=hypermnesic serve-cloud --index-db <repo>/.hypermnesic/index.db --host 127.0.0.1 \
#      --port 8850 --public-url https://homelab.<tailnet-host>.ts.net/mcp \
#      --resource https://homelab.<tailnet-host>.ts.net/mcp --repo <repo> \
#      --default-client-scopes read write
#    (or: hypermnesic setup <repo> --public-url …/mcp --resource …/mcp \
#      --default-client-scopes read write  — renders+starts+funnels+verifies)
systemctl --user restart hypermnesic-cloud

# 2. claim /mcp + the two /mcp root well-knowns for the unified endpoint (funnel, NOT serve)
sudo tailscale funnel --bg --https=443 --set-path /mcp http://127.0.0.1:8850/mcp
sudo tailscale funnel --bg --https=443 --set-path /.well-known/oauth-protected-resource/mcp http://127.0.0.1:8850/.well-known/oauth-protected-resource/mcp
sudo tailscale funnel --bg --https=443 --set-path /.well-known/oauth-authorization-server/mcp http://127.0.0.1:8850/.well-known/oauth-authorization-server/mcp

# 3. (transitional) keep /cloud → :8850 so old base URLs still reach the service for the one re-auth
#    (already routed; no change). Retire /cloud once connectors are migrated (deferred follow-up).
```

### Option B — zero re-auth, transitional parallel instance

Keep `:8850` serving `/cloud` unchanged (existing connectors untouched). Stand up a **second**
unified instance for `/mcp` on a fresh loopback port via `setup`, funnel `/mcp` → it. Converge to one
endpoint later when `/cloud` is retired. Zero re-auth, two instances transitionally.

```
hypermnesic setup <repo> --public-url https://homelab.<tailnet-host>.ts.net/mcp \
  --resource https://homelab.<tailnet-host>.ts.net/mcp --port 8852   # distinct unit/port
# setup configures the /mcp funnel + well-knowns and verifies discovery; /cloud:8850 stays as-is
```

## Retire the redundant lanes (both options)

```
systemctl --user disable --now hypermnesic-master-auth   # :8851 write master (folded into unified)
systemctl --user disable --now hypermnesic-as            # :8849 client_credentials AS (U7)
systemctl --user disable --now hypermnesic-token.timer hypermnesic-token.service
# :8848 hypermnesic.service (read companion) STAYS running.
```

## Verify (real output, not exit codes — KTD6)

```
# unified endpoint: discovery chain resolves over HTTPS to hypermnesic
curl -s -o /dev/null -w '%{http_code}\n' https://homelab.<tailnet-host>.ts.net/.well-known/oauth-protected-resource/mcp   # 200
curl -s https://homelab.<tailnet-host>.ts.net/.well-known/oauth-authorization-server/mcp | jq .token_endpoint            # non-null
# an unauth tools/list is 401 with a WWW-Authenticate; an authed tools/list (after re-auth) is 200 / 5 tools
# coexistence (AE5): /cloud + /honcho still public; honcho discovery unaffected
curl -s -o /dev/null -w '%{http_code}\n' https://homelab.<tailnet-host>.ts.net/honcho/.well-known/oauth-authorization-server  # 200
# the gbrain Gate-B counter still increments on a gbrain hit
sudo nft list counter inet gbrain_watch conns
```

## Reverse (one-op, restores the prior reach)

`~/.config/hypermnesic-decommission/u8-unified-revert.sh`:

```
#!/usr/bin/env bash
set -euo pipefail
# point /mcp back at the :8851 write master, drop the unified well-known mounts
sudo tailscale funnel --bg --https=443 --set-path /mcp http://100.64.0.55:8851/mcp
sudo tailscale funnel --https=443 --set-path /.well-known/oauth-protected-resource/mcp off
sudo tailscale funnel --https=443 --set-path /.well-known/oauth-authorization-server/mcp off
systemctl --user enable --now hypermnesic-master-auth hypermnesic-as
# guard: /cloud + /honcho + :8443 must remain (AllowFunnel[:443] + [:8443] both true)
tailscale funnel status
```

## Homelab mirror (BEFORE declaring the gate done)

Update `gbrain-brain/projects/homelab/services/hypermnesic.md` + `hypermnesic-cloud.md` + `LOG.md`:
the unified `/mcp` topology, the retired `:8849`/`:8851`/token services, the preserved nft counter,
and the reverse op. Decommission handoff: U9.
