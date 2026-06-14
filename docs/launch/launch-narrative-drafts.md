---
title: "Launch narrative drafts"
status: drafted
audience: operator
linear: LS-1689
last_checked: 2026-06-14
---

# Launch narrative drafts

This is the PR-20 / LS-1689 draft artifact. It gives one source-backed launch
story and channel-specific post drafts.

Do not post any text from this document to Hacker News, Reddit, X, Bluesky,
Discord, or any other external channel without operator approval.

## Evidence links every draft may use

- README and quick start:
  `https://github.com/leonardsellem/hypermnesic#quick-start`
- Local-proof demo:
  `https://github.com/leonardsellem/hypermnesic/blob/main/docs/assets/readme-local-proof.svg`
- Architecture:
  `https://github.com/leonardsellem/hypermnesic/blob/main/ARCHITECTURE.md`
- Benchmarks and caveats:
  `https://github.com/leonardsellem/hypermnesic/blob/main/harness/BENCHMARKS.md`
- Product readiness checklist:
  `https://github.com/leonardsellem/hypermnesic/blob/main/docs/launch/first-class-product-readiness-checklist.md`
- MCP tools reference:
  `https://github.com/leonardsellem/hypermnesic/blob/main/docs/reference/mcp-tools.md`
- Obsidian companion:
  `https://github.com/leonardsellem/hypermnesic-companion`

## Claims allowed

- Hypermnesic is git-first memory for AI agents.
- Markdown files are the source of truth; the retrieval index is disposable and
  rebuildable.
- Memory writes go through reviewable Git commits.
- The project exposes MCP, CLI, and a read-only Obsidian companion.
- Benchmarks exist and are documented with caveats.
- Product readiness is tracked separately from benchmark quality.
- The companion is public and read-only.

## Claims to avoid

- Do not claim hosted SaaS, multi-tenant service, or managed cloud availability.
- Do not claim PyPI install until LS-1684 is decided and publication is complete.
- Do not claim official directory listing until LS-1683 submissions/listings land.
- Do not claim Discussions/community forum availability until LS-1686 is complete.
- Do not imply the Obsidian companion can write to a vault.
- Do not imply dense retrieval is always available; degraded lexical-only mode is a
  supported state and should be visible.
- Do not present benchmark results as proof of the full product experience.

## Canonical story

Hypermnesic is memory for agents where the files stay in your repo.

The invariant is deliberately boring: Markdown files are truth, the index is a
rebuildable projection, and every memory write is a Git commit you can review.
Agents get recall over your notes through MCP and CLI surfaces, while humans keep
plain files, diffs, history, and the option to rebuild the index from scratch.

The public v0.1.0 release focuses on making that loop inspectable: local-proof
demo, reference docs, product-readiness gates, benchmark notes, OAuth MCP work, and
a separate read-only Obsidian companion.

It is not a hosted memory service. It is a self-hosted, git-backed memory layer for
people who want agents to remember without turning the index into the source of
truth.

## Show HN draft

Suggested title:

```text
Show HN: Hypermnesic - git-first memory for AI agents
```

Draft:

```md
Hi HN,

I built Hypermnesic, a self-hosted memory layer for AI agents where Markdown files
remain the source of truth and the retrieval index is disposable.

The design constraint is that a reindex should never be able to lose a memory. Agent
writes are Git commits, so they are reviewable, revertible, and visible in normal
repo history. The index is just a projection over the files.

The v0.1.0 release includes:

- MCP server and CLI surfaces
- a local-proof demo for recall + dry-run write flow
- hybrid lexical/dense retrieval with visible degraded states
- guarded writes through commit_note
- product readiness docs and remote-client smoke evidence
- a separate read-only Obsidian companion
- benchmark notes with caveats

Repo: https://github.com/leonardsellem/hypermnesic
Quick start: https://github.com/leonardsellem/hypermnesic#quick-start
Architecture: https://github.com/leonardsellem/hypermnesic/blob/main/ARCHITECTURE.md
Benchmarks/caveats: https://github.com/leonardsellem/hypermnesic/blob/main/harness/BENCHMARKS.md

Honest limitations:

- It is self-hosted, not a managed service.
- PyPI install and directory listings are not live unless the linked docs say they are.
- Dense retrieval can degrade to lexical-only when embeddings are unavailable.
- The Obsidian companion is read-only by design.
- Benchmark quality and product readiness are tracked separately.

I am interested in feedback on the file-first invariant, the write guard model, and
whether this shape makes agent memory easier to trust/debug than hosted black-box
memory.
```

