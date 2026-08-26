---
type: Reference
title: Quickstart
description: The entry point — what hypermnesic is, the one invariant, the development gates, the shortest path to proving local recall, and where every subsystem is documented.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-4d1d392666be6dfdd7a91a2e
    resource: repo://.github/workflows/release.yml
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-362e06c30ccfdafd87339cb0
    resource: repo://ARCHITECTURE.md
  - id: openwiki-source-f317ee207e1653d2033c81a4
    resource: repo://CONTRIBUTING.md
  - id: openwiki-source-196170e31ff8ec60a116165b
    resource: repo://docs/README.md
  - id: openwiki-source-f9fcdc4150867822e80d6070
    resource: repo://docs/reference/cli.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-9b37eab1bcb7a0dabc8255c1
    resource: repo://src/hypermnesic/cli.py
  - id: openwiki-source-f103fa2315aae36568406e00
    resource: repo://src/hypermnesic/commit_note.py
  - id: openwiki-source-5f17d71d8e2d83b9ea0bc2ae
    resource: repo://src/hypermnesic/config.py
  - id: openwiki-source-33b20611aee0ccb46de27828
    resource: repo://src/hypermnesic/local_proof.py
  - id: openwiki-source-802c4acce1763f2c8920a3cf
    resource: repo://src/hypermnesic/propose.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Quickstart

## What this is

hypermnesic is a **git-native memory layer**. A vault of plain markdown files in a git
repository you host becomes durable, searchable memory that every assistant — chat clients,
coding agents, an editor companion — reads and writes through **one endpoint**. Every memory is
a real git commit: reviewable, revertible, and yours.

Two things follow from that and are worth holding before you read any code:

> **Files are the source of truth. The search index is a disposable, rebuildable projection of
> the committed tree.**

and

> **`commit_note` is the one sanctioned write.** It is git-first, guarded, gated, and audited.
> Nothing else mutates the corpus without an owner approving a proposal.

If you internalize only those, most design questions in this repository answer themselves. The
full derivation is in [Architecture Overview](architecture-overview.md).

## Get set up

You need Python 3.11 or newer and `uv`.

```sh
git clone <repo-url> hypermnesic && cd hypermnesic
uv sync --extra dev
```

Most of the engine runs offline. Dense retrieval needs an embedding key, read from the
environment or a gitignored repo-root `.env`; without it retrieval degrades to lexical-only —
which is also how the test suite runs. See
[Configuration and Tunables](configuration-and-tunables.md).

## The gates you must pass

CI runs one job whose steps are exactly these, so local success and CI success are the same
event:

```sh
uv run ruff check .
uv run python scripts/check_version_consistency.py
uv run pytest
uv run python scripts/license_scan.py
uv run python scripts/preflight_public_scan.py
```

On an ordinary machine the whole loop fits comfortably inside a few minutes, with the test
suite the only step measured in minutes rather than seconds. Details, and the second CI job
that installs the built package with no lockfile, are in
[Testing and Release Gates](testing-and-release-gates.md).

## Prove recall in one command

```sh
hypermnesic local-proof /path/to/your/vault
```

Against an existing markdown git repository this validates the vault, builds the projection,
answers a natural question, shows the repo-relative source path the answer came from, and
previews a write as a **dry-run diff with no commit**. It is read-only by default, provisions
nothing, and works with no API key. Add `--demo-dir DIR` to try it on a tiny generated vault
first.

That ordering is deliberate: **prove local memory before any endpoint concept enters the
picture.** A remote failure is far easier to diagnose once you know retrieval is fine. See
[Provisioning and Diagnostics](provisioning-and-diagnostics.md).

## The rules that govern changes

- **Test-first.** No new production behaviour without a failing test first.
- **Branch off `dev`, PR into `dev`.** `dev` is the default branch and the baseline; `main` is
  the release branch and takes only `dev`. Never commit directly to either. A tag on `main` is
  what publishes — merging publishes nothing.
- **Documentation is part of the change.** Every document a change affects is corrected **in
  the same pull request**. "Update the docs later" is not allowed: later does not come, and a
  stale document actively misleads the next reader.
- **No "pre-existing" failures.** A red test is fixed in your change or filed as a tracked
  issue — never dismissed.
- **Permissive dependencies only**, each with an upper version bound.
- **Never echo secrets**, and use placeholder hosts in anything committed.
- **Respect the write guard.** Changes to the guard, the gate, auth, or the server are
  security-sensitive and route to the owner.

## Where everything is documented

**Start here**

| Page | What it answers |
|---|---|
| [Architecture Overview](architecture-overview.md) | The whole mental model, the layers, and which module owns what. |

**The engine**

| Page | What it answers |
|---|---|
| [Retrieval and Indexing](retrieval-and-indexing.md) | How a query becomes ranked hits; what the index holds; the graph. |
| [Read-Time Convergence](read-time-convergence.md) | How reads stay fresh while the index stays a pure projection. |
| [Git-First Write Path](git-first-write-path.md) | The one write, traced end to end, and the refusal contract. |
| [Write Guard and Security Model](write-guard-and-security-model.md) | What is protected, why, and what never leaves the process. |

**The surfaces**

| Page | What it answers |
|---|---|
| [MCP Tool Surface](mcp-tool-surface.md) | The client contract for every tool. |
| [CLI Surface](cli-surface.md) | Every subcommand, by role. |
| [Serving Topology and Authentication](serving-and-authentication.md) | The two lanes, OAuth, consent, and the bind invariants. |
| [Configuration and Tunables](configuration-and-tunables.md) | Every knob and the consequence of changing it. |

**Working with memory**

| Page | What it answers |
|---|---|
| [Capture and Thinking Surfaces](capture-and-thinking-surfaces.md) | Capture, triage, thinking mode, folder discovery, sidecars. |
| [Review and Navigation Surfaces](review-and-navigation-surfaces.md) | Proposals, the generated marker, digests, connections, the daily loop. |
| [Memory and Client Control](memory-and-client-control.md) | Inspect, export, forget, revert, audit, and grant revocation. |

**Operating and shipping**

| Page | What it answers |
|---|---|
| [Provisioning and Diagnostics](provisioning-and-diagnostics.md) | Local proof, doctor states, fail-closed setup, the hook. |
| [Agent Plugins and Hooks](agent-plugins-and-hooks.md) | How agent hosts reach the endpoint, and the auto-recall hook. |
| [Testing and Release Gates](testing-and-release-gates.md) | The suite, the gates, the branches, and how a release happens. |
| [Benchmarks and Evaluation](benchmarks-and-evaluation.md) | How retrieval quality is measured and reported honestly. |

## A note on reading the repository's own docs

The `docs/` tree separates **durable reference** from **process history** — plans, brainstorms,
handoffs, and gate artifacts record how the project got here and are not maintained as
reference. When a process-history document conflicts with the documentation index's
current-truth pins, **the pins win**. Two self-descriptions in particular have already been
corrected once and may still appear in older material: the write model is a **blocklist**, not
an allowlist, and the serving topology is **two lanes**, not tailnet-only.
