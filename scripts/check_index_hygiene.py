"""LS-4167 G4 — opt-in operator gate: index-hygiene census + five-query replay.

Read-only on ``--source`` (SQLite ``mode=ro`` then a backup to ``before.db``),
a scratch clone of the frozen ``meta.checkpoint_sha``, one real isolated
candidate rebuild of that clone, and a three-arm replay. It spends provider
money (the rebuild embeds the corpus) and must run only under an owner grant;
nothing here is a service, scheduler, CLI verb or schema migration.

Usage (build lane, after the grant):

    uv run python scripts/check_index_hygiene.py \
        --source <vault> --work-dir <fresh-private-dir> --base-rev "$BASE_REV"

Exit 0 and ``index_hygiene: PASS`` only when every census and replay check
holds; any mismatch prints its reason and exits nonzero.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

from hypermnesic import config, embed, ingest, retrieve
from hypermnesic import index as index_mod

# The five proof queries: (query, acceptable canonical targets, is LS-4002 case).
QUERIES = (
    ("pre-commit hook refuses commit",
     ("docs/plans/2026-09-04-001-fix-vault-commit-gate-portable-time-bound-plan.md",
      "projects/homelab/services/hermes-agent.md"), False),
    ("Paraphe decision inbox", ("projects/paraphe/README.md",), False),
    ("worktree sparse-checkout", ("projects/homelab/LOG.md", "AGENTS.md"), False),
    ("spec plan groom", ("projects/homelab/services/personal-skills.md",), True),
    ("hermes kanban",
     ("projects/homelab/runbooks/hermes-kanban-board-operator-guide.md",
      "projects/homelab/runbooks/dispatcher-pause-external-recovery.md"), True),
)

CLASSES = ("non_knowledge", "archive", "review", "reports_state", "openwiki", "primary")
TABLES = ("docs", "chunks")

BASE_DRIVER = '''
import json
import sys

sys.path.insert(0, {src!r})

from hypermnesic import index, retrieve  # noqa: E402


class Stub:
    model = "operator-gate-stub"
    dim = {dim}

    def __init__(self, vector):
        self.vector = vector

    def embed(self, texts):
        return [list(self.vector) for _ in texts]


db, query, qvec, k = json.loads(sys.argv[1])
idx = index.Index(db)
try:
    res = retrieve.search(idx, query, embedder=Stub(qvec), k=k)
    print(json.dumps([{{"path": h.path, "chunk_id": h.chunk_id, "score": h.score}}
                      for h in res.hits]))
finally:
    idx.close()
'''


class StubEmbedder:
    """The same query vector for every arm, so the arms differ only by code/corpus."""

    model = "operator-gate-stub"
    dim = config.EMBED_DIM

    def __init__(self, vector: list[float]):
        self.vector = vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(self.vector) for _ in texts]


class CensusError(RuntimeError):
    pass


def _run(args: list[str], *, check: bool = True, input: bytes | None = None):
    cp = subprocess.run(args, input=input, capture_output=True)
    if check and cp.returncode != 0:
        raise CensusError(f"{' '.join(args)} failed: {cp.stderr.decode(errors='replace')}")
    return cp


def _git(repo: Path, *args: str, check: bool = True, input: bytes | None = None):
    return _run(["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
                check=check, input=input)


def _table_counts(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    rows = conn.execute(f"SELECT path, COUNT(*) FROM {table} GROUP BY path").fetchall()
    return {path: count for path, count in rows}


def _census_class(path: str) -> str:
    parts = path.split("/")
    if ".brv" in parts[:-1] or ".worktrees" in parts[:-1] or any(
            part in ingest._SKIP_DIRS for part in parts[:-1]):
        return "non_knowledge"
    return retrieve.path_authority(path)


def _tree_modes(scratch: Path, sha: str) -> dict[str, bytes]:
    out = _git(scratch, "ls-tree", "-r", "-z", sha).stdout
    modes: dict[str, bytes] = {}
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, sep, raw = rec.partition(b"\t")
        fields = meta.split(b" ")
        if sep and len(fields) == 3:
            modes[os.fsdecode(raw)] = fields[0]
    return modes


def _ignored_at_head(scratch: Path, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    cp = _git(scratch, "-c", "core.excludesFile=/dev/null", "check-ignore",
              "--no-index", "--stdin", "-z", check=False,
              input=b"\0".join(os.fsencode(p) for p in paths) + b"\0")
    if cp.returncode not in (0, 1):
        raise CensusError(f"git check-ignore failed: {cp.stderr.decode(errors='replace')}")
    return {os.fsdecode(rec) for rec in cp.stdout.split(b"\0") if rec}


def _reasoner(scratch: Path, sha: str, paths: list[str]):
    tree = _tree_modes(scratch, sha)
    ignored = _ignored_at_head(scratch, paths)

    def reason(path: str) -> str:
        dirs = path.split("/")[:-1]
        if path in ignored:
            return "ignored"
        if ".brv" in dirs or any(part in ingest._SKIP_DIRS for part in dirs):
            return "hard_skip"
        if path not in tree:
            return "untracked" if (scratch / path).exists() else "missing"
        if tree[path] not in (b"100644", b"100755") or not (scratch / path).is_file():
            return "nonregular"
        return "ignored"          # tracked + regular + on disk, yet denied by a rule

    return reason


def _row_census(table: str, before: dict[str, int], after: dict[str, int],
                admitted: set[str], reason) -> dict:
    stats = {cls: {"kept": 0, "demoted": 0, "skipped": 0, "added": 0,
                   "content_delta": 0, "skipped_reasons": {}} for cls in CLASSES}
    for path, count in before.items():
        cls = _census_class(path)
        bucket = stats[cls]
        if path not in admitted:
            bucket["skipped"] += count
            why = reason(path)
            bucket["skipped_reasons"][why] = bucket["skipped_reasons"].get(why, 0) + count
            continue
        bucket["kept" if cls == "primary" else "demoted"] += count
        bucket["content_delta"] += after.get(path, 0) - count
    for path, count in after.items():
        if path not in before:
            stats[_census_class(path)]["added"] += count
    for cls, bucket in stats.items():
        assert bucket["skipped_reasons"] or not bucket["skipped"], (table, cls)
    return stats


def _expected_counts(scratch: Path, admitted: set[str]) -> tuple[dict, dict]:
    docs: dict[str, int] = {}
    chunks: dict[str, int] = {}
    for path in sorted(admitted):
        try:
            raw = (scratch / path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise CensusError(f"cannot read frozen {path}: {exc}") from exc
        n = len(ingest.chunks_for_text(path, raw))
        if n:
            chunks[path] = n
        if ingest.doc_surface(raw, path):
            docs[path] = 1
    return docs, chunks


def _orphans(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "orphan_fts": conn.execute(
            "SELECT COUNT(*) FROM fts_chunks WHERE rowid NOT IN "
            "(SELECT chunk_id FROM chunks)").fetchone()[0],
        "orphan_vec_chunks": conn.execute(
            "SELECT COUNT(*) FROM vec_chunks WHERE chunk_id NOT IN "
            "(SELECT chunk_id FROM chunks)").fetchone()[0],
        "orphan_vec_docs": conn.execute(
            "SELECT COUNT(*) FROM vec_docs WHERE doc_id NOT IN "
            "(SELECT doc_id FROM docs)").fetchone()[0],
    }


def _hard_paths(counts: dict[str, int]) -> int:
    return sum(n for path, n in counts.items()
               if ".brv" in path.split("/")[:-1] or ".worktrees" in path.split("/")[:-1])


def _arm(base_src: Path | None, db: Path, query: str, qvec: list[float],
         k: int = 10) -> list[dict]:
    if base_src is not None:
        driver = base_src.parent / "base_driver.py"
        payload = json.dumps([str(db), query, qvec, k])
        cp = _run([sys.executable, str(driver), payload])
        return json.loads(cp.stdout.decode())
    idx = index_mod.Index(db)
    try:
        res = retrieve.search(idx, query, embedder=StubEmbedder(qvec), k=k)
        return [{"path": h.path, "chunk_id": h.chunk_id, "score": h.score}
                for h in res.hits]
    finally:
        idx.close()


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LS-4167 G4 index-hygiene census + five-query replay (paid, opt-in).")
    parser.add_argument("--source", required=True, type=Path,
                        help="vault root whose .hypermnesic/index.db is read read-only")
    parser.add_argument("--work-dir", required=True, type=Path,
                        help="fresh private output dir (census.json, queries.json)")
    parser.add_argument("--base-rev", required=True,
                        help="pre-change integration revision (U0 BASE_REV)")
    args = parser.parse_args(argv)

    source: Path = args.source.resolve()
    work: Path = args.work_dir.resolve()
    source_db = source / ".hypermnesic" / "index.db"
    if not source_db.is_file():
        print(f"index_hygiene: FAIL — no index at {source_db}", file=sys.stderr)
        return 2
    if work.exists() and any(work.iterdir()):
        print(f"index_hygiene: FAIL — --work-dir must be fresh: {work}", file=sys.stderr)
        return 2
    work.mkdir(parents=True, exist_ok=True)

    head = _git(source, "rev-parse", "HEAD").stdout.decode().strip()
    _git(source, "cat-file", "-e", f"{args.base_rev}^{{commit}}")
    candidate = _git(Path(__file__).resolve().parents[1], "rev-parse", "HEAD",
                     check=False)
    candidate_sha = candidate.stdout.decode().strip() or "unknown"

    # 1. Read-only snapshot of the live projection.
    src = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    before_db = work / "before.db"
    dst = sqlite3.connect(before_db)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    before = sqlite3.connect(before_db)
    row = before.execute("SELECT value FROM meta WHERE key='checkpoint_sha'").fetchone()
    checkpoint = row[0] if row else None
    if not checkpoint or checkpoint != head:
        print(f"index_hygiene: FAIL — source drift: HEAD {head} != checkpoint "
              f"{checkpoint}", file=sys.stderr)
        return 2

    # 2. Independent scratch clone of the frozen checkpoint (no source writes).
    scratch = work / "scratch"
    _run(["git", "clone", "--no-local", "-q", str(source), str(scratch)])
    _git(scratch, "checkout", "-q", "--detach", checkpoint)
    if _git(scratch, "rev-parse", "HEAD").stdout.decode().strip() != checkpoint:
        print("index_hygiene: FAIL — scratch clone is not at the checkpoint", file=sys.stderr)
        return 2
    if _git(scratch, "status", "--porcelain").stdout.strip():
        print("index_hygiene: FAIL — scratch clone is not clean", file=sys.stderr)
        return 2

    # The pre-change code, extracted from the pinned base ref.
    base_src = work / "base-src"
    base_src.mkdir()
    archive = work / "base.tar"
    _git(scratch, "archive", "-o", str(archive), args.base_rev)
    with tarfile.open(archive) as tar:
        tar.extractall(base_src, filter="data")
    (base_src.parent / "base_driver.py").write_text(
        BASE_DRIVER.format(src=str(base_src / "src"), dim=config.EMBED_DIM),
        encoding="utf-8")

    # 3. One real isolated candidate rebuild of the scratch clone (paid).
    embedder = embed.OpenAIEmbedder(repo=scratch)
    state = work / "state"
    idx = index_mod.build_index(scratch, embedder, state_dir=state)
    idx.close()

    # 4. Census: frozen tree vs before/after projection, by path and class.
    admitted = ingest.admitted_paths_at(scratch, checkpoint)
    before_paths = {r[0] for r in before.execute(
        "SELECT path FROM chunks UNION SELECT path FROM docs").fetchall()}
    reason = _reasoner(scratch, checkpoint, sorted(before_paths | admitted))
    after = sqlite3.connect(state / "index.db")
    errors: list[str] = []
    census = {"source_sha": head, "candidate_sha": candidate_sha,
              "base_rev": args.base_rev, "checkpoint_sha": checkpoint,
              "tables": {}, "checks": {}}
    for table in TABLES:
        stats = _row_census(table, _table_counts(before, table),
                            _table_counts(after, table), admitted, reason)
        for cls, bucket in stats.items():
            bucket["before_total"] = (bucket["kept"] + bucket["demoted"]
                                      + bucket["skipped"])
            bucket["after_total"] = (bucket["kept"] + bucket["demoted"]
                                     + bucket["content_delta"] + bucket["added"])
            if cls == "non_knowledge" and bucket["after_total"]:
                errors.append(f"{table}: non_knowledge rows survived "
                              f"({bucket['after_total']})")
        census["tables"][table] = stats

    expected_docs, expected_chunks = _expected_counts(scratch, admitted)
    got_docs = _table_counts(after, "docs")
    got_chunks = _table_counts(after, "chunks")
    if got_docs != expected_docs:
        missing = sorted(set(expected_docs) - set(got_docs))
        extra = sorted(set(got_docs) - set(expected_docs))
        errors.append(f"docs path set mismatch: missing={missing[:5]} extra={extra[:5]}")
    if got_chunks != expected_chunks:
        missing = sorted(set(expected_chunks) - set(got_chunks))
        extra = sorted(set(got_chunks) - set(expected_chunks))
        errors.append(f"chunks path set mismatch: missing={missing[:5]} extra={extra[:5]}")
        for path in sorted(set(expected_chunks) & set(got_chunks)):
            if expected_chunks[path] != got_chunks[path]:
                errors.append(f"chunks count {path}: {got_chunks[path]} != "
                              f"{expected_chunks[path]}")

    ineligible_docs = sum(1 for p in got_docs if p not in admitted)
    ineligible_chunks = sum(1 for p in got_chunks if p not in admitted)
    checks = {
        "ineligible_docs": ineligible_docs,
        "ineligible_chunks": ineligible_chunks,
        **_orphans(after),
        "brv_worktrees_docs": _hard_paths(got_docs),
        "brv_worktrees_chunks": _hard_paths(got_chunks),
        "admitted_paths": len(admitted),
        "after_docs_paths": len(got_docs),
        "after_chunk_paths": len(got_chunks),
    }
    census["checks"] = checks
    for key, value in checks.items():
        if key == "admitted_paths" or key.startswith("after_"):
            continue
        if value:
            errors.append(f"{key}={value}, expected 0")
    _write_json(work / "census.json", census)

    # 5. Three-arm replay of the five proof queries with one query vector each.
    qvecs = embedder.embed([query for query, _targets, _ls4002 in QUERIES])
    rows = []
    for (query, targets, ls4002), qvec in zip(QUERIES, qvecs, strict=True):
        arms = {
            "base-before": _arm(base_src, before_db, query, qvec),
            "candidate-after": _arm(None, state / "index.db", query, qvec),
            "base-after": _arm(base_src, state / "index.db", query, qvec),
        }
        for hits in arms.values():
            for hit in hits:
                hit["class"] = _census_class(hit["path"])
        row = {"query": query, "canonical": list(targets), "ls4002": ls4002,
               "arms": arms}
        rows.append(row)

        top3 = arms["candidate-after"][:3]
        if not top3:
            errors.append(f"{query!r}: empty candidate result")
            continue
        if not all(retrieve.is_primary(hit["path"]) for hit in top3):
            errors.append(f"{query!r}: non-primary in top three "
                          f"{[hit['path'] for hit in top3]}")
        if not any(hit["path"] in targets for hit in top3):
            errors.append(f"{query!r}: canonical page absent from top three")
        base_before = arms["base-before"]
        if base_before and retrieve.is_primary(base_before[0]["path"]):
            winner = base_before[0]["path"]
            if winner in admitted and arms["candidate-after"][0]["path"] != winner:
                errors.append(f"{query!r}: primary #1 {winner} lost its position")
            base_after = arms["base-after"]
            if base_after and base_after[0]["path"] != winner:
                errors.append(f"{query!r}: base-on-rebuilt control #1 moved off {winner}")
        if ls4002:
            for name, hits in arms.items():
                if any(".worktrees" in hit["path"].split("/")[:-1] for hit in hits):
                    errors.append(f"{query!r}: .worktrees hit in {name}")
    _write_json(work / "queries.json", rows)

    before.close()
    after.close()
    if errors:
        for message in errors:
            print(f"index_hygiene: FAIL — {message}", file=sys.stderr)
        print(f"index_hygiene: FAIL ({len(errors)} mismatches; artifacts in {work})")
        return 1
    print(f"index_hygiene: PASS (candidate {candidate_sha}, source {head}, "
          f"base {args.base_rev}, artifacts {work})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
