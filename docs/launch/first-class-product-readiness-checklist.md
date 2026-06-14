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
| U1 Local-first value proof | `hypermnesic local-proof` and local product smoke prove source-grounded recall plus dry-run write preview. | `uv run python scripts/product_smoke.py --work-dir /tmp/hypermnesic-pr5-smoke --json` returned JSON `status: pass`; `uv run pytest tests/test_local_proof.py tests/test_smoke.py -q` passed with 16 tests. | Pass | Codex | 2026-06-12 | Yes |
| U2 Setup doctor/status | `setup`, `doctor`, and `status` contracts distinguish local, remote, OAuth, auth, write, and next-action states without mutation. | `uv run pytest tests/test_install.py tests/test_doctor.py tests/test_connect.py -q` passed with 63 tests. | Pass | Codex | 2026-06-12 | Yes |
| U3 Memory control center | Memory list/inspect/export/forget/revert/audit/write-scope flows are covered by tests and docs. | `uv run pytest tests/test_memory_control.py tests/test_audit_log.py tests/test_frontmatter_gate.py -q` passed with 26 tests. | Pass | Codex | 2026-06-12 | Yes |
| U4 Consent/client trust | Consent page, client grant listing, scope refusal, write approval, and revocation are covered by tests and docs. | `uv run pytest tests/test_auth_cloud.py tests/test_client_control.py tests/test_product_remote_smoke.py -q` passed with 49 tests. | Pass | Codex | 2026-06-12 | Yes |
| U5 Plugin hook observability | Hook status/test-recall surfaces stable non-secret outcomes and disable controls. | `uv run pytest tests/test_plugin_hook.py tests/test_hermes_plugin_hook.py -q` passed with 36 tests. | Pass | Codex | 2026-06-12 | Yes |
| U6 Memory taxonomy/agent guidance | Docs and plugin skills route durable project memory to Hypermnesic and preferences/session state elsewhere. | `uv run pytest tests/test_plugin.py tests/test_hermes_plugin.py tests/test_folders.py tests/test_mcp_server.py::test_list_folders_returns_taxonomy_and_schema_shape -q` passed with 33 tests. | Pass | Codex | 2026-06-12 | Yes |
| U7 Daily human workflows | Capture, triage, recall, write, review, and cleanup compose into `hypermnesic daily-review` and docs. | `uv run pytest tests/test_daily_review.py tests/test_capture.py tests/test_nav_surface.py -q` passed with 16 tests. | Pass | Codex | 2026-06-12 | Yes |
| U8 Product proof/launch readiness | Local smoke, offline remote contracts, manual remote-client smoke, docs, scans, and full suite are current. | Automated local smoke, offline remote contracts, docs, scans, and full suite are current in this checklist. LS-1675 is Done: ChatGPT, Claude, Claude Code, Codex, and Obsidian rows have reviewer/date evidence. Obsidian surfaced degraded lexical-only mode during the run; LS-1741 now makes embedding 429s operator-visible with `degraded_reason`, adds a provider cooldown, and has bounded dense-live smoke evidence showing dense can recover after funding. The client-smoke row itself passed because read-only status, `wrote:false`, and non-empty relations were visible. | Pass | Codex | 2026-06-14 | Yes |

## Automated command gates

