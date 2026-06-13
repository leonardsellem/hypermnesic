# Hypermnesic Incremental Doc-Surface Invalidation Brainstorm

## Problem

Hypermnesic's `converge` path keeps chunk-level dense vectors fresh for changed Markdown files, but existing document-level "doc surface" vectors can remain stale after edits. This makes ordinary incremental convergence an incomplete freshness mechanism for the doc-level retrieval lane and pushes operators toward full reindex/re-embed as the only way to force doc-surface freshness.

That is too expensive and product-wise wrong: a single edited file should not require re-embedding the entire vault to keep document-level retrieval current.

## Evidence From Current Implementation

Source inspected in `/path/to/.hermes/plugins/hypermnesic` on `main` with a clean worktree.

Relevant current behavior:

- `Index.upsert_lexical(path, chunks)` replaces changed-path lexical rows and chunk vectors:
  - deletes `chunks`
  - deletes `fts_chunks`
  - deletes `vec_chunks`
  - inserts fresh `chunks` and `fts_chunks`
- `upsert_lexical` does **not** delete or mark stale the path's existing doc-level vector in `docs` / `vec_docs`.
- `Index.remove_path(path)` does delete doc-lane rows, but it only runs for deleted paths.
- `embed_stale_locked(...)` fills:
  - `stale_chunk_ids()` for chunk vectors
  - `paths_missing_doc_vector()` for doc-surface vectors
- `paths_missing_doc_vector()` only detects paths with no `docs` row or no `vec_docs` row. It does not detect an existing-but-stale doc vector after a file edit.

Observed consequence during homelab docs update:

- Several Markdown documents were changed and converged.
- `converge` reported `replayed: 7`, `chunks_embedded: 128`, `docs_embedded: 1`.
- Edited homelab docs had chunk rows and existing doc rows, so their doc-surface vectors were not counted/refreshed by the missing-doc path.

## Users / Jobs To Be Done

### Primary user: operator / brain maintainer

- When project docs change and `hypermnesic converge <repo> --json` succeeds, the operator expects retrieval over both chunk and document lanes to reflect the new committed content.
- The operator should not need to decide between stale doc-level retrieval and an expensive full reindex.

### Primary runtime: Hermes / scheduled agents

- After a brain repo commit, scheduled jobs and task agents should be able to run cheap convergence and trust the index freshness.
- Agentic workflows should keep using `converge`; they should not routinely run `reindex`.

### Secondary runtime: MCP/remote retrieval

- Read-only MCP or remote clients should serve current committed state after convergence, without requiring downtime or whole-vault rebuilds.

## Requirements

### R1 — Changed-path doc-surface invalidation by default

When a committed Markdown path is replayed through incremental convergence, hypermnesic must invalidate that path's existing doc-surface vector so the next dense-fill pass re-embeds the doc surface.

Minimal acceptable implementation:

- Add an `Index.invalidate_doc_vector(path: str)` helper, or inline equivalent.
- When `upsert_lexical(path, chunks)` is called for a changed path, delete the associated `vec_docs` row for that path while preserving the `docs` row.
- After invalidation, `paths_missing_doc_vector()` must include that path until `embed_stale_locked(...)` re-embeds it.

Preferred implementation:

- Store a `surface_hash` or equivalent freshness marker and detect stale doc vectors via hash/model mismatch instead of only deleting rows.
- This is more robust, but not required for the first fix if row-deletion invalidation is shipped and tested.

### R2 — Incremental convergence remains cheap

For N changed Markdown files, convergence should re-embed only:

- stale/new chunks for changed paths, bounded by the existing chunk budget behavior;
- missing/stale doc surfaces for changed paths, bounded by the existing doc-surface budget behavior.

It must not re-embed the whole vault unless the user explicitly runs `reindex`.

### R3 — Preserve lexical-first / degraded-mode behavior

If the embedder is unavailable or fails:

- lexical/graph replay must still complete;
- checkpoint advancement behavior should remain consistent with today's degraded convergence semantics;
- no zero vectors or fake doc vectors should be written;
- the doc-surface vector should remain missing/stale so a later convergence with an available embedder can fill it.

