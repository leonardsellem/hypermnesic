# GATE 3 — Release the canary write? (snapshot record + plan)

**Plan:** `docs/plans/2026-06-02-008-feat-homelab-dogfood-cutover-plan.md`
**Phase D units:** U7 (pre-live snapshot — DONE), U9 (the single canary write — AWAITING RELEASE)
**Captured:** 2026-06-02 ~14:12 UTC, on `homelab-hetzner-staging`
**Status:** snapshot complete; **paused at Gate 3‑release** for the per-action write go-ahead.

---

## U7 — pre-live snapshot (captured, right-sized for ONE `sources/` note)

| Item | Value / decision |
|---|---|
| **Rollback anchor** | git tag `pre-hypermnesic-cutover` @ **`b5eeb8c2…`** (= recorded `origin/main` SHA) |
| **Tombstone set** | 249 entries backed up → `~/.cache/hypermnesic-gate3-snapshot/tombstones.pre-cutover.json` |
| **DB baseline** | `pages=3036`; canary slug **absent** (count=0) → rollback is a *targeted delete*, never a full restore |
| restic snapshot | **Not run** — restic isn't configured in this environment. Authoritative backup = git history + `origin/main` on GitHub (the canary is `git revert`-able to the tag). |
| Full `pg_dump` | **Deferred** — 782 MB; disproportionate for one note, and a full restore would clobber concurrent `put_page`/ingest. The safe DB rollback is a *targeted* `gbrain delete <canary-slug>`. Available on request. |
| Full orphan-audit baseline | **Deferred** — the tool does a full `gbrain export` (>120 s). Divergence signal = page-count delta (3036 → expect 3037) + canary-present-on-both-disk-and-DB. |
| Fleet quiesce | **None needed** — clean window (next scheduled push 15:05 restore / 15:22 remote-sync; `gbrain-pull` is a no-op pull). Nothing paused → nothing left paused. |

The restore cron is **NOT** altered (it keeps running).

## U9 — the single canary write (planned; runs only after release)

- **What:** exactly one coordinated `commit_note` through the **live deployed service**
  (so it exercises U11 coordination + writes `audit.jsonl`):
  - path: `sources/hypermnesic-canary-2026-06-02.md` (free-append zone; dogfood previewed `ok`)
  - a small note recording the first gated disk-first hypermnesic write.
- **Pre-write:** record `gbrain-pull.timer` state, **pause it** for the write (avoids `.git/index.lock`
  contention with a concurrent pull), backed by a **TTL watchdog** (`systemd-run --on-active`) that
  re-enables it regardless of agent liveness.
- **Validate (within budget):**
  1. commit reached `origin/main` (the deployed service pushed it — U11);
  2. trigger ingest explicitly: `GBRAIN_NO_GITIGNORE=1 gbrain sync --repo … --no-pull`
     (no scheduled sync exists; the flag is load-bearing — `manageGitignore` would otherwise
     rewrite the live `.gitignore`);
  3. recall-able via gbrain FTS **and** the hypermnesic MCP `search`;
  4. the (untouched) restore did not alter it; page-count delta = **+1** (only the canary);
  5. `audit.jsonl` has exactly one entry for the canary.
- **Resume `gbrain-pull.timer`** (guaranteed / watchdog).

## Rollback runbook (if any validation step HALTs)
1. `systemctl --user stop hypermnesic` (stand down the writer); verify inactive.
2. Pause `gbrain-pull.timer`.
3. **Tombstone first**, then revert: append the canary's `.md`-stripped slug
   (`sources/hypermnesic-canary-2026-06-02`) to `~/.skillops/state/gbrain-supabase-restore/tombstones.json`
   with `{deleted_at, reason}`, **then** `git revert` the canary and **push** the revert to `origin/main`.
4. If gbrain already ingested it: `gbrain delete sources/hypermnesic-canary-2026-06-02` (targeted; not a full restore).
5. Let `.hypermnesic/` re-converge against the reverted HEAD (recovery, not data loss).
6. Resume `gbrain-pull.timer`; restart hypermnesic if desired.
7. Verify: `git status` clean at/after the tag, `origin/main` no longer carries the canary,
   canary absent from disk + gbrain recall, page count back to 3036.

## Gate-3 decisions for the operator
- **Release** = authorize the one canary write above (the per-action go-ahead the threat-model proviso requires).
- **HALT before release IF** the snapshot is judged insufficient (e.g. you want the full `pg_dump`/restic belt first).
- **HALT at validation IF** the canary doesn't reach `origin/main`, sync doesn't ingest it, it's altered,
  or an unexpected orphan/divergence appears → run the rollback runbook; Phase 1 does not complete.
