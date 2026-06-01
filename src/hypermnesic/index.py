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
import sqlite3
import subprocess
from pathlib import Path

import sqlite_vec

from hypermnesic import config, ingest

STATE_DIRNAME = ".hypermnesic"
_BATCH = 128


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
        self.conn = sqlite3.connect(self.db_path)
        _load_vec(self.conn)

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
                "INSERT INTO fts_chunks (rowid, text) VALUES (?, ?)", (cid, ch.text)
            )
        c.commit()

    def add_docs(self, docs: list[tuple[str, str]], vectors: list[list[float]]) -> None:
        """docs: [(path, surface)] with parallel doc-surface embeddings."""
        assert len(docs) == len(vectors)
        c = self.conn
        for (path, _surface), vec in zip(docs, vectors, strict=True):
            cur = c.execute("INSERT OR IGNORE INTO docs (path) VALUES (?)", (path,))
            doc_id = cur.lastrowid
            if not doc_id:  # path already present
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

    def chunks_for_path(self, path: str) -> list[int]:
        return [r[0] for r in self.conn.execute(
            "SELECT chunk_id FROM chunks WHERE path=? ORDER BY chunk_id", (path,)).fetchall()]

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
        # with weak common-term matches and degrades fused ranking, so we keep
        # the precise phrase form and let dense own semantic recall.
        q = query_text.replace('"', " ").strip()
        if not q:
            return []
        rows = self.conn.execute(
            "SELECT rowid, bm25(fts_chunks) FROM fts_chunks "
            "WHERE fts_chunks MATCH ? ORDER BY bm25(fts_chunks) LIMIT ?",
            (f'"{q}"', k),
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

    def stats(self) -> dict:
        n = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_docs = self.conn.execute(
            "SELECT COUNT(DISTINCT path) FROM chunks"
        ).fetchone()[0]
        return {"chunks": n, "docs": n_docs, "checkpoint": self.get_checkpoint(),
                "model": config.EMBED_MODEL, "dim": config.EMBED_DIM}

    def close(self) -> None:
        self.conn.close()


def build_index(repo: Path, embedder, *, rebuild: bool = True,
                state_dir: Path | None = None) -> Index:
    """Full-scan build of the index over ``repo`` using ``embedder``.

    Full-scan-on-startup is acceptable for Phase 0; the checkpoint slot exists
    so Phase 1 can extend to delta-replay.

    By default the index lives in ``repo/.hypermnesic/`` (the design, ignored via
    ``.git/info/exclude``). Pass ``state_dir`` to keep the state entirely outside
    the indexed repo — used for the read-only gbrain-brain corpus so the
    canonical checkout is never written to in any way.
    """
    config.assert_embedder_agrees(embedder)
    repo = Path(repo)
    external = state_dir is not None
    state = Path(state_dir) if external else state_dir_for(repo)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    db_path = state / "index.db"
    if rebuild and db_path.exists():
        db_path.unlink()
    if not external:
        ensure_ignored(repo)

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
