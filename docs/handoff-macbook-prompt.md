# MacBook handoff prompt — hypermnesic Mac-side steps

Paste everything in the fenced block below into a fresh **Claude Code session on your MacBook**.
It is self-contained (the Mac session has no memory of the homelab session). It completes the
**Mac-side** steps for two workstreams the homelab agent built but cannot finish from the homelab
(the Mac is a 2nd tailnet peer it can't reach): (1) the **public cloud OAuth MCP** mobile
connector, and (2) the **Mac-side gbrain→hypermnesic cutover + Gate-A/B evidence**.

> Prereq it will check for you: the homelab-side endpoints must be live. If they aren't, it stops
> and tells you exactly what to deploy (the homelab agent has the runbooks committed on the branch).

```text
You are a fresh Claude Code session on a MacBook that is a Tailscale tailnet peer. A homelab
agent built two things on the GitHub repo leonardsellem/hypermnesic, branch
`claude/condescending-sutherland-4d9b29` (already pushed). Your job: complete the MAC-SIDE steps
and produce the operator evidence the homelab agent cannot (the Mac is a 2nd tailnet peer it
can't reach). Work ONLY on this Mac — never touch the homelab.

SETUP
- Clone/fetch the repo and check out the branch:
  `gh repo clone leonardsellem/hypermnesic ~/hypermnesic 2>/dev/null || (cd ~/hypermnesic && git fetch)`
  `cd ~/hypermnesic && git checkout claude/condescending-sutherland-4d9b29 && git pull`
- Read these for full detail before acting:
  - docs/cloud-oauth-mcp-deploy-runbook.md         (the public cloud MCP)
  - docs/gate-artifacts/2026-06-02-gate-A-plugin-and-oauth.md  (gbrain Gate A)
  - docs/gate-artifacts/2026-06-02-gate-A-rollout-runbook.md   (the homelab deploy it depends on)
  - docs/plans/2026-06-02-009-feat-gbrain-decommission-plan.md (U13 = the Mac consumer sweep)
- Confirm the tailnet: `tailscale status` shows `homelab` (<your-host>.ts.net).

HARD CONSTRAINTS
- NEVER print/echo/commit any OAuth token, client secret, or the cloud approval token. Read
  secrets from the environment or ask the operator to enter them in the browser; never log them.
- Every gbrain consumer flip is REVERSIBLE: back up the gbrain config block (comment it / save a
  copy) before changing it, so a failed proof reverts that one consumer without touching others.
- If a step needs a homelab endpoint that isn't live yet, STOP that step and tell the operator
  precisely which runbook step the homelab must run first. Do not try to deploy the homelab.

TASK 1 — RECON (always safe; do this first, change nothing)
Inventory every gbrain CLI/MCP reference on this Mac (this is the Gate-B grep evidence). Search and
list (do NOT edit yet), reporting a checklist of what exists:
- ~/.codex/config.toml                                  -> [mcp_servers.gbrain]
- ~/.claude.json                                        -> any project-scoped `gbrain serve`
- ~/.local/share/chezmoi/dot_codex/config.toml.tmpl     -> the DUPLICATED HTTP+stdio [mcp_servers.gbrain]
- ~/.local/share/chezmoi/dot_codex/AGENTS.md.tmpl       -> the GBrain lookup-order prose
- ~/.claude/skills/skillops-hourly-pieces-ltm-capture/.omp/mcp.json -> stale gbrain MCP declaration
- ~/.codex/hooks.json + ~/.claude/hooks/                -> gbrain-agent-hook wrappers
- shell profiles (~/.zshrc, ~/.zprofile, ~/.config/...)  -> GBRAIN_MCP_TOKEN, GBRAIN_NO_GITIGNORE
- Whether a chezmoi auto-sync timer/launchd job is enabled (it must be OFF during the cutover so it
  can't re-materialize a stale gbrain registration the operator just removed).

TASK 2 — CLOUD OAUTH MCP: install the mobile connector (the priority)
PREREQ CHECK: `curl -s https://<your-host>.ts.net/cloud/.well-known/oauth-authorization-server`
must return JSON containing "authorization_code" and "S256". If it 404s or refuses, STOP this task:
tell the operator the homelab cloud serve + Tailscale Funnel are not up yet (deploy-runbook steps
1-3). If it IS live:
- The operator (you, the human) holds the approval token; it is entered in the BROWSER consent
  screen, never by the agent.
- Guide the operator: in ChatGPT (Settings -> Connectors / "add MCP server") and in Claude
  (Settings -> Connectors -> add custom connector), add the remote MCP URL:
  https://<your-host>.ts.net/cloud/mcp
  The app does Dynamic Client Registration, then opens hypermnesic's /consent page in the browser;
  the operator confirms the shown client + scopes and enters the approval token; the app receives a
  token.
- Verify from each app: a memory `search` returns results, and a `commit_note` write succeeds (it
  lands in the `captures/` review zone). Confirm it works from mobile too.
- To revoke later: the operator removes the connector in the app, or the homelab revokes the token.

TASK 3 — gbrain Mac consumer cutover (plan U13) — reversible, per-consumer
THE HOMELAB IS LIVE (deployed 2026-06-02): AS at http://<your-host>.ts.net:8849 (tailnet),
auth-on write master at http://<your-host>.ts.net:8851/mcp (tailnet, direct IP — NOT the hostname),
companion-read on http://<your-host>.ts.net:8848 (read-only). The Mac identity (`mac`) is enrolled.
PROVISION THIS MAC'S TOKEN (do not print the secret/token):
  1) the operator retrieves the Mac client secret from the homelab once:
       (on homelab) `cat ~/.config/hypermnesic-as/mac.env`  -> HYPERMNESIC_AS_CLIENT_SECRET=...
     and sets it in THIS Mac session's env as $MAC_SECRET (never committed/echoed).
  2) mint a short-lived token from the AS:
       export HYPERMNESIC_MCP_TOKEN=$(curl -s -X POST http://<your-host>.ts.net:8849/token \
         -d grant_type=client_credentials -d client_id=mac \
         --data-urlencode client_secret="$MAC_SECRET" \
         --data-urlencode resource=https://<your-host>.ts.net/mcp -d scope=write \
         | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
VERIFY an AUTHENTICATED round-trip (this is Gate-A criterion 5; do not print the token):
  curl -s -H "Authorization: Bearer $HYPERMNESIC_MCP_TOKEN" -H 'Content-Type: application/json' \
       -H 'Accept: application/json' -X POST http://<your-host>.ts.net:8851/mcp \
       -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
must return the hypermnesic tool list (search/build_context/think/resolve + commit_note); an
unauthenticated call to :8851 must 401. Paste BOTH results into the Gate-A artifact (criterion 5).
If the endpoints don't answer, STOP and tell the operator the homelab services are down.
If live, flip each Mac consumer (back up its gbrain block first; prove each with a REAL
authenticated hypermnesic call, not just exit 0):
- Pieces: remove the stale gbrain MCP declaration in the Pieces .omp/mcp.json (the capture flow
  never calls gbrain — this is a stale decl only).
- Codex ~/.codex/config.toml [mcp_servers.gbrain] -> hypermnesic; same in the chezmoi
  dot_codex/config.toml.tmpl (incl. the duplicate); rewrite dot_codex/AGENTS.md.tmpl lookup order
  to hypermnesic.
- Claude ~/.claude.json project gbrain serve -> hypermnesic; the gbrain hook wrappers -> the
  hypermnesic plugin hook (Task 4).
- Remove the old GBRAIN_MCP_TOKEN from the Mac env/profile; confirm the chezmoi auto-sync timer is
  disabled so it can't re-add a stale gbrain reg.

TASK 4 — install the hypermnesic plugin on the Mac (Gate-A criterion 7)
- Claude Code: add the in-repo marketplace (plugin/.claude-plugin/marketplace.json on the branch)
  and install the `hypermnesic` plugin.
- Codex: install via plugin/plugins/hypermnesic/.codex-plugin/plugin.json.
- Confirm the SKILL loads and the auto-query hook fires on a relevant prompt and stays SILENT on a
  401 / missing token (it must never block a turn).

TASK 5 — produce the Mac evidence + report (this is what the gates need)
Print a Markdown report with:
- The authenticated tools/list + search output from THIS Mac against hypermnesic (OAuth enforced),
  and a grep showing NO remaining gbrain CLI/MCP reference in the Mac's registrations/hooks/configs.
- Confirmation the cloud connector works from ChatGPT + Claude.
- Per-consumer: what was flipped and the one-line revert for each.
- Anything blocked on the homelab (with the exact runbook step needed).
This evidence block is meant to be pasted into the homelab's Gate-A and Gate-B artifacts.

DONE WHEN: the Mac consumers are off gbrain (grep clean, proven by real authenticated calls), the
plugin is installed and its hook behaves, the cloud connector works from both apps, and the
evidence report is produced. HALT at any unmet prereq and tell the operator exactly what the
homelab must deploy first.
```

## After the Mac session runs
Paste its evidence report back to the homelab agent (or into the Gate-A / Gate-B artifacts on the
branch) so the gbrain decommission can proceed past Gate A → Gate B, and so the cloud connector is
confirmed working end-to-end from mobile.