### R4 — Preserve deletion semantics

Deleted Markdown paths must still remove:

- chunks;
- FTS rows;
- chunk vectors;
- doc rows;
- doc vectors.

`remove_path(path)` behavior should remain correct and covered.

### R5 — Preserve move/rekey semantics unless explicitly changed

Existing `rekey_path(old, new)` is documented as preserving embeddings for a pure path move. The new invalidation behavior should not accidentally force re-embedding for path-only renames unless content actually changes or a separate design decision changes move semantics.

### R6 — Metrics should distinguish replay from embedding freshness

The `converge --json` output should remain understandable:

- `replayed` = changed Markdown paths replayed into lexical/graph index.
- `chunks_embedded` = chunk vectors written this pass.
- `docs_embedded` = doc-surface vectors written this pass.

If possible, add a metric for doc surfaces made stale/invalidated, e.g. `docs_invalidated`, but this is optional for the first fix.

### R7 — Budget behavior must remain bounded and resumable

The existing `budget` behavior should still bound work:

- no unbounded dense fill during read-time convergence;
- if there are more stale doc surfaces than budget allows, subsequent converge/embed passes should drain the remainder;
- repeated converge calls should be idempotent once all stale chunks/doc surfaces are filled.

### R8 — Backward compatibility

Existing indexes should not require a manual migration for the minimal fix. Deleting `vec_docs` rows for changed paths during future replay is enough.

If implementing hash-based freshness:

- add a safe schema migration path;
- do not require full reindex to start operating correctly;
- existing rows without hash should be treated as stale or lazily upgraded in a bounded way.

## Non-Goals

- Do not make full reindex part of normal convergence.
- Do not re-embed all doc surfaces on every converge.
- Do not change the default retrieval ranking model unless tests reveal ranking regressions caused by freshness changes.
- Do not remove the doc-level lane; the problem is freshness, not the existence of doc-surface retrieval.
- Do not couple doc-surface invalidation to wall-clock mtimes; Git commit content/checkpoint state should remain the source of truth.
- Do not broaden this into a general schema redesign unless needed for the minimal freshness fix.

## Edge Cases

### E1 — Edited file with existing doc vector

A file already in `docs`/`vec_docs` is edited and committed.

Expected:

- `converge` replays the path;
- `vec_docs` for that path is removed or marked stale;
- `paths_missing_doc_vector()` includes the path before embedding;
- `embed_stale_locked` re-embeds the doc surface;
- `docs_embedded` increments for that path when budget allows.

### E2 — New file with no doc vector

A new file is committed.

Expected:

- current missing-doc behavior still works;
- the new path gets a doc-surface vector during dense fill.

### E3 — Deleted file

A file is deleted and committed.

Expected:

- no stale doc row or vector remains.

### E4 — Empty / no-surface file

A changed file produces no meaningful `doc_surface`.

Expected:

- no fake doc vector is written;
- behavior is explicit and idempotent;
- avoid retrying forever if the file is intentionally surface-less, or document why retrying is acceptable.

### E5 — Embedder down during convergence

A changed file invalidates its doc vector, but dense embedding fails.

Expected:

- lexical/graph are current;
- the stale/missing doc vector remains to be filled later;
- `degraded: true` is reported;
- no misleading successful doc freshness metric is emitted.

### E6 — Budget smaller than changed-doc count

Three changed files need doc-surface refresh and budget allows only one.

Expected:

- one doc surface is embedded;
- remaining changed paths stay missing/stale;
- later convergence drains them without re-embedding the already refreshed one.

### E7 — Rename without content change

A path is renamed but content is unchanged.

Expected:

- current `rekey_path` move semantics should preserve embeddings, unless the implementation cannot distinguish rename-only from edit+rename; if not distinguishable, document the conservative behavior.

### E8 — Existing legacy index rows

An old index has doc vectors but no freshness hash.

Expected:

- minimal row-deletion invalidation works on future edited paths;
- hash-based implementation handles missing hash safely.

