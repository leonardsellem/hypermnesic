---
title: "Launch narrative drafts"
status: drafted
audience: operator
linear: LS-1689
last_checked: 2026-06-19
---

# Launch narrative drafts

This is the PR-20 / LS-1689 draft artifact. It gives one source-backed launch
story and channel-specific post drafts.

Do not post any text from this document to Hacker News, Reddit, X, Bluesky,
Discord, or any other external channel without operator approval.

**Refreshed 2026-06-19** — the framing now leads with the authentic angle (built
for the author's own workflow; deliberately opinionated; lightweight setup; portable
memory you own), and two proof points are strengthened. PyPI `0.1.0` is published,
so every engine draft opens on the one-command `uv tool install hypermnesic`; and the
server is listed on Glama with a passing automated build check and an **A**
tool-definition-quality grade, cited as a third-party signal. The
official-MCP-registry and awesome-list "listed" claims remain off-limits until they
land.

## Narrative spine (keep this voice in every channel)

- It is a personal tool first: I built it for my own workflow, not as a platform.
- It is deliberately opinionated — it does one thing (portable, file-first agent
  memory) and does not try to be everything.
- Setup is lightweight: one command to install, one to prove recall locally.
- The point is portability: the memory is plain Markdown in your own Git repo, so it
  is yours to move, diff, and rebuild — no vendor database, no lock-in.

## Evidence links every draft may use

- README and quick start:
  `https://github.com/leonardsellem/hypermnesic#quick-start`
- PyPI package (v0.1.0 published):
  `https://pypi.org/project/hypermnesic/`
- Glama listing (passing build check, Tool Definition Quality A):
  `https://glama.ai/mcp/servers/ak6x81u3rr`
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
- Built for the author's own workflow; it is deliberately opinionated, not a
  general-purpose platform.
- Lightweight setup: a one-command `uv tool install hypermnesic` plus a local-proof
  demo.
- Memory is portable and owned: plain Markdown in your own Git repo, movable and
  rebuildable, with no vendor lock-in.
- Markdown files are the source of truth; the retrieval index is disposable and
  rebuildable.
- Memory writes go through reviewable Git commits.
- The project exposes MCP, CLI, and a read-only Obsidian companion.
- Installable from PyPI today: `uv tool install hypermnesic` (v0.1.0 published).
- Listed on Glama with a passing automated build check and an A grade for
  tool-definition quality (a third-party directory, not the official MCP registry).
- Benchmarks exist and are documented with caveats.
- Product readiness is tracked separately from benchmark quality.
- The companion is public and read-only.

## Claims to avoid

- Do not claim hosted SaaS, multi-tenant service, or managed cloud availability.
- Do not claim the official MCP registry listing or an awesome-list listing as live
  yet: the registry submission is not filed and the awesome-mcp-servers PR is still
  open (not merged). Citing the live Glama listing is fine; calling it an "official
  registry" listing is not.
- Do not claim Discussions/community forum availability until LS-1686 is complete.
- Do not imply the Obsidian companion can write to a vault.
- Do not imply dense retrieval is always available; degraded lexical-only mode is a
  supported state and should be visible.
- Do not present benchmark results as proof of the full product experience.

## Canonical story

Hypermnesic is portable memory for agents: the files stay in your repo, so the memory
is yours to move, diff, and rebuild.

I built it for my own workflow. I wanted my agents' memory to be something I own and
can take anywhere — plain files, not rows in a vendor's database I can't see or
export. So it is deliberately opinionated and lightweight rather than a do-everything
platform. The invariant is boring on purpose: Markdown files are truth, the index is
a rebuildable projection, and every memory write is a Git commit you can review.
Setup is one command; agents get recall over MCP and CLI surfaces, while humans keep
plain files, diffs, history, and the option to rebuild the index from scratch.

The public v0.1.0 release focuses on making that loop inspectable: a one-command PyPI
install, a local-proof demo, reference docs, product-readiness gates, benchmark
notes, OAuth MCP work, and a separate read-only Obsidian companion.

