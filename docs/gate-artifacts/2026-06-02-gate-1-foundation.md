# GATE 1 — Foundation healthy? (Go/No-Go)

**Plan:** `docs/plans/2026-06-02-008-feat-homelab-dogfood-cutover-plan.md`
**Phase B units:** U3 (master + index), U4 (Mac client config), U12 (.gitignore guard)
**Captured:** 2026-06-02, on `homelab-hetzner-staging` (tailnet `100.64.0.55`)
**Verdict:** all agent-verifiable PASS; **2 items are operator-side (Mac)** — see ▢ below.

---

## PASS checklist (plan Gate 1)

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | `is-active=active`, `is-enabled=enabled`, `Linger=yes` | ✅ | `active` / `enabled` / `Linger=yes`; `NRestarts=0` |
| 2 | ExecStart = absolute venv path; socket bound only to `100.64.0.55` (not wildcard) | ✅ | `ExecStart=<home>/.local/bin/hypermnesic … --host 100.64.0.55 --enable-write`; `ss -ltnp` → `LISTEN 100.64.0.55:8848` (pid hypermnesic) |
| 3 | `tools/list` + `search` return hits; `build_context`+`think` answer; `degraded_lexical_only:false`; `manual_reindex_recommended:false` | ✅ (agent) / ▢ (Mac peer) | MCP probe over `http://100.64.0.55:8848/mcp`: tools `[build_context, commit_note, search, think]`; search 10 hits, `degraded_lexical_only:False`, top via `['dense','doc']`; think `wrote:False`, 8 related; build_context ok — all `manual_reindex_recommended:False`. **Probed from the homelab hitting the tailnet IP; literal "second peer = Mac" is ▢ operator-side.** |
| 4 | Tool list includes `commit_note` (write-enabled) AND `audit.jsonl` has zero entries | ✅ | `commit_note` present; `{vault}/.hypermnesic/audit.jsonl` **absent** (zero hypermnesic writes — present-but-unused) |
| 5 | Indexed-doc count ≈ tracked `.md` (build completeness) | ✅ | index: 27,199 chunks / **3,520 docs** vs **3,095** tracked `.md` (≥ tracked; extra = untracked working-tree md). Build exit 0 → the unparseable-YAML docs did **not** abort it |
| 6 | Vault `git status` clean; `.hypermnesic/` excluded; `{vault}/.env` gitignored; `.gitignore` byte-stable (U12) | ✅ | porcelain 0 lines; `.git/info/exclude` has `.hypermnesic/` (engine-written) + `.env`; `check-ignore .env` ✅; `.gitignore` no `db_only` block, `sources/` not ignored, 0 modified lines |
| 7 | U11 push smoke — (a) `commit_note` on a file test remote lands + no local-only commit; (b) **real-origin push from the service environment** succeeds | ✅✅ | (a) live `commit_note` on an isolated bare remote: landed on `origin/main`, local-ahead=0. (b) `systemd-run --user` (HOME set, **no inherited ssh-agent** — same env as `hypermnesic.service`) `git push origin main` → `3d374e6..d4afb69`, rc=0. SSH `id_ed25519` reachable from the unit ✅ |
| 8 | Obsidian related-notes panel populates over the tailnet | ▢ operator-side | Mac client config emitted at `~/.cache/hypermnesic-mac-client.json` (`mcpServers.hypermnesic` → `streamable-http` `http://100.64.0.55:8848/mcp`) — apply on the Mac + load Obsidian |
| 9 | Homelab mirror doc + `LOG.md` entry exist (R16) | ✅ | `projects/homelab/services/hypermnesic.md` + `LOG.md` entry committed + pushed to `origin/main` (`d4afb69`) |

**Bonus (de-risks U6/U9):** the live service's read-time convergence ingested a
**foreign git commit** (the mirror, pushed past the index checkpoint) and made it
recall-able on the first read — the exact disk→index path the canary validation needs.

---

## Deploy decisions recorded (deferred-to-impl, now resolved)
- **OpenAI key:** sourced from `~/.gbrain/config.json:openai_api_key` into `{vault}/.env`
  (mode 600, gitignored). gbrain uses the **same** `text-embedding-3-large`@1536.
- **Durable exe:** `uv tool install` → `~/.local/bin/hypermnesic` (Phase-1 branch snapshot;
  independent of the ephemeral worktree). Re-install when Phase A lands on `main`.
- **Push creds:** `~/.ssh/id_ed25519` works in `BatchMode` from a `systemd --user`
  context — no agent needed (verified by smoke 7b).
- **Allowlist:** rendered unit uses `DEFAULT_WRITE_ALLOWLIST` (`sources/` included →
  canary works). `serve --allowlist` available for a tighter surface (follow-up).

## Operator actions before approving Gate 1
1. On the Mac: apply the emitted `mcpServers.hypermnesic` config, set the Obsidian
   plugin URL to `http://100.64.0.55:8848/mcp`, load Obsidian, confirm the
   related-notes panel populates + the read-only badge (items 3 "Mac peer" + 8).
2. Approve to release **Phase C** (U5 dry-run dogfood on the live vault, U6 isolated
   clone canary) → Gate 2.

## HALT conditions (none currently tripped)
Any item 1–7 or 9 failing → stop, surface the signal, await decision. Items 3(Mac)/8
pending operator verification on the Mac.
