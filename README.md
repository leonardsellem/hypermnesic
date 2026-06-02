# hypermnesic

A markdown-native memory layer that turns a git repository into a searchable
second brain. The repository's files are the **single source of truth**; the
search/graph index is a disposable, rebuildable projection of the git tree.

This repo is **private** and under active pre-release development. The product's
public license is an explicit pre-release decision — see the plans under
`docs/plans/`.

## What it does

A hybrid retrieval engine over a git-tracked markdown corpus, a git-first write
path, and the human-facing surfaces built on top:

- **Hybrid retrieval** — SQLite **FTS5** (lexical) fused with **sqlite-vec** KNN
  (dense; OpenAI `text-embedding-3-large` pinned to **1536 dims**, held equal to
  gbrain) via RRF, degrading gracefully to lexical-only when embeddings are down.
- **Read-time convergence** — every read first catches the index up to `HEAD` and
  closes a bounded slice of the dense lag, so recall stays fresh without a manual
  reindex. Reads never block on a writer; an oversized delta signals a manual
  reindex instead of auto-rebuilding.
- **Tailnet MCP server** — read tools `search` / `build_context` / `think`. A
  git-first, gated `commit_note` **write** tool is registered only on a
  write-enabled master, never reachable by read-only clients.
- **Write path** — `commit_note` commits to git through a diff-or-die frontmatter
  gate, a protected-path write guard, single-writer locks, and an append-only
  audit log. Maintenance edits land as **review-gated proposals** (PR branches the
  owner approves), never silent rewrites.
- **Per-result recency** — each hit carries the git committer-time of the most
  recent commit touching its path, so a consumer can rank by freshness.
- **Human surfaces** — thinking-mode, salience + spaced-review digest, serendipity
  connections, an always-organized navigation surface (MOCs/dashboards + Obsidian
  **Bases**), frictionless capture→triage, multi-format sidecar extraction
  (PDF/DOCX/XLSX/PPTX/PNG via Docling/MarkItDown), and a thin **read-only**
  Obsidian companion for retrieval-while-writing.
- **Role-aware install** — `hypermnesic install --role={single|master|client}`
  provisions each role end-to-end: an always-on master (systemd or Docker) with
  the convergence hook, a config-only client pointed at the master, or localhost
  for single.

## Phase status

- **Phase 0** — read-only hybrid retrieval, the French/English parity harness
  (recall@10 / MRR vs a frozen gbrain baseline), and the zero-infra portability
  probe (`clone && init`). **Done.**
- **Phase 1** — git-first write kernel: `commit_note`, the diff-or-die frontmatter
  gate (incl. U17 surgical scalar-set), the append-only audit log,
  index-as-projection, locks, and worktree-isolated reindex. **Done.**
- **Phase 2** — the human/product surface: review-gated proposals, thinking-mode,
  salience, connections, navigation, capture, sidecars, and the Obsidian
  companion. **Merged** (PR #1).
- **Phase 2.5 (Plan 1)** — engine convergence, the `commit_note` MCP write tool,
  single-JSON serve, and the role-aware installer. **Completed** (PRs #2/#3).
- **Phase 2.5 (Plan 2)** — the Obsidian companion redesign: a calm, read-only
  recall surface (status-bar / opt-in sidebar / optional inline marker),
  thinking-mode, forgetting-curve ranking off the engine recency signal, and an
  interrogable reinvention nudge. **Merged** (PR #5).

## Docs

- `implementation-notes.md` — running log of decisions and deviations, Phase 0 → 2.5.
- `docs/plans/` — the per-phase execution plans (the authoritative scope of record).
- `docs/threat-model-commit-note.md` — the write-path threat model (Phase-1 gate artifact).
- `harness/PARITY_VERDICT.md` — the French/English retrieval-parity verdict.
- `obsidian-plugin/README.md` — the read-only Obsidian companion.

## Develop

```sh
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run python scripts/license_scan.py   # zero AGPL/GPL/SSPL gate
```

## Credentials

The OpenAI key is read from `OPENAI_API_KEY` (env var or a gitignored repo-root
`.env`). It is never written to the index, the audit log, or any output.

## License

Proprietary / private. See [LICENSE](LICENSE). Third-party dependencies are
permissive and verified copyleft-free by `scripts/license_scan.py`.
