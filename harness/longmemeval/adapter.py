"""U3 — per-haystack index + retrieval adapter (+ content-hash embedding cache).

One index per instance: materialize → ``index.build_index`` over that instance's
sessions with a ``state_dir`` **outside** the corpus → ``retrieve.search`` →
discard. Run once over the per-session corpus and once over the per-turn corpus
(mirrors ``harness/portability_probe.probe_repo``). The production embedding
config is used unchanged (R12) and the fusion params are frozen from the manifest
(R19); near-dup handling stays symmetric with the engine's
``collapse_duplicates=True``.

**Void gate (R20/AE2):** if embeddings are unavailable, the run is *voided*, not
scored. ``retrieve_for_corpus`` catches ``EmbeddingError`` (raised by a down
embedder during build or search) and surfaces it as ``degraded=True`` with no
ranking; ``retrieve_instances`` marks the whole run ``void`` if any corpus
degraded — never a lexical-only score (the engine never silently zero-fills).
The live CLI also calls ``embed.smoke_embed_or_die()`` before scoring.

**Embedding cache:** ``CachingEmbedder`` keys vectors by ``(model, dim, text)``
hash, so the per-session and per-turn corpora (which embed the same conversation
text) and the F3 critic re-run reuse embeddings instead of re-paying — keeping a
re-run well under the U1 cost ceiling. The default store is in-memory;
``SqliteEmbeddingCache`` persists across processes.
"""

from __future__ import annotations

import hashlib
import sqlite3
from array import array
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from pathlib import Path

from hypermnesic import embed as embed_mod
from hypermnesic import index, retrieve
from longmemeval import manifest as mf
from longmemeval.materialize import Instance, Materialized, materialize_instance

# Diagnostic retrieval depth: how deep a candidate list to rank before slicing at
# @5/@10/@50 in the scorer. This is a *measurement* depth (it must exceed the
# largest k the diagnostic reports), NOT a tuned fusion parameter — the fusion
# weights, lanes, and dedup stay frozen at the manifest values (R19).
SEARCH_DEPTH = 200


@dataclass
class HaystackResult:
    instance_id: str
    granularity: str               # "session" | "turn"
    ranked_units: list[str]        # ranked unique unit ids (best-first)
    degraded: bool                 # dense channel unavailable → not scorable
    gold_units: set[str] = field(default_factory=set)  # gold unit ids (empty for `_abs`)


@dataclass
class InstanceRetrieval:
    instance: Instance
    session: HaystackResult
    turn: HaystackResult


@dataclass
class RetrievalRun:
    results: list[InstanceRetrieval] = field(default_factory=list)
    void: bool = False             # True if any corpus degraded (R20/AE2)


class CachingEmbedder:
    """Embedder wrapper that caches vectors by content hash.

    Satisfies the embedder protocol (``.dim`` / ``.embed``). ``store`` is any
    mutable mapping of ``hash -> vector`` (defaults to an in-process dict);
    ``SqliteEmbeddingCache`` gives cross-process persistence.
    """

    def __init__(self, embedder, store: MutableMapping[str, list[float]] | None = None):
        self._embedder = embedder
        self.dim = embedder.dim
        self.model = getattr(embedder, "model", "unknown")
        self._store: MutableMapping[str, list[float]] = {} if store is None else store

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}:{self.dim}:{text}".encode()).hexdigest()

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float] | None] = [None] * len(texts)
        miss_texts: list[str] = []
        miss_slots: list[tuple[int, str]] = []
        for i, text in enumerate(texts):
            key = self._key(text)
            try:                          # single lookup (no separate membership probe)
                out[i] = self._store[key]
            except KeyError:
                miss_texts.append(text)
                miss_slots.append((i, key))
        if miss_texts:
            vecs = self._embedder.embed(miss_texts)
            fresh: dict[str, list[float]] = {}
            for (i, key), vec in zip(miss_slots, vecs, strict=True):
                out[i] = vec
                fresh[key] = vec
            self._store.update(fresh)     # one write/commit for the whole batch
        return [v for v in out if v is not None]


