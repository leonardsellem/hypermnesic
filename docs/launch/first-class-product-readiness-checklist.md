# First-class product readiness checklist

This checklist gates any claim that Hypermnesic is first-class. It is separate from the public
license flip. A benchmark score alone is not sufficient: first-class status requires current
evidence that people can operate the product end to end.

## Release-blocking rule

The first-class claim is blocked unless every row below has a current `Recorded result`,
`Pass/fail`, `Reviewer`, and `Date`. Missing evidence, stale evidence, failed commands,
unreviewed docs drift, secret-scan findings, or a failed remote-client smoke are release-blocking.

## Sprint-unit evidence matrix

| Sprint unit | Expected evidence | Recorded result | Pass/fail | Reviewer | Date | Release-blocking |
|---|---|---|---|---|---|---|
| U1 Local-first value proof | `hypermnesic local-proof` and local product smoke prove source-grounded recall plus dry-run write preview. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| U2 Setup doctor/status | `setup`, `doctor`, and `status` contracts distinguish local, remote, OAuth, auth, write, and next-action states without mutation. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| U3 Memory control center | Memory list/inspect/export/forget/revert/audit/write-scope flows are covered by tests and docs. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| U4 Consent/client trust | Consent page, client grant listing, scope refusal, write approval, and revocation are covered by tests and docs. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| U5 Plugin hook observability | Hook status/test-recall surfaces stable non-secret outcomes and disable controls. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| U6 Memory taxonomy/agent guidance | Docs and plugin skills route durable project memory to Hypermnesic and preferences/session state elsewhere. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| U7 Daily human workflows | Capture, triage, recall, write, review, and cleanup compose into `hypermnesic daily-review` and docs. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| U8 Product proof/launch readiness | Local smoke, offline remote contracts, manual remote-client smoke, docs, scans, and full suite are current. | Pending for release run. | Pending. | Pending. | Pending. | Yes |

## Automated command gates

| Command | Expected evidence | Recorded result | Pass/fail | Reviewer | Date | Release-blocking |
|---|---|---|---|---|---|---|
| `uv sync --extra dev` | Dependency environment resolves. | Resolved 157 packages and installed the dev environment for release evidence run. | Pass | Codex | 2026-06-12 | Yes |
| `uv run python scripts/product_smoke.py --work-dir /tmp/hypermnesic-smoke --json` | JSON status is `pass`; no private absolute paths or secrets in output. | After clearing a stale `/tmp/hypermnesic-smoke` fixture from a prior run, rerun returned JSON `status: pass` with all seven first-class loop stages passing. | Pass | Codex | 2026-06-12 | Yes |
| `uv run pytest tests/test_smoke.py tests/test_product_remote_smoke.py` | Local product smoke and offline remote contracts pass. | 8 passed. | Pass | Codex | 2026-06-12 | Yes |
| `uv run ruff check .` | Lint passes. | `All checks passed!` | Pass | Codex | 2026-06-12 | Yes |
| `uv run python scripts/check_version_consistency.py` | Version authority and manifests agree. | All 5 version slots agree with `pyproject.toml = 0.0.6`. | Pass | Codex | 2026-06-12 | Yes |
| `uv run pytest` | Full deterministic suite passes. | 702 passed, 1 skipped, 1 warning. | Pass | Codex | 2026-06-12 | Yes |
| `uv run python scripts/license_scan.py` | Dependency license gate passes. | 46 packages scanned; 0 AGPL/GPL/SSPL findings. | Pass | Codex | 2026-06-12 | Yes |
| `uv run python scripts/preflight_public_scan.py` | Public-surface scan has no operator secret or host findings. | Default scan checked 159 files with 59 deferred; no operator secret or host findings. | Pass | Codex | 2026-06-12 | Yes |
| `git diff --check` | No whitespace errors. | No whitespace errors. | Pass | Codex | 2026-06-12 | Yes |

## Manual remote-client gate

Run [`../guides/remote-client-smoke-checklist.md`](../guides/remote-client-smoke-checklist.md)
after automated gates pass.

| Client | Expected evidence | Recorded result | Pass/fail | Reviewer | Date | Release-blocking |
|---|---|---|---|---|---|---|
| ChatGPT | OAuth discovery, read-scoped call, write refusal without write scope, write-scoped call when approved, revocation. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| Claude | OAuth discovery, read-scoped call, write refusal without write scope, write-scoped call when approved, revocation. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| Claude Code | OAuth discovery, read-scoped call, plugin/hook status path, write refusal, write approval when applicable, revocation. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| Codex | OAuth discovery, read-scoped call, plugin/hook status path, write refusal, write approval when applicable, revocation. | Pending for release run. | Pending. | Pending. | Pending. | Yes |
| Obsidian | Tailnet read companion works and exposes no write path. | Pending for release run. | Pending. | Pending. | Pending. | Yes |

## Benchmark versus operability

LongMemEval measures retrieval quality under a fixed benchmark harness. It is useful evidence for
memory ranking and answer quality, but it does not prove setup, consent, memory control, plugin
observability, daily workflows, or remote-client operability.

First-class readiness requires both:

- benchmark evidence that retrieval quality is credible and honestly scoped;
- product operability proof that a user can capture, retrieve, write, inspect, forget or revert,
  reconnect clients, grant/revoke scopes, and recover from degraded states.

Benchmark scores are not a substitute for product readiness. Product proof is the local smoke,
offline remote-contract tests, manual remote-client smoke, docs coverage, and public-surface scans.

## Docs coverage gate

Before making a first-class claim, confirm these docs are current and linked from
[`../README.md`](../README.md):

- [`../../README.md`](../../README.md)
- [`../README.md`](../README.md)
- [`../guides/getting-started.md`](../guides/getting-started.md)
- [`../guides/memory-control.md`](../guides/memory-control.md)
- [`../guides/memory-taxonomy.md`](../guides/memory-taxonomy.md)
- [`../guides/daily-workflows.md`](../guides/daily-workflows.md)
- [`../guides/consent-and-clients.md`](../guides/consent-and-clients.md)
- [`../guides/remote-client-smoke-checklist.md`](../guides/remote-client-smoke-checklist.md)
- [`../reference/cli.md`](../reference/cli.md)
- [`../reference/mcp-tools.md`](../reference/mcp-tools.md)
- [`../../harness/BENCHMARKS.md`](../../harness/BENCHMARKS.md)
