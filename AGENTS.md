# AGENTS.md

## Linear Task Creation

Every Linear task or subtask created by an agent must be fully documented at creation time with a state-of-the-art description: context, intent, acceptance criteria, validation plan, and handoff/deployment notes when relevant.

Required creation metadata is non-negotiable: effort estimate, priority, and dependency relations (`blockedBy` / `blocks`) mapped from the plan, parent issue, or nearest sibling. If a connector cannot set one of those fields during creation, state the gap immediately and fill it through the next available Linear surface before handoff.


Contract for AI coding agents (Claude Code, Codex, and similar) working in this
repository. Humans: see [`CONTRIBUTING.md`](CONTRIBUTING.md) — the two are consistent;
this file states the parts an autonomous agent most needs up front.

> [`CLAUDE.md`](CLAUDE.md) is a **symlink to this file** — the two are one document, not
> two. Edit `AGENTS.md`; the mirror follows. (These governance files are themselves
> protected by the write guard — they are **refused** by the `commit_note` memory write
> path and can only be changed in an ordinary, reviewed PR.)

## The prime invariant

**Files are the source of truth; the index is a disposable, rebuildable projection of
the git tree.** Never treat the index as a database of record. A reindex must never be
able to lose a committed write. Everything in [`ARCHITECTURE.md`](ARCHITECTURE.md)
follows from this one line.

## Repo map — where things live

| Area | Path | What it is |
|---|---|---|
| Engine source | `src/hypermnesic/` | The Python package (details below) |
| Retrieval | `retrieve.py`, `index.py`, `embed.py`, `graph.py`, `converge.py` | Hybrid FTS5 + sqlite-vec search; read-time convergence |
| Write path | `commit_note.py`, `serialize.py`, `frontmatter_gate.py`, `audit_log.py` | The one git-first write, its guards, its gate, its log |
| Serving | `mcp_server.py`, `auth.py`, `auth_cloud.py` | Public OAuth `/mcp` + tailnet read companion |
| Local surface | `cli.py` | The engine-host-local `hypermnesic` CLI |
| Provisioning / config | `install.py`, `connect.py`, `config.py` | Roles, setup, env-driven config |
| Human surfaces | `capture.py`, `salience.py`, `nav_surface.py`, `think.py`, `propose.py`, `expand.py`, `sidecar.py`, `folders.py`, `generated.py` | Capture/triage, digest, navigation, thinking-mode, sidecar extraction |
| Tests | `tests/` | `pytest`, `--import-mode=importlib` |
| Gate scripts | `scripts/` | `check_version_consistency.py`, `license_scan.py`, `preflight_public_scan.py` |
| Plugin | `plugin/` | Claude Code / Codex plugin (OAuth-discovery, distribution-generic) |
| Companion | `obsidian-plugin/` | Read-only Obsidian companion (ships from a **separate** GPL-3.0 repo) |
| Benchmarks | `harness/` | LongMemEval harness + `harness/BENCHMARKS.md` |
| Docs | `docs/` | Start at [`docs/README.md`](docs/README.md) — it pins current truth |

## Build, test, and gates