## r/selfhosted draft

```md
I released Hypermnesic v0.1.0, a self-hosted memory layer for AI agents.

The main idea: your Markdown files are the source of truth. The retrieval index can
be deleted and rebuilt. If an agent writes memory, it leaves a Git commit.

Links:

- Repo and quick start: https://github.com/leonardsellem/hypermnesic#quick-start
- Architecture: https://github.com/leonardsellem/hypermnesic/blob/main/ARCHITECTURE.md
- Product readiness checklist: https://github.com/leonardsellem/hypermnesic/blob/main/docs/launch/first-class-product-readiness-checklist.md

It exposes MCP and CLI surfaces, supports self-hosted OAuth MCP deployment, and has
a separate read-only Obsidian companion.

Limitations: this is not hosted SaaS; setup still assumes you are comfortable with a
repo, Python/uv, and self-hosting. Dense retrieval can degrade to lexical-only if
embeddings are unavailable, and the docs call that out instead of hiding it.
```

## r/ObsidianMD draft

```md
I released Hypermnesic Companion, a read-only Obsidian plugin that surfaces related
notes from a self-hosted Hypermnesic index while you write.

The companion does not write to your vault. It asks the Hypermnesic engine for
related notes/questions and displays them in Obsidian.

Companion repo: https://github.com/leonardsellem/hypermnesic-companion
Engine repo and setup: https://github.com/leonardsellem/hypermnesic#quick-start

The engine is built around a file-first invariant: Markdown files are truth, the
retrieval index is disposable, and agent writes are reviewable Git commits.

Limitations: the companion requires a running Hypermnesic engine/MCP endpoint, and
semantic retrieval can visibly degrade to lexical-only if the embedding channel is
unavailable.
```

## r/LocalLLaMA draft

```md
Hypermnesic is a self-hosted memory layer for AI agents where the source of truth is
plain Markdown in your own Git repo.

Why it may be interesting here:

- the index is disposable and rebuildable from files
- agent writes are Git commits, not hidden database mutations
- recall is exposed through MCP/CLI surfaces
- degraded lexical-only mode is explicit when dense retrieval is unavailable
- benchmark results and caveats are documented separately from product-readiness
  gates

Repo: https://github.com/leonardsellem/hypermnesic
Benchmarks/caveats: https://github.com/leonardsellem/hypermnesic/blob/main/harness/BENCHMARKS.md

It is not a local model runtime. It is a memory substrate you can connect to MCP
clients and agent workflows when you want the memory layer to stay inspectable.
```

## X / Bluesky thread draft

```text
1/ Hypermnesic v0.1.0 is public.

It is git-first memory for AI agents: Markdown files are truth, the retrieval index
is disposable, and every memory write is a reviewable Git commit.

https://github.com/leonardsellem/hypermnesic

2/ The invariant: a reindex must never be able to lose a memory.

Files are the durable source of truth. The index can be rebuilt from the repo.

3/ Surfaces in v0.1.0:

- MCP server
- CLI
- local-proof demo
- guarded commit_note writes
- read-only Obsidian companion
- benchmark/readiness docs

4/ It is self-hosted, not hosted SaaS.

Dense retrieval can degrade to lexical-only. The Obsidian companion is read-only.
Benchmark quality and product readiness are tracked separately.

5/ Quick start and docs:

https://github.com/leonardsellem/hypermnesic#quick-start
```

## MCP community Discord draft

```md
I released Hypermnesic v0.1.0, a git-first memory MCP server for AI agents.

The memory source of truth is Markdown in a Git repo; the index is rebuildable, and
agent writes are reviewable commits. The release includes MCP/CLI surfaces,
guarded writes, a local-proof demo, and a separate read-only Obsidian companion.

Repo and quick start:
https://github.com/leonardsellem/hypermnesic#quick-start

MCP tools reference:
https://github.com/leonardsellem/hypermnesic/blob/main/docs/reference/mcp-tools.md

I would especially appreciate MCP client compatibility reports and feedback on the
write guard / OAuth flow.
```

## Review checklist before posting

- [ ] The target channel is still appropriate.
- [ ] The post links the README quick start or demo.
- [ ] Benchmark claims link `harness/BENCHMARKS.md`.
- [ ] Product-readiness claims link the readiness checklist.
- [ ] No PyPI or directory-listing claims are included unless those tasks are Done.
- [ ] No Discussions/community-forum claims are included unless LS-1686 is Done.
- [ ] No private hostnames, tokens, vault contents, or local absolute paths are included.
- [ ] Operator explicitly approves the final text and channel.