## Acceptance Criteria

### AC1 — Unit: `upsert_lexical` invalidates existing doc vector

Given an indexed file with a `vec_docs` row, when `idx.upsert_lexical(path, new_chunks)` runs, then:

- chunk rows are replaced as today;
- old chunk vectors are removed as today;
- the file's `vec_docs` row is removed or marked stale;
- `idx.paths_missing_doc_vector()` returns the path.

### AC2 — Unit: `embed_stale` refreshes changed doc surface only

Given an indexed corpus with files `a.md` and `b.md`, when only `a.md` is replayed via `upsert_lexical` and `embed_stale` runs, then:

- `docs_embedded == 1`;
- `a.md` is no longer missing/stale;
- `b.md` is not re-embedded.

Use the fake embedder call counts or vector counts to prove only the changed doc-surface was embedded.

### AC3 — Integration: `converge` on edited file refreshes doc lane

Given a Git repo indexed at commit 1, when `a.md` is edited and committed, then `converge(repo, idx, fake_embedder, debounce_seconds=0)`:

- returns `status == "converged"`;
- returns `replayed == 1`;
- returns `docs_embedded == 1` when budget allows;
- leaves the checkpoint at HEAD;
- makes retrieval over the doc lane use the updated doc surface.

### AC4 — Integration: degraded embedder leaves doc surface stale but lexical current

Given an edited file and a failing embedder, `converge` should:

- return `degraded: true`;
- keep lexical search current;
- leave the path in `paths_missing_doc_vector()` or equivalent stale-doc set;
- avoid writing zero/fake vectors.

### AC5 — Budget resumability

Given three edited files and a doc budget of one, repeated convergence/embed passes should eventually embed all three doc surfaces with no whole-vault re-embedding and no duplicate embedding once complete.

### AC6 — Existing tests remain green

Focused test suite must pass, at minimum:

```bash
python -m pytest tests/test_embed_stale.py tests/test_converge.py tests/test_index.py -q -o 'addopts='
```

If the CLI surface changes metrics or output, also run:

```bash
python -m pytest tests/test_cli.py -q -o 'addopts='
```

### AC7 — Real smoke on `gbrain-brain`

On a non-destructive temp repo or disposable copy of a small fixture, prove:

1. initial index embeds both chunks and doc surfaces;
2. edit one Markdown file;
3. run `hypermnesic converge <repo> --json`;
4. observe `docs_embedded` includes the changed doc surface without full reindex.

Do not use the production `gbrain-brain` index as the only verification surface.

## Open Questions

1. Should minimal invalidation delete `vec_docs` only, or also delete the `docs` row?
   - Recommendation: delete `vec_docs` only. Preserve `docs` identity and let `add_docs` upsert the new vector.
2. Should `docs_embedded` be complemented with `docs_invalidated`?
   - Recommendation: optional, but useful for operator observability.
3. Should doc-surface freshness be modeled by row deletion or `surface_hash`?
   - Recommendation: ship row-deletion invalidation first; consider hash-based freshness as a follow-up if stale detection needs to survive manual DB mutations or schema evolution.
4. How should surface-less docs be represented?
   - Recommendation: either accept repeated no-op attempts for rare surface-less paths or add a lightweight `docs(surface_empty=true)` marker later.
5. Should `replay_changes(..., embedder=...)` directly embed doc surfaces when an embedder is supplied?
   - Recommendation: no for the first fix; preserve the current separation where replay updates lexical/graph and `embed_stale_locked` performs bounded dense fill.

## Recommended Next Step

Run `/ce-plan` to turn this into an implementation plan against `/path/to/.hermes/plugins/hypermnesic`, with a TDD sequence:

1. Add failing tests for existing-doc edit invalidation.
2. Implement minimal `vec_docs` invalidation on changed-path lexical upsert.
3. Verify bounded doc-surface refresh through `embed_stale_locked` and `converge`.
4. Run focused tests.
5. Optionally add a follow-up issue/plan for hash-based doc-surface freshness metadata.
