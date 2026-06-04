# hypermnesic

<!-- Badges are STAGED — they 404 on a private repo (shields.io needs a public repo), and the
     license badge presumes the AGPL flip. The public-flip PR activates them (docs/launch/).
[![CI](https://github.com/leonardsellem/hypermnesic/actions/workflows/ci.yml/badge.svg)](https://github.com/leonardsellem/hypermnesic/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/tag/leonardsellem/hypermnesic?label=version)](CHANGELOG.md)
-->

**The git-native memory layer for AI agents.** A self-hosted second brain where your
markdown files are the **single source of truth** and the search index is a disposable,
rebuildable projection of the git tree. Every agent you use — ChatGPT, Claude, the Claude
Code / Codex plugin, an Obsidian companion — shares **one OAuth-secured MCP endpoint**
(browser-login once, then silent refresh). On the machine that holds the vault you use the
`hypermnesic` **CLI** directly.

**Who it's for:** developers and power note-takers who want durable, portable agent memory
they *own* — plain markdown in their own git repo, no vendor memory database, no lock-in.

**Why it's different:** files-are-truth with a throwaway index (not a proprietary memory DB),
git-first writes (every memory is a reviewable commit), and one endpoint every client shares.
See [why hypermnesic](docs/why-hypermnesic.md) and the [benchmarks](#benchmarks) below.

> **Status:** private, pre-release. The public open-source license (AGPL-3.0) is **staged,
> not yet live** — see [`docs/launch/`](docs/launch/).

---

## Quick start

### A. Prove local memory works

Start on the machine that holds the vault. You need only a **git repo** of markdown
notes. Dense embeddings improve ranking when `OPENAI_API_KEY` is configured, but the
proof also works offline in lexical mode.

```sh
# 1. install the engine (from a clone of this repo)
uv tool install .

# 2. prove recall from your own markdown files, with a dry-run write preview
hypermnesic local-proof /path/to/your/vault

# or try a tiny generated demo vault first
hypermnesic local-proof --demo-dir /tmp/hypermnesic-demo
```

The proof path validates a git-backed vault, projects committed markdown files into the
disposable `.hypermnesic/` index, asks a natural-language question, returns the
repo-relative source markdown path, and shows a `commit_note` dry-run diff without
creating a write commit. The success milestone is **Local memory works**.

### B. Self-host the endpoint

After the local proof succeeds, bring the shared endpoint online for remote apps. You need
[Tailscale](https://tailscale.com) installed and logged in (`tailscale up`); hypermnesic
uses Tailscale Funnel for public HTTPS + automatic TLS, so there is no reverse proxy or
cert to manage.

```sh
hypermnesic setup /path/to/your/vault \
  --public-url https://<your-host>.ts.net/mcp \
  --resource   https://<your-host>.ts.net/mcp
```

`setup` renders + starts a user service, generates an owner-only **consent secret**
(`~/.config/hypermnesic-cloud/cloud.env`, chmod 600), configures the Tailscale funnel
(the `/mcp` mount + the OAuth discovery well-knowns), then **verifies the live HTTPS
discovery chain** before reporting success. Re-running it converges to the same state.
It prints your endpoint URL and login instructions.

### C. Connect a client (any remote app)

Point the app's MCP server at your endpoint URL — that's it. OAuth is automatic:

- **Claude / ChatGPT (cloud connectors), Claude Code plugin, Codex:** add the MCP
  server URL `https://<your-host>.ts.net/mcp`. On first connect the app discovers the
  OAuth server, opens a browser once for you to authorize, then silently refreshes.
- **Read vs. write:** read access is the default. To grant the `commit_note` **write**
  tool, approve **write** on the consent page (type your approval token from
  `~/.config/hypermnesic-cloud/cloud.env`). The consent page shows exactly which scopes
  you're granting.
- **Claude Code / Codex plugin:** install the plugin in `plugin/` and set
  `HYPERMNESIC_MCP_URL` to your endpoint — the bundled `.mcp.json` is discovery-only and
  carries no host or token. See `plugin/README.md`.
- **Obsidian companion:** read-only over your tailnet — point it at the tailnet read
  route `http://<tailnet-ip>:8848/mcp` (no OAuth; tailnet membership is the boundary). It
  ships from a **separate repository under GPL-3.0** (private until its first release) —
  see [`obsidian-plugin/README.md`](obsidian-plugin/README.md) and the license boundary below.

### D. Use it locally (on the engine host)

The host that runs the engine skips the network entirely and uses the CLI:

```sh
hypermnesic local-proof /path/to/vault                           # first local value proof
hypermnesic retrieve /path/to/vault "what do we know about X"   # hybrid search
hypermnesic think    /path/to/vault "topic"                     # thinking-mode
hypermnesic resolve  /path/to/vault "Some Entity"               # name → page path
hypermnesic commit-note /path/to/vault notes/x.md --body "…"    # git-first write (dry-run preview)
```

---

## How it works

A hybrid retrieval engine over a git-tracked markdown corpus, a git-first write path,
and the surfaces built on top:

- **Hybrid retrieval** — SQLite **FTS5** (lexical) fused with **sqlite-vec** KNN (dense;
  OpenAI `text-embedding-3-large` at **1536 dims**) via RRF, degrading gracefully to
  lexical-only when embeddings are down.
- **Read-time convergence** — every read first catches the index up to `HEAD` and closes a
  bounded slice of the dense lag, so recall stays fresh without a manual reindex.
- **Two serving lanes** —
  1. a single **public OAuth MCP endpoint** at `/mcp` (Tailscale-funnel'd HTTPS; OAuth 2.1
     with DCR + PKCE; **read tools always, the gated `commit_note` write tool by scope**),
     used by every remote client the same way;
  2. a **tailnet read companion** (`:8848`, auth-off) for the Obsidian companion and the
     proactive per-prompt hook on tailnet devices.

  By default a **write-enabled** serve requires OAuth (`write_enabled ⇒ auth-required`). The
  advanced `--allow-tailnet-write` opt-in accepts **tailnet membership itself as the write
  boundary** — permitting an auth-off, write-enabled serve, but **only** on a Tailscale CGNAT
  address (`100.64.0.0/10`). A non-tailnet bind is still refused (it would be a public write hole),
  and every `commit_note` guard (the blocklist write surface, protected-path refusal, diff-or-die
  gate, audit log) still applies. Use it only when the tailnet is your trust boundary and the
  public OAuth lane carries all untrusted traffic.
- **Write path** — `commit_note` takes a caller-supplied repo-relative path and commits it
  to git through a diff-or-die frontmatter gate and a **blocklist write guard**
  (write-anywhere-under-guards: a note may land anywhere in the vault *except* the protected
  classes — `.git/`, `.github/`, agent-instruction files like `CLAUDE.md`/`AGENTS.md`,
  `scripts/`/`hooks/`/`skills/`, and build/CI/credential files — which are refused regardless of
  any allowlist), single-writer locks, and an append-only audit log. An explicit allowlist is an
  opt-in way to *narrow* the surface, not the default guard. The index follows as a projection — a
  reindex never loses a write. Write requires auth (`write_enabled ⇒ auth-required`).
- **Security** — operator-consent gates the `write` scope at login; audience-bound tokens
  (RFC 8707); refresh rotation + whole-grant revoke; a per-request consent CSP. See
  `docs/2026-06-03-unified-write-anywhere-security-review.md`.
- **Human surfaces** — thinking-mode, salience + spaced-review digest, serendipity
  connections, an always-organized navigation surface, frictionless capture→triage,
  multi-format sidecar extraction (PDF/DOCX/XLSX/PPTX/PNG), and a read-only Obsidian companion.

## Benchmarks

On **LongMemEval V1** (the `_s` 500-question set), hypermnesic's end-to-end QA accuracy is
**88.6% overall / 89.7% task-averaged** with a GPT-4.1 reader, and **83.2 / 86.6** with a
GPT-4o reader — both graded by the canonical `gpt-4o-2024-08-06` judge. Session-level retrieval
`recall@10` is **0.949** (every gold session in the top-10 for 94.9% of questions).

**Read these honestly.** They are on the matched **GPT-4o-judge** axis — the only
apples-to-apples memory-system comparison — where hypermnesic sits **on par with Mastra
Observational Memory (84.2)**, **+12 over Zep (71.2)**, and **+23 over the no-memory
full-context floor (60.2)**. They are **not** comparable to the GPT-4.1-*judged* ~95%
leaderboard rows — that gap is judge leniency, not memory quality. The full methodology,
comparability envelope, per-ability tables, corrections log, and a re-runnable harness
(pinned dataset hash; ~$31 to reproduce) are in
[`harness/BENCHMARKS.md`](harness/BENCHMARKS.md).

## Docs

Start with the [documentation index](docs/README.md). Highlights:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — how it works (the disposable-index invariant, retrieval, write path, serving lanes).
- [`docs/guides/getting-started.md`](docs/guides/getting-started.md) — the three setup paths + failure modes.
- [`docs/reference/`](docs/reference/) — the MCP tool, CLI, and configuration references.
- `docs/unified-oauth-mcp-deploy-runbook.md` — the unified endpoint: topology, cutover, reverse.
- `plugin/README.md` — the Claude Code / Codex plugin (OAuth-discovery, distribution-generic).
- `docs/plans/` — the per-phase execution plans (the authoritative scope of record).
- `docs/threat-model-commit-note.md` + `docs/2026-06-03-unified-write-anywhere-security-review.md`
  — the write-path threat model and the public write-surface review.
- `implementation-notes.md` — running log of decisions and deviations.

## Develop

```sh
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run python scripts/license_scan.py   # zero AGPL/GPL/SSPL *dependency* gate
```

## Credentials

The OpenAI key is read from `OPENAI_API_KEY` (env var or a gitignored repo-root `.env`). It is
never written to the index, the audit log, or any output. The OAuth consent secret lives only in
an owner-only env file; tokens are never logged or committed.

## License

Proprietary / private (pre-release). See [LICENSE](LICENSE). The public open-source license is a
staged, pre-public decision — the planned engine license is **AGPL-3.0** (the staged text + a
one-PR flip runbook live in `docs/launch/`).

The `scripts/license_scan.py` "zero AGPL/GPL/SSPL" gate is **dependency-scoped**: it governs
hypermnesic's *third-party dependencies*, keeping the dependency tree copyleft-free. It does **not**
govern — and is not contradicted by — the engine's own (planned-AGPL) license: the gate excludes the
project's own distribution before classifying, so it stays green when the engine itself is licensed
AGPL-3.0. Third-party dependencies are permissive and verified copyleft-free on every CI run.

**Engine ↔ companion license boundary.** The Obsidian companion ships from a separate repository
under **GPL-3.0**; the engine's planned license is **AGPL-3.0**. Neither is a derivative of the
other — and that holds **because** they are separate processes that communicate only at arm's
length over the MCP network protocol (`search` / `build_context` / `think`), with no shared or
statically-linked code. The boundary stays true only while the **companion does not vendor,
import, or statically link engine source** (the read-only-over-the-wire invariant). Keep that
condition and the two licenses remain independent.
