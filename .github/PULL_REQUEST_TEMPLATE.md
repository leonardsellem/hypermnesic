<!-- Thanks for contributing! Keep PRs focused. See CONTRIBUTING.md and AGENTS.md. -->

## What & why

Briefly describe the change and the problem it solves. Link any issue or plan
(`docs/plans/…`).

## Gates (must pass — same as CI's `lint-test-license` job)

- [ ] `uv run ruff check .`
- [ ] `uv run python scripts/check_version_consistency.py`
- [ ] `uv run pytest` (new behavior is covered by a test — test-first)
- [ ] `uv run python scripts/license_scan.py` (no new AGPL/GPL/SSPL dependency)
- [ ] `uv run python scripts/preflight_public_scan.py` (no operator host/IP/token/secret added)

## Security surface

- [ ] This PR does **not** touch auth (`src/hypermnesic/auth*.py`), the MCP server,
      the write path (`commit_note` / `serialize` / `frontmatter_gate`), or the
      protected-path / governance guard.
- [ ] If it does: I referenced the relevant `SECURITY.md` / threat-model entry, and a
      CODEOWNER review is requested.

## Docs

- [ ] User-facing changes are reflected in the docs (README / references / guides /
      `CHANGELOG.md`), and any tool/CLI/config surface change updates the matching
      reference doc.

## Sign-off

- [ ] My commits are signed off (`git commit -s`) per the DCO (see `CONTRIBUTING.md`).