| Command | Expected evidence | Recorded result | Pass/fail | Reviewer | Date | Release-blocking |
|---|---|---|---|---|---|---|
| `uv sync --extra dev` | Dependency environment resolves. | Resolved 157 packages and checked the dev environment for the LS-1741 dense-degradation run. | Pass | Codex | 2026-06-14 | Yes |
| `uv run python scripts/product_smoke.py --work-dir /tmp/hypermnesic-smoke --json` | JSON status is `pass`; no private absolute paths or secrets in output. | After clearing `/tmp/hypermnesic-smoke`, rerun returned JSON `status: pass` with all seven first-class loop stages passing and lexical-only degradation explicitly reported. | Pass | Codex | 2026-06-13 | Yes |
| `uv run pytest tests/test_smoke.py tests/test_product_remote_smoke.py` | Local product smoke and offline remote contracts pass. | 8 passed. | Pass | Codex | 2026-06-13 | Yes |
| `uv run ruff check .` | Lint passes. | `All checks passed!` | Pass | Codex | 2026-06-14 | Yes |
| `uv run python scripts/check_version_consistency.py` | Version authority and manifests agree. | All 5 version slots agree with `pyproject.toml = 0.0.6`. | Pass | Codex | 2026-06-14 | Yes |
| `uv run pytest` | Full deterministic suite passes. | 711 passed, 1 skipped, 1 warning. | Pass | Codex | 2026-06-14 | Yes |
| `uv run python scripts/license_scan.py` | Dependency license gate passes. | 46 packages scanned; 0 AGPL/GPL/SSPL findings. | Pass | Codex | 2026-06-14 | Yes |
| `uv run python scripts/preflight_public_scan.py` | Public-surface scan has no operator secret or host findings. | Default scan checked 159 files with 59 deferred; no operator secret or host findings. | Pass | Codex | 2026-06-14 | Yes |
| `git diff --check` | No whitespace errors. | No whitespace errors. | Pass | Codex | 2026-06-14 | Yes |
| `uv run hypermnesic doctor /home/ubuntu/brain --check-dense-live --json` | Opt-in dense-live smoke confirms the embedding provider is reachable without printing secrets. | Doctor returned `status: ready`; dense live check passed. The production vault still reports stale/absent vectors, so broad convergence was not run in this issue. | Pass | Codex | 2026-06-14 | Yes |
| Tiny temp-repo dense retrieval smoke | A bounded dense search can return `degraded_lexical_only:false` after the provider condition clears. | Two-note temp repo indexed with the live key; one query returned `degraded_lexical_only:false`, `degraded_reason:null`, `dense_used:true`, and dense channels on returned hits. | Pass | Codex | 2026-06-14 | Yes |

## Manual remote-client gate

Run [`../guides/remote-client-smoke-checklist.md`](../guides/remote-client-smoke-checklist.md)
after automated gates pass.

| Client | Expected evidence | Recorded result | Pass/fail | Reviewer | Date | Release-blocking |
|---|---|---|---|---|---|---|
| ChatGPT | OAuth discovery, read-scoped call, write refusal without write scope, write-scoped call when approved, revocation. | Hosted ChatGPT was accepted as an operator-approved read+write client per the personal-use waiver in PR #48. Post-PR #46 read output used repo-relative paths and did not expose tokens, credential bodies, approval secrets, endpoint URLs, or actual absolute local paths. Write smoke committed `captures/2026-06-13-ls-1675-chatgpt-write-smoke.md` at `854cb9422beccc472a193883d9fbde921c8dc620`; recall returned the marker; protected write to `scripts/ls-1675-chatgpt-protected-refusal.md` was refused; revocation/reconnect passed per operator report. | Pass | Léonard Sellem | 2026-06-13 | Yes |
| Claude | OAuth discovery, read-scoped call, write refusal without write scope, write-scoped call when approved, revocation. | Hosted Claude was accepted as an operator-approved read+write client per the personal-use waiver in PR #48. Read/list/search output used repo-relative paths and did not expose local absolute paths, private endpoint URLs, tokens, or secrets. Write smoke committed `captures/2026-06-13-ls-1675-claude-write-smoke.md` at `c2f61082b49d99efb3f3f6486f82856eb5f00aac`; recall returned the marker; protected write to `scripts/ls-1675-claude-protected-refusal.md` was refused; revocation/reconnect passed per operator report. | Pass | Léonard Sellem | 2026-06-13 | Yes |
| Claude Code | OAuth discovery, read-scoped call, plugin/hook status path, write refusal, write approval when applicable, revocation. | Operator reported the Claude Code public OAuth path connected to the public endpoint, read-scope OAuth passed, read-only refusal passed, write-scope smoke passed, and revocation/reconnect passed. | Pass | Léonard Sellem | 2026-06-13 | Yes |
| Codex | OAuth discovery, read-scoped call, plugin/hook status path, write refusal, write approval when applicable, revocation. | Configured Codex tailnet MCP row passed after LS-1707 was fixed and deployed: live MCP discovery/read succeeded, approved low-risk `commit_note` writes were recalled, and protected `AGENTS.md` writes remained refused. Linear LS-1675 comments record the live service restart and recall/refusal evidence after PR #44. | Pass | Codex | 2026-06-13 | Yes |
| Obsidian | Tailnet read companion works and exposes no write path. | Laptop Obsidian companion against `http://100.103.0.55:8848/mcp` showed `read-only` and `wrote: false`; rendered 8 related entries plus 3 not-yet-linked entries; exposed no write controls and no reported token, approval secret, refresh token, credential body, or raw local absolute path. It also surfaced `lexical-only — the semantic channel is down`; service logs showed embeddings `429 Too Many Requests`. LS-1741 adds explicit degraded reasons and a cooldown so the same condition is actionable instead of ambiguous. | Pass | Léonard Sellem | 2026-06-14 | Yes |

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
