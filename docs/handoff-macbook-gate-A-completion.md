# MacBook handoff — COMPLETE Gate A (criteria 5, 7, 9 from the Mac, against the fixed branch)

Paste the fenced block below into a fresh **Claude Code session on your MacBook**. It is
self-contained. It produces the three operator-only Gate-A evidence items the homelab agent
cannot generate (the Mac is a 2nd tailnet peer it can't reach), **re-verified against the now-fixed
branch** (the plugin load defect + honcho issuer were fixed on the branch after your last Mac run,
so the plugin must be reinstalled from the branch rather than your earlier local patch).

> All homelab-side Gate-A criteria are already GREEN and live (AS, auth-on write master, companion
> read split, both homelab hosts' plugins enabled). This handoff closes the Mac half so you can
> reply **"Gate A approved"** to the homelab agent with full evidence in hand.

```text
You are a fresh Claude Code session on a MacBook that is a Tailscale tailnet peer (the homelab is
`homelab` / 100.103.0.55). A homelab agent finished Phase A of the gbrain→hypermnesic decommission
on GitHub repo leonardsellem/hypermnesic, branch `claude/condescending-sutherland-4d9b29` (HEAD
b51c94f, pushed — it INCLUDES the plugin load-defect fix 69e0096). Your job: produce the three
Mac-side Gate-A evidence items and a paste-back report. Work ONLY on this Mac; never touch the
homelab. This is Gate-A completion ONLY — do NOT start Phase B, and do NOT flip any gbrain
consumer here (that was a separate earlier handoff).

SETUP
- Fetch + check out the branch at its latest HEAD:
  `gh repo clone leonardsellem/hypermnesic ~/hypermnesic 2>/dev/null || true`
  `cd ~/hypermnesic && git fetch origin && git checkout claude/condescending-sutherland-4d9b29 && git pull --ff-only`
  Confirm `git rev-parse --short HEAD` is b51c94f or later (it must contain commit 69e0096 —
  `git log --oneline | grep 69e0096` must hit; that is the plugin fix).
- Read for context: docs/gate-artifacts/2026-06-02-gate-A-plugin-and-oauth.md (the checklist).
- Confirm the tailnet: `tailscale status | grep homelab` shows 100.103.0.55.

HARD CONSTRAINTS
- NEVER print, echo, log, or commit any OAuth token or client secret. Read the Mac client secret
  from the environment ($MAC_SECRET); keep minted tokens in-process only.
- Reversible: the plugin reinstall is undoable (`claude plugin uninstall` / `codex plugin remove`).
  Change nothing else on this Mac.

PREREQ CHECK (stop and tell the operator which unit is down if any fails)
  curl -s -o /dev/null -w 'AS    :8849 -> %{http_code}\n' http://100.103.0.55:8849/.well-known/oauth-authorization-server
  curl -s -o /dev/null -w 'master:8851 -> %{http_code}\n' http://100.103.0.55:8851/mcp   # expect 401
Both must answer (AS 200, master 401). If they don't, STOP — the homelab services are down.

TASK 1 — Gate-A criterion 5: authenticated round-trip from this 2nd tailnet peer
  PROVISION (operator does this once, secret never echoed):
   - On the homelab: `cat ~/.config/hypermnesic-as/mac.env` → copy the HYPERMNESIC_AS_CLIENT_SECRET
     value and, in THIS Mac session, `export MAC_SECRET='<that value>'` (do not commit/print it).
  MINT (token stays in the shell var, never printed):
   export HYPERMNESIC_MCP_TOKEN=$(curl -s -X POST http://100.103.0.55:8849/token \
     -d grant_type=client_credentials -d client_id=mac \
     --data-urlencode client_secret="$MAC_SECRET" \
     --data-urlencode resource=https://homelab.taildabf2.ts.net/mcp -d scope=write \
     | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
  VERIFY (this is the criterion-5 evidence — capture the HTTP codes + the tool list, NOT the token):
   # negative: unauthenticated must 401 with an RFC 9728 WWW-Authenticate header
   curl -s -i -X POST http://100.103.0.55:8851/mcp -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | grep -iE 'HTTP/|www-authenticate'
   # positive: authenticated tools/list -> 200 with the full toolset
   curl -s -X POST http://100.103.0.55:8851/mcp \
     -H "Authorization: Bearer $HYPERMNESIC_MCP_TOKEN" -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
   # positive: a real authenticated search returns hits
   curl -s -X POST http://100.103.0.55:8851/mcp \
     -H "Authorization: Bearer $HYPERMNESIC_MCP_TOKEN" -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search","arguments":{"query":"gbrain decommission","k":3}}}'
  PASS = unauth → 401 (+ WWW-Authenticate), authed tools/list → 200 with
  [build_context, commit_note, resolve, search, think], authed search → ≥1 hit.

TASK 2 — Gate-A criteria 7 + 9: install the FIXED plugin on this Mac (Claude + Codex)
  The branch fix (69e0096) removed the duplicate `hooks` key from the manifest. If you installed
  the plugin on this Mac before (with a local patch), reinstall from the branch so the Mac matches
  upstream and any local edit is dropped.
  CLAUDE:
   claude plugin marketplace remove hypermnesic 2>/dev/null || true
   claude plugin marketplace add "$PWD/plugin"
   claude plugin install hypermnesic@hypermnesic
   claude plugin list | grep -A3 'hypermnesic@hypermnesic'      # MUST show: Status: ✔ enabled
   # if it instead shows "✘ failed to load: Duplicate hooks file", your checkout is stale —
   # re-run `git pull --ff-only` and confirm 69e0096 is present, then reinstall.
   git -C "$PWD" status --porcelain plugin/   # MUST be empty — no leftover local manifest patch
  CODEX:
   codex plugin marketplace add "$PWD/plugin" 2>/dev/null || true
   codex plugin add hypermnesic@hypermnesic
   codex plugin list | grep hypermnesic                          # MUST show: installed, enabled
  HOOK BEHAVIOR (criterion 8 spot-check): with NO token in env, confirm the auto-query hook stays
  SILENT and never blocks a turn (it must swallow a 401/missing-token). With the SKILL loaded,
  confirm `hypermnesic-memory` is offered on a memory-relevant prompt.

TASK 3 — produce the paste-back Gate-A evidence report (Markdown)
  Print a block with:
   - HEAD short SHA (proving 69e0096 is in the checkout).
   - Criterion 5: the unauth 401 line + WWW-Authenticate, the authed tools/list result (the 5
     tool names), and the search hit count. (No token/secret printed.)
   - Criteria 7/9: `claude plugin list` line (✔ enabled) + `codex plugin list` line (installed,
     enabled) + the `git status plugin/` clean confirmation + one line on the hook staying silent
     on a missing token.
   - One line: "Mac Gate-A evidence complete — ready for operator approval."
  This block is meant to be pasted into docs/gate-artifacts/2026-06-02-gate-A-plugin-and-oauth.md
  (criterion 5 row + the session-update section) and back to the homelab agent.

OPTIONAL (NOT part of Gate A — only if you also want mobile now): add the cloud connector. In
ChatGPT and Claude, add the remote MCP server https://homelab.taildabf2.ts.net/cloud/mcp ; it opens
a consent page in your browser where you type the cloud approval token (retrieve once on the
homelab: `cat ~/.config/hypermnesic-cloud/cloud.env`). This lane is live and independent of the gate.

DONE WHEN: criterion-5 round-trip proven from this Mac, the plugin shows enabled on BOTH Claude and
Codex from the branch (clean tree), the hook is silent on a missing token, and the paste-back
report is printed. HALT on any unmet prereq and tell the operator exactly which homelab unit to check.
```

## After the Mac session runs
Paste its evidence block back to the homelab agent (or directly into
`docs/gate-artifacts/2026-06-02-gate-A-plugin-and-oauth.md`). Then reply **"Gate A approved"** to
authorize Phase B (U6 read-parity → U7 content-distill cutover → U8 hostname repoint → U13 consumer
sweep → Gate B).
