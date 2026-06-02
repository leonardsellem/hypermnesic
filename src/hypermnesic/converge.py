"""U27 — read-time convergence: catch the index up to HEAD + close a bounded
dense slice before serving. The one shared step (KTD1) every read path calls.

Properties, all spec:
- **Debounced** (FR-R26): a recent convergence (timestamp in the state dir) short-
  circuits before any lock is taken.
- **Lock-safe** (KTD2/FR-R27): takes the single-indexer ``FileLock`` non-blocking;
  on ``LockBusyError`` it serves the current state — a writer or another converger
  is already advancing the index, so a read must never stall.
- **Never a full reindex** (FR-R32): convergence is delta-replay + a bounded embed;
  it never calls ``reindex_isolated`` (the OOM scar). Full reindex stays manual.
- **Bounded embed** (FR-R31): at most ``CONVERGE_EMBED_BUDGET`` stale chunks per read.
- **Graceful dense degradation** (FR-R34): a dead/absent embedder still completes the
  lexical/graph catch-up and advances the checkpoint; the result is flagged degraded.
- **Host-aware** (FR-R29/R30/R35): a serve/replica host projects committed SHAs only;
  an authoring host additionally re-applies the uncommitted working-tree overlay
  (lexical only — never advancing the checkpoint).
- **Oversized-delta guarded** (FR-R33): a delta beyond ``CONVERGE_MAX_DELTA_FILES`` is
  not replayed inline; convergence serves the current consistent projection and
  signals a manual reindex.

Convergence writes only the ``.hypermnesic/`` projection (FR-R35) — never the repo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from hypermnesic import config, serialize
from hypermnesic import index as index_mod

_STAMP_NAME = "converge.stamp"


@dataclass
class ConvergeResult:
    """Outcome of one convergence pass. ``status`` is the discriminator:
    ``converged`` (did a pass — possibly a no-op when already current),
    ``debounced`` (skipped, recent), ``lock_busy`` (skipped, another holder),
    ``oversized_delta`` (skipped replay, manual reindex recommended)."""

    status: str
    replayed: int = 0
    chunks_embedded: int = 0
    docs_embedded: int = 0
    degraded: bool = False
    manual_reindex_recommended: bool = False
    overlay_paths: list[str] = field(default_factory=list)
    head: str | None = None
    checkpoint_advanced: bool = False

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "replayed": self.replayed,
            "chunks_embedded": self.chunks_embedded,
            "docs_embedded": self.docs_embedded,
            "degraded_lexical_only": self.degraded,
            "manual_reindex_recommended": self.manual_reindex_recommended,
            "overlay_paths": self.overlay_paths,
            "head": self.head,
            "checkpoint_advanced": self.checkpoint_advanced,
        }


def _stamp_path(idx) -> Path:
    return Path(idx.db_path).parent / _STAMP_NAME


def _within_debounce(idx, debounce: float) -> bool:
    if debounce <= 0:
        return False
    try:
        last = float(_stamp_path(idx).read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        return False
    return (time.time() - last) < debounce


def _write_stamp(idx) -> None:
    try:
        _stamp_path(idx).write_text(f"{time.time()}\n", encoding="utf-8")
    except OSError:
        pass


def converge(repo, idx, embedder, *, authoring_host: bool = False,
             debounce_seconds: float | None = None,
             embed_budget: int | None = None,
             max_delta_files: int | None = None) -> ConvergeResult:
    """Bring ``idx`` up to ``repo``'s HEAD and close a bounded dense slice.

    ``None`` for any tunable falls back to the configured default
    (``config.CONVERGE_*``); tests pass explicit values (e.g. ``debounce_seconds=0``)
    to make the path under test deterministic. Returns a :class:`ConvergeResult`;
    never raises on a read-path failure (embedder down → degraded, lock held → skip).
    """
    repo = Path(repo)
    debounce = config.CONVERGE_DEBOUNCE_SECONDS if debounce_seconds is None else debounce_seconds
    budget = config.CONVERGE_EMBED_BUDGET if embed_budget is None else embed_budget
    max_delta = config.CONVERGE_MAX_DELTA_FILES if max_delta_files is None else max_delta_files

    if _within_debounce(idx, debounce):
        return ConvergeResult(status="debounced")

    lock = serialize.index_write_lock(repo)
    try:
        lock.acquire(blocking=False)              # KTD2: non-blocking single-indexer lock
    except serialize.LockBusyError:
        return ConvergeResult(status="lock_busy")  # another writer/converger is advancing it

    try:
        overlay_paths: list[str] = []
        if authoring_host:
            # FR-R29: re-apply uncommitted/untracked markdown (lexical only). Never
            # advances the checkpoint — a replica indexing the same SHA never sees these.
            try:
                overlay_paths = index_mod.apply_working_tree_overlay(idx, repo)
            except Exception:
                overlay_paths = []                # no git / transient — overlay is best-effort

        head, cp, have_cp, changes = index_mod.changes_since_checkpoint(idx, repo)
        replayed = 0
        advanced = False
        if changes is not None:                   # HEAD != checkpoint
            if len(changes) > max_delta:
                # FR-R33: an oversized delta is not replayed inline. A partial replay
                # could not advance the checkpoint to HEAD, so it would redo the same
                # work on every read with no progress; serve the current consistent
                # projection and recommend a manual reindex instead.
                _write_stamp(idx)
                return ConvergeResult(status="oversized_delta", head=head,
                                      manual_reindex_recommended=True,
                                      overlay_paths=overlay_paths)
            # lexical/graph catch-up only (embedder=None); dense is the bounded pass below.
            res = index_mod.replay_changes(idx, repo, head, cp, changes,
                                           embedder=None, have_cp=have_cp)
            replayed = res.get("replayed", 0)
            advanced = True

        # FR-R31 + FR-R34: bounded dense fill. Any embedder failure (API down, dim
        # mismatch) degrades to lexical/graph — the checkpoint already advanced — and
        # never raises on the read path; partially-embedded batches leave real vectors,
        # never zero placeholders.
        chunks_embedded = docs_embedded = 0
        degraded = embedder is None
        if embedder is not None:
            try:
                emb = index_mod.embed_stale_locked(idx, repo, embedder, budget=budget)
                chunks_embedded = emb["chunks_embedded"]
                docs_embedded = emb["docs_embedded"]
            except Exception:
                degraded = True                   # FR-R34: dense down, serve lexical/graph

        _write_stamp(idx)
        return ConvergeResult(status="converged", replayed=replayed,
                              chunks_embedded=chunks_embedded, docs_embedded=docs_embedded,
                              degraded=degraded, overlay_paths=overlay_paths,
                              head=head, checkpoint_advanced=advanced)
    finally:
        lock.release()
