"""Read-only index: sqlite-vec KNN + SQLite FTS5 + a SHA checkpoint slot.

The index is a disposable, rebuildable projection of the git tree, living under
a per-repo ``.hypermnesic/`` state dir (created 0700; the db file 0600). The
engine ignores its state dir via ``.git/info/exclude`` — it **never** mutates
the target repo's ``.gitignore`` or any tracked file (KTD8).

Dense retrieval uses the sqlite-vec KNN ``MATCH ... k = ?`` query shape, never a
brute-force ``ORDER BY vec_distance_*`` (KTD3, ~200× slower at scale).
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

import sqlite_vec

from hypermnesic import config, ingest, serialize
from hypermnesic import embed as embed_mod

STATE_DIRNAME = ".hypermnesic"
_BATCH = 128
_RATE_LIMIT_BACKOFF_SECONDS = (0.25, 0.5, 1.0)
_FTS_TEXT_VERSION = "2"
_LEXICAL_FALLBACK_STOPWORDS = {
    "a", "an", "and", "are", "about", "do", "for", "in", "is", "it", "of", "on",
    "or", "the", "to", "what", "we",
}


def state_dir_for(repo: Path) -> Path:
    return Path(repo) / STATE_DIRNAME


def _load_vec(conn: sqlite3.Connection) -> None:
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def _git_head(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _fts_text(ch: ingest.Chunk) -> str:
    return f"{ch.heading}\n{ch.text}" if ch.heading else ch.text


def ensure_ignored(repo: Path) -> None:
    """Ignore the state dir via .git/info/exclude — never the tracked .gitignore."""
    git_dir = Path(repo) / ".git"
    if not git_dir.exists():
        return
    info = git_dir / "info"
    info.mkdir(exist_ok=True)
    exclude = info / "exclude"
    entry = f"{STATE_DIRNAME}/"
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if entry not in existing.splitlines():
        with exclude.open("a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(f"# hypermnesic disposable index state\n{entry}\n")


class Index:
    KNN_SQL = (
        "SELECT chunk_id, distance FROM vec_chunks "
        "WHERE embedding MATCH ? AND k = ? ORDER BY distance"
    )

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._open()

    def _open(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        # Bound after connect so a freshly created file records its real identity,
        # and BEFORE anything below touches self.conn (which would recurse).
        self._file_id = self._current_file_id()
        _load_vec(self._conn)
        self.refresh_fts_projection_if_needed()

    def _current_file_id(self) -> tuple[int, int] | None:
        """Identity of the file currently at ``db_path`` — ``None`` if absent."""
        try:
            st = os.stat(self.db_path)
        except OSError:
            return None
        return (st.st_dev, st.st_ino)

    @property
    def conn(self) -> sqlite3.Connection:
        """The live connection, reopened if the database file was swapped.

        ``reindex_isolated`` installs a rebuilt index with ``os.replace``. A
        long-lived holder (the MCP servers) would otherwise keep its connection
        on the unlinked inode: reads would silently serve the frozen snapshot
        and writes would fail with "attempt to write a readonly database". One
        ``stat`` per operation is negligible beside the query that follows.

        A missing file is NOT a swap — an in-flight rebuild must not make us
        reopen onto nothing, so we keep serving the connection we have. Neither
        is an open transaction a safe place to reopen: that would discard
        buffered writes, so we finish on the handle the caller started with.
        """
        current = self._current_file_id()
        if (current is not None and current != self._file_id
                and not self._conn.in_transaction):
            self._reopen()
        return self._conn

    def _reopen(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass                                  # the old inode is already gone
        self._open()

    def create_schema(self) -> None:
        c = self.conn
        c.execute(
            "CREATE TABLE IF NOT EXISTS chunks ("
            "chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "path TEXT NOT NULL, ord INTEGER NOT NULL, heading TEXT, text TEXT NOT NULL)"
        )
        c.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0("
            f"chunk_id INTEGER PRIMARY KEY, embedding float[{config.EMBED_DIM}])"
        )
        c.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5("
            "text, tokenize='unicode61 remove_diacritics 2')"
        )
        # doc-level lane: one embedding per document (title+headings+lead surface)
        c.execute(
            "CREATE TABLE IF NOT EXISTS docs ("
            "doc_id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL)"
        )
        c.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_docs USING vec0("
            f"doc_id INTEGER PRIMARY KEY, embedding float[{config.EMBED_DIM}])"
        )
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        c.commit()
        self.refresh_fts_projection_if_needed()

    def refresh_fts_projection_if_needed(self) -> bool:
        """Keep the disposable lexical projection aligned with ``chunks`` rows.

        Older indexes stored only chunk body text in FTS. Rebuilding FTS from the
        already-indexed ``chunks`` table is cheap, deterministic, and requires no
        embeddings, so degraded lexical recall can self-heal on open.
        """
        tables = {
            row[0] for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            ).fetchall()
        }
        if not {"chunks", "fts_chunks", "meta"}.issubset(tables):
            return False
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key='fts_text_version'"
        ).fetchone()
        if row and row[0] == _FTS_TEXT_VERSION:
            return False
        chunk_rows = self.conn.execute(
            "SELECT chunk_id, heading, text FROM chunks ORDER BY chunk_id"
        ).fetchall()
        self.conn.execute("DELETE FROM fts_chunks")
        self.conn.executemany(
            "INSERT INTO fts_chunks (rowid, text) VALUES (?, ?)",
            [
                (cid, f"{heading}\n{text}" if heading else text)
                for cid, heading, text in chunk_rows
            ],
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('fts_text_version', ?)",
            (_FTS_TEXT_VERSION,),
        )
        self.conn.commit()
        return True

    def add_documents(self, chunks: list[ingest.Chunk],
                      vectors: list[list[float]]) -> None:
        assert len(chunks) == len(vectors)
        c = self.conn
        for ch, vec in zip(chunks, vectors, strict=True):
            cur = c.execute(
                "INSERT INTO chunks (path, ord, heading, text) VALUES (?, ?, ?, ?)",
                (ch.path, ch.ord, ch.heading, ch.text),
            )
            cid = cur.lastrowid
            c.execute(
                "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                (cid, sqlite_vec.serialize_float32(vec)),
            )
            c.execute(
                "INSERT INTO fts_chunks (rowid, text) VALUES (?, ?)", (cid, _fts_text(ch))
            )
        c.commit()

    def add_docs(self, docs: list[tuple[str, str]], vectors: list[list[float]]) -> None:
        """docs: [(path, surface)] with parallel doc-surface embeddings."""
        assert len(docs) == len(vectors)
        c = self.conn
        for (path, _surface), vec in zip(docs, vectors, strict=True):
            cur = c.execute("INSERT OR IGNORE INTO docs (path) VALUES (?)", (path,))
            if cur.rowcount == 1:
                doc_id = cur.lastrowid
            else:  # path already present
                doc_id = c.execute("SELECT doc_id FROM docs WHERE path=?", (path,)).fetchone()[0]
            c.execute("INSERT OR REPLACE INTO vec_docs (doc_id, embedding) VALUES (?, ?)",
                      (doc_id, sqlite_vec.serialize_float32(vec)))
        c.commit()

    def has_doc_lane(self) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='vec_docs'").fetchone()
        return row is not None and self.conn.execute(
            "SELECT COUNT(*) FROM vec_docs").fetchone()[0] > 0

    def doc_dense_search(self, query_vec: list[float], k: int = 10):
        return self.conn.execute(
            "SELECT d.path, v.distance FROM vec_docs v JOIN docs d ON d.doc_id = v.doc_id "
            "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
            (sqlite_vec.serialize_float32(query_vec), k),
        ).fetchall()

    def upsert_lexical(self, path: str, chunks: list[ingest.Chunk]) -> list[int]:
        """Replace a path's chunks with fresh lexical+graph content (NO embeddings).

        commit_note (U7) calls this synchronously so a written page is findable
        lexically immediately; dense vectors catch up in a later async embed pass
        (AE5). Removes the path's stale chunk/FTS/vec rows first, and invalidates
        its doc-surface vector so bounded dense fill refreshes changed docs too.
        """
        c = self.conn
        old = [r[0] for r in c.execute(
            "SELECT chunk_id FROM chunks WHERE path=?", (path,)).fetchall()]
        for cid in old:
            c.execute("DELETE FROM chunks WHERE chunk_id=?", (cid,))
            c.execute("DELETE FROM fts_chunks WHERE rowid=?", (cid,))
            c.execute("DELETE FROM vec_chunks WHERE chunk_id=?", (cid,))
        self.invalidate_doc_vector(path)
        new_ids = []
        for ch in chunks:
            cur = c.execute(
                "INSERT INTO chunks (path, ord, heading, text) VALUES (?, ?, ?, ?)",
                (ch.path, ch.ord, ch.heading, ch.text))
            cid = cur.lastrowid
            c.execute("INSERT INTO fts_chunks (rowid, text) VALUES (?, ?)", (cid, _fts_text(ch)))
            new_ids.append(cid)
        c.commit()
        return new_ids

    def chunks_for_path(self, path: str) -> list[int]:
        return [r[0] for r in self.conn.execute(
            "SELECT chunk_id FROM chunks WHERE path=? ORDER BY chunk_id", (path,)).fetchall()]

    def invalidate_doc_vector(self, path: str) -> bool:
        """Mark a path's doc-surface vector stale while preserving its docs row.

        Returns True when an existing vec_docs row was deleted. A missing docs row
        is already stale/missing from paths_missing_doc_vector(), so this is a
        no-op for never-embedded paths.
        """
        row = self.conn.execute("SELECT doc_id FROM docs WHERE path=?", (path,)).fetchone()
        if not row:
            return False
        cur = self.conn.execute("DELETE FROM vec_docs WHERE doc_id=?", (row[0],))
        return cur.rowcount > 0

    def remove_path(self, path: str) -> None:
        """Drop all index rows for a path (chunks/FTS/vec + doc lane)."""
        c = self.conn
        for cid in [r[0] for r in c.execute(
                "SELECT chunk_id FROM chunks WHERE path=?", (path,)).fetchall()]:
            c.execute("DELETE FROM chunks WHERE chunk_id=?", (cid,))
            c.execute("DELETE FROM fts_chunks WHERE rowid=?", (cid,))
            c.execute("DELETE FROM vec_chunks WHERE chunk_id=?", (cid,))
        row = c.execute("SELECT doc_id FROM docs WHERE path=?", (path,)).fetchone()
        if row:
            c.execute("DELETE FROM vec_docs WHERE doc_id=?", (row[0],))
            c.execute("DELETE FROM docs WHERE path=?", (path,))
        c.commit()

    def all_paths(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT DISTINCT path FROM chunks").fetchall()}

    def stale_chunk_ids(self) -> list[int]:
        """Chunks with no dense vector yet (the AE5 lexical-ahead-of-dense gap)."""
        return [r[0] for r in self.conn.execute(
            "SELECT chunk_id FROM chunks WHERE chunk_id NOT IN "
            "(SELECT chunk_id FROM vec_chunks) ORDER BY chunk_id").fetchall()]

    def paths_missing_doc_vector(self) -> list[str]:
        """Indexed paths whose doc-lane vector is missing (no docs row, or a docs
        row with no vec_docs) — e.g. pages written by commit_note's lexical upsert."""
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT c.path FROM chunks c LEFT JOIN docs d ON d.path = c.path "
            "WHERE d.doc_id IS NULL OR d.doc_id NOT IN (SELECT doc_id FROM vec_docs) "
            "ORDER BY c.path").fetchall()]

    def rekey_path(self, old: str, new: str) -> None:
        """Re-key a moved doc old→new in place (U10). Preserves chunk_ids and
        their embeddings (a move is the same content at a new path — no re-embed,
        no tombstone). Clears any existing rows at ``new`` first."""
        if old == new:
            return
        self.remove_path(new)  # avoid a UNIQUE(docs.path) collision
        c = self.conn
        c.execute("UPDATE chunks SET path=? WHERE path=?", (new, old))
        c.execute("UPDATE docs SET path=? WHERE path=?", (new, old))
        c.commit()

    # --- checkpoint ------------------------------------------------------
    def set_checkpoint(self, sha: str | None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('checkpoint_sha', ?)",
            (sha,),
        )
        self.conn.commit()

    def get_checkpoint(self) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key='checkpoint_sha'"
        ).fetchone()
        return row[0] if row else None

    # --- retrieval -------------------------------------------------------
    def dense_search(self, query_vec: list[float], k: int = 10):
        return self.conn.execute(
            self.KNN_SQL, (sqlite_vec.serialize_float32(query_vec), k)
        ).fetchall()

    def lexical_search(self, query_text: str, k: int = 10):
        # Phrase-match the query tokens. This is precise for exact/proper-noun
        # queries and gracefully no-ops on free-form NL questions (the dense
        # channel carries those). Measured: OR-of-terms floods the candidate set
        # with weak common-term matches and degrades fused ranking. If the exact
        # phrase misses, fall back to an explicit AND over salient tokens so
        # lexical-only degraded mode can still recall hyphenated/non-contiguous
        # identifiers such as LS-1675 public-release smoke notes.
        q = query_text.replace('"', " ").strip()
        if not q:
            return []
        rows = self.conn.execute(
            "SELECT rowid, bm25(fts_chunks) FROM fts_chunks "
            "WHERE fts_chunks MATCH ? ORDER BY bm25(fts_chunks) LIMIT ?",
            (f'"{q}"', k),
        ).fetchall()
        if rows:
            return rows
        tokens = [
            tok for tok in re.findall(r"\w+", q, flags=re.UNICODE)
            if tok.lower() not in _LEXICAL_FALLBACK_STOPWORDS
        ]
        if len(tokens) < 2:
            return rows
        fallback = " AND ".join(f'"{tok}"' for tok in tokens)
        rows = self.conn.execute(
            "SELECT rowid, bm25(fts_chunks) FROM fts_chunks "
            "WHERE fts_chunks MATCH ? ORDER BY bm25(fts_chunks) LIMIT ?",
            (fallback, k),
        ).fetchall()
        return rows

    # --- accessors -------------------------------------------------------
    def get_chunk(self, chunk_id: int) -> dict:
        row = self.conn.execute(
            "SELECT chunk_id, path, ord, heading, text FROM chunks WHERE chunk_id=?",
            (chunk_id,),
        ).fetchone()
        if not row:
            raise KeyError(chunk_id)
        return {"chunk_id": row[0], "path": row[1], "ord": row[2],
                "heading": row[3], "text": row[4]}

    def all_chunks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT chunk_id, path, ord, heading, text FROM chunks ORDER BY chunk_id"
        ).fetchall()
        return [{"chunk_id": r[0], "path": r[1], "ord": r[2],
                 "heading": r[3], "text": r[4]} for r in rows]

    def note_vectors(self) -> dict[str, list[float]]:
        """Mean dense vector per path over its embedded chunks — read access to the
        STORED vectors (U21 salience centrality + U22 pairwise similarity need this;
        the kernel previously exposed only query-vector KNN). Paths whose chunks are
        not yet embedded (the AE5 lexical-ahead gap) are simply absent. Deterministic
        order so callers' rankings are reproducible."""
        import json

        rows = self.conn.execute(
            "SELECT c.path, vec_to_json(v.embedding) FROM vec_chunks v "
            "JOIN chunks c ON c.chunk_id = v.chunk_id ORDER BY c.path, v.chunk_id"
        ).fetchall()
        acc: dict[str, list[list[float]]] = {}
        for path, vec_json in rows:
            acc.setdefault(path, []).append(json.loads(vec_json))
        out: dict[str, list[float]] = {}
        for path, vecs in acc.items():
            dim = len(vecs[0])
            out[path] = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
        return out

    def stats(self) -> dict:
        n = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_docs = self.conn.execute(
            "SELECT COUNT(DISTINCT path) FROM chunks"
        ).fetchone()[0]
        return {"chunks": n, "docs": n_docs, "checkpoint": self.get_checkpoint(),
                "model": config.EMBED_MODEL, "dim": config.EMBED_DIM}

    def close(self) -> None:
        self._conn.close()          # closing must never trigger a reopen


