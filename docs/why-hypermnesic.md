# Why hypermnesic

Most "agent memory" products store your memories in *their* database. hypermnesic
doesn't. Your memory is **plain markdown in your own git repository**; the search index
is a disposable projection you can delete and rebuild at any time. That one architectural
choice is the wedge — everything below follows from it.

> Comparisons here are drawn on the **architectural axis** (where memory lives, how it's
> written, how clients reach it), not a feature-by-feature scorecard — adjacent tools
> evolve quickly. Verify current specifics against each project's own docs.

## The wedge, in four claims

1. **Files are the source of truth; the index is disposable.** Every memory is a
   committed markdown file. The hybrid search index (SQLite FTS5 + sqlite-vec KNN, fused
   with RRF) is a *rebuildable projection of the git tree* — a reindex never loses a
   committed write. There is no separate database of record to corrupt, migrate, or be
   locked into.
2. **Git-first writes.** The one write path (`commit_note`) writes a file and commits it
   to git *first*; the index follows. Every memory is therefore a reviewable diff with
   full history, guarded by a diff-or-die frontmatter gate, a protected-path/governance
   blocklist, and an append-only audit log. You can read, edit, `git revert`, or grep your
   memory with ordinary tools.
3. **One endpoint every client shares.** A single OAuth-secured MCP endpoint serves
   ChatGPT, Claude, the Claude Code / Codex plugin, and an Obsidian companion — the same
   memory, the same way, browser-login once. Not a per-app silo.
4. **Self-hosted and portable.** You run it over your own vault on your own machine
   (Tailscale Funnel for HTTPS; no reverse proxy). No vendor memory cloud; no per-seat
   memory database.

And it's **measured**: see [`harness/BENCHMARKS.md`](../harness/BENCHMARKS.md) for
LongMemEval V1 results with an honest comparability envelope (no judge-axis cherry-picking).

## Versus adjacent tools

### vs. mem0

mem0 is a memory layer whose memories live in its own vector (and optional graph) store,
fronted by an API/SDK (hosted or self-hosted). hypermnesic keeps memories as **markdown
in your git repo** instead of a managed memory store — so the system of record is files
you already own and can diff, edit, and version, and the index is throwaway. If you want
a memory *API backed by a vector DB*, mem0 fits; if you want **your files to be the
memory**, hypermnesic does.

### vs. Letta (formerly MemGPT)

Letta is an agent *framework/runtime* — stateful agents with self-editing memory, served
from its own server + database. hypermnesic is **not** a framework: it's just the memory
layer, exposed over MCP, that *any* client or framework can share. Reach for Letta to
build stateful agents end-to-end; reach for hypermnesic when you want durable, portable,
file-backed memory that isn't tied to one agent runtime.

### vs. basic-memory

basic-memory is the closest in spirit — it also stores knowledge as local markdown over
MCP. hypermnesic's distinct bets are: **hybrid dense + lexical retrieval** (sqlite-vec KNN
fused with FTS5 via RRF, graceful lexical-only degradation) with **read-time convergence**
so a just-written note is recall-able without a manual reindex; a **gated git-first write
path** (frontmatter gate + blocklist guard + audit log) rather than plain file writes; and
**one shared OAuth endpoint** for remote clients (not only local stdio), with retrieval
quality reported against a public benchmark. If you want the simplest local markdown MCP,
basic-memory is excellent; hypermnesic trades a bit more setup for hybrid retrieval, a
guarded write path, and a multi-client remote endpoint.

### vs. plain Obsidian (+ search / local plugins)

Obsidian already treats your markdown files as truth — that's the shared foundation, and
hypermnesic ships a read-only **Obsidian companion**. But Obsidian's search is local and
lexical; it is not an agent-facing memory layer. hypermnesic adds **dense + lexical hybrid
retrieval, entity resolution, a git-first write API, and an MCP endpoint** on top of the
*same* files — so your agents get high-quality recall over the vault you already keep in
Obsidian, without exporting anything into a separate store.

## When hypermnesic is *not* the right fit

- You want a turnkey hosted memory API and don't want to self-host → a managed service
  (mem0 cloud, etc.) is less setup.
- You want an end-to-end agent framework with built-in tools and orchestration → Letta or
  a full agent framework fits better.
- Your memory isn't text/markdown-shaped, or you need a transactional database of record
  → the files-are-truth model is the wrong tool.

hypermnesic is for the case where you want **agent memory you own, in plain files, in your
own git history, reachable by every client over one endpoint.**