class SqliteEmbeddingCache:
    """Persistent content-hash → vector store (a minimal mapping) for cross-run
    reuse. Stores vectors as packed float64 blobs so a cached vector is byte-for-
    byte what the embedder returned — a cached run reproduces a fresh one exactly
    (the cache must not perturb rankings via lossy truncation)."""

    def __init__(self, path: Path):
        self.conn = sqlite3.connect(str(path))
        # WAL + NORMAL sync: a cache is rebuildable, so trade strict durability for
        # far fewer fsyncs on the cold-population pass (the dominant SQLite write cost).
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, vec BLOB)")
        self.conn.commit()

    def __contains__(self, key: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM cache WHERE key=?", (key,)).fetchone() is not None

    def __getitem__(self, key: str) -> list[float]:
        row = self.conn.execute("SELECT vec FROM cache WHERE key=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return list(array("d", row[0]))

    def __setitem__(self, key: str, vec: list[float]) -> None:
        self.update({key: vec})

    def update(self, items: dict[str, list[float]]) -> None:
        """Batch-insert vectors with a single commit (one fsync per embed batch,
        not per vector — the cold-run hot path)."""
        if not items:
            return
        self.conn.executemany(
            "INSERT OR REPLACE INTO cache (key, vec) VALUES (?, ?)",
            [(k, array("d", v).tobytes()) for k, v in items.items()])
        self.conn.commit()

    def _count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]

    def close(self) -> None:
        self.conn.close()


def _ranked_units(hits, path_to_unit: dict[str, str]) -> list[str]:
    """Collapse ranked chunk hits → ordered unique unit ids (session or turn).

    Mirrors ``parity_harness.doc_ranking`` but maps each hit's path through the
    materializer's path→unit map (multiple chunks of one session/round collapse
    to a single unit, keeping the highest-ranked sighting)."""
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        unit = path_to_unit.get(h.path)
        if unit and unit not in seen:
            seen.add(unit)
            out.append(unit)
    return out


def retrieve_for_corpus(materialized: Materialized, question: str, embedder, *,
                        state_dir: Path,
                        weights: tuple[float, float, float] | None = None,
                        use_doc_lane: bool = mf.RETRIEVAL_USE_DOC_LANE,
                        collapse_duplicates: bool = mf.RETRIEVAL_COLLAPSE_DUPLICATES,
                        search_depth: int = SEARCH_DEPTH) -> HaystackResult:
    """Build an isolated index over one corpus and return ranked unit ids.

    Catches ``EmbeddingError`` (build or search) → ``degraded=True`` with an
    empty ranking, so a down embedder voids rather than crashing or silently
    scoring lexical-only.
    """
    weights = tuple(mf.RETRIEVAL_WEIGHTS) if weights is None else weights
    gold = set(materialized.gold_units)
    try:
        idx = index.build_index(materialized.corpus_dir, embedder, state_dir=Path(state_dir))
    except embed_mod.EmbeddingError:
        return HaystackResult(materialized.instance_id, materialized.granularity, [], True, gold)
    try:
        res = retrieve.search(idx, question, embedder=embedder, k=search_depth,
                              candidate_k=search_depth, use_doc_lane=use_doc_lane,
                              collapse_duplicates=collapse_duplicates, weights=weights)
    except embed_mod.EmbeddingError:
        idx.close()
        return HaystackResult(materialized.instance_id, materialized.granularity, [], True, gold)
    idx.close()
    return HaystackResult(materialized.instance_id, materialized.granularity,
                          _ranked_units(res.hits, materialized.path_to_unit),
                          res.degraded, gold)


def retrieve_instances(instances: list[Instance], work_dir: Path, embedder, *,
                       weights: tuple[float, float, float] | None = None,
                       search_depth: int = SEARCH_DEPTH) -> RetrievalRun:
    """Materialize + retrieve every instance over both granularities.

    Each instance gets its own corpus + state dir (per-haystack isolation). The
    run is ``void`` if any corpus degraded (R20/AE2) — the scorer must not report
    a number for a void run.
    """
    work_dir = Path(work_dir)
    run = RetrievalRun()
    for inst in instances:
        base = work_dir / safe_name(inst.question_id)
        sessions_m, turns_m = materialize_instance(inst, base)
        sres = retrieve_for_corpus(sessions_m, inst.question, embedder,
                                   state_dir=base / "state_sessions",
                                   weights=weights, search_depth=search_depth)
        tres = retrieve_for_corpus(turns_m, inst.question, embedder,
                                   state_dir=base / "state_turns",
                                   weights=weights, search_depth=search_depth)
        run.results.append(InstanceRetrieval(inst, sres, tres))
        if sres.degraded or tres.degraded:
            run.void = True
    return run


def safe_name(name: str) -> str:
    """Filesystem-safe per-instance work-dir name. Shared by the diagnostic
    (``retrieve_instances``) and QA (``run_qa``) runners so both lay out the same
    per-haystack directories — the embed cache hits only if they agree."""
    return "".join(c if c.isalnum() or c in "._-" else "-" for c in name)[:80] or "x"
