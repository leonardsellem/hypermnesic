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
