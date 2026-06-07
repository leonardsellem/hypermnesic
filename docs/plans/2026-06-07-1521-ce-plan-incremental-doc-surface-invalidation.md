# Incremental Doc-Surface Invalidation Implementation Plan

> **For Hermes:** Use `ce-work` or `subagent-driven-development` to implement this plan task-by-task. Do not implement directly from the brainstorm; this plan is the scope of record for LS-1521.

**Goal:** Make `hypermnesic converge` keep document-level dense vectors fresh for changed Markdown files without full-vault reindex/re-embedding.

**Architecture:** Preserve the existing convergence split: replay changed files into lexical/graph state first, then perform a bounded dense fill. The minimal fix is to make changed-path lexical replay invalidate that path's existing doc-surface vector so the already-existing `paths_missing_doc_vector()` + `embed_stale_locked()` path refreshes only changed documents. Do not introduce a schema migration in the first implementation unless tests prove row-deletion invalidation is insufficient.

**Tech Stack:** Python 3.11+, SQLite/FTS5/sqlite-vec, `uv`, pytest, deterministic `FakeEmbedder`, Git-backed fixture repos.

---

## Source Requirements

- Linear: `LS-1521 — P1: Incrementally invalidate stale doc-surface vectors during hypermnesic converge`
- Brainstorm: `docs/brainstorms/2026-06-07-hypermnesic-incremental-doc-surface-invalidation.md`
- Branch for implementation: `ls-1521-p1-incrementally-invalidate-stale-doc-surface-vectors-during` or a similarly named branch off `origin/main`.

## Current State / Evidence

Observed implementation paths on `main`:

- `src/hypermnesic/index.py`
  - `Index.upsert_lexical(path, chunks)` deletes and recreates `chunks` / `fts_chunks` and deletes stale `vec_chunks` for the path, but does **not** touch the doc lane.
  - `Index.remove_path(path)` deletes both chunk-lane and doc-lane rows, but only for deleted paths.
  - `Index.paths_missing_doc_vector()` returns paths with no `docs` row or no `vec_docs` row; it cannot detect existing-but-stale `vec_docs` rows.
  - `embed_stale_locked(...)` re-embeds only missing doc vectors from `paths_missing_doc_vector()`.
- `src/hypermnesic/converge.py`
  - `converge(...)` calls `index_mod.replay_changes(..., embedder=None)` for lexical/graph catch-up.
  - It then calls `index_mod.embed_stale_locked(..., budget=budget)` for bounded dense fill.
  - If the embedder is missing or fails, lexical catch-up still advances and the result is degraded.
- `src/hypermnesic/ingest.py`
  - `doc_surface(raw, path)` is the deterministic document-level surface.
- Existing tests:
  - `tests/test_index.py` covers doc-lane table creation, doc dense search, stale chunk budgets, and basic `upsert_lexical` helper behavior.
  - `tests/test_embed_stale.py` covers backfilling doc vectors for commit-note-created pages and idempotence.
  - `tests/test_converge.py` covers read-time convergence, degraded embedder behavior, budgeted dense fill, and the “never full reindex” invariant.

Root cause: incremental replay updates changed-path lexical/chunk state but leaves `vec_docs` in place, so the changed path is invisible to `paths_missing_doc_vector()` and the doc-surface vector is not refreshed.

## Requirements / Acceptance Criteria

### Functional

1. Editing a committed Markdown file and running `converge(..., debounce_seconds=0)` must refresh that file's doc-surface vector when an embedder is available.
2. Only changed/missing doc surfaces should be embedded; unchanged docs must not be re-embedded.
3. Full `reindex` must remain manual and must not be called by convergence.
4. Deleted paths must still remove doc-lane rows.
5. Pure path moves should preserve current `rekey_path` semantics unless implementation analysis proves the existing diff model cannot distinguish a move from an edit+move.
6. Degraded convergence must leave stale/missing doc vectors for a later successful dense pass and must not write fake vectors.
7. Existing budget behavior must remain bounded and resumable.

### Observability

