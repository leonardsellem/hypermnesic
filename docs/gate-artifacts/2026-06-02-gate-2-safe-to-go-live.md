# GATE 2 — Safe to go live? (evidence review)

**Plan:** `docs/plans/2026-06-02-008-feat-homelab-dogfood-cutover-plan.md`
**Phase C units:** U5 (dry-run dogfood on the live vault, read-only), U6 (GBRAIN_HOME-isolated clone canary)
**Captured:** 2026-06-02, on `homelab-hetzner-staging`
**Verdict:** **GO** — cutover writes are safe, foreign-commit ingest + recall proven, isolation perfect. No HALT condition tripped.

---

## U5 — Dry-run dogfood on the LIVE vault (read-only, `dry_run=True` throughout)

Run as two passes via `harness/dogfood_commit_note.py --repo <home>/gbrain-brain`.

### Pass 1 — cutover set (the intended Phase-1 writes) → **`safe_to_cut_over: true`, 0 blocked**
| Input | Verdict |
|---|---|
| `sources/hypermnesic-canary-2026-06-02.md` (new) | `ok` (create, 6 diff lines) |
| `sources/hypermnesic-dogfood-probe.md` (new) | `ok` (create, 6 diff lines) |

The intended canary path is **safe** on the live vault (AE1). `sources/` is a free-append
zone → no frontmatter-gate exposure for a fresh note.

### Pass 2 — guard/gate negative controls (expected blocked, must not crash) → all blocked, no crash
| Input | Verdict | Why it's correct |
|---|---|---|
| `AGENTS.md` | `refused` | protected agent-instruction file |
| `…/skills/_template/SKILL.md` (one of the unparseable-YAML docs) | `refused` | protected `skills/` dir — bad YAML never even reaches the parser |
| live meeting doc + structural `set_fields` | `gate-abort` (diff returned) | diff-or-die caught a real reflow (`participants: null` → `participants:`) |

`safe_to_cut_over:false` here is **by design** (deliberate negative controls), not a cutover blocker.

## U6 — Clone canary on a `GBRAIN_HOME`-isolated PGLite DB (zero risk to live Supabase)

Every gbrain command carried `GBRAIN_HOME=<tmp>`; a local clone of the vault was the brain repo.

| Check | Result |
|---|---|
| Isolated init | `gbrain init --pglite` → isolated `engine: pglite` under `<tmp>/.gbrain`; global stayed `postgres` |
| Initial text import (`sync --no-embed`) | 2,689 pages / 13,291 chunks into the isolated DB; the **2 unparseable-YAML docs** surfaced as parse failures (gbrain blocks the bookmark — expected) |
| **Foreign git-first commit ingest** (AE2) | added a new `sources/…` commit (no `put_page` origin); `sync --no-embed --skip-failed` → **`1 file imported, checkpoint 43981ec5`** |
| **Recall-able** (AE2) | `gbrain search <marker>` → `[0.2432] sources/u6-foreign-… # u6 foreign canary` (FTS, no embeddings needed) |
| **Isolation held** | global `~/.gbrain/config.json` mtime **2026-05-29**, `sync-failures.jsonl` **2026-05-21** — both predate this session; **nothing** written to global state; live gbrain HTTP serve untouched; engine `postgres` throughout |
| U12 corroboration | `gbrain sync` logged **"Managing .gitignore anyway"** and touched the *clone's* `.gitignore` → confirms `manageGitignore()` is real (mitigated live by `GBRAIN_NO_GITIGNORE=1`; dormant — no scheduled shell `gbrain sync` exists) |
| Resurrection sub-test | **Directionally validated by the live restore code** (`gbrain_supabase_restore.py`: `slug_for_path` strips `.md`, `if slug_for_path(rel) in tombstones` re-deletes) + U13 unit tests. PGLite restore-only run skipped — the gbrain CLI is unreliable on the throwaway PGLite cold-start, and per the plan PGLite ≠ the live-Supabase restore path (directional only) |

Throwaway isolated brain (438 MB) + clone removed after the run.

---

## HALT conditions (plan Gate 2) — none tripped
- `safe_to_cut_over:false` on the **cutover set**? No — it's `true`.
- Clone canary ingest failure? No — foreign commit ingested + recall-able.
- Isolation leak (`~/.gbrain/config.json` engine changed)? No — `postgres` throughout; global state untouched.

## What Gate 2 approval releases
Phase D (Gate 3): **U7** coordinated pre-live snapshot (writers quiesced; tag + origin SHA +
restic + DB dump + tombstone set; restore cron NOT altered) → **U9** the single gated,
coordinated `commit_note` canary to `sources/`, validated end-to-end
(committed → `origin/main` → ingested → recall-able), reversible via `git revert` (pushed) +
a tombstone of the canary slug.

**Phase-D ingest note (from U6/recon):** there is **no scheduled disk→DB `gbrain sync`** on
the homelab, so the canary will not be recall-able until an explicit sync. U9 will trigger
`GBRAIN_NO_GITIGNORE=1 gbrain sync` for the vault as part of validation (the flag is
load-bearing — `manageGitignore` would otherwise rewrite the live `.gitignore`).
