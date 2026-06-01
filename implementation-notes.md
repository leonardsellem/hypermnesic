# hypermnesic — implementation notes (Phase 0)

Running log of decisions, deviations from the plan, and open questions. The
authoritative plan lives in the gbrain-brain vault at
`projects/hypermnesic/docs/plans/2026-06-01-001-feat-hypermnesic-phase0-kernel-plan.md`.

## Conventions

- Python ≥3.11, `uv` for deps, `ruff` (line-length 100), `pytest`
  (`--import-mode=importlib`). CLI tooling mirrors the vault convention:
  standalone `main()` + `argparse` + `--json` (`ensure_ascii=False`).
- Permissive primitives only. The U1 license gate
  (`scripts/license_scan.py`) fails on any AGPL/GPL/SSPL transitive dep.
- gbrain-brain is read **only** — corpus + parity baseline. Never written; its
  `.gitignore` / tracked files are never mutated (KTD8).

## U1 — scaffold (in progress)

- Repo created at `<home>/dev/hypermnesic`, `git init -b main`.
- Deps declared: `sqlite-vec`, `openai`, `mcp`, `ruamel.yaml`; dev:
  `pytest`, `ruff`, `pip-licenses`.
- `LICENSE`: proprietary/private placeholder. Plan allows no public LICENSE
  while private; an internal notice is added for clarity. Public terms TBD
  pre-release (Open Questions).
- License gate: `scripts/license_scan.py` denies AGPL/GPL/SSPL; LGPL reported
  informationally (not in the deny set per the plan). Prefers `pip-licenses`,
  falls back to `importlib.metadata`.

### Direct dependency licenses (recorded per U1 acceptance criterion)

| Package | Version | License |
|---|---|---|
| sqlite-vec | 0.1.9 | MIT + Apache-2.0 |
| openai | 2.38.0 | Apache-2.0 |
| mcp | 1.27.2 | MIT |
| ruamel.yaml | 0.19.1 | MIT |
| pytest | 9.0.3 | MIT |
| ruff | 0.15.15 | MIT |
| pip-licenses | 5.5.5 | MIT |

Full resolved tree: 46 packages, **0 AGPL/GPL/SSPL**, 0 LGPL (G2 PASS).

### Resolved blockers (U1)

- **OPENAI_API_KEY**: operator populated `<home>/dev/hypermnesic/.env`
  (verified non-empty, `sk-` prefix, 164 chars; value never echoed). `.env` is
  gitignored. Key blocker cleared for U2/U5/U6 live gates.

## U2 — read-only index core (done, live-verified)

- `config.py` pins `text-embedding-3-large` @ 1536 in one place;
  `assert_embedder_agrees` fails fast on a dim mismatch. Key read from env/.env
  only, never echoed/persisted.
- `embed.py`: `dimensions=1536` sent explicitly; `smoke_embed_or_die` fails loud
  on missing/invalid key (never zero-vectors). Live smoke embed confirmed the
  key is actually *read* by the SDK.
- `ingest.py`: walks `*.md`, strips frontmatter, chunks to ≤4000 chars.
  **Bug found + fixed on first full index:** a single >8192-token block
  overflowed the embedding API (`input[118]`); `_split_oversized` now hard-splits
  oversized blocks (regression test added).
- `index.py`: sqlite-vec `vec0(... float[1536])` + FTS5 (`unicode61
  remove_diacritics 2`) + `meta` checkpoint slot. KNN uses `MATCH ... k = ?`
  (tested invariant, KTD3). State dir 0700, db 0600.
- **Corpus written read-only via an EXTERNAL state dir** (`build_index(...,
  state_dir=...)`): gbrain-brain itself is never written — not even a gitignored
  dir or a `.git/info/exclude` entry. The in-repo `.hypermnesic/` default (with
  `ensure_ignored` via `.git/info/exclude`, never `.gitignore`) is reserved for
  U6 portability targets.
- **Live full index:** 27,451 chunks / 3,518 docs, checkpoint = HEAD
  `42f6ac5`. Corpus verified untouched (clean tree, no `.hypermnesic/`, no
  exclude edit). Known queries return sensible pages; rebuild is deterministic.

## U3 — hybrid retrieval + build_context (done, live-verified)

- `retrieve.py`: RRF fusion of FTS5 + sqlite-vec; **optional** rerank stage
  (KTD5, default off); graceful lexical-only degradation flagged
  `dense_used=False` so U5 can VOID (not FAIL) a degraded run.
- `graph.py`: body-`[[wikilink]]` edges only (frontmatter relations excluded for
  free — ingest already stripped frontmatter). `build_context` BFS over in+out
  edges, cycle-safe, depth-bounded. Live: 3,518 nodes; `build_context` from
  `gbrain.md` returns 53 linked pages.

## U4 — read-only MCP server (code done; G5 live check pending)

- `mcp_server.py`: FastMCP, streamable-http, binds a specific Tailscale IP
  (refuses `0.0.0.0`/`::` at construction — KTD10). Exactly two tools (`search`,
  `build_context`), both `readOnlyHint=True`; **no write tool exists** (structural
  read-only). Dense degrades gracefully; lexical+graph always answer.

## U5 — parity harness prerequisites (operator-owned, not yet present)

The plan marks these "owner: operator — must exist before U5 runs":

1. **Frozen query set** `harness/queries.frozen.jsonl` — ~25–40 real queries
   (≥15 French) with **human-judged** known-relevant docs (gbrain-independent
   labels, KTD6). Label production over a 3,100-page corpus is real operator
   work, not a harness side effect.
2. **Frozen gbrain baseline** — gbrain's ranked results per query captured once
   at the **un-reranked** level (KTD5), versioned beside the query set.
   Capturing it requires bracketing the shared homelab service's *global*
   `search.reranker.enabled` setting (set → capture → restore).

**Awaiting operator decision** on how to source both (provide vs authorize
agent best-effort vs authorize the bracketed reranker toggle on the shared
service).
