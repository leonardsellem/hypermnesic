---
type: Reference
title: Retrieval and Indexing
description: How a query becomes ranked hits — markdown chunking, the FTS5 and sqlite-vec channels, the doc lane, RRF fusion, dedup and recency, the wikilink graph, and the exact degradation contract.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-03ee9a9e716fb46eb5e59693
    resource: repo://docs/reference/mcp-tools.md
  - id: openwiki-source-1a863cad5946181fc4252610
    resource: repo://harness/longmemeval/adapter.py
  - id: openwiki-source-41f901f9f19f630d69b443e1
    resource: repo://harness/parity_harness.py
  - id: openwiki-source-5f17d71d8e2d83b9ea0bc2ae
    resource: repo://src/hypermnesic/config.py
  - id: openwiki-source-eca76e73bbc2749831def863
    resource: repo://src/hypermnesic/embed.py
  - id: openwiki-source-5974acb66f0bfa1a0ca1d95e
    resource: repo://src/hypermnesic/expand.py
  - id: openwiki-source-5bc4d4cc0e683518554afb42
    resource: repo://src/hypermnesic/graph.py
  - id: openwiki-source-d0c2638cdea3e85ab949dd06
    resource: repo://src/hypermnesic/index.py
  - id: openwiki-source-b176d8b6149dd2b6fdc03229
    resource: repo://src/hypermnesic/ingest.py
  - id: openwiki-source-f2d2daf9ca9b4a326a178c61
    resource: repo://src/hypermnesic/retrieve.py
  - id: openwiki-source-614eabcd0f8a5da6b1127eec
    resource: repo://src/hypermnesic/think.py
  - id: openwiki-source-9f96f06bbd9cdd32677cab48
    resource: repo://tests/test_graph.py
  - id: openwiki-source-01bd17e0ea705fb9b8a4a3f6
    resource: repo://tests/test_index_projection.py
  - id: openwiki-source-2eba846ab3cbfcc6150d04e3
    resource: repo://tests/test_index.py
  - id: openwiki-source-98479a6745d5864e8d9698dd
    resource: repo://tests/test_retrieve.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Retrieval and Indexing

This is the read half of the system: how committed markdown becomes a queryable projection,
and how a query becomes a ranked list.

## Ingestion and chunking

Markdown is walked in **sorted path order** so a rebuild is reproducible, skipping the git
directory, the engine's own state directory, and the usual editor and tooling directories.
Files are read defensively: non-UTF-8 bytes are replaced rather than raising, so one bad byte
in one note cannot fail an index build.

YAML frontmatter is **stripped before chunking**, and this has a consequence worth noting: the
graph never sees frontmatter at all, so frontmatter relations cannot become graph edges even
by accident.

Paragraphs are grouped into chunks with a hard character cap, tracking the nearest preceding
heading so each chunk carries the section it belongs to. The cap sits well under the embedding
model's token limit — a deliberate margin after a real failure where an oversized chunk was
rejected by the API mid-build. A block that exceeds the cap on its own is split, preferring
line boundaries and falling back to a hard slice for something with no usable whitespace, such
as a giant table row or an encoded blob.

## What the index holds, and why deleting it is safe

The index is a SQLite database in a per-repository state directory, created with restrictive
permissions. It contains:

| Table | Contents |
|---|---|
| `chunks` | Chunk rows: path, ordinal, heading, text. |
| `fts_chunks` | The FTS5 lexical projection, tokenized with diacritic folding. |
| `vec_chunks` | One vector per chunk, at the pinned dimension. |
| `docs` / `vec_docs` | One row and one vector per document — the doc-level lane. |
| `meta` | Key/value slots, including the commit-SHA checkpoint. |

**Every row here is derived from committed markdown.** Nothing exists in the index that is not
already in the git tree, which is what makes deletion cost only rebuild time. See
[Architecture Overview](architecture-overview.md).

The engine ignores its state directory through git's local exclude file, **never** by editing
the repository's tracked ignore file. The engine does not modify tracked files to make room for
itself.

The lexical projection can also **self-heal**: the FTS content is versioned, and an index built
under an older scheme is rebuilt from the already-indexed chunk rows on open. That repair is
cheap, deterministic, and needs no embeddings, so degraded lexical recall fixes itself without
an API key.

Dense search uses the sqlite-vec KNN `MATCH ... k = ?` query shape rather than a brute-force
distance ordering — a deliberate choice, since the brute-force form is orders of magnitude
slower at scale.

## Embeddings

The embedding model and dimension are pinned in one place, and the dimension parameter is sent
**explicitly** to the API rather than relying on a default. Embedding failures are never
swallowed and **never zero-filled** — a zero vector would silently participate in ranking,
which is worse than a missing one.

A startup smoke embed exists to answer a specific question: is the key actually *read by the
SDK*, not merely present in the environment? It fails fast and loudly on a missing or invalid
credential, and refuses to proceed on a short or empty vector. This is scar tissue from a long
silent failure.

