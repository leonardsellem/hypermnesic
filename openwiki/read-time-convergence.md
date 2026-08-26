---
type: Reference
title: Read-Time Convergence
description: The correctness step every read runs first — delta-replay to HEAD, bounded dense catch-up, the debounce, the non-blocking lock, and the advisory manual-reindex signal.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-9b37eab1bcb7a0dabc8255c1
    resource: repo://src/hypermnesic/cli.py
  - id: openwiki-source-c76fa3ae1f9c3796f441ee08
    resource: repo://src/hypermnesic/converge.py
  - id: openwiki-source-eca76e73bbc2749831def863
    resource: repo://src/hypermnesic/embed.py
  - id: openwiki-source-d0c2638cdea3e85ab949dd06
    resource: repo://src/hypermnesic/index.py
  - id: openwiki-source-54a007908deccb21b5ddc567
    resource: repo://src/hypermnesic/install.py
  - id: openwiki-source-37433895d4b7b6af7cd92f4f
    resource: repo://src/hypermnesic/mcp_server.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-1cdf1c709d5be9d61313c7ca
    resource: repo://tests/test_converge.py
  - id: openwiki-source-62cb10f2760b68602ddbd7a7
    resource: repo://tests/test_embed_stale.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Read-Time Convergence

Convergence is the single step that makes the prime invariant survivable in practice. If the
index is a disposable projection of the committed tree, something must keep it close enough to
`HEAD` that reads are trustworthy — **without** turning the index into a database of record or
requiring anyone to run a rebuild by hand.

That something is `converge()`, and **every read path calls it first**: every MCP read tool and
every read subcommand on the CLI. It is one shared step, not a per-caller reimplementation.

The property it buys is concrete: **a note committed a moment ago is recall-able on the next
read**, with no manual reindex, on any host serving that vault.

## What one pass does

1. **Debounce check.** If a convergence happened recently, return immediately — before any lock
   is taken. The timestamp lives in the index state directory.
2. **Take the single-indexer lock, non-blocking.** If someone else holds it, return and serve
   the current state. A writer or another converger is already advancing the index; a read must
   never stall waiting for that.
3. **Optional authoring-host overlay.** On an authoring host, uncommitted and untracked
   markdown is re-applied so in-progress notes are findable before they are committed.
4. **Size the delta** between the index checkpoint and `HEAD`.
5. **Replay the delta — lexically only.** Deletions remove their rows; added and modified files
   are read *from the commit* and re-chunked. The checkpoint advances to `HEAD`.
6. **Close a bounded slice of the dense lag**, embedding at most the configured budget of stale
   chunks and doc surfaces.
7. **Write the debounce stamp** and return a structured result.

Convergence writes **only** the index state directory. It never touches the repository.

## The four outcomes

The result's `status` is a discriminator, and each value means something operationally
different:

| Status | What happened |
|---|---|
| `converged` | A pass ran. Possibly a no-op, if the index was already current. |
| `debounced` | Skipped — a pass ran recently. |
| `lock_busy` | Skipped — another writer or converger holds the lock. |
| `oversized_delta` | The replay was skipped; a manual reindex is **recommended**. |

Alongside it the result reports how many paths were replayed, how many chunks and doc surfaces
were embedded, whether the pass was degraded and why, the overlay paths applied, the `HEAD` it
saw, and whether the checkpoint actually advanced.

## Convergence is never a full reindex

This is a hard rule, and it is scar tissue: convergence is delta-replay plus a bounded embed,
and it never invokes the isolated rebuild path. **Full reindex stays a manual, explicit
operation.** A read path that could trigger an unbounded rebuild is a read path that can
exhaust memory on a large vault, at a moment nobody chose.

## Signalling a manual reindex is not performing one

When the delta exceeds the configured file cap — after a large merge, say — convergence does
**not** replay it inline. It serves the current, consistent projection and sets
`manual_reindex_recommended`.

The reasoning is worth internalizing, because "just replay part of it" is the obvious wrong
answer: a *partial* replay could not advance the checkpoint to `HEAD`. The next read would
compute the same oversized delta and redo the same work, forever, with no progress. Better to
serve a consistent older projection and tell the operator plainly.

Every read tool surfaces `manual_reindex_recommended` in its result. It is a **signal**, not an
action: nothing rebuilds itself, and the caller decides. See
[MCP Tool Surface](mcp-tool-surface.md).

## Graceful dense degradation

Convergence **never raises on the read path.** With no embedder configured, or an embedder that
fails — provider down, dimension mismatch, rate limited — the lexical and graph catch-up still
completes and the checkpoint still advances; only the dense fill is skipped, and the result is
flagged degraded with a named reason.

Two details keep this from becoming quiet corruption:

- The checkpoint advances on the **lexical** replay, which is exactly why a dense failure
  afterwards is a degradation rather than a rollback.
- A partially embedded batch leaves **real vectors**, never zero placeholders. A zero-filled
  vector is worse than a missing one: it silently ranks.

## The authoring-host overlay

On an authoring host, uncommitted and untracked markdown is indexed so a note being written is
findable before it is committed. Two constraints keep this from leaking:

- The overlay is **lexical only**, and its paths are excluded from the dense fill, so
  uncommitted text never enters the vector table.
- It **does not advance the checkpoint**. A replica projecting the same committed SHA sees none
  of it, which preserves the rule that the index is a projection of *committed* state.

The overlay is best-effort: if git is unavailable or the call fails, convergence continues
without it rather than failing the read.

## Reading from the commit, not the working tree

Delta replay reads each changed file's content **from the commit object**, not from disk. That
is what makes the projection a projection of `HEAD` rather than of whatever happens to be in
the working tree.

If that read fails — a missing, pruned, or corrupt object — the path's existing index rows are
**left intact** rather than being overwritten with empty content. A transient git failure
degrades to staleness, not to a blanked note.

## The tunables and how they fail

See [Configuration and Tunables](configuration-and-tunables.md) for defaults.

| Tunable | Set too low | Set too high |
|---|---|---|
| **Embed budget** | Dense coverage lags lexical for longer; reads stay fast but semantic recall is thin until it catches up. | The read that pays absorbs several embedding round-trips, so first-read latency and cost climb. |
| **Debounce** | Every read in a burst pays full convergence cost. | A just-committed note stays invisible for longer — mitigated because callers can force a non-debounced pass explicitly. |
| **Max delta files** | Ordinary merges trip the oversized-delta guard and operators are nagged for manual reindexes they do not need. | A single read may absorb a very large inline replay, making read latency unpredictable exactly when the repository just changed a lot. |

Every tunable is injectable per call, which is how tests make each path deterministic — for
example by setting the debounce to zero.

## Where convergence is triggered

- **Every MCP read tool**, before answering.
- **Every read CLI subcommand**, with `--now` available to force a non-debounced pass — the
  flag you need to recall something you committed inside the debounce window.
- **The `converge` subcommand**, as a manual pre-warm.
- **The post-merge git hook**, so a pull warms the index instead of leaving the cost to the
  next reader. See [Provisioning and Diagnostics](provisioning-and-diagnostics.md).
