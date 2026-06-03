# AGENTS.md

Contract for AI coding agents (Claude Code, Codex, and similar) working in this
repository. Humans: see [`CONTRIBUTING.md`](CONTRIBUTING.md). The two are consistent;
this file states the parts an autonomous agent most needs up front.

## The prime invariant

**Files are the source of truth; the index is a disposable, rebuildable projection of
the git tree.** Never treat the index as a database of record. A reindex must never be
able to lose a committed write. See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Build, test, and gates

Python ≥ 3.11, [uv](https://docs.astral.sh/uv/) for dependencies. The full gate set —
identical to CI's single `lint-test-license` job — is:

```sh
uv sync --extra dev
uv run ruff check .
uv run python scripts/check_version_consistency.py
uv run pytest
uv run python scripts/license_scan.py
uv run python scripts/preflight_public_scan.py
```

All six must pass before a change is done. The suite runs offline and deterministic
(the OpenAI key is neutralized in tests; dense retrieval degrades to lexical).

## Working rules

- **Test-first.** No new production behavior without a failing test first. Tests live
  in `tests/`, run with `--import-mode=importlib`.
- **Branch off `main`; never commit to `main` directly.** Use a worktree per task when
  changes could conflict. Commit per logical unit with a conventional subject and a
  `Signed-off-by:` DCO line (`git commit -s`).
- **Permissive dependencies only.** Any new dependency must keep
  `scripts/license_scan.py` green (zero AGPL/GPL/SSPL). The gate is dependency-scoped;
  it does not constrain the engine's own (planned-AGPL) license.
- **Never echo secrets.** The OpenAI key, OAuth consent secret, and tokens are read
  from the environment / a gitignored `.env` only — never written to the index, the
  audit log, any output, or chat. `scripts/preflight_public_scan.py` enforces that no
  operator host/IP/token ships in the public surface.
- **Respect the write guard.** The write path (`commit_note`) is git-first and bounded
  by a blocklist (protected-path + governance-file fence). Do not weaken it; changes to
  `serialize.py` / `frontmatter_gate.py` / `auth*.py` / `mcp_server.py` are
  security-sensitive (CODEOWNERS-routed).

## How this repo plans and ships work

- **Plans** live under `docs/plans/` (`YYYY-MM-DD-NNN-<type>-<slug>-plan.md`). They are
  the authoritative scope of record; brainstorms (the "what") live under
  `docs/brainstorms/`.
- **Gate artifacts** (`docs/gate-artifacts/`) and dated **security reviews**
  (`docs/*-security-review.md`, with `amends:` / `signed_off:` frontmatter) record
  signed-off decisions. Do not rewrite a signed-off review — add a dated amendment.
- **Decisions** worth keeping live under `docs/solutions/`; release history is
  [`CHANGELOG.md`](CHANGELOG.md); the narrative build log is `implementation-notes.md`
  (historical, not a changelog).

## Reference

- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- MCP tools: [`docs/reference/mcp-tools.md`](docs/reference/mcp-tools.md)
- CLI: [`docs/reference/cli.md`](docs/reference/cli.md)
- Configuration: [`docs/reference/configuration.md`](docs/reference/configuration.md)
- Security: [`SECURITY.md`](SECURITY.md)
- Glossary: [`GLOSSARY.md`](GLOSSARY.md)