def _is_md(path: str) -> bool:
    parts = Path(path).parts
    return path.endswith(".md") and not any(p in ingest._SKIP_DIRS for p in parts)


def _changed_md_since(repo: Path, old: str, new: str) -> list[tuple[str, str]]:
    out = subprocess.run(
        # core.quotepath=false: emit non-ASCII paths raw (café.md, 日記.md) instead of
        # octal-escaped+quoted, so _is_md matches them and they are not silently dropped.
        ["git", "-C", str(repo), "-c", "core.quotepath=false",
         "diff", "--name-status", f"{old}..{new}"],
        capture_output=True, text=True, check=True).stdout
    changes: list[tuple[str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if parts[0].startswith("R") and len(parts) >= 3:   # rename = delete old + add new
            changes += [("D", parts[1]), ("A", parts[2])]
        elif len(parts) >= 2:
            changes.append((parts[0][0], parts[1]))
    return [(s, p) for s, p in changes if _is_md(p)]


def _md_files_at(repo: Path, sha: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=false",
                          "ls-tree", "-r", "--name-only", sha],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if _is_md(p)]


def catch_up(idx: Index, repo: Path, *, embedder=None) -> dict:
    """Delta-replay the index to HEAD from its SHA checkpoint (R10).

    Replays only files changed since the checkpoint (a full ls-tree if the
    checkpoint is missing/unknown), reading **committed** content (`git show
    HEAD:path`) so it is a pure projection of the committed tree — independent of
    a dirty working tree. Deletes vanished paths. Lexical+graph are replayed
    synchronously; dense embeddings are an async follow-up (pass ``embedder`` to
    also refresh vectors for changed files). Advances the checkpoint to HEAD.

    When ``embedder`` is passed this is a dense-fill entrypoint, so it takes the
    shared dense-maintenance exclusion first (non-blocking). Contention still
    replays the lexical delta (the same progress convergence preserves) with the
    dense step deferred: the result is a named ``lock_busy`` deferral carrying the
    replayed count, with zero paid calls.
    """
    head, cp, have_cp, changes = changes_since_checkpoint(idx, repo)
    if head is None:
        return {"status": "no-git", "replayed": 0}
    if changes is None:
        return {"status": "current", "replayed": 0, "to": head}
    maintenance = None
    dense_deferred = False
    if embedder is not None:
        maintenance = serialize.dense_maintenance_lock(idx.db_path.parent)
        try:
            maintenance.acquire()
        except serialize.LockBusyError:
            dense_deferred = True
            maintenance = None
    try:
        try:
            lock = serialize.FileLock(idx.db_path.parent / "index.lock").acquire()
        except serialize.LockBusyError:
            # A real drain/build holds maintenance then index.lock for its whole
            # run: catch_up must return a named deferral, never raise into the
            # local-proof read path.
            return {"status": "lock_busy", "replayed": 0,
                    "dense_deferred": dense_deferred,
                    "reason": "index_writer_busy"}
        try:
            result = replay_changes(
                idx, repo, head, cp, changes,
                embedder=None if dense_deferred else embedder, have_cp=have_cp)
        finally:
            lock.release()
        if dense_deferred:
            result = {**result, "status": "lock_busy", "dense_deferred": True,
                      "reason": "dense_maintenance_busy"}
        return result
    finally:
        if maintenance is not None:
            maintenance.release()


def changes_since_checkpoint(idx: Index, repo: Path):
    """Pure delta plan from the index checkpoint to HEAD — no lock, no mutation.

    Returns ``(head, cp, have_cp, changes)``. ``head`` is None when ``repo`` is
    not a git repo; ``changes`` is None when the index is already current
    (cp == head). Convergence uses this to size the delta (oversized-delta guard,
    FR-R33) before deciding whether to replay."""
    repo = Path(repo)
    head = _git_head(repo)
    if not head:
        return (None, None, False, None)
    cp = idx.get_checkpoint()
    if cp == head:
        return (head, cp, True, None)
    have_cp = bool(cp) and subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-t", cp or ""],
        capture_output=True, text=True).stdout.strip() == "commit"
    changes = (_changed_md_since(repo, cp, head) if have_cp
               else [("A", p) for p in _md_files_at(repo, head)])
    return (head, cp, have_cp, changes)


