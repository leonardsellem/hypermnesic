# hero-receipt-loop.tape (U4) — the engine hero: write -> git log -> recall.
#
# Renders media/engine/hero-receipt-loop.gif: an agent writes a memory through the REAL
# MCP commit_note tool, `git log` shows the resulting REAL commit, and a fresh session
# recalls and cites it. Silent, looping, ~15 s (<=20 s), write->commit inside the first
# ~5 s of the visible loop (AE1).
#
# RE-RECORD:  vhs media/engine/hero-receipt-loop.tape   (run from the repo root)
# REQUIRES:   vhs (brew install vhs) + ffmpeg + ttyd; `hypermnesic` importable (the hidden
#             setup activates ./.venv if present, else assumes it is installed on PATH);
#             and OPENAI_API_KEY in the environment so `hypermnesic init` builds the index
#             and `retrieve` recalls semantically (without a key the read path still works
#             but degrades to lexical and prints "degraded=True"). The recall query is
#             chosen so it matches on BOTH the semantic (keyed) and lexical (no-key) paths.
# SAFETY:     loopback master only (127.0.0.1, no auth -> no OAuth issuer/consent on
#             screen); the fixture identity is set by materialize-demo-vault so `git log`
#             never shows the operator's real name/email. Review every frame against
#             docs/guides/demo-asset-frame-review-checklist.md before publishing.

Require git

Output media/engine/hero-receipt-loop.gif

Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 600
Set Padding 24
Set Theme "TokyoNight"
Set Framerate 15
Set TypingSpeed 18ms
Set PlaybackSpeed 1.0

# ---- hidden setup: build a clean disposable vault + loopback write-enabled master ----
Hide
Type "REPO=$PWD" Enter
Type "source $REPO/.venv/bin/activate 2>/dev/null || true" Enter
Type "export PS1='demo$ '" Enter
Type "clear" Enter
Type "rm -rf /tmp/hypermnesic-hero" Enter
Type "$REPO/media/engine/materialize-demo-vault /tmp/hypermnesic-hero >/dev/null" Enter
Type "cp $REPO/media/engine/hero_commit.py /tmp/hypermnesic-hero/agent_write.py" Enter
Type "cd /tmp/hypermnesic-hero" Enter
Type "hypermnesic init . >/dev/null 2>&1" Enter
Type "hypermnesic serve --enable-write --host 127.0.0.1 --port 8765 --index-db .hypermnesic/index.db --repo . >/tmp/hero-serve.log 2>&1 &" Enter
Type "sleep 3" Enter
Type "clear" Enter
Show

# ---- the receipt loop (visible) ----
Type "# An agent writes a memory through the real MCP commit_note tool" Enter
Sleep 700ms
Type "python agent_write.py --path decisions/ship-receipts-first.md --summary 'Lead the launch with the git receipt' --body 'The git receipt: write a memory, the commit is real, a fresh session recalls it.'" Enter
Sleep 2200ms

Type "# The write produced a REAL git commit -- here is the receipt:" Enter
Sleep 500ms
Type "git log --oneline -3" Enter
Sleep 2400ms

Type "# A fresh session recalls it, cited to the source markdown file" Enter
Sleep 500ms
Type "hypermnesic retrieve . 'git receipt'" Enter
Sleep 3200ms

# ---- hidden teardown ----
Hide
Type "kill %1 2>/dev/null" Enter
Type "cd $REPO" Enter
Show