Provider failures are **classified** rather than lumped together: a rate limit is distinguished
from another API error, which is distinguished from a generic embedding error. After a rate
limit, an in-process cooldown suppresses further attempts so reads keep serving lexical and
graph results instead of hammering a throttled provider. See
[Configuration and Tunables](configuration-and-tunables.md).

## The three retrieval lanes

**Lexical (FTS5).** The query is phrase-matched, which is precise for exact and proper-noun
queries and gracefully returns nothing for free-form natural-language questions — the dense
channel carries those. This is measured, not assumed: an OR-of-terms query floods the candidate
pool with weak common-term matches and *degrades* fused ranking. When the exact phrase misses,
there is one fallback: an explicit AND over the salient tokens with stopwords dropped, which is
what lets lexical-only degraded mode still recall hyphenated or non-contiguous identifiers.

**Dense (sqlite-vec KNN).** The query is embedded and matched against chunk vectors.

**Doc lane.** One embedding per document, built from its title, headings, and lead surface. A
doc-surface match lifts that document through its representative chunk. This exists because
"tell me about this document" style questions align with a document as a whole rather than with
any one chunk of it.

## Fusion

The three lanes are combined by **reciprocal rank fusion**: each lane contributes a
rank-derived score, and the per-lane weights default to equal. RRF is chosen because it is
parameter-light and scale-free — it needs no comparable raw scores across a BM25 lane and a
cosine-distance lane, which is exactly the problem you would otherwise have to hand-tune.

Fusion runs over a candidate pool larger than the requested result count, and that headroom is
what absorbs the filters applied afterwards.

**Optional multi-query expansion** generates alternative phrasings and fuses the **dense**
results of every variant. A document that answers the question from several angles accumulates
fusion mass and rises. Lexical deliberately runs on the original query only, because
phrase-matching paraphrases is noisy. Expansion is opt-in and graceful: any expander failure
falls back to no expansion rather than failing the search.

An **optional rerank** stage exists for harness comparability. It reorders only the top window
and preserves membership at the requested count, and it is off by default so no proprietary
reranker enters the product path.

## After fusion: dedup, exclusion, recency

**Near-duplicate collapse** (on by default) drops a hit whose chunk text is byte-identical to a
higher-ranked one, keeping the highest-ranked copy. Corpora routinely mirror the same document
at two paths, and without this those copies flood the list and crowd out distinct documents.

**Self-exclusion** drops hits at a caller-supplied path before truncation, which is how
thinking mode stops a note from matching itself. The larger candidate pool absorbs the drop, so
a self-match does not shrink the result below the requested count when other matches exist.

**Recency** attaches the epoch seconds of the most recent commit touching each hit's path —
git commit time being canonical, since the index is a projection of git. It has **no ranking
effect** here; consumers derive their own forgetting curve from it. Untracked paths get null.

The recency map is built by a **single** `git log` pass on first lookup, not one subprocess per
hit, which previously added a git fork per result to every search. A unit-separator sentinel
marks timestamp lines so a digit-only filename cannot be misread as a timestamp, and path
quoting is disabled so non-ASCII paths match.

One deliberate tolerance: if a fused candidate's chunk row has disappeared — a concurrent
projection update can briefly leave stale candidates visible to a reader — that candidate is
skipped rather than failing the search. The git tree is the source of truth; an orphaned index
row is not a reason to break recall.

## The degradation contract

A caller can observe exactly what happened:

- `degraded_lexical_only` is true when the dense channel did not contribute.
- `degraded_reason` is null when it did, and otherwise names the cause:
  `missing_embedder` (no embedder configured), `rate_limited`, `cooldown`, `api_error`, or
  `embedding_error`.
- `channels` on each hit records which lanes matched it — `lexical`, `dense`, `doc`, and
  `graph` for graph-derived results.

Naming the reason is what lets an operator distinguish "no key configured" from "provider is
throttling" from "the index is broken", and it is what lets a benchmark harness **void** a
silently degraded run rather than scoring it as a failure. See
[Benchmarks and Evaluation](benchmarks-and-evaluation.md).

## The wikilink graph

Graph edges are **body wikilinks only**. Frontmatter relation fields are deliberately not
edges — and because ingestion strips frontmatter before chunking, the graph never sees them.
A link target is normalized by dropping any display alias and any anchor.

The graph answers two things:

**Context expansion.** `build_context` walks **both** incoming and outgoing edges to a bounded
depth. It is cycle-safe through a visited set, excludes the start page itself, and returns a
sorted list so results are reproducible.

**Entity resolution.** A name resolves through exact path matching, a markdown-suffix match, or
an unambiguous stem. A name whose stem is shared by more than one page, or that matches
nothing, resolves to **null rather than a guess**. Resolution uses the *same* matcher the body
wikilink resolver uses, so resolving a name gives you exactly what writing that wikilink would
bind to — the two cannot disagree.

That null-over-guess rule is the important one: a wrong wikilink target silently connects two
unrelated notes, and both people and agents will believe it.