def replay_changes(idx: Index, repo: Path, head: str, cp: str | None,
                   changes: list[tuple[str, str]], *, embedder=None,
                   have_cp: bool = True) -> dict:
    """Lock-free delta-replay of a precomputed change set — the caller MUST hold
    the single-indexer lock. Advances the checkpoint to ``head``. ``converge``
    calls this while holding the lock; :func:`catch_up` wraps it with the lock
    for standalone callers."""
    return _replay(idx, Path(repo), head, cp, changes, embedder, have_cp)


def _replay(idx, repo, head, cp, changes, embedder, have_cp) -> dict:
    for status, path in changes:
        if status == "D":
            idx.remove_path(path)
            continue
        shown = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=false",
                                "show", f"{head}:{path}"], capture_output=True, text=True)
        if shown.returncode != 0:
            # transient git failure (object missing, pruned, corrupt) — leave the path's
            # existing index rows intact rather than blanking them with empty content.
            continue
        chunks = ingest.chunks_for_text(path, shown.stdout)
        idx.upsert_lexical(path, chunks)
        if embedder is not None and chunks:
            vectors = embedder.embed([c.text for c in chunks])
            cids = idx.chunks_for_path(path)
            for cid, vec in zip(cids, vectors, strict=False):
                idx.conn.execute("INSERT OR REPLACE INTO vec_chunks (chunk_id, embedding) "
                                 "VALUES (?, ?)", (cid, sqlite_vec.serialize_float32(vec)))
            idx.conn.commit()
    idx.set_checkpoint(head)
    return {"status": "replayed", "replayed": len(changes), "from": cp, "to": head,
            "full": not have_cp}


