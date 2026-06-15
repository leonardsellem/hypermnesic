# media/ — launch demo assets

Home for the launch-promotion assets: rendered media (GIF/PNG/SVG), the `.tape`
sources that produce the terminal recordings, captions, and the disposable fixture
vaults the recordings run against.

> **Why `media/` and not `docs/launch/`?** `docs/launch/` is *unconditionally
> excluded* from the leak scanner (`scripts/preflight_public_scan.py`) — it is the
> staging area that documents the very secrets being prepared. Assets placed there
> would bypass the leak gate. `media/` is a non-`docs/` path, so its tracked text is
> in the scanner's **default** scope (a regression test in
> [`tests/test_preflight_public_scan.py`](../tests/test_preflight_public_scan.py)
> locks this — see U3).

## Layout

```text
media/
  README.md                       # this file — the placeholder/scan convention
  .review-log.md                  # per-asset manual frame-review sign-off (U3)
  engine/
    demo-vault-seed/              # dev-flavored seed files (no nested .git) — U2
    materialize-demo-vault        # record-time helper: seed -> scratch git repo — U2
    hero-receipt-loop.tape        # scripted terminal hero — U4
    hero-receipt-loop.gif
    index-recovery.tape           # destructive-recovery — U5
    index-recovery.gif
    benchmark-longmemeval.svg     # committed chart, no new dependency — U6
    claude-code-client.gif        # GUI screen recording — U7
    connector-montage/            # placeholder-URL stills — U7
    carousel-selfhosted/          # 3-5 stills — U8
    carousel-localllama/
    carousel-hn/
  companion/
    demo-vault-seed/              # PKM-flavored seed files — U10
    RECORDING.md                  # Obsidian + companion recording setup — U10
    companion-hero.gif            # U11
    read-only-proof.gif           # U11
    obsidianmd-still.png          # U12
```

## The placeholder/scan convention (read before adding any asset)

Every asset runs against a **disposable, committed fixture vault** with no real brain
content, no real endpoint, and no secrets. The **only** allowed stand-ins are:

| Use | Placeholder |
|---|---|
| Remote MCP endpoint | `https://<your-host>.ts.net/mcp` |
| Local vault path | `/path/to/your/vault` |
| Tailnet / private IPs | the CGNAT range `100.64.0.0/10` (e.g. `100.64.0.1`) |
| Tokens / keys | redacted (`<redacted-token>`), never a real value |
| Git committer in recordings | the fixture identity (`hypermnesic demo` / `local-proof@example.invalid`), **never** the operator's global git name/email |

Never put a real tailnet hostname, homelab IP, OpenAI key, JWT, PEM key, or an
absolute home path (`/Users/<you>/…`, `/home/<you>/…`, `/var/folders/…`) into a
`.tape`, caption, or rendered frame.

## The two-gate leak check (mandatory before any asset ships)

Text and rendered frames fail differently, so there are two gates:

1. **Text gate — automatic.** `.tape` files and caption `.md` under `media/` are
   git-tracked text and are scanned by `scripts/preflight_public_scan.py` on every
   run (and in CI). The deny-set covers operator host/IP, credential classes, and
   home paths — including macOS `/Users/<name>/` and `/var/folders/…` (added in U3).
   Run it locally with `uv run python scripts/preflight_public_scan.py`.
2. **Frame gate — manual.** A regex-over-bytes scanner cannot read pixels, so every
   rendered GIF/PNG/SVG is reviewed by hand against
   [`docs/guides/demo-asset-frame-review-checklist.md`](../docs/guides/demo-asset-frame-review-checklist.md)
   and signed off in [`.review-log.md`](.review-log.md) (one row per published
   binary) **before** it is embedded anywhere. This gate is not optional.

## Reproducing assets

- **Engine terminal recordings (U4, U5)** are driven by committed VHS `.tape` files
  ([charmbracelet/vhs](https://github.com/charmbracelet/vhs), MIT). Install with
  `brew install vhs`, then `vhs media/engine/<name>.tape`. They are deterministic and
  re-recordable by anyone, not just the author.
- **GUI recordings (U7 Claude Code, U11/U12 Obsidian companion)** are partly manual
  and cannot be `.tape`-scripted. The reproducible substitute is the documented setup
  in [`companion/RECORDING.md`](companion/RECORDING.md) plus the sanitization items in
  the frame-review checklist.
