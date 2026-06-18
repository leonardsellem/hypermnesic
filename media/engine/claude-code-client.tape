# claude-code-client.tape (U7) — "same endpoint, a real client": Claude Code drives the live MCP.
#
# Renders media/engine/claude-code-client.gif: the Claude Code TUI, pointed at the SAME loopback
# master via streamable-HTTP MCP, calling the real read/write tools (search -> think -> a real
# commit_note). This was originally flagged "manual GUI capture / not .tape-scriptable"; the
# LS-1778 research corrected that — VHS runs real commands in a real shell, so it drives a live
# Claude Code -> loopback-MCP session, and `Wait+Screen` makes it latency-tolerant (R10 recovered).
#
# ┌──────────────────────────────────────────────────────────────────────────────────────────┐
# │ STATUS: SETUP VALIDATED · VISIBLE TUI SECTION RENDER-PENDING.                               │
# │ The hidden setup (materialize → init → serve → `claude mcp add --transport http`) is        │
# │ smoke-tested working. The visible Claude Code TUI section could NOT be render-validated in   │
# │ the build env because a standalone `claude` invocation returns 401 (the agent session's      │
# │ Anthropic auth is a harness-managed OAuth token bound to a custom ANTHROPIC_BASE_URL; a      │
# │ fresh subprocess can't use it, and ~/.claude/.credentials.json is stale).                    │
# │ TO RENDER: run `claude login` first, then `vhs media/engine/claude-code-client.tape`.        │
# │ Model wording is non-deterministic — re-render until clean; the `Wait+Screen` patterns below │
# │ may need timing tweaks on first real render. Then frame-review + sign off media/.review-log. │
# └──────────────────────────────────────────────────────────────────────────────────────────┘
#
# REQUIRES:   vhs + ffmpeg + ttyd; `hypermnesic` importable; the `claude` CLI authenticated
#             (`claude login`); OPENAI_API_KEY in the environment (read at record time, never
#             written into this tape) so the hidden `hypermnesic init` can build the index.
# SAFETY:     loopback master only (127.0.0.1, no auth → no OAuth issuer/consent on screen);
#             fixture identity via materialize-demo-vault; sanitized `demo$` prompt; the MCP
#             endpoint shows only 127.0.0.1. The Claude Code TUI must show NO account badge/avatar
#             and NO window-title path bar — use a clean profile/crop. Review EVERY frame against
#             docs/guides/demo-asset-frame-review-checklist.md before publishing.

Require git

Output media/engine/claude-code-client.gif

Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 720
Set Padding 24
Set Theme "TokyoNight"
Set Framerate 15
Set TypingSpeed 22ms
Set PlaybackSpeed 1.0

# ---- hidden setup: disposable vault + loopback write-enabled master + Claude Code MCP registration ----
# (Same VHS discipline as the other tapes: await each slow step; clear via ANSI printf, not the
# `clear` command, which is a no-op in VHS's headless terminal — see hero-receipt-loop.tape.)
Hide
Type "REPO=$PWD" Enter
Type "source $REPO/.venv/bin/activate 2>/dev/null || true" Enter
Type "export PS1='demo$ '" Enter
Type "rm -rf /tmp/hypermnesic-cc" Enter
Type "$REPO/media/engine/materialize-demo-vault /tmp/hypermnesic-cc >/dev/null" Enter
Sleep 1500ms
Type "cd /tmp/hypermnesic-cc" Enter
Type "hypermnesic init . >/dev/null 2>&1" Enter
Sleep 5s
Type "hypermnesic serve --enable-write --host 127.0.0.1 --port 8765 --index-db .hypermnesic/index.db --repo . >/tmp/cc-serve.log 2>&1 &" Enter
Sleep 3s
Type "claude mcp add --transport http --scope local hypermnesic http://127.0.0.1:8765/mcp >/dev/null 2>&1" Enter
Sleep 2s
Type "printf '\033[3J\033[2J\033[H'" Enter
Sleep 600ms
Show

# ---- the multi-client proof (visible): Claude Code calls the same MCP endpoint ----
Type "# Claude Code, pointed at the same hypermnesic MCP endpoint (127.0.0.1:8765/mcp):" Enter
Sleep 900ms
# Start the TUI with an initial prompt that exercises search -> think -> a real commit_note.
Type "claude --dangerously-skip-permissions 'Use the hypermnesic search tool to find the sqlite-vec decision, use think to reflect, then commit_note a short note at decisions/ship-receipts-first.md that links [[decisions/use-sqlite-vec]].'" Enter
# Block until the write tool is actually invoked, then until it lands — tolerant of model latency.
Wait+Screen /commit_note/
Sleep 1500ms
Wait+Screen /committed|wrote|✓/
Sleep 3500ms
# Leave the TUI cleanly.
Ctrl+C
Sleep 400ms
Ctrl+C
Sleep 800ms

# ---- hidden teardown ----
Hide
Type "claude mcp remove --scope local hypermnesic >/dev/null 2>&1" Enter
Type "kill %1 2>/dev/null" Enter
Type "cd $REPO" Enter
Show
