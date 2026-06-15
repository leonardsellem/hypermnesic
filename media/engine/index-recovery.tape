# index-recovery.tape (U5) — files are the truth; the index is disposable.
#
# Renders media/engine/index-recovery.gif: delete the entire index, show the markdown
# survives (ls before/after), rebuild from the committed files, recall restored (AE4).
#
# RE-RECORD:  vhs media/engine/index-recovery.tape   (run from the repo root)
# REQUIRES:   vhs + ffmpeg + ttyd; `hypermnesic` importable (hidden setup activates ./.venv
#             if present, else assumes it is installed); OPENAI_API_KEY for `hypermnesic init`
#             (without a key the rebuild + recall still work but degrade to lexical).
# SAFETY:     disposable fixture vault only; sanitized `demo$` prompt; review every frame
#             against docs/guides/demo-asset-frame-review-checklist.md before publishing.

Require git

Output media/engine/index-recovery.gif

Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 640
Set Padding 24
Set Theme "TokyoNight"
Set Framerate 15
Set TypingSpeed 18ms
Set PlaybackSpeed 1.0

# ---- hidden setup ----
Hide
Type "REPO=$PWD" Enter
Type "source $REPO/.venv/bin/activate 2>/dev/null || true" Enter
Type "export PS1='demo$ '" Enter
Type "clear" Enter
Type "rm -rf /tmp/hypermnesic-recovery" Enter
Type "$REPO/media/engine/materialize-demo-vault /tmp/hypermnesic-recovery >/dev/null" Enter
Type "cd /tmp/hypermnesic-recovery" Enter
Type "hypermnesic init . >/dev/null 2>&1" Enter
Type "clear" Enter
Show

# ---- the recovery proof (visible) ----
Type "# Your memory is plain markdown in git; the index is a disposable projection" Enter
Sleep 700ms
Type "ls" Enter
Sleep 1400ms
Type "ls .hypermnesic" Enter
Sleep 1600ms

Type "# Delete the entire index" Enter
Sleep 400ms
Type "rm -rf .hypermnesic" Enter
Sleep 600ms
Type "ls   # the markdown files are untouched -- files are the truth" Enter
Sleep 1800ms

Type "# Rebuild the index from the committed markdown" Enter
Sleep 400ms
Type "hypermnesic init ." Enter
Sleep 2200ms
Type "hypermnesic retrieve . 'vector-search extension'   # recall restored" Enter
Sleep 3000ms

# ---- hidden teardown ----
Hide
Type "cd $REPO" Enter
Show
