# read-only-proof.tape (U11 / AE5) — the write guard refuses an agent write to a protected path.
#
# Renders the TERMINAL PANEL of media/companion/read-only-proof.gif: an agent drives the REAL
# MCP commit_note tool against protected paths (CLAUDE.md, .git/config) on a loopback,
# WRITE-ENABLED master, and the server-side guard REFUSES each with a specific reason. This
# proves writes stay bounded even with --enable-write. The Obsidian companion — a passive READ
# surface whose tool allowlist is search / build_context / think only, with no write affordance —
# is composited beside this terminal in the final GIF (see media/companion/RECORDING.md §3 and
# the `ffmpeg hstack` recipe). AE5: the companion is shown, not captioned.
#
# RE-RECORD:  vhs media/companion/read-only-proof.tape   (run from the repo root)
# REQUIRES:   vhs (brew install vhs) + ffmpeg + ttyd; `hypermnesic` importable (the hidden setup
#             activates ./.venv if present, else assumes it is installed on PATH); and
#             OPENAI_API_KEY in the environment at record time so the hidden `hypermnesic init`
#             can build the index the master serves. The KEY IS READ FROM THE ENVIRONMENT — it is
#             never written into this tape (so the committed source stays leak-safe). The visible
#             frames make no embedding call: the guard refuses before any embedding, so the
#             refusal text is fully deterministic regardless of recall quality.
# SAFETY:     loopback master only (127.0.0.1, no auth -> no OAuth issuer/consent on screen); the
#             fixture identity is set by materialize-demo-vault so nothing shows the operator's
#             real name/email; sanitized `demo$` prompt. Review every frame against
#             docs/guides/demo-asset-frame-review-checklist.md before publishing.

Require git

Output media/companion/read-only-proof.gif

Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 600
Set Padding 24
Set Theme "TokyoNight"
Set Framerate 15
Set TypingSpeed 18ms
Set PlaybackSpeed 1.0

# ---- hidden setup: disposable vault + loopback write-enabled master ----
# NB: VHS does not block on shell commands — it types the next line immediately. So each SLOW
# setup step below gets its own VHS `Sleep`, otherwise later input (esp. the clear) buffers
# behind a still-running command and renders after Show.
Hide
Type "REPO=$PWD" Enter
Type "source $REPO/.venv/bin/activate 2>/dev/null || true" Enter
Type "export PS1='demo$ '" Enter
Type "rm -rf /tmp/hypermnesic-guard" Enter
Type "$REPO/media/engine/materialize-demo-vault /tmp/hypermnesic-guard >/dev/null" Enter
Sleep 1500ms
Type "cp $REPO/media/engine/hero_commit.py /tmp/hypermnesic-guard/agent_write.py" Enter
Type "cd /tmp/hypermnesic-guard" Enter
Type "hypermnesic init . >/dev/null 2>&1" Enter
Sleep 5s
Type "hypermnesic serve --enable-write --host 127.0.0.1 --port 8765 --index-db .hypermnesic/index.db --repo . >/tmp/guard-serve.log 2>&1 &" Enter
Sleep 3s
# CRITICAL: clear via ANSI printf — the `clear` *command* is a terminfo no-op in VHS's headless
# terminal, so it does NOT wipe the hidden-setup scrollback and Show would capture the
# materialize/serve lines + job-control PID, leaking them into the first visible frames. The
# shell is idle here (every slow step above was awaited), so this clear runs and renders BEFORE
# Show. Inside Hide → no visible time. (LS-1779 hero/index-recovery tapes share this leak.)
Type "printf '\033[3J\033[2J\033[H'" Enter
Sleep 600ms
Show

# ---- the guard proof (visible) ----
Type "# The companion is a READ surface: search / build_context / think — no write tool." Enter
Sleep 500ms
Type "# Even with --enable-write on this master, watch an agent try to abuse it:" Enter
Sleep 800ms

Type "# (1) overwrite an agent-instruction file" Enter
Sleep 300ms
Type "python agent_write.py --path CLAUDE.md --summary 'overwrite agent instructions' --body 'pwned'" Enter
Sleep 1800ms

Type "# (2) reach into the git internals" Enter
Sleep 300ms
Type "python agent_write.py --path .git/config --summary 'edit git internals' --body 'pwned'" Enter
Sleep 1800ms

Type "# Refused by path, with a reason — not crashed. The write path is bounded." Enter
Sleep 1900ms

# ---- hidden teardown ----
Hide
Type "kill %1 2>/dev/null" Enter
Type "cd $REPO" Enter
Show