def _doc_surface_for_projection(repo: Path, path: str) -> str | None:
    """Return the doc surface for the committed projection, falling back off-git.

    Git-backed indexes are projections of HEAD, not of a dirty working tree. The
    fallback preserves embed_stale behavior for non-git/local scratch corpora.
    """
    head = _git_head(repo)
    if head:
        shown = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=false",
                                "show", f"{head}:{path}"], capture_output=True, text=True)
        if shown.returncode != 0:
            return None
        raw = shown.stdout
    else:
        fp = repo / path
        if not fp.is_file():
            return None
        raw = fp.read_text(encoding="utf-8", errors="replace")
    return ingest.doc_surface(raw, path) or None


def _embed_resilient(embedder, texts: list[str], stats: dict, on_success=None):
    """Embed ``texts`` in adaptive batches, halving the batch on a 429 (LS-4058).

    ``stats["batch"]`` is the working batch for the pass: it starts at the
    configured/CLI batch, halves on each ``rate_limited`` failure, and the size
    that last worked stays in force for the rest of the run.
    ``stats["rate_limit_retries"]`` counts one per 429-triggered
    halving-and-retry. The pending texts are re-chunked at the smaller size
    after each halving; a one-input request that still answers 429 re-raises,
    leaving the cooldown armed for later read-path callers. The cooldown armed
    by *this* 429 is cleared for the retry (via ``clear_cooldown`` when the
    embedder exposes it), never a pre-existing one: a drain that starts inside
    a cooldown sees ``reason="cooldown"`` and fails without clearing it.

    ``on_success(offset, vectors)`` runs after every successful subrequest, so a
    caller can commit those exact rows before attempting the remainder — a later
    failure must never discard paid vectors (LS-4075 R2). ``offset`` is the
    input index of the first vector in ``vectors``. Returns the vectors in
    input order.
    """
    vectors: list[list[float]] = []
    pending = list(texts)
    offset = 0
    while pending:
        size = min(stats["batch"], len(pending))
        try:
            got = embedder.embed(pending[:size])
        except embed_mod.EmbeddingError as exc:
            if getattr(exc, "provider_code", None):
                stats["provider_code"] = exc.provider_code
            if getattr(exc, "provider_type", None):
                stats["provider_type"] = exc.provider_type
            if getattr(exc, "reason", None) != "rate_limited" or size <= 1:
                raise
            stats["batch"] = max(1, stats["batch"] // 2)
            stats["rate_limit_retries"] += 1
            clear = getattr(embedder, "clear_cooldown", None)
            if clear is not None:
                clear()
            step = stats["rate_limit_retries"] - 1
            time.sleep(_RATE_LIMIT_BACKOFF_SECONDS[
                min(step, len(_RATE_LIMIT_BACKOFF_SECONDS) - 1)])
            continue
        vectors.extend(got)
        if on_success is not None and got:
            on_success(offset, got)
        offset += len(got)
        pending = pending[size:]
    return vectors


def embed_stale(idx: Index, repo: Path, embedder, *, batch: int = 128,
                budget: int | None = None) -> dict:
    """Async embed pass (U13): fill the dense vectors that lag lexical (AE5).

    Embeds only chunks/docs that have no vector yet — idempotent, resumable. Chunk
    text comes from the index; doc surfaces are recomputed from the committed file
    via ``ingest.doc_surface`` (so commit_note-written pages get a doc lane too).
    Holds the shared dense-maintenance exclusion, then the single-indexer lock;
    contention raises :class:`serialize.LockBusyError` before any provider call.

    ``budget`` (U26/LS-4075): when set, embed at most ``budget`` stale chunks and
    at most ``budget`` missing doc-surface vectors this call, leaving the rest for
    the next call — the scheduled tick uses ``--batch 32 --budget 32``. Because
    each lane only ever processes *missing* items, capping a slice stays
    idempotent and resumable. ``None`` preserves the manual full-drain behavior
    (and the analytical ``ensure_full_coverage`` pass).

    Returns one honest report dict: ``status`` (complete/noop/budget_partial),
    actual per-lane counters, the effective batch, retry count, both remaining
    measurements, provider code/type (sanitized, reported-not-verified) and
    ``account_state: unverified``. A caught failure re-raises with the same
    counters attached as ``exc.progress`` so the CLI can report partial progress.
    """
    lock = serialize.dense_maintenance_lock(idx.db_path.parent).acquire()
    try:
        index_lock = serialize.FileLock(idx.db_path.parent / "index.lock").acquire()
        try:
            return embed_stale_locked(idx, repo, embedder, batch=batch, budget=budget)
        finally:
            index_lock.release()
    finally:
        lock.release()


def _embed_progress(idx, n_chunks: int, n_docs: int, stats: dict,
                    exc: Exception | None = None) -> dict:
    """Actual counters for a failed/interrupted run; unknown measurements stay None."""
    try:
        stale_left = len(idx.stale_chunk_ids())
    except Exception:
        stale_left = None
    try:
        docs_stale_left = len(idx.paths_missing_doc_vector())
    except Exception:
        docs_stale_left = None
    return {
        "chunks_embedded": n_chunks,
        "docs_embedded": n_docs,
        "effective_batch": stats["batch"],
        "rate_limit_retries": stats["rate_limit_retries"],
        "stale_left": stale_left,
        "docs_stale_left": docs_stale_left,
        "provider_code": getattr(exc, "provider_code", None) or stats.get("provider_code"),
        "provider_type": getattr(exc, "provider_type", None) or stats.get("provider_type"),
        "account_state": "unverified",
    }


def embed_stale_locked(idx: Index, repo: Path, embedder, *, batch: int = 128,
                       budget: int | None = None,
                       exclude_paths: set[str] | None = None) -> dict:
    """Lock-free core of :func:`embed_stale` — the caller MUST already hold the
    dense-maintenance exclusion and the single-indexer lock (``converge`` holds
    both for its bounded pass, so it cannot re-enter the public
    :func:`embed_stale`). Budget semantics: see :func:`embed_stale`.
    ``exclude_paths`` lets convergence keep authoring-host overlay rows lexical-only.

    Each successful adaptive subrequest commits its exact rows immediately, so a
    later failure keeps the paid vectors and the next tick resumes only what is
    still missing.
    """
    config.assert_embedder_agrees(embedder)
    repo = Path(repo)
    excluded = exclude_paths or set()
    stale = idx.stale_chunk_ids()
    if budget is not None:
        stale = stale[:budget]
    stats: dict = {"batch": batch, "rate_limit_retries": 0}
    n_chunks = 0
    n_docs = 0

    try:
        for i in range(0, len(stale), batch):
            ids = stale[i:i + batch]
            rows = idx.conn.execute(
                f"SELECT chunk_id, text, path FROM chunks WHERE chunk_id IN "
                f"({','.join('?' * len(ids))})", ids).fetchall()
            if excluded:
                rows = [r for r in rows if r[2] not in excluded]
            if not rows:
                continue

            def _commit_chunks(offset, vecs, rows=rows):
                nonlocal n_chunks
                for (cid, _text, _path), vec in zip(
                        rows[offset:offset + len(vecs)], vecs, strict=True):
                    idx.conn.execute(
                        "INSERT OR REPLACE INTO vec_chunks (chunk_id, embedding) "
                        "VALUES (?, ?)", (cid, sqlite_vec.serialize_float32(vec)))
                idx.conn.commit()
                n_chunks += len(vecs)

            _embed_resilient(embedder, [r[1] for r in rows], stats,
                             on_success=_commit_chunks)

        missing_docs = idx.paths_missing_doc_vector()
        if excluded:
            missing_docs = [p for p in missing_docs if p not in excluded]
        if budget is not None:
            missing_docs = missing_docs[:budget]
        docs: list[tuple[str, str]] = []
        for path in missing_docs:
            surface = _doc_surface_for_projection(repo, path)
            if surface:
                docs.append((path, surface))

        def _commit_docs(offset, vecs):
            nonlocal n_docs
            idx.add_docs(docs[offset:offset + len(vecs)], vecs)
            n_docs += len(vecs)

        if docs:
            _embed_resilient(embedder, [s for _, s in docs], stats,
                             on_success=_commit_docs)
    except Exception as exc:
        # Attach real counters for every caught failure, not only EmbeddingError:
        # a storage/report fault after a committed subrequest must never report 0.
        try:
            exc.progress = _embed_progress(
                idx, n_chunks, n_docs, stats,
                exc if isinstance(exc, embed_mod.EmbeddingError) else None)
        except Exception:
            pass
        raise

    stale_left = len(idx.stale_chunk_ids())
    docs_stale_left = len(idx.paths_missing_doc_vector())
    if stale_left == 0 and docs_stale_left == 0:
        status = "noop" if n_chunks == 0 and n_docs == 0 else "complete"
        reason = None
    elif budget is not None:
        status, reason = "budget_partial", "budget"
    else:
        status = "budget_partial"
        reason = "excluded_paths" if excluded else "stale_remaining"
    return {
        "status": status,
        "chunks_embedded": n_chunks,
        "docs_embedded": n_docs,
        "effective_batch": stats["batch"],
        "rate_limit_retries": stats["rate_limit_retries"],
        "stale_left": stale_left,
        "docs_stale_left": docs_stale_left,
        "reason": reason,
        "provider_code": stats.get("provider_code"),
        "provider_type": stats.get("provider_type"),
        "account_state": "unverified",
    }


_EMBED_REPORT_STATUSES = frozenset(
    {"complete", "noop", "budget_partial", "lock_busy", "failed"})


def validate_embed_report(report: dict) -> list[str]:
    """Return the contract violations of a would-be ``embed --json`` report.

    The native CLI refuses to emit/return0 on an invalid report: an unvalidated
    "success" object is a reporting failure, not a completion claim.
    """
    if not isinstance(report, dict):
        return ["report is not a JSON object"]
    errors: list[str] = []
    status = report.get("status")
    if status not in _EMBED_REPORT_STATUSES:
        errors.append("status")
    counters = {}
    for key in ("chunks_embedded", "docs_embedded", "rate_limit_retries"):
        value = report.get(key)
        counters[key] = value
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(key)
    batch = report.get("effective_batch")
    if not isinstance(batch, int) or isinstance(batch, bool) or batch < 1:
        errors.append("effective_batch")
    remaining = {}
    for key in ("stale_left", "docs_stale_left"):
        value = report.get(key)
        remaining[key] = value
        if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0):
            errors.append(key)
    reason = report.get("reason")
    if reason is not None and not isinstance(reason, str):
        errors.append("reason")
    for key in ("provider_code", "provider_type"):
        value = report.get(key)
        if value is not None and embed_mod.sanitize_provider_scalar(value) is None:
            errors.append(key)
    if report.get("account_state") != "unverified":
        errors.append("account_state")

    left = (remaining.get("stale_left"), remaining.get("docs_stale_left"))
    done = (counters.get("chunks_embedded"), counters.get("docs_embedded"))
    if status in ("complete", "noop") and left != (0, 0):
        errors.append("remaining")
    if status == "complete" and done == (0, 0):
        errors.append("counters")
    if status == "noop" and done != (0, 0):
        errors.append("counters")
    if status == "budget_partial" and not any(isinstance(v, int) and v > 0 for v in left):
        errors.append("remaining")
    if status == "lock_busy" and done != (0, 0):
        errors.append("counters")
    if status == "failed" and not isinstance(reason, str):
        errors.append("reason")
    return errors