1. Existing `docs_embedded` should keep meaning “doc-surface vectors written this pass.”
2. Optional: add `docs_invalidated` to replay/converge results if it can be done without widening the change. Do **not** block the main fix on this metric.
3. The CLI/JSON output must remain backward-compatible unless a clear new metric is added.

### Documentation

Because this touches retrieval/convergence/index behavior, update in the same implementation PR:

- `ARCHITECTURE.md` — read-time convergence section must say changed doc surfaces are invalidated and refreshed incrementally, not only chunks.
- `README.md` — “How it works” bullet for read-time convergence must not imply doc-lane freshness requires full reindex.
- `docs/README.md` — current-truth pins only if wording there needs to mention the doc lane; otherwise no change.
- `CHANGELOG.md` — `[Unreleased]` / `Fixed` entry for stale doc-surface vectors during incremental convergence.

## Proposed Approach

Ship the minimal correct fix first:

1. Add a small helper on `Index`, likely:

   ```python
   def invalidate_doc_vector(self, path: str) -> bool:
       row = self.conn.execute("SELECT doc_id FROM docs WHERE path=?", (path,)).fetchone()
       if not row:
           return False
       cur = self.conn.execute("DELETE FROM vec_docs WHERE doc_id=?", (row[0],))
       return bool(cur.rowcount)
   ```

2. Call `invalidate_doc_vector(path)` inside `Index.upsert_lexical(path, chunks)` after deleting old chunk vectors and before/after inserting fresh chunks.

3. Preserve the `docs` row; delete only `vec_docs`. This keeps document identity stable while making `paths_missing_doc_vector()` return the changed path.

4. Do **not** change `embed_stale_locked(...)` initially. The existing bounded missing-doc path should refresh invalidated doc surfaces by reading committed file content and calling `idx.add_docs(...)`.

5. Add tests before production changes:
   - unit test proving `upsert_lexical` invalidates an existing doc vector;
   - unit test proving `embed_stale` refreshes only the invalidated doc and remains idempotent;
   - convergence test proving an edited committed file yields `replayed == 1` and `docs_embedded == 1` with a budget that allows it;
   - degraded test extension proving invalidated doc remains missing after embed failure.

6. Only consider `surface_hash` / schema migration as a follow-up issue if the minimal row-deletion design cannot handle observed cases.

## Implementation Phases

### Phase 0: Branch and baseline

**Objective:** Start from a clean implementation branch and capture baseline test behavior.

**Files:** none.

**Steps:**

1. Branch from `origin/main`:

   ```bash
   cd <hypermnesic-repo>
   git fetch origin main
   git checkout -b ls-1521-p1-incrementally-invalidate-stale-doc-surface-vectors-during origin/main
   ```

2. Run focused baseline tests:

   ```bash
   uv run pytest tests/test_index.py tests/test_embed_stale.py tests/test_converge.py -q -o 'addopts='
   ```

   Expected: PASS before changes. If baseline fails, stop and file/update Linear with the failure.

3. Optional quick lint baseline:

   ```bash
   uv run ruff check src/hypermnesic/index.py tests/test_index.py tests/test_embed_stale.py tests/test_converge.py
   ```

### Phase 1: Add failing unit test for doc-vector invalidation

**Objective:** Prove today’s bug at the `Index.upsert_lexical` level.

**Files:**

- Modify: `tests/test_index.py`

**Test to add:** near existing doc-lane tests around `test_doc_lane_table_and_one_row_per_doc`.

```python
def test_upsert_lexical_invalidates_existing_doc_vector(make_corpus, fake_embedder):
    from hypermnesic import ingest

    repo = make_corpus({"a.md": "# A\n\noriginal lead.\n"})
    idx = index.build_index(repo, fake_embedder)
    row = idx.conn.execute("SELECT doc_id FROM docs WHERE path='a.md'").fetchone()
    assert row is not None
    assert idx.conn.execute("SELECT COUNT(*) FROM vec_docs WHERE doc_id=?", row).fetchone()[0] == 1

    idx.upsert_lexical("a.md", ingest.chunks_for_text("a.md", "# A\n\nupdated lead.\n"))

    assert idx.conn.execute("SELECT COUNT(*) FROM docs WHERE path='a.md'").fetchone()[0] == 1
    assert idx.conn.execute("SELECT COUNT(*) FROM vec_docs WHERE doc_id=?", row).fetchone()[0] == 0
    assert "a.md" in idx.paths_missing_doc_vector()
    idx.close()
```