Python ≥ 3.11, [uv](https://docs.astral.sh/uv/) for dependencies. The full gate set —
identical to CI's single `lint-test-license` job — is:

```sh
uv sync --extra dev
uv run ruff check .                                   # lint (line-length 100; E,F,I,UP,B)
uv run python scripts/check_version_consistency.py    # pyproject ↔ manifests ↔ __init__
uv run pytest                                         # full suite (offline, deterministic)
uv run python scripts/license_scan.py                 # zero AGPL/GPL/SSPL *dependency* gate
uv run python scripts/preflight_public_scan.py        # no operator secret/host in the public surface
```

All six must pass before a change is done. The suite runs offline and deterministic
(the OpenAI key is neutralized in tests; dense retrieval degrades to lexical).

## Working rules

- **Test-first.** No new production behavior without a failing test first. Tests live
  in `tests/`, run with `--import-mode=importlib`.
- **No "pre-existing" failures.** A red test is either fixed in your change or filed as a
  tracked issue — never dismissed or deleted.
- **Branch off `main`; never commit to `main` directly.** Use a worktree per task when
  changes could conflict. Commit per logical unit with a conventional subject and a
  `Signed-off-by:` DCO line (`git commit -s`).
- **Permissive dependencies only.** Any new dependency must keep
  `scripts/license_scan.py` green (zero AGPL/GPL/SSPL). The gate is dependency-scoped;
  it does not constrain the engine's own (planned-AGPL) license.
- **Never echo secrets.** The OpenAI key, OAuth consent secret, and tokens are read
  from the environment / a gitignored `.env` only — never written to the index, the
  audit log, any output, or chat. `scripts/preflight_public_scan.py` enforces that no
  operator host/IP/token ships in the public surface — so **use placeholders**
  (`<your-host>.ts.net`, the `100.64.0.0/10` CGNAT range), never real operator values,
  in any doc or fixture.
- **Respect the write guard.** The write path (`commit_note`) is git-first and bounded
  by a blocklist (protected-path + governance-file fence). Do not weaken it; changes to
  `serialize.py` / `frontmatter_gate.py` / `auth*.py` / `mcp_server.py` are
  security-sensitive (CODEOWNERS-routed) and must cite [`SECURITY.md`](SECURITY.md) and
  the threat model.
- **Native primitives first.** Before adding any adapter, wrapper, shell-out, or
  parser, check whether an upstream tool (the MCP SDK, Tailscale, OAuth libs, uv) already
  exposes the primitive. Prefer it over re-inventing it.

## Documentation must not drift — NON-NEGOTIABLE

**Documentation is part of the change, not a follow-up.** A change is **not done** until
every document it affects is corrected **in the same PR**. "Update the docs later" is not
allowed — later never comes, and a stale doc actively misleads the next agent.

This is not a style preference; it is paid-for scar tissue. This repo has been bitten
twice: the **0.0.4 ↔ 0.0.5** release that bumped only the Python package and let the
plugin manifests drift (now caught by `scripts/check_version_consistency.py`), and a
whole **"Phase A — drift correction"** in [`PR #26`](https://github.com/leonardsellem/hypermnesic/pull/26)
spent un-stale-ing the "tailnet-only / read-only" self-description and the
"allowlist-by-default" write model that code had long since moved past. Every hour spent
there is an hour the rule below would have saved.

### When you change X, update its docs in the same PR

| If your change touches… | …update, in the same PR |
|---|---|
| **MCP tool surface** (`mcp_server.py` — add/remove/rename a tool or change args) | [`docs/reference/mcp-tools.md`](docs/reference/mcp-tools.md); the tool list in [`README.md`](README.md); `ARCHITECTURE.md` if the serving picture changes |
| **CLI** (`cli.py` — commands/flags) | [`docs/reference/cli.md`](docs/reference/cli.md); the CLI examples in [`README.md`](README.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| **Config / env** (`config.py`, `.env.example`) | [`docs/reference/configuration.md`](docs/reference/configuration.md); `.env.example`; any `CONVERGE_*`/budget mentions in [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| **Write guard / protected paths / governance fence** (`serialize.py`, `frontmatter_gate.py`, `commit_note.py`) | `ARCHITECTURE.md` write-path section; [`SECURITY.md`](SECURITY.md) + [`docs/threat-model-commit-note.md`](docs/threat-model-commit-note.md); the write-model pin in [`docs/README.md`](docs/README.md); the write-guard bullet above; `README.md` "How it works" |
| **Auth / serving topology / lanes** (`auth*.py`, `mcp_server.py`) | `ARCHITECTURE.md` serving section; the serving-topology pin in `docs/README.md`; [`docs/unified-oauth-mcp-deploy-runbook.md`](docs/unified-oauth-mcp-deploy-runbook.md); `README.md`; `SECURITY.md` |
| **Retrieval / convergence / index** (`retrieve.py`, `converge.py`, `index.py`, `embed.py`, `graph.py`) | `ARCHITECTURE.md` retrieval + convergence sections; `README.md` "How it works" if user-visible; `harness/BENCHMARKS.md` if measured numbers move |
| **Version** (`pyproject.toml` `[project].version`) | `src/hypermnesic/__init__.__version__` **and the plugin manifests** — do not hand-enumerate them; run `scripts/check_version_consistency.py`, which names every file that must match; plus a dated [`CHANGELOG.md`](CHANGELOG.md) section |
| **Any new dependency** | keep `scripts/license_scan.py` green; record it in `pyproject.toml` |
| **New term or concept** | [`GLOSSARY.md`](GLOSSARY.md) |
| **Renaming / superseding a doc** | the [`docs/README.md`](docs/README.md) index **and** its "current truth" pins; move the superseded doc to `docs/archive/` with a pointer banner to its replacement |
| **Any user-visible behavior at all** | a dated entry under `[Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md) |

### Anti-drift discipline

- **Point to the enforcing gate; don't re-list the enumerable set.** Where an automated
  gate already pins truth (versions → `check_version_consistency.py`; copyleft →
  `license_scan.py`; secrets/hosts → `preflight_public_scan.py`), reference the gate
  rather than copying its list into prose — a copied list is the next thing to drift.
- **`docs/README.md` "current truth" is the tie-breaker.** When a process-history doc
  (a plan, brainstorm, handoff, gate artifact) conflicts with current truth, the pins in
  [`docs/README.md`](docs/README.md) win. If your change moves current truth, update those
  pins.
- **Signed-off reviews are append-only.** Do not rewrite a dated, signed-off security
  review or gate artifact — add a dated amendment (`amends:` / `signed_off:` frontmatter).
- **Found drift you didn't cause? Fix it or file it.** Same rule as a failing test — a
  doc that contradicts the code is a defect, not background noise.

## Linear

- Use `linear-safe` / `linear-ls` for routine interactive issue reads,
  comments, branch starts, and status changes. Keep Linear MCP as a
  fallback/lifecycle surface only when a task explicitly requires MCP behavior
  or wrapper healthchecks fail.
- The repo-root `.linear.toml` pins `workspace = "ls-ventures"` and
  `team_id = "LS"` only as a human/raw-CLI fallback. It is not the agent safety
  boundary because ambient Linear env vars override `.linear.toml`; wrappers
  remain the agent default.

## How this repo plans and ships work

- **Plans** live under `docs/plans/` (`YYYY-MM-DD-NNN-<type>-<slug>-plan.md`) and are the
  authoritative scope of record; brainstorms (the "what") live under `docs/brainstorms/`.
  Both are **process history** — when they conflict with `docs/README.md`'s current
  truth, the pins win.
- **Gate artifacts** (`docs/gate-artifacts/`) and dated **security reviews**
  (`docs/*-security-review.md`, with `amends:` / `signed_off:` frontmatter) record
  signed-off decisions; reusable design decisions live under `docs/solutions/`.
- **Release history** is [`CHANGELOG.md`](CHANGELOG.md) (Keep a Changelog format); the
  narrative build log is `implementation-notes.md` (historical, not a changelog).
- **Public-launch staging** lives under `docs/launch/` — the AGPL-3.0 text, the one-PR
  flip runbook, and the launch checklist are staged but **not live**; the `LICENSE` stays
  proprietary until the flip PR.

## Reference

- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Documentation index (start here): [`docs/README.md`](docs/README.md)
- MCP tools: [`docs/reference/mcp-tools.md`](docs/reference/mcp-tools.md)
- CLI: [`docs/reference/cli.md`](docs/reference/cli.md)
- Configuration: [`docs/reference/configuration.md`](docs/reference/configuration.md)
- Security: [`SECURITY.md`](SECURITY.md) · threat model: [`docs/threat-model-commit-note.md`](docs/threat-model-commit-note.md)
- Glossary: [`GLOSSARY.md`](GLOSSARY.md)
- Contributing (humans): [`CONTRIBUTING.md`](CONTRIBUTING.md)