def ensure_full_coverage(idx: Index, repo: Path, embedder) -> bool:
    """Full (unbudgeted) embed so ``note_vectors()`` reflects every chunk before an
    analytical read (U30/FR-R39 — salience centrality + connection similarity must
    not silently compute on a half-embedded corpus).

    Returns coverage completeness (FR-R40): ``True`` when no stale chunk remains;
    ``False`` when the embedder is absent or fails mid-fill (e.g. API down) — the
    analytical result is then partial, and the caller surfaces that. Best-effort
    under lock contention: a busy lock leaves coverage partial rather than blocking.
    """
    if not idx.stale_chunk_ids():
        return True                          # already complete — nothing to fill
    if embedder is None or repo is None:
        return False                         # cannot fill → partial
    try:
        embed_stale(idx, repo, embedder, budget=None)   # unbounded analytical pass
    except Exception:
        pass                                 # embedder down / lock busy → partial coverage
    return not idx.stale_chunk_ids()


def reindex_isolated(repo: Path, embedder, *, state_dir: Path | None = None) -> dict:
    """Broad reindex without blocking narrow writers (U14, KTD9/U12).

    Builds a fresh index from a clean ``git worktree`` at HEAD — the long phase
    runs lock-free against its OWN state dir, so concurrent ``commit_note`` writers
    (which hold the *live* lock) are not blocked. Then takes the live lock only for
    a millisecond ``os.replace`` swap. Falls back to an in-place locked rebuild when
    git/worktree is unavailable. The build db lives beside the live db (same
    filesystem) so the swap is atomic.
    """
    config.assert_embedder_agrees(embedder)
    repo = Path(repo)
    live_state = Path(state_dir) if state_dir else state_dir_for(repo)
    live_state.mkdir(mode=0o700, parents=True, exist_ok=True)
    live_db = live_state / "index.db"
    head = _git_head(repo)
    # Full lifetime admission: the whole build (not just its swap) excludes every
    # other dense-fill/bulk entrypoint. Narrow writers keep using index.lock.
    maintenance = serialize.dense_maintenance_lock(live_state).acquire()
    try:
        return _reindex_isolated_admitted(
            repo, embedder, live_state=live_state, live_db=live_db, head=head)
    finally:
        maintenance.release()


