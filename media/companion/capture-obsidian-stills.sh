#!/usr/bin/env bash
# capture-obsidian-stills.sh (U11/U12) — scripted Obsidian-CLI capture of the companion stills.
#
# The companion assets were originally flagged "manual Obsidian GUI capture". Obsidian's official
# CLI (`dev:screenshot`, GA 1.12.4) makes them scriptable AND TCC-free — Obsidian screenshots its
# own window via CDP, so no macOS Screen-Recording grant is needed. This script materializes a
# DISPOSABLE demo vault (never a real vault — AE2), wires the companion to a loopback master, opens
# it, drives each surface, and screenshots it.
#
# PREREQUISITES:
#   - Obsidian INSTALLER >= 1.12.4 (Settings → About; the in-app "Check for updates" only bumps the
#     app/asar, NOT the installer — reinstall from https://obsidian.md/download). `dev:screenshot`
#     silently fails on older installers.
#   - OPENAI_API_KEY in the env (the master's `hypermnesic init` requires it) — never printed.
#   - The companion plugin built at $COMPANION (main.js/manifest.json/styles.css).
#
# GOTCHAS (learned the hard way, baked in below):
#   - dev:screenshot captures a STALE frame unless Obsidian is FOREGROUND — every shot is preceded
#     by `osascript ... activate`.
#   - The reinvention nudge fires only when hits[0].score >= reinventThreshold; this tiny demo
#     vault's RRF scores are ~0.03, so we set a demo threshold below the (genuine) top score.
#   - Opening a brand-new vault needs it registered in obsidian.json + an Obsidian restart.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPANION="${COMPANION:-/Volumes/Dev/hypermnesic-companion}"
VAULT="${1:-/tmp/companion-demo-vault}"
OUT="${2:-/tmp/companion-stills}"
OBS=/Applications/Obsidian.app/Contents/MacOS/obsidian
PORT=8765
flt() { grep -v "Loading updated\|installer is out of date"; }
shot() { osascript -e 'tell application "Obsidian" to activate' >/dev/null 2>&1; sleep 1; rm -f "$1"; "$OBS" dev:screenshot path="$1" 2>&1 | flt >/dev/null; echo "  → $1 ($(wc -c <"$1" 2>/dev/null)b)"; }
cmd()  { "$OBS" command id="$1" 2>&1 | flt >/dev/null; }

[ -d "$COMPANION" ] || { echo "companion plugin not found at $COMPANION"; exit 1; }
mkdir -p "$OUT"

echo "== 1. materialize disposable vault + companion plugin + loopback master =="
lsof -ti tcp:$PORT 2>/dev/null | xargs -r kill 2>/dev/null
rm -rf "$VAULT"; mkdir -p "$VAULT"; cp -R "$REPO/media/companion/demo-vault-seed/." "$VAULT"/
P="$VAULT/.obsidian/plugins/hypermnesic-companion"; mkdir -p "$P"
cp "$COMPANION"/main.js "$COMPANION"/manifest.json "$COMPANION"/styles.css "$P"/
printf '%s\n' '["hypermnesic-companion"]' > "$VAULT/.obsidian/community-plugins.json"
printf '{"mcpUrl":"http://127.0.0.1:%s/mcp","openSidebarOnLoad":true,"showStatusBar":true,"showGutter":true,"reinventThreshold":0.02}\n' "$PORT" > "$P/data.json"
( cd "$VAULT"
  git init -q -b main; git config user.name "hypermnesic demo"; git config user.email "demo@hypermnesic.invalid"
  GIT_AUTHOR_DATE="2026-05-06T09:00:00" GIT_COMMITTER_DATE="2026-05-06T09:00:00" \
  GIT_AUTHOR_NAME="hypermnesic demo" GIT_AUTHOR_EMAIL="demo@hypermnesic.invalid" \
  GIT_COMMITTER_NAME="hypermnesic demo" GIT_COMMITTER_EMAIL="demo@hypermnesic.invalid" \
    bash -c 'git add daily ideas people projects 2>/dev/null; git commit -q -m "Seed companion demo vault"'
  hypermnesic init . >/dev/null 2>&1
  hypermnesic serve --enable-write --host 127.0.0.1 --port '"$PORT"' --index-db .hypermnesic/index.db --repo . >/tmp/companion-serve.log 2>&1 &
)
for i in $(seq 1 30); do grep -qiE "Uvicorn running" /tmp/companion-serve.log 2>/dev/null && break; sleep 0.5; done
echo "  master: $(lsof -ti tcp:$PORT >/dev/null && echo UP || echo DOWN)"