It is not a hosted memory service and does not try to be everything. It is a
self-hosted, git-backed memory layer for people who want agents to remember with
memory that stays portable and theirs.

## Show HN draft

Suggested title:

```text
Show HN: Hypermnesic - git-first, portable memory for AI agents
```

Draft:

```md
Hi HN,

I built Hypermnesic for my own workflow: I wanted my AI agents' memory to be portable
and mine - plain files I can move, diff, and rebuild - instead of rows in a vendor's
database I can't see or export. So it is deliberately opinionated and lightweight.
Markdown files stay the source of truth and the retrieval index is disposable.

Try it in two commands - no account, no service:

    uv tool install hypermnesic
    hypermnesic local-proof --demo-dir /tmp/hypermnesic-demo

That builds a tiny Markdown git repo, projects it into the disposable index, recalls
the source note, and previews the exact commit_note write diff without writing it.

The design constraint is that a reindex should never be able to lose a memory. Agent
writes are Git commits, so they are reviewable, revertible, and visible in normal
repo history. The index is just a projection over the files.

The v0.1.0 release includes:

- MCP server (OAuth) and CLI surfaces; read tools (search, read_note, build_context,
  resolve, think, list_folders) plus a guarded commit_note write
- a local-proof demo for recall + dry-run write flow
- hybrid lexical/dense retrieval with visible degraded states
- a separate read-only Obsidian companion
- benchmark notes with caveats

It's also listed on Glama with a passing automated build check and an A grade for
tool-definition quality: https://glama.ai/mcp/servers/ak6x81u3rr

Repo: https://github.com/leonardsellem/hypermnesic
Quick start: https://github.com/leonardsellem/hypermnesic#quick-start
Architecture: https://github.com/leonardsellem/hypermnesic/blob/main/ARCHITECTURE.md
Benchmarks/caveats: https://github.com/leonardsellem/hypermnesic/blob/main/harness/BENCHMARKS.md

This is a personal, opinionated tool, with honest limitations:

- It is self-hosted, not a managed service, and it doesn't try to be everything.
- Directory listings (official MCP registry / awesome lists) are not live yet.
- Dense retrieval can degrade to lexical-only when embeddings are unavailable.
- The Obsidian companion is read-only by design.
- Benchmark quality and product readiness are tracked separately.

I am interested in feedback on the file-first invariant, the write guard model, and
whether this shape makes agent memory easier to trust/debug than hosted black-box
memory.
```

## r/selfhosted draft

```md
I released Hypermnesic v0.1.0, a self-hosted memory layer for AI agents. I built it
for my own setup because I wanted agent memory I actually own and can move - plain
files, not a vendor database I can't export. It is deliberately opinionated and
lightweight.

The main idea: your Markdown files are the source of truth. The retrieval index can
be deleted and rebuilt. If an agent writes memory, it leaves a Git commit.

Install and prove it locally in two commands:

    uv tool install hypermnesic
    hypermnesic local-proof /path/to/your/vault

Links:

- Repo and quick start: https://github.com/leonardsellem/hypermnesic#quick-start
- Architecture: https://github.com/leonardsellem/hypermnesic/blob/main/ARCHITECTURE.md
- Product readiness checklist: https://github.com/leonardsellem/hypermnesic/blob/main/docs/launch/first-class-product-readiness-checklist.md

It exposes MCP and CLI surfaces, supports self-hosted OAuth MCP deployment, and has
a separate read-only Obsidian companion. It is also listed on Glama with a passing
build check and an A tool-definition-quality grade:
https://glama.ai/mcp/servers/ak6x81u3rr

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

I built the engine for my own workflow: portable, file-first agent memory you own.
It installs in one command (`uv tool install hypermnesic`) and keeps Markdown files
as the source of truth, with a disposable index and reviewable Git-commit writes.

Limitations: the companion requires a running Hypermnesic engine/MCP endpoint, and
semantic retrieval can visibly degrade to lexical-only if the embedding channel is
unavailable.
```

## r/LocalLLaMA draft