**Run:**

```bash
uv run pytest tests/test_index.py::test_upsert_lexical_invalidates_existing_doc_vector -q -o 'addopts='
```

**Expected before implementation:** FAIL because `vec_docs` remains present.

### Phase 2: Implement minimal invalidation helper

**Objective:** Make changed-path lexical upsert mark that path’s doc vector stale/missing.

**Files:**

- Modify: `src/hypermnesic/index.py`

**Implementation sketch:**

1. Add helper near `paths_missing_doc_vector()` or before `upsert_lexical`:

   ```python
   def invalidate_doc_vector(self, path: str) -> bool:
       """Mark a path's doc-surface vector stale while preserving doc identity."""
       row = self.conn.execute("SELECT doc_id FROM docs WHERE path=?", (path,)).fetchone()
       if not row:
           return False
       cur = self.conn.execute("DELETE FROM vec_docs WHERE doc_id=?", (row[0],))
       return bool(cur.rowcount)
   ```

2. Call it from `upsert_lexical` before `c.commit()`:

   ```python
   self.invalidate_doc_vector(path)
   ```

   If using `self.conn` while `c = self.conn` is already local, avoid an inner commit in the helper. The helper should not commit; `upsert_lexical` owns the transaction boundary.

3. Update the `upsert_lexical` docstring to say it also invalidates the path’s doc-surface vector so bounded dense fill refreshes it.

**Run:**

```bash
uv run pytest tests/test_index.py::test_upsert_lexical_invalidates_existing_doc_vector -q -o 'addopts='
```

**Expected after implementation:** PASS.

### Phase 3: Add unit tests for bounded doc refresh and idempotence

**Objective:** Prove `embed_stale` refreshes only invalidated doc surfaces and remains resumable.

**Files:**

- Modify: `tests/test_embed_stale.py`

**Test A — only invalidated doc is refreshed:**

```python
def test_embed_stale_refreshes_invalidated_doc_surface_only(make_corpus, fake_embedder):
    from hypermnesic import ingest

    repo = make_corpus({
        "a.md": "# A\n\noriginal alpha.\n",
        "b.md": "# B\n\noriginal beta.\n",
    })
    idx = ix.build_index(repo, fake_embedder)
    before_docs = idx.conn.execute("SELECT COUNT(*) FROM vec_docs").fetchone()[0]

    (repo / "a.md").write_text("# A\n\nupdated alpha.\n", encoding="utf-8")
    idx.upsert_lexical("a.md", ingest.chunks_for_text("a.md", "# A\n\nupdated alpha.\n"))
    assert idx.paths_missing_doc_vector() == ["a.md"]

    res = ix.embed_stale(idx, repo, fake_embedder, budget=10)

    assert res["docs_embedded"] == 1
    assert idx.conn.execute("SELECT COUNT(*) FROM vec_docs").fetchone()[0] == before_docs
    assert idx.paths_missing_doc_vector() == []
    second = ix.embed_stale(idx, repo, fake_embedder, budget=10)
    assert second["docs_embedded"] == 0
    idx.close()
```

**Test B — doc budget resumes:** if not already covered by Phase 4, add a focused test with two invalidated docs and `budget=1`, expecting one missing path to remain after the first pass and zero after the second.

**Run:**

```bash
uv run pytest tests/test_embed_stale.py -q -o 'addopts='
```

### Phase 4: Add convergence integration tests

**Objective:** Prove the real git/checkpoint path refreshes doc-surface vectors for edited committed files.

**Files:**

- Modify: `tests/test_converge.py`

**Test A — edited committed file refreshes doc lane:** add near the happy-path convergence tests.

```python
def test_converge_refreshes_doc_surface_for_edited_file(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\noriginal alpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    _commit_file(repo, "a.md", "# A\n\nupdated alpha DOCSURFACENEW.\n", "update a")

    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0, embed_budget=10)

    assert res.status == "converged"
    assert res.replayed == 1
    assert res.docs_embedded == 1
    assert "a.md" not in idx.paths_missing_doc_vector()
    idx.close()
```