echo "== 2. register + open the vault in Obsidian (restart to pick it up) =="
OBSJSON="$HOME/Library/Application Support/obsidian/obsidian.json"
cp "$OBSJSON" "/tmp/obsidian.json.bak.$$"
python3 - "$OBSJSON" "$VAULT" <<'PY'
import json,sys,time
p,vault=sys.argv[1],sys.argv[2]
d=json.load(open(p)); v=d.setdefault('vaults',{})
for e in v.values(): e['open']=False
vid=next((k for k,e in v.items() if e.get('path')==vault), None) or ("%016x"%(int(time.time()*1000)&((1<<64)-1)))
v[vid]={'path':vault,'ts':int(time.time()*1000),'open':True}
json.dump(d,open(p,'w'),indent=2)
PY
osascript -e 'tell application "Obsidian" to quit' >/dev/null 2>&1; sleep 3
pgrep -x Obsidian >/dev/null && { pkill -x Obsidian; sleep 2; }
open -a Obsidian; sleep 7
echo "  active vault: $("$OBS" eval code='this.app.vault.adapter.basePath' 2>&1 | flt | tail -1)"

echo "== 3. drive each surface + screenshot =="
echo "thinking-mode:"; "$OBS" open file=second-brain 2>&1|flt>/dev/null; sleep 1; cmd hypermnesic-companion:think-about-note; sleep 5; shot "$OUT/thinking-mode.png"
echo "sidebar:";       "$OBS" open file=second-brain 2>&1|flt>/dev/null; sleep 1; cmd hypermnesic-companion:open-recall-sidebar; cmd hypermnesic-companion:recall-related-now; sleep 4; shot "$OUT/sidebar.png"

echo "obsidianmd-still (agent writes a [[wikilink]] note -> new graph node):"
python3 "$REPO/media/engine/hero_commit.py" --url "http://127.0.0.1:$PORT/mcp" \
  --path ideas/atomic-notes.md --summary "Capture atomic notes as the unit of thought" \
  --body "Atomic notes are the unit of reusable thought. They link out to related ideas like [[ideas/evergreen-notes]] and [[ideas/second-brain]], so the graph stays connected." 2>&1 | flt | head -2
sleep 2; "$OBS" open file=atomic-notes 2>&1|flt>/dev/null; sleep 1; cmd graph:open; sleep 4; shot "$OUT/obsidianmd-still.png"

echo "reinvention-nudge (a note paraphrasing second-brain -> 'You may be reinventing' the genuine top match):"
cat > "$VAULT/ideas/rediscovering.md" <<'MD'
# Rediscovering my own thinking

An external place to keep the thinking you'd rather not redo. The real test is
retrieval: can you find a claim months later, with its original context intact?
It should be plain files you own, not locked inside an app.
MD
sleep 2; "$OBS" open file=rediscovering 2>&1|flt>/dev/null; sleep 1
cmd hypermnesic-companion:recall-related-now; sleep 5; shot "$OUT/reinvention-nudge.png"

echo "== done. stills in $OUT/ =="
echo "Next: frame-review + OCR-sweep each, downscale for the companion README, then sign off media/.review-log.md."
echo "Restore your own session by reopening your vault in Obsidian (this script left the demo vault active)."
