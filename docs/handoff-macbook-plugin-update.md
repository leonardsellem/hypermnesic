# MacBook handoff — update the hypermnesic plugin locally (slim hook + latest fixes)

Paste the fenced block below into a Claude Code session on your MacBook. It re-pulls the branch
and reinstalls the plugin on **Claude + Codex** so the Mac picks up the slimmed, user-neutral
auto-recall hook (one `UserPromptSubmit` event, no SessionStart preamble, no Bash guard, no gbrain
content) and the latest fixes. Reversible (`claude/codex plugin remove`). Secrets are never printed.

```text
You are a Claude Code session on a MacBook (a Tailscale tailnet peer; homelab = <your-host>.ts.net).
Update the locally-installed `hypermnesic` plugin to the latest branch and verify it. Work ONLY on
this Mac. Never print or commit any token or secret.

1) PULL THE BRANCH
   cd ~/hypermnesic 2>/dev/null || cd /Volumes/Dev/worktrees/hypermnesic/condescending-sutherland-4d9b29
   git fetch origin && git checkout claude/condescending-sutherland-4d9b29 && git pull --ff-only
   git log --oneline -1        # expect 5ecfb7d or later
   # confirm the slim hook landed: exactly ONE event, zero gbrain
   python3 -c "import json,sys; d=json.load(open('plugin/plugins/hypermnesic/hooks/hooks.json')); print('events:', list(d['hooks'])); assert list(d['hooks'])==['UserPromptSubmit']"
   grep -ric gbrain plugin/ || echo "gbrain refs: 0 (user-neutral)"

2) REINSTALL ON CLAUDE (refresh the cached snapshot)
   claude plugin uninstall hypermnesic@hypermnesic 2>/dev/null || true
   # canonical: GitHub-backed source (content-addressed, reused across sessions); falls back to the local plugin/ dir
   claude plugin marketplace update hypermnesic 2>/dev/null \
     || claude plugin marketplace add leonardsellem/hypermnesic 2>/dev/null \
     || claude plugin marketplace add "$PWD/plugin"
   claude plugin install hypermnesic@hypermnesic
   claude plugin list | grep -A2 'hypermnesic@hypermnesic'      # MUST show: Status: ✔ enabled

3) REINSTALL ON CODEX
   codex plugin remove hypermnesic@hypermnesic 2>/dev/null || true
   codex plugin marketplace add "$PWD/plugin" 2>/dev/null || true
   codex plugin add hypermnesic@hypermnesic
   codex plugin list | grep hypermnesic                          # MUST show: installed, enabled

4) (OPTIONAL) ACTIVATE PROACTIVE AUTO-RECALL
   The slim hook is silent unless BOTH HYPERMNESIC_MCP_URL and HYPERMNESIC_MCP_TOKEN are in the
   environment (otherwise it no-ops, never blocking a turn). To turn it on for this Mac, export
   in your shell profile (the token is short-lived; mint it as in the Gate-A handoff):
     export HYPERMNESIC_MCP_URL=http://<your-host>.ts.net:8851/mcp
     # export HYPERMNESIC_MCP_TOKEN=...   # minted from the AS; never commit it
   Then a memory-relevant prompt injects top hits; everything else stays silent.

5) HARDEN THE LOCAL SECRET FILE (the Gate-A residual you flagged)
   chmod 600 /Volumes/Dev/hypermnesic/.env   # holds HYPERMNESIC_AS_CLIENT_SECRET + OPENAI_API_KEY
   ls -l /Volumes/Dev/hypermnesic/.env        # confirm -rw------- (was world-readable 644)

6) REPORT: print the Claude + Codex plugin-list lines (both enabled), the HEAD SHA, and the
   "gbrain refs: 0" line.

NOTE (separate from the plugin — the cloud mobile connector): the consent-form bug is now FIXED on
the homelab (commit 5ecfb7d). In ChatGPT and Claude, REMOVE any existing "Hypermnesic" connector
and re-add it with the EXACT URL https://<your-host>.ts.net/cloud/mcp (NOT the bare /mcp —
that is a different app). The browser will open the consent page; type your cloud approval token
(homelab: `cat ~/.config/hypermnesic-cloud/cloud.env`) and Approve. It now completes the grant.
```

## Why reinstall
The plugin's manifest declares no `hooks`/`skills` paths (Claude Code auto-discovers them), so a
plain `git pull` updates the source but the **installed cache** still holds the old snapshot —
`uninstall → marketplace update → install` refreshes it. Both hosts share the skills dir via the
`~/.codex/skills → ../.claude/skills` symlink.
