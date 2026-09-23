---
okf_version: "0.2"
---

# Files

- [Agent Plugins and Hooks](agent-plugins-and-hooks.md) - How hypermnesic reaches agent hosts — the Claude Code/Codex pack and its auto-recall hook, the Hermes CLI pack, and the arm's-length Obsidian companion boundary.
- [Architecture Overview](architecture-overview.md) - The whole mental model of hypermnesic — files as the single source of truth, the index as a disposable projection, the read and write paths, the two serving lanes, and which module owns what.
- [Benchmarks and Evaluation](benchmarks-and-evaluation.md) - How retrieval quality is measured and reported — the LongMemEval harness, its pinned manifest, the reader/judge/release comparability envelope, and why a benchmark score is not a product-readiness proof.
- [Capture and Thinking Surfaces](capture-and-thinking-surfaces.md) - The input and pre-write surfaces — frictionless capture, deferred triage, structurally read-only thinking mode, folder discovery, and content-addressed sidecar extraction.
- [CLI Surface](cli-surface.md) - The engine-host-local hypermnesic command line — 22 subcommands by role, the shared conventions, which commands preview by default, and which are CLI twins of MCP tools.
- [Configuration and Tunables](configuration-and-tunables.md) - Every operational knob — environment variables and their readers, the exact credential lookup order, the pinned embedding model, convergence budgets, discovery bounds, and write-zone tiers — with the consequence of changing each.
- [Git-First Write Path](git-first-write-path.md) - The single sanctioned write, traced end to end — guard order, the diff-or-die frontmatter gate, multi-host coordination, the refusal contract, degraded-index success, and the append-only audit log.
- [MCP Tool Surface](mcp-tool-surface.md) - The client contract — seven read tools and one gated write tool, their typed output schemas, registration conditions, shared read guarantees, and the security boundaries built into each.
- [Memory and Client Control](memory-and-client-control.md) - The owner surfaces over what is remembered and who may connect — listing, inspection, export, git-backed forget, safe revert, audit history, write-scope answering, and secret-free grant revocation.
- [Provisioning and Diagnostics](provisioning-and-diagnostics.md) - Getting a host working and proving it works — the local-first proof, non-mutating doctor states, fail-closed public setup, role provisioning, the convergence hook, and client next actions.
- [Quickstart](quickstart.md) - The entry point — what hypermnesic is, the one invariant, the development gates, the shortest path to proving local recall, and where every subsystem is documented.
- [Read-Time Convergence](read-time-convergence.md) - The correctness step every read runs first — delta-replay to HEAD, bounded dense catch-up, the debounce, the non-blocking lock, and the advisory manual-reindex signal.
- [Retrieval and Indexing](retrieval-and-indexing.md) - How a query becomes ranked hits — markdown chunking, the FTS5 and sqlite-vec channels, the doc lane, RRF fusion, dedup and recency, the wikilink graph, and the exact degradation contract.
- [Review and Navigation Surfaces](review-and-navigation-surfaces.md) - The generated, review-gated organizing layer — the proposal queue, the GENERATED demarcation, salience digests, serendipity connections, MOC/dashboard navigation, and the daily loop.
- [Serving Topology and Authentication](serving-and-authentication.md) - The two serving lanes — a public OAuth 2.1 endpoint with DCR, PKCE, an operator consent gate and audience-bound revocable tokens, and a read-only tailnet companion — plus the invariants that keep them safe.
- [Testing and Release Gates](testing-and-release-gates.md) - How change is validated and shipped — the offline deterministic suite, the gate set CI mirrors exactly, the fresh-install job, the branch topology, and the tag-triggered publish.
- [Write Guard and Security Model](write-guard-and-security-model.md) - The blocklist write surface and the protections around it — protected classes, the governance fence, within-repo resolution, allowlist narrowing, locks, body-free auditing, and what never leaves the process.