**Test B — degraded embedder leaves invalidated doc missing:** extend the existing degraded test or add a new one:

```python
def test_converge_embedder_failure_leaves_doc_surface_missing(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\noriginal alpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    _commit_file(repo, "a.md", "# A\n\nupdated alpha.\n", "update a")

    res = converge.converge(repo, idx, _DownEmbedder(), debounce_seconds=0, embed_budget=10)

    assert res.degraded is True
    assert res.replayed == 1 and res.checkpoint_advanced
    assert "a.md" in idx.paths_missing_doc_vector()
    idx.close()
```

**Run:**

```bash
uv run pytest tests/test_converge.py::test_converge_refreshes_doc_surface_for_edited_file tests/test_converge.py::test_converge_embedder_failure_leaves_doc_surface_missing -q -o 'addopts='
```

### Phase 5: Decide on optional `docs_invalidated` metric

**Objective:** Avoid metric churn unless it materially helps operators.

**Default decision:** Skip `docs_invalidated` in the first implementation. `docs_embedded` becomes meaningful for changed docs after invalidation, and the helper can be verified by tests.

**If adding the metric anyway:**

- Modify: `src/hypermnesic/index.py` to return invalidation count from `_replay` / `replay_changes`.
- Modify: `src/hypermnesic/converge.py` to add `docs_invalidated` to `ConvergeResult` and JSON output.
- Modify: `tests/test_converge.py` and likely `tests/test_cli.py` for output expectations.
- Update `docs/reference/cli.md` if CLI JSON docs enumerate the field.

Do not add this metric unless the implementation remains small and backward-compatible.

### Phase 6: Documentation updates

**Objective:** Keep docs current in the same PR, per `AGENTS.md`.

**Files:**

- Modify: `ARCHITECTURE.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Maybe modify: `docs/README.md` only if current-truth pins need a retrieval/convergence bullet.

**Required edits:**

1. In `ARCHITECTURE.md`, update the Read-time convergence section around lines 68–76 to state that convergence delta-replays lexical/graph state and invalidates changed-path doc-surface vectors, then bounded dense fill refreshes stale chunks and stale doc surfaces.

2. In `README.md`, update the “Read-time convergence” bullet around the “How it works” section to mention bounded dense catch-up covers stale chunks and doc surfaces for changed committed files.

3. In `CHANGELOG.md`, add under `[Unreleased]` / `### Fixed`:

   ```markdown
   - Incremental convergence now invalidates changed-path doc-surface vectors so edited Markdown files refresh the document-level dense lane without requiring a full reindex.
   ```

   If no `### Fixed` section exists under `[Unreleased]` after current changes, create one in the proper Keep-a-Changelog order.

### Phase 7: Focused validation

**Objective:** Prove the behavior and guard the touched surface.

Run:

```bash
uv run ruff check src/hypermnesic/index.py src/hypermnesic/converge.py tests/test_index.py tests/test_embed_stale.py tests/test_converge.py
uv run pytest tests/test_index.py tests/test_embed_stale.py tests/test_converge.py -q -o 'addopts='
```

If CLI JSON fields changed, also run:

```bash
uv run pytest tests/test_cli.py -q -o 'addopts='
```

### Phase 8: Full gates before PR/Done

**Objective:** Satisfy repository contract.

Run the repo gate set from `AGENTS.md`:

```bash
uv sync --extra dev
uv run ruff check .
uv run python scripts/check_version_consistency.py
uv run pytest
uv run python scripts/license_scan.py
uv run python scripts/preflight_public_scan.py
```

Expected: all pass. Do not mark LS-1521 Done without this evidence, docs updated, and a clean git status.

## Risks / Edge Cases

