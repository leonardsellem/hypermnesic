# Cloud OAuth MCP — go-live runbook (ChatGPT/Claude mobile, read+write)

Ready-to-execute steps to take the **public** cloud OAuth MCP live, with rollback inverses.
The code is complete, tested (463 passing), live-proven, and security-hardened (commit `ec80801`).
**Nothing here has run.** It exposes a public **write** endpoint to your memory, so it is gated on
your explicit go-ahead. The agent can do the homelab-side steps (1–3, 5) reversibly on your
approval; **steps 4 (the ChatGPT/Claude connector install) and the approval token are yours.**

> Secrets (V9): the approval token + RS env never appear in a flag, a log, or a committed file.

## Pre-req — merge + install
A persistent unit must run the **installed** engine, not this worktree. Merge
`claude/condescending-sutherland-4d9b29` → `dev` (PR; `dev`/`main` are read-only to the agent),
then reinstall the engine on the homelab.

## Step 1 — choose + set the approval token (operator)
This single secret gates every public connection (you type it at the consent screen). Make it
strong (the engine refuses < 24 chars):
```
HYPERMNESIC_CLOUD_APPROVAL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
```
Store it in an owner-only env file for the unit (e.g. `~/.config/hypermnesic-cloud/cloud.env`,
`chmod 600`) — never committed. Keep a copy in your password manager (you'll type it to approve
connections).

## Step 2 — run the cloud serve (homelab, loopback)
Systemd user unit `hypermnesic-cloud.service`:
```
ExecStart=hypermnesic serve-cloud \
  --index-db <repo>/.hypermnesic/index.db --host 127.0.0.1 --port 8850 \
  --public-url https://homelab.<tailnet-host>.ts.net/cloud \
  --resource  https://homelab.<tailnet-host>.ts.net/cloud/mcp --repo <repo>
EnvironmentFile=-~/.config/hypermnesic-cloud/cloud.env   # HYPERMNESIC_CLOUD_APPROVAL_TOKEN
```
`systemctl --user enable --now hypermnesic-cloud`. (Loopback bind; the funnel terminates TLS and
proxies to it. The write_enabled⇒auth invariant is satisfied — auth is on via the AS provider.)
- **Rollback:** `systemctl --user disable --now hypermnesic-cloud`.

## Step 3 — public exposure via Tailscale Funnel (homelab)
Expose the cloud path publicly (as honcho is exposed). On the path the connectors discover:
```
tailscale funnel --set-path /cloud http://127.0.0.1:8850
# verify publicly: the AS metadata + RFC 9728 protected-resource metadata resolve over HTTPS
curl -s https://homelab.<tailnet-host>.ts.net/cloud/.well-known/oauth-authorization-server | jq .grant_types_supported
curl -s -o /dev/null -w '%{http_code}\n' https://homelab.<tailnet-host>.ts.net/cloud/.well-known/oauth-protected-resource/mcp
```
Confirm the existing honcho `/honcho` funnel route is untouched (per-path funnel, not hostname-wide).
- **Rollback (one inverse op):** `tailscale funnel --set-path /cloud off` — removes public reach;
  the tailnet + gbrain lanes are unaffected.

## Step 4 — install the connector in ChatGPT + Claude (operator)
In each app's connector/MCP settings, add the remote MCP server URL:
`https://homelab.<tailnet-host>.ts.net/cloud/mcp`. The app runs DCR → opens hypermnesic's `/consent` in
your browser → **you enter your approval token + confirm the client/scopes shown** → the app gets a
token. Then memory `search`/`build_context`/`think`/`resolve` (read) and `commit_note` (write,
lands in `captures/`) are available from the app, including mobile.
- This is also the **compatibility spike** (Open Q6): it confirms each app's exact connector flow.
- **Rollback:** remove the connector in the app; or revoke server-side (Step below).

## Step 5 — homelab mirror + standing guard (homelab)
- Mirror: `gbrain-brain/projects/homelab/services/hypermnesic-cloud.md` + `LOG.md` (the new public
  service, its funnel route, the approval-token location — not the value).
- Monitor: add the cloud endpoint to the healthcheck (reachability + token-verify-failure rate);
  rate-limit `/register` + `/authorize` + `/consent` at the funnel/edge (the review residual).

## Revoking access
- **One connector:** revoke its token at `/revoke` (kills the whole grant — access + refresh).
- **Everything (emergency):** rotate `HYPERMNESIC_CLOUD_APPROVAL_TOKEN` + restart the unit (no new
  connections approvable) and/or `tailscale funnel --set-path /cloud off` (kill public reach).

## Relationship to the other lanes
- **Independent** of the gbrain decommission (parked at Gate A) and of honcho.
- **Separate** from the tailnet machine lane (U12 `client_credentials` AS, `tailscale serve`) — the
  public cloud AS never issues tailnet tokens. Two lanes, two trust boundaries.