```md
Hypermnesic is a self-hosted memory layer for AI agents where the source of truth is
plain Markdown in your own Git repo. I built it for my own workflow - opinionated and
lightweight, with memory that stays portable and yours.

Install: `uv tool install hypermnesic` (then `hypermnesic local-proof --demo-dir
/tmp/hypermnesic-demo` to see recall plus a dry-run write on a throwaway vault).

Why it may be interesting here:

- the index is disposable and rebuildable from files
- agent writes are Git commits, not hidden database mutations
- recall is exposed through MCP/CLI surfaces
- degraded lexical-only mode is explicit when dense retrieval is unavailable
- benchmark results and caveats are documented separately from product-readiness
  gates

Repo: https://github.com/leonardsellem/hypermnesic
Benchmarks/caveats: https://github.com/leonardsellem/hypermnesic/blob/main/harness/BENCHMARKS.md
Glama listing (passing build, Tool Definition Quality A): https://glama.ai/mcp/servers/ak6x81u3rr

It is not a local model runtime. It is a memory substrate you can connect to MCP
clients and agent workflows when you want the memory layer to stay inspectable.
```

## X / Bluesky thread draft

```text
1/ Hypermnesic v0.1.0 is public.

I built it for my own workflow: portable, git-first memory for AI agents. Markdown
files are truth, the index is disposable, every write is a reviewable Git commit.
Opinionated and lightweight by design.

  uv tool install hypermnesic

https://github.com/leonardsellem/hypermnesic

2/ The invariant: a reindex must never be able to lose a memory.

Files are the durable source of truth. The index can be rebuilt from the repo, so the
memory stays yours to move and diff.

3/ Surfaces in v0.1.0:

- MCP server (OAuth)
- CLI
- local-proof demo
- guarded commit_note writes
- read-only Obsidian companion
- benchmark/readiness docs

4/ It is self-hosted, not hosted SaaS, and it doesn't try to be everything.

Dense retrieval can degrade to lexical-only. The Obsidian companion is read-only.
Benchmark quality and product readiness are tracked separately.

5/ Listed on Glama with a passing build check and an A tool-definition-quality grade:
https://glama.ai/mcp/servers/ak6x81u3rr

Quick start and docs:
https://github.com/leonardsellem/hypermnesic#quick-start
```

## MCP community Discord draft

```md
I released Hypermnesic v0.1.0, a git-first memory MCP server for AI agents. I built it
for my own workflow - opinionated and lightweight, with portable memory you own.

The memory source of truth is Markdown in a Git repo; the index is rebuildable, and
agent writes are reviewable commits. The release includes MCP (OAuth) / CLI surfaces,
guarded writes, a local-proof demo, and a separate read-only Obsidian companion.

Install: uv tool install hypermnesic

Repo and quick start:
https://github.com/leonardsellem/hypermnesic#quick-start

MCP tools reference:
https://github.com/leonardsellem/hypermnesic/blob/main/docs/reference/mcp-tools.md

It is listed on Glama with a passing automated build check and an A
tool-definition-quality grade: https://glama.ai/mcp/servers/ak6x81u3rr

I would especially appreciate MCP client compatibility reports and feedback on the
write guard / OAuth flow.
```

## Review checklist before posting

- [ ] The target channel is still appropriate.
- [ ] The post keeps the personal / opinionated / lightweight / portable voice.
- [ ] The post links the README quick start or demo.
- [ ] The post leads with the PyPI install (`uv tool install hypermnesic`).
- [ ] Benchmark claims link `harness/BENCHMARKS.md`.
- [ ] Product-readiness claims link the readiness checklist.
- [ ] The Glama claim is stated as a third-party listing (passing build + Tool
      Definition Quality A), not as the official MCP registry.
- [ ] No official-MCP-registry or awesome-list "listed" claim is included until those
      submissions/listings land.
- [ ] No Discussions/community-forum claims are included unless LS-1686 is Done.
- [ ] No private hostnames, tokens, vault contents, or local absolute paths are included.
- [ ] Operator explicitly approves the final text and channel.
