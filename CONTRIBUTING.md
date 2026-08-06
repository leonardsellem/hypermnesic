# Contributing to hypermnesic

Thanks for your interest. This document takes a contributor from a clone to passing
the same gates CI runs, and documents how releases and security-sensitive changes are
handled.

> **Status:** the repository is currently private / pre-release. The contribution
> process below is the steady-state contract that goes live with the public flip.

## Development setup

You need **Python ≥ 3.11** and [**uv**](https://docs.astral.sh/uv/).

```sh
git clone <repo-url> hypermnesic && cd hypermnesic
uv sync --extra dev          # base + dev tooling (pytest, ruff, pip-licenses)
```

Most of the engine runs offline. Dense retrieval needs an `OPENAI_API_KEY` (read from
the environment or a gitignored repo-root `.env`); without it, retrieval degrades to
lexical-only — which is also how the test suite runs (the key is neutralized so tests
are deterministic and offline).

The cold release-verification path was checked on 2026-06-13 from a fresh clone with
no repo `.env`, an empty `HOME`, an empty `UV_CACHE_DIR`, and `OPENAI_API_KEY` unset.
Use these as ballpark wall-clock expectations on a Linux runner with Python 3.11:

| Step | Expected runtime |
|---|---:|
| `uv sync --extra dev` | < 1 minute from an empty uv cache |
| `uv run ruff check .` | < 1 minute |
| `uv run python scripts/check_version_consistency.py` | < 1 minute |
| `uv run pytest` | about 3 minutes |
| `uv run python scripts/license_scan.py` | < 1 minute |
| `uv run python scripts/preflight_public_scan.py` | < 1 minute |

The full local gate loop should fit comfortably under 5 minutes on that class of machine.

## The gates (run these before every PR)

CI runs one job, `lint-test-license`, which is exactly the following steps. Run them
locally and they will match CI:

```sh
uv run ruff check .                                   # lint (line-length 100; E,F,I,UP,B)
uv run python scripts/check_version_consistency.py    # pyproject ↔ manifests ↔ __init__
uv run pytest                                         # the full suite (offline, deterministic)
uv run python scripts/license_scan.py                 # zero AGPL/GPL/SSPL *dependency* gate
uv run python scripts/preflight_public_scan.py        # no operator secret/host in the public surface
```

- **Lint:** `ruff` with `select = ["E", "F", "I", "UP", "B"]`, line length 100.
- **Version consistency:** `pyproject.toml` `[project].version` is the single source of
  truth; package, plugin, and citation metadata versions must match.
- **Tests:** `pytest` with `--import-mode=importlib`; tests under `tests/`. New
  production behavior gets a test (the project is test-first — see `AGENTS.md`).
- **License gate:** verifies the dependency tree stays free of AGPL/GPL/SSPL. It is
  **dependency-scoped** — it excludes the project's own distribution, so it does not
  govern hypermnesic's own (planned-AGPL) license. Add only permissively-licensed deps.
- **Preflight public scan:** ensures no operator host/IP/token/credential ships in the
  to-be-public surface. The default mode is the CI gate; `--strict` is the flip-time gate.

## Running a local endpoint to test against

On the machine that holds a markdown vault:

```sh
uv tool install .                            # install the `hypermnesic` CLI
hypermnesic init /path/to/your/vault         # build the index (uses OPENAI_API_KEY)
hypermnesic retrieve /path/to/vault "query"  # exercise hybrid retrieval locally
```

For the network surface, `hypermnesic setup` brings up the unified OAuth `/mcp`
endpoint; see [`docs/guides/getting-started.md`](docs/guides/getting-started.md).

## Branches, commits, and pull requests

- Branch off `dev`; do not commit directly to `dev` or `main`. See
  [Branches](#branches) — `main` is the release branch and takes only `dev`.
- Use clear, conventional commit subjects (`feat:`, `fix:`, `docs:`, `chore:`,
  `test:`, `refactor:`). Reference the unit/requirement when relevant.
- Open a PR into `dev`. The PR template's checklist ties your change to the gates
  above and flags security-surface changes.
- **DCO sign-off (required).** Add a `Signed-off-by: Name <email>` line to each commit
  (`git commit -s`). By signing off you certify the [Developer Certificate of
  Origin](https://developercertificate.org/). Once the project is public + AGPL-3.0,
  inbound contributions are inbound=outbound AGPL-3.0; the DCO is the lightweight
  provenance attestation (a CLA is intentionally not required).

## Security-sensitive changes

Changes to auth (`src/hypermnesic/auth*.py`), the MCP server, the write path
(`commit_note` / `serialize` / `frontmatter_gate`), or the protected-path/governance
guard are security-sensitive. They are routed to the owner via
[`.github/CODEOWNERS`](.github/CODEOWNERS) and should reference the relevant entry in
[`SECURITY.md`](SECURITY.md) and the threat model. Never report a vulnerability in a
public issue — see [`SECURITY.md`](SECURITY.md).

## Branches

`dev` is the default branch and the baseline for all work. `main` is the **release
branch**: it receives `dev` at release time and never a feature branch.

```text
feature/fix branch ──PR──▶ dev ──PR──▶ main ──tag v*.*.*──▶ PyPI + GitHub release
```

Branch off `dev`, PR into `dev`, and let `gh pr create` use the repository default
rather than passing `--base`. Never commit directly to `dev` or `main`.

If `main` and `dev` drift apart, reconcile by merging `main` back into `dev`. Do not
cherry-pick across them — that leaves the same content under two SHAs to untangle at
the next release.

## Releasing

The engine is pre-1.0 and uses `0.x` semantics (any release may carry breaking
changes while the kernel stabilizes).

**Merging to `main` publishes nothing.**
[`release.yml`](.github/workflows/release.yml) triggers only on a `v*.*.*` **tag push**
or a manual `workflow_dispatch`; a branch merge runs `ci.yml` and stops. Publishing is a
deliberate act, never a side effect of merging — so a release that "should have gone out"
after a merge did not fail, it was never triggered.

1. **Choose the number.** `0.x` semantics are loose about breakage, but the shape still
   holds: new backwards-compatible functionality — a new MCP tool, new fields on a tool's
   output — is a **minor** bump; **patch** is for releases that are fixes only. Decide by
   reading the whole pending `[Unreleased]` section, not just the last change merged.
2. **Bump the version.** `pyproject.toml` `[project].version` is the single source of
   truth; `src/hypermnesic/__init__.__version__`, the plugin manifests, and the citation
   metadata mirror it. Do not enumerate them from memory — run
   `scripts/check_version_consistency.py`, which names every slot and is the same gate
   the release build runs.
3. **Cut the changelog.** In [`CHANGELOG.md`](CHANGELOG.md) (Keep a Changelog format),
   rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, leave a fresh empty `[Unreleased]`
   above it, and update the compare links at the foot of the file. The GitHub release
   notes come from this section: anything absent here ships undocumented.
4. **Promote `dev` to `main`** via PR.
5. **Tag `vX.Y.Z` on `main`**, on the exact commit you intend to ship, and push the tag.
   That pushes the build through PyPI OIDC Trusted Publishing. There is no stored API
   token, so a mistaken tag cannot be neutralised by rotating a credential — check the
   commit before pushing it.

**Keep the dates honest.** The `[X.Y.Z]` heading and `date-released` in both
`CITATION.cff` files must equal the date the tag is actually pushed. When release prep
lands days ahead of the tag, update them at tag time. Letting them drift is what allowed
the `0.0.4`/`0.0.5` pair to disagree twice.

The Obsidian companion ships from its own repository under GPL-3.0 with its own
version and release cadence; it is not released from here.
