# gbrain-decommission — live STATE snapshot (2026-06-03, for post-compact handoff)

Authoritative resume point for the `/goal` (make hypermnesic the sole memory layer). Plan:
`docs/plans/2026-06-02-009-feat-gbrain-decommission-plan.md`. Phase loop A→B→C→D, HALT at each
gate for explicit operator approval. Never commit to `main`/`dev`. Mirror every homelab/vault
change to `gbrain-brain/projects/homelab/{services,LOG.md}`. Never echo/commit secrets.

## Branches / HEADs
- hypermnesic repo, branch `claude/condescending-sutherland-4d9b29`, worktree
  `<home>/dev/hypermnesic/.claude/worktrees/condescending-sutherland-4d9b29`. **HEAD `0a40510`** (U6).
  PR #15 merged to `origin/main` (`e368cf7`) = Phase A + U12. Post-#15 commits (slim hook 993bdd9,
  cloud fixes c164bd8/5ecfb7d, output schemas 42e2ec5, U6 0a40510) are NOT yet on main.
- vault `gbrain-brain` (hot multi-writer, on `main`): **HEAD `53a1c738`** (U7). Path-scoped commits + rebase.

## Phase A — DONE + Gate A APPROVED
Plugin on both homelab hosts + Mac (`✔ enabled`); OAuth2 RS/AS; Mac 2nd-peer evidence recorded in
`docs/gate-artifacts/2026-06-02-gate-A-plugin-and-oauth.md`. Cloud OAuth MCP (separate lane)
DEPLOYED + working on ChatGPT + Claude after 3 browser fixes (consent form action `5ecfb7d`, CSP
form-action redirect `c164bd8`, per-tool output schemas `42e2ec5`).

## Live homelab services (systemd --user)
- `hypermnesic-as.service` — AS, **100.64.0.55:8849**, client_credentials + RFC8707 + introspection. WORKTREE-pinned.
- `hypermnesic-master-auth.service` — **write master AUTH-ON, 100.64.0.55:8851**, introspects the AS. WORKTREE-pinned.
- `hypermnesic.service` — **read companion AUTH-OFF, 100.64.0.55:8848**. Runs the **installed canonical engine** `~/.local/bin/hypermnesic` (reinstalled from `origin/main` e368cf7 → has `resolve`).
- `hypermnesic-cloud.service` — **public cloud OAuth MCP, 127.0.0.1:8850**, Funnel `/cloud`. WORKTREE-pinned. In-memory grants (restart wipes → must reconnect). Approval token: `~/.config/hypermnesic-cloud/cloud.env` (0600). Connector URL: `https://homelab.<tailnet-host>.ts.net/cloud/mcp`.
- `hypermnesic-token.timer` — mints `HYPERMNESIC_MCP_TOKEN` (45-min) to `~/.config/hypermnesic/token.env` (0600).
- Engine note: master-auth/as/cloud run the **worktree** `.venv/bin/hypermnesic`; companion runs the **installed** canonical engine. Re-pin everything to `main` once the post-#15 commits merge.

## Phase B progress
- **U6 (read-parity): DONE + pushed `0a40510`.** `harness/parity_harness.py` (resolve_parity +
  freshness_recall + safe_to_cut_over), `harness/PARITY_VERDICT.md` = **SAFE TO CUT OVER**. 471 tests pass.
- **U7 (content-distill cutover): DONE + pushed (vault `53a1c738`).** Reads `gbrain search/get` →
  `hypermnesic resolve/retrieve`; STEP-9 `gbrain sync/extract/embed` removed (read-time convergence).
  Files: `gbrain-brain/skills/content-distill/{distill.prompt.md,SKILL.md,tests/test_prompt_contract.py}`
  (9 contract tests pass) + cron `~/.hermes/cron/jobs.json` job `1d677f1a003a` prompt synced.
  **Revert:** `cp ~/.hermes/cron/jobs.json.pre-u7.bak ~/.hermes/cron/jobs.json` + `git checkout` the 3 skill files.
  **⚠ Gate-B verification PENDING:** confirm the next *scheduled* content-distill run (cron 9:40/21:40)
  resolves via hypermnesic with zero gbrain calls. The Hermes **gateway** (PID was 4084541, `gateway
  run --replace`, up since 2026-06-02) may have cached the old prompt — if the next run still hits
  gbrain, restart the gateway so it re-reads `jobs.json`. Did NOT restart it (would interrupt the whole fleet).
- **U8 (reach repoint): IN PROGRESS — recon only, NO flip yet.** Recorded live `tailscale serve`/funnel map:
  hostname `/` → `127.0.0.1:3131` (a `bun` proc), `/cloud` → `:8850`, `/honcho` → `:8788`; **`/mcp` is FREE**
  (falls through `/`→`:3131`, returns 405). `gbrain-mcp-http.service` is active (the Gate-B traffic-count
  instrumentation target). **OPEN before flipping:** confirm gbrain's exact listen port + whether `:3131`
  (bun) is gbrain or another app, and which exact endpoint string each consumer calls. **U8 plan:**
  (a) instrument `gbrain-mcp-http` (request counter/access log) for the Gate-B zero-traffic signal;
  (b) no-gap cutover — AS up + every consumer holds a valid token + verified → THEN
  `sudo tailscale serve --set-path /mcp http://100.64.0.55:8851` (auth-on master), tailnet-only NOT funnel;
  (c) reversible single inverse op (`tailscale serve --set-path /mcp off`). NB: Mac consumers already use the
  direct IP `:8851`; the plugin `.mcp.json` uses the hostname `/mcp` (so it benefits from the repoint).
- **U13 (consumer sweep): NOT STARTED.** Homelab registrations/healthcheck (`gbrain stats` job `ff85e57bdf9d`
  → hypermnesic health)/docs + Mac-side (Pieces `.omp/mcp.json`, Mac registrations, chezmoi templates) which
  are operator-applied with pasted evidence. Per-consumer reversible (strangler).

## Gate B (after U8+U13) — HALT for operator approval
PASS needs ALL: grep of homelab cron/scripts/skills/hooks/docs shows zero gbrain CLI/MCP ref; gbrain
request log zero non-baseline traffic over the window; content-distill + healthcheck each ran ≥1 real
*scheduled* cycle on hypermnesic; Mac operator evidence pasted into the Gate-B artifact.

## Phases C/D — NOT STARTED
C: U9 orphan reconciliation → `gbrain_supabase_orphan_audit.py --json` db_only==0 + conservation ledger
(keep the restore unit MASKED, fail-closed, until U11). D: U10 snapshot + restore-rehearse + soak;
**U11 Supabase teardown is IRREVERSIBLE — only after Gate D operator release.**

## Mac-side pending (operator-run)
`docs/handoff-macbook-plugin-update.md` (slim-hook reinstall), reconnect ChatGPT/Claude cloud
connectors (in-memory grants wiped on restart), U13 Mac consumer sweep + evidence.

## Rollback points
`~/.hermes/cron/jobs.json.pre-u7.bak`; `~/.config/systemd/user/hypermnesic.service.pre-phase2.bak`;
worktree services reversible by `systemctl --user stop`; cloud public reach off via
`sudo tailscale funnel --https=443 --set-path /cloud off`; gbrain is fully alive (every consumer flips back).

## RESUME HERE
Finish **U8** (instrument gbrain → verify no-gap conditions → flip `/mcp`→`:8851`, reversible), then
**U13** (homelab sweep + Mac evidence), then run **Gate B** and HALT for operator approval. Also verify
the U7 content-distill Gate-B item (next scheduled run uses hypermnesic; restart the gateway if it cached).
