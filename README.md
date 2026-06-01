# hypermnesic

A markdown-native memory layer that turns a git repository into a searchable
second brain. The repository's files are the **single source of truth**; the
search/graph index is a disposable, rebuildable projection of the git tree.

This repo is **private** and under active Phase-0 development. The product's
public license is an explicit pre-release decision — see the plan.

## Phase 0 (current slice)

A thin, **read-only** retrieval index built on permissively-licensed primitives:

- **sqlite-vec** (KNN `MATCH ... k=N`) for dense vectors
- **SQLite FTS5** for lexical search
- **OpenAI `text-embedding-3-large`** pinned to **1536 dims** (held equal to gbrain)
- the **MIT MCP SDK** for a tailnet-only, read-only `search` + `build_context` server

Plus two validation probes:

- a **French/English retrieval-parity harness** (recall@10 / MRR vs a frozen gbrain baseline)
- a **zero-infra portability probe** (`clone && init`) over a second repo

No write path ships in Phase 0 — the `commit_note` write kernel is Phase 1 and
is gated on the parity verdict.

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
