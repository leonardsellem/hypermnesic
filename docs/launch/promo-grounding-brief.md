---
title: "Promotion grounding brief"
status: grounding
audience: operator
last_checked: 2026-06-25
source_of_record: docs/launch/* + README.md + docs/why-hypermnesic.md + ARCHITECTURE.md
linear_project: hypermnesic
linear_team: LS Ventures (LS)
linear_milestone: Public release
---

# Promotion grounding brief — hypermnesic

Grounding pass for the promotion-planning workflow. Everything below was verified against
the repo (README, `docs/why-hypermnesic.md`, the launch docs, the deploy runbook, and the
`install.py` source) on 2026-06-25. Do **not** invent features beyond what is recorded here.
Channel drafts and the claims-allowed / claims-avoid lists already live in
[`launch-narrative-drafts.md`](launch-narrative-drafts.md) — this brief grounds and
cross-checks them; it does not replace them.

## 1. Positioning confirmations

The promotion SEED is confirmed accurate against the repo. Confirmed claims:

- **"Files are truth; the index is disposable."** Confirmed — README "How it works",
  `docs/why-hypermnesic.md` claim #1, and `ARCHITECTURE.md`'s prime invariant. A reindex can
  never lose a committed write; the index is a rebuildable projection of the git tree.
- **Git-first guarded write (`commit_note`).** Confirmed — diff-or-die frontmatter gate +
  **blocklist** write guard (write-anywhere-under-guards; protected classes `.git/`,
  `.github/`, `CLAUDE.md`/`AGENTS.md`, `scripts/`/`hooks/`/`skills/`, build/CI/credential
  files are refused) + single-writer locks + append-only audit log. README "How it works"
  and `docs/why-hypermnesic.md` claim #2.
- **Hybrid retrieval (FTS5 + sqlite-vec via RRF), graceful lexical-only degrade.** Confirmed
  — README states OpenAI `text-embedding-3-large` at **1536 dims**. Note the dims: the SEED
  did not specify them; the README says 1536. Degraded lexical-only mode is explicit
  (`degraded_reason`, embedding-429 cooldown).
- **Read-time convergence.** Confirmed — every read catches the index up to `HEAD` and
  closes a bounded slice of dense lag, so a just-written note is recall-able without a manual
  reindex.
- **One public OAuth 2.1 MCP endpoint over Tailscale Funnel + a tailnet read companion on
  `:8848`.** Confirmed — README "How it works" + the unified-OAuth runbook. Two serving
  lanes: public `/mcp` (OAuth 2.1, DCR + PKCE, read tools always, gated `commit_note` write
  by scope) and the auth-off tailnet read companion on `:8848`. HTTPS + automatic TLS via
  Tailscale Funnel, **no reverse proxy**.
- **LongMemEval V1, honest comparability envelope.** Confirmed and slightly RICHER than the
  SEED. README benchmark section: **88.6% overall / 90.2% task-averaged with a GPT-4.1
  reader**, and **83.6 / 87.1 with a GPT-4o reader**, both graded by the canonical
  `gpt-4o-2024-08-06` judge. On the matched GPT-4o-judge axis: **on par with Mastra (84.2)**,
  **+12 over Zep (71.2)**, **+23 over the no-memory floor (60.2)**. Session-level
  `recall@10 = 0.949`. The ~95% GPT-4.1-*judged* leaderboard rows (OMEGA 95.4, Mastra 94.9)
  are explicitly NOT comparable (judge leniency). Full methodology in `harness/BENCHMARKS.md`.
- **Read-only Obsidian companion from a SEPARATE GPL-3.0 repo.** Confirmed —
  `hypermnesic-companion`, GPL-3.0-or-later, first release `0.3.0`. Engine is **AGPL-3.0-only**.
  The arm's-length MCP-protocol boundary (no shared/static-linked code) is what keeps the two
  licenses independent.

### Corrections / enrichments to the SEED

- **PyPI install is now LIVE and is shipped truth, not a pending decision.** The SEED treats
  `uv tool install hypermnesic` as citable-live, which is correct: LS-1684 (the PyPI go/no-go)
  is **Done**, the CHANGELOG records "now that `0.1.0` is published to PyPI", and the README
  quick start installs from PyPI with a PyPI version badge. NOTE the staleness trap: the
  `launch-narrative-drafts.md` "Claims to avoid" still says *"Do not claim PyPI install until
  LS-1684 is decided"* — that guard is now **obsolete** because LS-1684 shipped. Promotion copy
  MAY claim PyPI install; the drafts doc's avoid-line should be updated when next touched.
- **Embedding dimensions = 1536** (README), in case promo copy wants the spec.
- **Status is "public v0.1.0 release"** — the repo is already public and released, not
  pre-flip. The proprietary→AGPL flip and the v0.1.0 release have landed.
- **Glama listing claim — VERIFY before asserting "A grade".** The repo ships `glama.json`
  and the CHANGELOG documents a deliberate Tool-Definition-Quality-Score push (full
  self-describing tool descriptions, 100% parameter-description coverage). The SEED's "Glama
  listing with a passing build + Tool Definition Quality A grade" is plausible but the **A
  grade is an external Glama-side result not provable from the repo alone** — confirm on the
  live Glama listing (id `ak6x81u3rr`) before putting the letter grade in public copy.
- **awesome-mcp-servers — SEED says MERGED; repo evidence says OPEN.**
  `directory-submission-prep.md` records PR `punkpeye/awesome-mcp-servers/pull/8056` as
  **open** (Glama listing flagged as a likely precondition the maintainer asks for). The SEED
  asserts it is MERGED. **Treat as needs-verification**: confirm the PR's current merge state
  before claiming "merged into awesome-mcp-servers" in any post. If still open, downgrade the
  claim to "submitted / PR open".
- **Official MCP Registry — NOT yet published.** `directory-submission-prep.md`: registry
  search for `hypermnesic` returns no entries; publication is blocked pending an operator
  `mcp-publisher login github`. The SEED's voice-rules already forbid claiming registry
  listing until published — keep that guard.

## 2. Native-primitives-first deploy findings (grounds the deploy initiative)

This is the load-bearing section for the deploy plan. Exact state of the deploy/container
surface:

| Artifact | Present? | Detail |
|---|---|---|
| **Committed `Dockerfile`** | **No** | No `Dockerfile` anywhere in the repo (root or `src/`). |
| **Committed `compose.yaml` / `docker-compose.yml`** | **No** | None committed anywhere. |
| **`src/hypermnesic/templates/` dir** | **No** | The phase-2.5 plan *names* such a dir, but it does **not exist on disk**. |
| **`glama.json`** | **Yes** | `/Volumes/Dev/hypermnesic/glama.json` — but it contains ONLY `$schema` + `maintainers: ["leonardsellem"]`. It does **NOT** reference a Docker build, build args, an entrypoint, or any startCommand. |
| **Runtime-generated Docker** | **Yes (generated, not shipped)** | `src/hypermnesic/install.py` `render_docker()` (lines 199–222) emits a `Dockerfile` + `compose.yaml` INTO the state dir at runtime when `hypermnesic install --service=docker` runs. These are generated artifacts, never committed or inspectable in the repo tree. |
| **Deploy runbooks/docs** | **Yes** | `docs/unified-oauth-mcp-deploy-runbook.md` (current two-lane topology), `docs/launch/public-flip-runbook.md`, `docs/plans/2026-06-02-006-feat-phase-2-5-engine-deployment-plan.md`, plus archived runbooks under `docs/archive/`. |
| **CI workflows** | `.github/workflows/ci.yml`, `release.yml` | No container-build job. |

### The key deploy insight

The deploy story is deliberately **native-primitive-first and container-light**:

- Production serving is **systemd + Tailscale Funnel** (HTTPS + automatic TLS, **no reverse
  proxy, no container required**). The runbook drives everything through
  `tailscale funnel` and `systemctl --user`. This is the chosen, opinionated path.
- Docker exists only as a **secondary, generated install target** (`install --service=docker`
  renders a minimal `FROM python:3.11-slim` Dockerfile + a compose file that runs
  `hypermnesic serve … --enable-write`, with `OPENAI_API_KEY` supplied at runtime via
  `env_file: .env`, never baked into the image). It is rendered on demand, not committed.

### Consequence for Glama (the actual gap the deploy initiative likely targets)

Glama's static inspector builds an MCP server from a **committed** Docker build. Because
hypermnesic ships **no committed Dockerfile** and `glama.json` references **no Docker build**,
Glama cannot stand up the HTTP server itself — the listing rests on metadata + the TDQS push,
not a Glama-built running server. If the deploy initiative's goal is "make the HTTP server
inspectable / buildable on Glama" (consistent with the operator's standing Glama note), the
native-primitives-first move is to **commit a Dockerfile (and optionally reference it from
`glama.json`)** rather than rely on the runtime-generated one. Before building anything new:
the engine already has `render_docker()` — a committed Dockerfile should be reconciled with /
derived from that existing template, not hand-rolled separately, to avoid drift.

## 3. Related Linear issues

- **Launch project / initiative:** **hypermnesic** (project id `d5f202a5-10f8-4142-9443-44ac605b7450`)
- **Milestone:** **Public release** (id `a86d9eca-f14e-4d0a-b707-d3b7b1f1e237`)
- **Team:** **LS Ventures** (key `LS`, id `f83d29ef-5a04-4f97-929a-c66f68ddc298`)
- All launch work is labeled `release` plus a `phase:*` label (`phase:4-launch-surface`,
  `phase:5-contribution-funnel`, `phase:6-announcement`). Source plan for every issue:
  `docs/plans/2026-06-12-002-feat-public-release-milestone-plan.md`.

| ID | Title | State | Phase | URL |
|---|---|---|---|---|
| LS-1683 | Submit to MCP and Obsidian directories | In Review | 4-launch-surface | https://linear.app/ls-ventures/issue/LS-1683/submit-to-mcp-and-obsidian-directories |
| LS-1684 | (Decide) PyPI publication for one-command install | Done | 4-launch-surface | https://linear.app/ls-ventures/issue/LS-1684/decide-pypi-publication-for-one-command-install |
| LS-1685 | Seed 10–15 `good first issue` / `help wanted` issues | Done | 5-contribution-funnel | https://linear.app/ls-ventures/issue/LS-1685/seed-10-15-good-first-issue-help-wanted-issues |
| LS-1686 | Public roadmap + Discussions | Done | 5-contribution-funnel | https://linear.app/ls-ventures/issue/LS-1686/public-roadmap-discussions |
| LS-1687 | Contributor on-ramp: 5-minute dev setup, verified cold | Done | 5-contribution-funnel | https://linear.app/ls-ventures/issue/LS-1687/contributor-on-ramp-5-minute-dev-setup-verified-cold |
| LS-1688 | Launch-week response SLO | In Review | 5-contribution-funnel | https://linear.app/ls-ventures/issue/LS-1688/launch-week-response-slo |
| LS-1689 | Write the launch narrative + per-channel posts | Done | 6-announcement | https://linear.app/ls-ventures/issue/LS-1689/write-the-launch-narrative-per-channel-posts |
| LS-1690 | Launch sequencing: stagger the channels | In Review | 6-announcement | https://linear.app/ls-ventures/issue/LS-1690/launch-sequencing-stagger-the-channels |

Open threads still live (not Done): **LS-1683** (directory submissions — MCP Registry +
Obsidian PRs not yet landed), **LS-1688** (launch-week response SLO), **LS-1690** (channel
sequencing / retro). These are the issues the promotion plan most directly extends.

> Tooling note: `mcp__linear__list_issues` failed repeatedly with a GraphQL "Argument
> Validation Error" (both with and without a `query`/`project`/`team` filter), so the set
> above was assembled via direct `get_issue` lookups across the contiguous LS-1683..LS-1690
> range. All eight resolve to the same project + milestone, which bounds the launch issue set
> with high confidence, but a fresh `list_issues` once the connector is healthy could surface
> any later marketing/distribution issues created outside this range.

## 4. Voice & claims summary

Authoritative source: [`launch-narrative-drafts.md`](launch-narrative-drafts.md) (approved
drafts + claims lists). Carry these into all promotion copy.

**Voice:** personal, opinionated, lightweight, portable, honest. "One brain. Every AI.
Yours." The hero is the compounding flywheel (Capture → Curate → Recall → Compound) and
ownership (your files, your git history, reviewable commits). Origin beat (founder essay
only, never a competitor row): the prior database-backed "gbrain" drifted from its files;
hypermnesic is the git-first rebuild. Honest limitations are a feature, not a hedge — they
win on HN; overclaim dies there.

**Claims allowed (citable):** git-first memory; files-are-truth / disposable rebuildable
index; writes are reviewable git commits; MCP + CLI + read-only Obsidian companion;
benchmarks exist with documented caveats; product readiness tracked separately from benchmark
quality; companion is public and read-only; **PyPI install is live** (`uv tool install
hypermnesic` — LS-1684 Done).

**Claims to avoid (hard):**
- No hosted SaaS / managed cloud / multi-tenant service.
- Do **not** claim official MCP Registry listing until publication actually lands (still
  blocked on operator `mcp-publisher login github`).
- Do **not** claim the awesome-mcp-servers entry is **merged** until verified — repo evidence
  shows PR #8056 **open**. (SEED said merged; reconcile before asserting.)
- Do **not** claim the Glama "A" Tool-Definition-Quality grade until confirmed on the live
  listing (`ak6x81u3rr`); the repo proves the *effort*, not the grade.
- Do **not** imply the Obsidian companion can write a vault (read-only by design).
- Do **not** imply dense retrieval is always on — lexical-only degraded mode is a supported,
  visible state.
- Do **not** present benchmark numbers as proof of the full product, and never quote outside
  the published comparability envelope (no GPT-4.1-judged ~95% comparisons).
- No private hostnames, tokens, vault contents, or local absolute paths in any post.
- **Stale-guard note:** `launch-narrative-drafts.md` still lists "do not claim PyPI until
  LS-1684 is decided" — that line is now obsolete (LS-1684 shipped) and should be corrected
  when the drafts doc is next edited.

**Differentiation (compete on ownership + compounding + reviewable writes, NOT benchmark
rank):** vs mem0/Zep = their managed DB vs your files; vs Letta = an agent framework vs just
the memory layer; vs basic-memory = adds hybrid retrieval + guarded git-first write + shared
OAuth endpoint; vs Hindsight = its own vector store + a higher LongMemEval number on a MORE
LENIENT judge axis (state plainly, do not hide); vs Honcho = COMPLEMENTARY (Honcho = who you
are / preferences; hypermnesic = what you know, in files — use both); vs plain Obsidian = adds
agent-facing hybrid retrieval + a write API on the same files.
