# Demo-asset frame-review checklist (manual leak gate)

The automatic text scanner (`scripts/preflight_public_scan.py`) reads tracked **text**
— `.tape` sources and caption `.md` under `media/`. It **cannot read pixels**: a leak
rendered into a GIF/PNG frame (a shell prompt, a window title, an account badge)
decodes as bytes and is skipped on `UnicodeDecodeError`. So every rendered binary gets
this **manual** review before it is embedded anywhere, and the result is signed off in
[`media/.review-log.md`](../../media/.review-log.md). This gate is **not optional**
(plan U3 / AE2; origin R13).

## Before you record — sanitize the environment

- **Shell prompt:** export a neutral prompt, e.g. `PS1='demo$ '` (zsh: `PROMPT='demo$ '`).
  Never record a prompt that shows your real `user@host` or `cwd`.
- **Working dir:** `cd` into the materialized vault and keep the path generic
  (`/tmp/demo-vault`, shown as `demo$`), never the raw `/var/folders/…` mktemp path or a
  `/Users/<you>/…` path. The materialize helper can take an explicit dest:
  `media/engine/materialize-demo-vault /tmp/demo-vault`.
- **Endpoint:** only the placeholder `https://<your-host>.ts.net/mcp`; for the live write
  use the loopback `127.0.0.1` master (no auth → no OAuth issuer/consent on screen).
- **Window chrome (GUI captures — Claude Code, Obsidian):** crop or use a clean profile
  so no account badge/avatar, no window-title path bar, and no real vault name appear.
- **Terminal width/theme:** ~100 columns, a dark theme, large enough to stay legible at
  mobile width.

## Scrub every frame for — fail the asset if ANY appears

- [ ] **Real endpoint URL** — only `https://<your-host>.ts.net/mcp` (placeholder) may show.
- [ ] **Operator host / IP** — no real tailnet hostname, no homelab node IP. Tailnet/private
      IPs only from the CGNAT range `100.64.0.0/10` (e.g. `100.64.0.1`).
- [ ] **Absolute home / scratch paths** — no `/Users/<name>/…`, `/home/<name>/…`, or
      `/var/folders/…`. Use `/path/to/your/vault` or a generic `/tmp/demo-vault`.
- [ ] **Secrets / tokens** — no OpenAI key (`sk-…`), JWT (`eyJ…`), PEM private key, Bearer
      token, or `*_TOKEN=<value>`. The key lives in the env, never on screen.
- [ ] **Private note bodies** — only the committed disposable fixture vault content
      (`media/engine/demo-vault-seed/`, `media/companion/demo-vault-seed/`) may appear; no
      real brain notes (AE2).
- [ ] **Committer identity in `git log`** — only the fixture identity
      (`hypermnesic demo <demo@hypermnesic.invalid>`), never the operator's real name/email.
- [ ] **GUI leak surfaces** — no Claude Code account badge/avatar, no window-title path bar,
      no real Obsidian vault name, no notification/menu-bar PII.

## Optional machine assist (OCR)

A rough second pass: OCR the rendered frames and grep the text against the deny-set.

```sh
# extract frames, OCR, and re-run the text scanner's deny-set over the OCR output
ffmpeg -i media/engine/hero-receipt-loop.gif -vsync 0 /tmp/frames/%04d.png
for f in /tmp/frames/*.png; do tesseract "$f" - 2>/dev/null; done > /tmp/ocr.txt
uv run python -c "import scripts.preflight_public_scan as p,sys; \
  hits=p.scan_text(open('/tmp/ocr.txt').read()); print(hits or 'OCR clean')"
```

OCR is lossy (it misreads fonts), so it **supplements** the human pass — it does not
replace it. Record the OCR result in the sign-off row when you run it.

## Sign off

After a clean review, add a row to [`media/.review-log.md`](../../media/.review-log.md):
asset path, reviewer, date (`YYYY-MM-DD`), `pass`/`fail`, and any notes (e.g. "OCR clean").
An asset is **not shippable** — not embedded in any README, not posted — until its row
reads `pass`.