def _reindex_isolated_admitted(repo, embedder, *, live_state: Path,
                               live_db: Path, head: str | None) -> dict:
    wt = None
    if head:
        wt = Path(tempfile.mkdtemp(prefix="hypermnesic-reindex-"))
        rc = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", "--force", str(wt), head],
            capture_output=True, text=True)
        if rc.returncode != 0:
            shutil.rmtree(wt, ignore_errors=True)
            wt = None
    if wt is None:  # no git / worktree unsupported → in-place locked rebuild
        _build_index_locked(repo, embedder, state=live_state, db_path=live_db,
                            rebuild=True).close()
        return {"status": "fallback-inplace", "to": head}

    build_state = live_state / ".reindex-build"
    try:
        shutil.rmtree(build_state, ignore_errors=True)
        # Build in the private state dir: it locks build_state/index.lock — NOT the
        # live lock — so the long build phase never blocks live writers. The
        # already-held maintenance exclusion is reused, never re-acquired.
        _build_index_locked(wt, embedder, state=build_state,
                            db_path=build_state / "index.db", rebuild=True).close()
        new_db = build_state / "index.db"
        lock = serialize.FileLock(live_state / "index.lock").acquire()  # brief swap lock
        try:
            os.replace(new_db, live_db)   # atomic (same filesystem)
        finally:
            lock.release()
        return {"status": "reindexed", "to": head}
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                       capture_output=True, text=True)
        shutil.rmtree(wt, ignore_errors=True)
        shutil.rmtree(build_state, ignore_errors=True)