1. **Helper transaction boundary:** `invalidate_doc_vector` should not commit internally if called from `upsert_lexical`; keep transaction ownership clear.
2. **Virtual table rowcount:** sqlite virtual-table `DELETE` rowcount may be unreliable. Tests should verify actual absence in `vec_docs`, not only helper return value.
3. **Docs row preservation:** deleting `docs` rows would also work but is less stable; prefer preserving `docs` and deleting `vec_docs` only.
4. **Surface-less docs:** `paths_missing_doc_vector()` may keep returning files whose `doc_surface` is empty. Existing `doc_surface` normally falls back to path/title, so this should be rare; do not add surface-empty schema in this fix.
5. **Rename handling:** `_changed_md_since` currently treats renames as `D` + `A`, while `rekey_path` exists elsewhere. Do not broaden LS-1521 into rename optimization unless tests reveal a regression. Conservative re-embed on Git rename is acceptable only if documented as current behavior.
6. **Budget interaction:** `embed_stale_locked` applies the same `budget` independently to chunks and docs today. Do not accidentally make doc refresh unbounded while fixing freshness.
7. **Degraded checkpoint semantics:** current convergence advances checkpoint after lexical replay even if embeddings fail. Preserve that behavior; stale/missing vectors must be drainable later because the checkpoint will not replay the same commit again.
8. **Read path exceptions:** `converge` must never raise on embedder failure; tests should assert degraded behavior.

## Verification Commands

Focused implementation validation:

```bash
cd <hypermnesic-repo>
uv run ruff check src/hypermnesic/index.py src/hypermnesic/converge.py tests/test_index.py tests/test_embed_stale.py tests/test_converge.py
uv run pytest tests/test_index.py tests/test_embed_stale.py tests/test_converge.py -q -o 'addopts='
```

Full repository gates:

```bash
uv sync --extra dev
uv run ruff check .
uv run python scripts/check_version_consistency.py
uv run pytest
uv run python scripts/license_scan.py
uv run python scripts/preflight_public_scan.py
```

Optional real smoke on a disposable repo:

```bash
TMP=$(mktemp -d)
mkdir -p "$TMP/vault"
cd "$TMP/vault"
git init -b main
git config user.email test@example.com
git config user.name Test
printf '# A\n\noriginal alpha.\n' > a.md
git add a.md && git commit -m 'seed'
hypermnesic reindex "$PWD" --isolated --json
printf '# A\n\nupdated alpha DOCSURFACENEW.\n' > a.md
git add a.md && git commit -m 'update a'
hypermnesic converge "$PWD" --json
```

Expected smoke result: the converge JSON reports `replayed >= 1`, `docs_embedded >= 1` when an embedder is configured and not degraded. If no embedder is configured, it should report degraded lexical-only and not write fake vectors.

## Rollback / Recovery

- Production code rollback: revert the implementation commit(s). This restores previous convergence behavior and leaves the index rebuildable from Git.
- Index recovery: if any local index looks inconsistent, run manual `hypermnesic reindex <repo> --isolated --json`; the index is disposable and rebuilt from committed Markdown.
- If the minimal invalidation causes unexpected re-embedding volume, remove the `upsert_lexical` invalidation call and keep the tests skipped only while filing a follow-up; do not leave hidden behavior drift.
- If docs are updated incorrectly, revert doc commits or amend before merge; process docs should not override `docs/README.md` current-truth pins.

## Follow-up Compounding Opportunities

- Create a separate issue for hash-based doc-surface freshness (`surface_hash`, model id, dimension) if future requirements need explicit stale detection rather than row-deletion invalidation.
- Consider a tiny operator metric (`docs_invalidated`) once the minimal fix ships and the JSON output contract is reviewed.
- Add a lightweight index-health diagnostic showing stale chunk count and stale/missing doc-surface count without requiring SQLite spelunking.

## Handoff Checklist

- [ ] Implementation branch created from `origin/main`, not committed directly to `main`.
- [ ] Failing tests added before production changes.
- [ ] `Index.upsert_lexical` invalidates existing changed-path doc vectors.
- [ ] Existing `embed_stale_locked` refreshes invalidated doc surfaces without full reindex.
- [ ] Degraded and budgeted paths covered by tests.
- [ ] `ARCHITECTURE.md`, `README.md`, and `CHANGELOG.md` updated in the same PR.
- [ ] Focused tests pass.
- [ ] Full repo gates pass before marking Linear Done.