def apply_working_tree_overlay(idx: Index, repo: Path) -> list[str]:
    """Authoring-host overlay (R16): index uncommitted/untracked markdown so
    in-progress notes are findable before commit. Does NOT advance the checkpoint
    — a replica indexing the same committed SHA never sees these edits.
    """
    repo = Path(repo)
    out = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=false",
                          "status", "--porcelain"],
                         capture_output=True, text=True, check=True).stdout
    paths = set()
    for line in out.splitlines():
        p = line[3:]
        if "->" in p:                       # rename: take the new path
            p = p.split("->")[-1].strip()
        p = p.strip().strip('"')
        if _is_md(p):
            paths.add(p)
    for p in sorted(paths):
        fp = repo / p
        if fp.exists():
            idx.upsert_lexical(p, ingest.chunks_for_text(
                p, fp.read_text(encoding="utf-8", errors="replace")))
        else:
            idx.remove_path(p)
    return sorted(paths)


def build_index(repo: Path, embedder, *, rebuild: bool = True,
                state_dir: Path | None = None) -> Index:
    """Full-scan build of the index over ``repo`` using ``embedder``.

    Full-scan-on-startup is acceptable for Phase 0; the checkpoint slot exists
    so Phase 1 can extend to delta-replay.

    By default the index lives in ``repo/.hypermnesic/`` (the design, ignored via
    ``.git/info/exclude``). Pass ``state_dir`` to keep the state entirely outside
    the indexed repo — used for the read-only gbrain-brain corpus so the
    canonical checkout is never written to in any way.

    The whole build holds the shared dense-maintenance exclusion (non-blocking),
    so a scheduled drain and a full build can never spend provider calls against
    each other. Contention raises ``serialize.LockBusyError`` before any call.
    """
    config.assert_embedder_agrees(embedder)
    repo = Path(repo)
    external = state_dir is not None
    state = Path(state_dir) if external else state_dir_for(repo)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    if not external:
        ensure_ignored(repo)
    maintenance = serialize.dense_maintenance_lock(state).acquire()
    try:
        return _build_index_locked(repo, embedder, state=state,
                                   db_path=state / "index.db", rebuild=rebuild)
    finally:
        maintenance.release()


def _build_index_locked(repo, embedder, *, state: Path, db_path: Path,
                        rebuild: bool) -> Index:
    """Admitted build core — the caller already holds the maintenance exclusion."""
    lock = serialize.FileLock(state / "index.lock").acquire()  # single indexer (KTD9)
    try:
        if rebuild and db_path.exists():   # destroy the old index only once locked
            db_path.unlink()
        return _build_locked(repo, embedder, db_path)
    finally:
        lock.release()


def _build_locked(repo, embedder, db_path) -> Index:
    idx = Index(db_path)
    os.chmod(db_path, 0o600)
    idx.create_schema()

    batch: list[ingest.Chunk] = []

    def _flush():
        if not batch:
            return
        vectors = embedder.embed([c.text for c in batch])
        idx.add_documents(batch, vectors)
        batch.clear()

    for chunk in ingest.iter_chunks(repo):
        batch.append(chunk)
        if len(batch) >= _BATCH:
            _flush()
    _flush()

    # doc-level lane: one embedding per document (UA — representation parity)
    doc_batch: list[tuple[str, str]] = []

    def _flush_docs():
        if not doc_batch:
            return
        vectors = embedder.embed([s for _, s in doc_batch])
        idx.add_docs(doc_batch, vectors)
        doc_batch.clear()

    for path, surface in ingest.iter_doc_surfaces(repo):
        doc_batch.append((path, surface))
        if len(doc_batch) >= _BATCH:
            _flush_docs()
    _flush_docs()

    idx.set_checkpoint(_git_head(repo))
    return idx
