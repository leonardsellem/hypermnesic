"""LS-4167 — one admission rule, atomic reconciliation, authority tiers.

R1: every index lane reads the same eligible path set (Git-tracked, .gitignore
aware, hard skips, regular files only). R2: a path that stops being eligible
loses every mirror atomically on the next successful pass. R3: archive/review/
generated copies are secondary; they never outrank a primary hit and never pad a
one/two-primary result.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import sqlite_vec

from hypermnesic import commit_note, config, converge, graph, index, ingest, retrieve

ZERO = {"chunks": 0, "fts": 0, "vec_chunks": 0, "docs": 0, "vec_docs": 0}


def _git(repo: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    return cp.stdout


def _commit(repo: Path, msg: str = "c") -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").strip()


def _rows(idx, path: str) -> dict:
    """Counts (and IDs) of every mirror row a path owns across the five tables."""
    c = idx.conn
    cids = [r[0] for r in c.execute("SELECT chunk_id FROM chunks WHERE path=?", (path,))]
    doc = c.execute("SELECT doc_id FROM docs WHERE path=?", (path,)).fetchone()
    doc_id = doc[0] if doc else None
    return {
        "chunks": len(cids),
        "fts": sum(1 for cid in cids if c.execute(
            "SELECT 1 FROM fts_chunks WHERE rowid=?", (cid,)).fetchone()),
        "vec_chunks": sum(1 for cid in cids if c.execute(
            "SELECT 1 FROM vec_chunks WHERE chunk_id=?", (cid,)).fetchone()),
        "docs": int(doc_id is not None),
        "vec_docs": int(doc_id is not None and c.execute(
            "SELECT 1 FROM vec_docs WHERE doc_id=?", (doc_id,)).fetchone() is not None),
        "chunk_ids": cids,
        "doc_id": doc_id,
    }


def _seed(idx, path: str, *, chunks: bool = True) -> tuple[int | None, int | None]:
    """Seed a historical row set by hand (old chunk/doc + vector IDs)."""
    c = idx.conn
    cid = None
    if chunks:
        cid = c.execute("INSERT INTO chunks (path, ord, heading, text) VALUES (?, 0, ?, ?)",
                        (path, "H", "SEEDBODY")).lastrowid
        c.execute("INSERT INTO fts_chunks (rowid, text) VALUES (?, ?)", (cid, "H\nSEEDBODY"))
        c.execute("INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                  (cid, sqlite_vec.serialize_float32([0.0] * config.EMBED_DIM)))
    doc_id = c.execute("INSERT INTO docs (path) VALUES (?)", (path,)).lastrowid
    c.execute("INSERT INTO vec_docs (doc_id, embedding) VALUES (?, ?)",
              (doc_id, sqlite_vec.serialize_float32([0.0] * config.EMBED_DIM)))
    c.commit()
    return (cid, doc_id)


def _finds(idx, term: str, path: str) -> bool:
    return any(idx.get_chunk(cid)["path"] == path for cid, _ in idx.lexical_search(term, k=10))


# --- G1: one admission rule across every writer ------------------------------

GITIGNORE = ("force.md\n"          # root rule, re-added with -f
             "excl/\n!excl/keep.md\n"   # excluded parent: the negation cannot re-include
             "notes/*.md\n!notes/keep.md\n"  # reachable negation DOES re-include
             "vendor/\n")           # directory-only rule: never the file `vendor.md`


def _admission_corpus(make_corpus):
    repo = make_corpus({
        "canon.md": "# Canon\n\nCANONBODY canonical page.\n",
        "force.md": "# Force\n\nFORCEBODY force added but ignored.\n",
        "excl/keep.md": "# Excl keep\n\nEXCLBODY excluded parent.\n",
        "notes/drop.md": "# Drop\n\nDROPBODY nested rule excludes me.\n",
        "notes/keep.md": "# Notes keep\n\nKEEPBODY reachable negation.\n",
        "vendor/x.md": "# Vendor\n\nVENDORBODY ignored directory.\n",
        "vendor.md": "# Vendor page\n\nVENDORPAGE a regular file, not the directory.\n",
    }, gitignore=GITIGNORE)
    # Track even the ignored files: a tracked-but-ignored entry is still excluded by R1.
    _git(repo, "add", "-f", "force.md", "excl/keep.md", "notes/drop.md", "vendor/x.md")
    _git(repo, "commit", "-q", "-m", "force add ignored")
    return repo


def test_git_admission_across_writers(make_corpus, fake_embedder, monkeypatch):
    repo = _admission_corpus(make_corpus)
    head = _git(repo, "rev-parse", "HEAD").strip()
    expected = {"canon.md", "notes/keep.md", "vendor.md"}

    # one admission result, every reader lane
    assert ingest.enumerate_markdown(repo) == expected
    assert ingest.admitted_paths_at(repo, head) == expected
    assert {c.path for c in ingest.iter_chunks(repo)} == expected
    assert {p for p, _ in ingest.iter_doc_surfaces(repo)} == expected
    assert graph.Graph.from_repo(repo).nodes == expected

    idx = index.build_index(repo, fake_embedder)
    assert idx.indexed_paths() == expected
    assert not ({"force.md", "excl/keep.md", "notes/drop.md", "vendor/x.md"}
                & idx.indexed_paths())

    # incremental: a committed edit to an ignored path cannot resurrect it
    (repo / "force.md").write_text("# Force\n\nFORCEBODY edited.\n", encoding="utf-8")
    _commit(repo, "edit ignored")
    res = index.catch_up(idx, repo)
    assert res["status"] == "replayed"
    assert "force.md" not in idx.indexed_paths()

    # staged draft: lexical preview only, no checkpoint advance
    (repo / "staged.md").write_text("# Staged\n\nSTAGEDWORD body.\n", encoding="utf-8")
    _git(repo, "add", "staged.md")
    (repo / "draft.md").write_text("# Draft\n\nDRAFTWORD body.\n", encoding="utf-8")
    checkpoint = idx.get_checkpoint()
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                            authoring_host=True)
    assert res.status == "converged"
    assert "staged.md" in res.overlay_paths
    assert _finds(idx, "STAGEDWORD", "staged.md")
    assert "draft.md" not in idx.indexed_paths() and not _finds(idx, "DRAFTWORD", "draft.md")
    assert idx.get_checkpoint() == checkpoint
    assert res.chunks_embedded == 0
    # the standalone dense drain cannot embed the staged draft either
    staged_ids = set(idx.chunks_for_path("staged.md"))
    assert staged_ids and staged_ids.issubset(set(idx.stale_chunk_ids()))
    emb = index.embed_stale(idx, repo, fake_embedder, budget=64)
    assert emb["chunks_embedded"] == 0
    assert staged_ids.issubset(set(idx.stale_chunk_ids()))

    # a dirty ignore rule: replica keeps the pinned membership, authoring applies it
    (repo / ".gitignore").write_text(GITIGNORE + "canon.md\n", encoding="utf-8")
    assert index.catch_up(idx, repo)["status"] == "current"
    assert "canon.md" in idx.indexed_paths()
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                            authoring_host=True)
    assert res.status == "converged"
    assert "canon.md" not in idx.indexed_paths()
    assert _rows(idx, "canon.md") == {**ZERO, "chunk_ids": [], "doc_id": None}

    # undoing a dirty tracked edit restores committed recall at unchanged HEAD
    (repo / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (repo / "canon.md").write_text("# Canon\n\nDRAFTEDIT body.\n", encoding="utf-8")
    converge.converge(repo, idx, fake_embedder, debounce_seconds=0, authoring_host=True)
    assert _finds(idx, "DRAFTEDIT", "canon.md")
    (repo / "canon.md").write_text("# Canon\n\nCANONBODY canonical page.\n", encoding="utf-8")
    converge.converge(repo, idx, fake_embedder, debounce_seconds=0, authoring_host=True)
    assert _finds(idx, "CANONBODY", "canon.md")
    assert not _finds(idx, "DRAFTEDIT", "canon.md")

    # an unreadable applicable ignore file refuses the pass: no prune, no advance
    (repo / "notes" / "keep.md").unlink()
    checkpoint = idx.get_checkpoint()

    def _unreadable(fp):
        raise ingest.AdmissionError(f"simulated unreadable {fp}")

    monkeypatch.setattr(ingest, "_read_ignore_file", _unreadable)
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                            authoring_host=True)
    assert res.status == "enumeration_failed" and res.degraded
    assert _rows(idx, "notes/keep.md")["chunks"] > 0        # not pruned
    assert idx.get_checkpoint() == checkpoint
    monkeypatch.undo()

    # synchronous projection: an excluded path is never upserted by a landed write
    assert commit_note._upsert_index_best_effort(idx, repo, "force.md", "# x\n\nX.\n") is None
    assert "force.md" not in idx.indexed_paths()
    (repo / "force.md").write_text("# Force\n\nFORCEBODY written again.\n", encoding="utf-8")
    result = commit_note.commit_note(repo, "force.md", body="FORCEBODY written again.\n",
                                     summary="edit ignored note", idx=idx)
    assert result.new_sha and not result.index_degraded
    assert "force.md" not in idx.indexed_paths()            # no resurrection, no failure
    idx.close()


def test_standalone_markdown_without_git(make_corpus, fake_embedder):
    repo = make_corpus({
        "notes/plain.md": "# Plain\n\nSTANDALONEMARK body.\n",
        "notes/skip.md": "# Skip\n\nSKIPMARK body.\n",
        "node_modules/pkg/readme.md": "# Dep\n\nDEPMARK.\n",
    }, git=False, gitignore="notes/skip.md\n")
    (repo / "link.md").symlink_to(repo / "notes" / "plain.md")

    expected = {"notes/plain.md"}
    assert ingest.enumerate_markdown(repo) == expected       # no tracking requirement
    assert graph.Graph.from_repo(repo).nodes == expected

    idx = index.build_index(repo, fake_embedder)
    assert idx.indexed_paths() == expected
    res = retrieve.search(idx, "STANDALONEMARK", embedder=fake_embedder, k=5)
    assert [h.path for h in res.hits] == ["notes/plain.md"]

    (repo / "notes" / "plain.md").unlink()                   # vanished, no Git lane
    res = index.catch_up(idx, repo)
    assert res["status"] == "no-git"
    assert "notes/plain.md" not in idx.indexed_paths()
    idx.close()


# --- G2: existing rows, not just a fresh scan --------------------------------

def test_ignore_added_after_ingest(make_corpus, fake_embedder):
    repo = make_corpus({
        "notes/a.md": "# A\n\nALPHAKEEP body.\n",
        "control.md": "# Control\n\nCONTROLBODY.\n",
    })
    (repo / "notes" / "b.md").write_text("# B\n\nBETALATE body.\n", encoding="utf-8")
    _git(repo, "add", "-f", "notes/b.md")
    _git(repo, "commit", "-q", "-m", "force b")
    idx = index.build_index(repo, fake_embedder)
    keep_ids = _rows(idx, "notes/a.md")
    assert keep_ids["chunks"] and keep_ids["docs"] and keep_ids["vec_docs"]
    control_before = (repo / "control.md").read_bytes()

    (repo / ".gitignore").write_text("notes/\n", encoding="utf-8")   # uncommitted rule
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                            authoring_host=True)
    assert res.status == "converged"
    assert _rows(idx, "notes/a.md") == {**ZERO, "chunk_ids": [], "doc_id": None}
    assert _rows(idx, "notes/b.md") == {**ZERO, "chunk_ids": [], "doc_id": None}
    for cid in keep_ids["chunk_ids"]:
        assert not idx.conn.execute("SELECT 1 FROM fts_chunks WHERE rowid=?", (cid,)).fetchone()
        assert not idx.conn.execute("SELECT 1 FROM vec_chunks WHERE chunk_id=?", (cid,)).fetchone()
    assert not idx.conn.execute("SELECT 1 FROM vec_docs WHERE doc_id=?",
                                (keep_ids["doc_id"],)).fetchone()
    assert (repo / "notes/a.md").exists() and (repo / "notes/b.md").exists()
    assert (repo / "control.md").read_bytes() == control_before
    assert _rows(idx, "control.md")["chunks"] > 0

    (repo / ".gitignore").unlink()                    # rule removed, Markdown unchanged
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                            authoring_host=True)
    assert res.status == "converged"
    assert _rows(idx, "notes/a.md")["chunks"] > 0
    assert _finds(idx, "ALPHAKEEP", "notes/a.md")     # re-admitted with unchanged bytes
    idx.close()


def test_deleted_file_loses_all_rows(make_corpus, fake_embedder):
    repo = make_corpus({
        "gone.md": "# Gone\n\nGONEBODY.\n",
        "control.md": "# Control\n\nCONTROLBODY.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    gone = _rows(idx, "gone.md")
    assert gone["chunks"] and gone["docs"]
    stale_cid, stale_doc = _seed(idx, "stale.md")     # deleted+committed before checkpoint
    ghost_cid, ghost_doc = _seed(idx, "ghost.md", chunks=False)   # docs-only record
    assert stale_cid and ghost_doc

    # replica, HEAD == checkpoint: stale historical rows leave without a delete event
    res = index.catch_up(idx, repo)
    assert res["status"] == "current"
    for path, cid, doc_id in (("stale.md", stale_cid, stale_doc),
                              ("ghost.md", ghost_cid, ghost_doc)):
        assert _rows(idx, path) == {**ZERO, "chunk_ids": [], "doc_id": None}
        assert not idx.conn.execute("SELECT 1 FROM chunks WHERE chunk_id=?", (cid,)).fetchone()
        assert not idx.conn.execute("SELECT 1 FROM docs WHERE doc_id=?", (doc_id,)).fetchone()
    assert _rows(idx, "gone.md")["chunks"] > 0        # replica control: still present

    # authoring deletion without a new commit loses every mirror
    (repo / "gone.md").unlink()
    res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                            authoring_host=True)
    assert res.status == "converged"
    assert _rows(idx, "gone.md") == {**ZERO, "chunk_ids": [], "doc_id": None}
    assert _rows(idx, "control.md")["chunks"] > 0

    # replica control: the file survives locally until its deletion is committed
    res = index.catch_up(idx, repo)
    assert _rows(idx, "gone.md")["chunks"] > 0        # pinned tree still has it
    (repo / "control.md").unlink()
    _commit(repo, "rm control")
    res = index.catch_up(idx, repo)
    assert res["status"] == "replayed"
    assert _rows(idx, "control.md") == {**ZERO, "chunk_ids": [], "doc_id": None}
    idx.close()


def test_prune_failure_rolls_back(make_corpus, fake_embedder, monkeypatch):
    repo = make_corpus({
        "drop/one.md": "# One\n\nONEBODY.\n",
        "drop/two.md": "# Two\n\nTWOBODY.\n",
        "keep.md": "# Keep\n\nKEEPBODY.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    checkpoint = idx.get_checkpoint()
    before = {p: _rows(idx, p) for p in ("drop/one.md", "drop/two.md", "keep.md")}
    assert all(before[p]["chunks"] and before[p]["docs"] for p in before)
    control_bytes = (repo / "keep.md").read_bytes()

    (repo / ".gitignore").write_text("drop/\n", encoding="utf-8")

    original = index.Index._remove_path_rows
    calls: list[str] = []

    def boom(self, path):
        original(self, path)
        calls.append(path)
        if len(calls) == 2:                 # mid-transaction, after the first deletes
            raise RuntimeError("injected prune failure")

    monkeypatch.setattr(index.Index, "_remove_path_rows", boom)
    try:
        converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                          authoring_host=True)
    except RuntimeError as exc:
        assert "injected" in str(exc)
    else:                                    # pragma: no cover - the injection must fire
        raise AssertionError("prune failure did not propagate")
    monkeypatch.undo()

    assert len(calls) >= 2
    for path in ("drop/one.md", "drop/two.md", "keep.md"):
        assert _rows(idx, path) == before[path]      # every delete rolled back
    assert idx.get_checkpoint() == checkpoint
    assert (repo / "keep.md").read_bytes() == control_bytes
    idx.close()


# --- G3: authority tiers -----------------------------------------------------

_SECONDARY_DIRS = ("_archive", "jude-scratch", "reports", "openwiki")

CASES = {
    "multi_primary": {
        "query": "pre-commit hook refuses commit",
        "files": {
            "canon-a.md": "# pre-commit hook refuses commit\n\nThe pre-commit hook "
                          "refuses commit without the bound. pre-commit hook refuses "
                          "commit.\n",
            "canon-b.md": "# Canon B note\n\nA long note that explains when the "
                          "pre-commit hook refuses commit and what to do about it in "
                          "practice, with the usual caveats and a few more words to "
                          "lengthen it.\n",
            "canon-c.md": "# Canon C note\n\nAnother note about the pre-commit hook "
                          "refuses commit behaviour in practice, phrased at some "
                          "length so the normalisation matters here too.\n",
            "_archive/old-a.md": "# Old copy\n\npre-commit hook refuses commit "
                                 "pre-commit hook refuses commit here.\n",
            "jude-scratch/log.md": "# Scratch\n\nthe pre-commit hook refuses commit here\n",
        },
        "primary": 3,
        "secondary": 2,
    },
    "single_primary": {
        "query": "Paraphe decision inbox",
        "files": {
            "projects/paraphe/README.md": "# Paraphe\n\nThe Paraphe decision inbox "
                                          "routes owner decisions.\n",
            "_archive/paraphe-old.md": "# Paraphe decision inbox\n\nParaphe decision "
                                       "inbox Paraphe decision inbox legacy copy.\n",
            "openwiki/paraphe.md": "# Paraphe decision inbox\n\nParaphe decision inbox "
                                   "generated page.\n",
        },
        "primary": 1,
        "secondary": 2,
    },
    "two_primary": {
        "query": "worktree sparse-checkout",
        "files": {
            "projects/homelab/LOG.md": "# Log\n\nworktree sparse-checkout notes from "
                                       "the homelab.\n",
            "AGENTS.md": "# Agents\n\nworktree sparse-checkout rules live here.\n",
            "_archive/wt.md": "# worktree sparse-checkout\n\nworktree sparse-checkout "
                              "worktree sparse-checkout old copy.\n",
            "reports/wt.md": "# Report\n\nworktree sparse-checkout generated report.\n",
        },
        "primary": 2,
        "secondary": 2,
    },
    "no_primary": {
        "query": "spec plan groom",
        "files": {
            "_archive/groom.md": "# spec plan groom\n\nspec plan groom old copy.\n",
            "openwiki/groom.md": "# spec plan groom\n\nspec plan groom generated.\n",
            "jude-scratch/groom.md": "# Scratch\n\nspec plan groom scratch notes.\n",
        },
        "primary": 0,
        "secondary": 3,
    },
    "duplicate_pair": {
        "query": "hermes kanban",
        "files": {
            "docs/hk-a.md": "# Kanban A\n\nThe hermes kanban board guide lives here.\n",
            "docs/hk-b.md": "# Kanban B\n\nAnother hermes kanban note lives here.\n",
            "docs/hk-dupe.md": "# Canonical hermes kanban\n\nThe hermes kanban "
                               "operator guide body.\n",
            "_archive/hk-dupe.md": "# hermes kanban hermes kanban hermes kanban\n\n"
                                   "The hermes kanban operator guide body.\n",
            "_archive/hk-other.md": "# hermes kanban\n\nan old hermes kanban note.\n",
        },
        "primary": 3,
        "secondary": 2,
    },
}

# Non-matching archive pages give bm25 a real IDF (a corpus where every page
# matches scores every page identically and the premise would be vacuous).
for _case in CASES.values():
    for _i in range(8):
        _case["files"][f"_archive/filler-{_i}.md"] = (
            f"# Unrelated archive note {_i}\n\nThis archive page discusses an "
            f"unrelated topic number {_i} with no matching phrase at all.\n")

DUPETEXT = "The hermes kanban operator guide body."


def _tier_blind_rerank(query, hits):
    """A reranker that ignores authority — applied per tier it must be a no-op."""
    return sorted(hits, key=lambda hit: hit.score, reverse=True)


def _corpus(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    for rel, body in files.items():
        fp = repo / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(body, encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _commit(repo, "fixture")
    return repo


def _assert_tiered(hits, primary_count: int, case: dict):
    classes = [retrieve.path_authority(h.path) == "primary" for h in hits]
    if primary_count >= 3:
        assert classes[:3] == [True, True, True], [h.path for h in hits]
        assert classes == sorted(classes, reverse=True)   # no secondary above a primary
    elif primary_count:
        assert len(hits) == primary_count, [h.path for h in hits]
        assert all(classes), [h.path for h in hits]
    else:
        assert hits and not any(classes), [h.path for h in hits]


def test_authority_tiers_preserve_primary_and_fallback(tmp_path, fake_embedder):
    for name, case in CASES.items():
        repo = _corpus(tmp_path, name, case["files"])
        idx = index.build_index(repo, fake_embedder)
        try:
            # lexical arm: exact scores/order allow premises AND no-score-change checks
            lexical = retrieve.search(idx, case["query"], embedder=None, k=10)
            ranks = {}
            for rank, (cid, _bm25) in enumerate(idx.lexical_search(case["query"], k=50)):
                ranks[idx.get_chunk(cid)["path"]] = rank
            assert len(ranks) == case["primary"] + case["secondary"], (name, ranks)

            if name == "multi_primary":
                assert ranks["canon-a.md"] == 0
                assert ranks["_archive/old-a.md"] < min(
                    ranks[p] for p in ("canon-b.md", "canon-c.md"))
            if name == "duplicate_pair":
                assert ranks["_archive/hk-dupe.md"] < ranks["docs/hk-dupe.md"]

            # unchanged scores and within-tier order (plain RRF, rerank disabled)
            expected = sorted(
                (p for p in ranks if retrieve.is_primary(p)), key=lambda p: ranks[p])
            got = [h.path for h in lexical.hits[:len(expected)]]
            assert got == expected, (name, got, expected)
            for hit in lexical.hits:
                assert hit.score == 1.0 / (retrieve._RRF_K0 + ranks[hit.path])
            _assert_tiered(lexical.hits, case["primary"], case)

            # a tier-blind reranker cannot lift a secondary above a primary
            reranked = retrieve.search(idx, case["query"], embedder=None, k=10,
                                       rerank=_tier_blind_rerank)
            _assert_tiered(reranked.hits, case["primary"], case)
            assert [h.chunk_id for h in reranked.hits] == [h.chunk_id for h in lexical.hits]

            # fake-dense arm: the same tier contract holds on a fused pool
            dense = retrieve.search(idx, case["query"], embedder=fake_embedder, k=10)
            _assert_tiered(dense.hits, case["primary"], case)

            if name == "duplicate_pair":
                # byte-identical primary/secondary pair: the primary copy keeps the
                # one slot that survives content dedup, in either ranking mode
                for embedder in (None, fake_embedder):
                    res = retrieve.search(idx, case["query"], embedder=embedder, k=10)
                    dupes = [h for h in res.hits if h.text == DUPETEXT]
                    assert len(dupes) == 1, [h.path for h in res.hits]
                    assert dupes[0].path == "docs/hk-dupe.md"
        finally:
            idx.close()


# --- Round-1 review findings: sparse omission, overlay ordering, rename-into-ignored ---


def test_sparse_omission_converges_instead_of_failing(make_corpus, fake_embedder):
    """P1: a skip-worktree path is absent by design, so the authoring pass projects
    its committed blob instead of returning blob_read_failed on every pass."""
    repo = make_corpus({
        "keep/present.md": "# Present\n\nPRESENTBODY page.\n",
        "drop/omitted.md": "# Omitted\n\nOMITTEDBODY sparse-omitted page.\n",
    })
    _git(repo, "sparse-checkout", "init", "--cone")
    _git(repo, "sparse-checkout", "set", "keep")
    assert not (repo / "drop" / "omitted.md").exists()         # the omission is real
    assert "drop/omitted.md" in ingest.missing_but_protected(repo)

    idx = index.build_index(repo, fake_embedder)
    assert "drop/omitted.md" not in idx.indexed_paths()
    try:
        res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                                authoring_host=True)
        assert res.status == "converged", res.degraded_reason
        assert _finds(idx, "OMITTEDBODY", "drop/omitted.md")
        assert idx.get_checkpoint() == _git(repo, "rev-parse", "HEAD").strip()
    finally:
        idx.close()


def test_overlay_enumeration_failure_prunes_nothing(make_corpus, fake_embedder, monkeypatch):
    """P2: the overlay set is resolved before the replay, so enumeration_failed
    cannot be reported after rows were already pruned."""
    repo = make_corpus({"keep.md": "# Keep\n\nKEEPBODY page.\n",
                        "gone.md": "# Gone\n\nGONEBODY page.\n"})
    idx = index.build_index(repo, fake_embedder)
    (repo / "gone.md").unlink()
    (repo / "keep.md").write_text("# Keep\n\nDRAFTBODY edit.\n", encoding="utf-8")
    checkpoint = idx.get_checkpoint()

    def _fail(_repo):
        raise ingest.AdmissionError("simulated dirty scan failure")

    monkeypatch.setattr(ingest, "dirty_paths", _fail)
    try:
        res = converge.converge(repo, idx, fake_embedder, debounce_seconds=0,
                                authoring_host=True)
        assert res.status == "enumeration_failed" and res.degraded
        assert _rows(idx, "gone.md")["chunks"] > 0             # not pruned
        assert idx.get_checkpoint() == checkpoint
    finally:
        idx.close()


def test_rename_into_excluded_dir_leaves_no_rows(make_corpus, fake_embedder):
    """P2: `git mv a.md hidden/b.md` must not rekey rows into an excluded path."""
    repo = make_corpus({"a.md": "# A\n\nABODY page.\n"}, gitignore="hidden/\n")
    idx = index.build_index(repo, fake_embedder)
    assert _finds(idx, "ABODY", "a.md")
    (repo / "hidden").mkdir(exist_ok=True)
    try:
        result = commit_note.rename_note(repo, "a.md", "hidden/b.md", idx=idx)
        assert result.new_sha and not result.index_degraded
        assert _rows(idx, "hidden/b.md")["chunks"] == 0
    finally:
        idx.close()


def _hygiene_driver():
    spec = importlib.util.spec_from_file_location(
        "check_index_hygiene",
        Path(__file__).resolve().parent.parent / "scripts" / "check_index_hygiene.py")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver


def test_g4_driver_reads_the_vec_tables(make_corpus, fake_embedder):
    """G4's census queries vec_chunks/vec_docs, so its connections must load sqlite-vec."""
    driver = _hygiene_driver()

    repo = make_corpus({"a.md": "# A\n\nABODY page.\n"})
    idx = index.build_index(repo, fake_embedder)
    db = idx.db_path
    idx.close()
    for conn in (driver._connect(db), driver._connect(db, ro=True)):
        try:
            assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] >= 1
        finally:
            conn.close()
    # a non-knowledge #1 (.brv) or one admission drops cannot anchor a position
    assert not driver._anchors([{"path": ".brv/context-tree/x.md"}], {".brv/context-tree/x.md"})
    assert not driver._anchors([{"path": "notes/a.md"}], set())
    assert driver._anchors([{"path": "notes/a.md"}], {"notes/a.md"})


def test_g4_canonical_clause_is_no_regression():
    """Owner-agreed G4 clause (Paraphe 4b284099): the canonical page must not regress."""
    driver = _hygiene_driver()
    page = "projects/homelab/services/personal-skills.md"
    filler = {"path": "notes/a.md"}
    base = [filler] * 19 + [{"path": page}]                 # #20 before
    assert driver._replay_errors("q", (page,), base, [filler] * 11 + [{"path": page}]) == []
    assert driver._replay_errors("q", (page,), [], [filler] * 9 + [{"path": page}]) == []
    # both outside the window is not a regression; leaving it is
    assert driver._replay_errors("q", (page,), [], [filler] * 3) == []
    assert "left the top" in driver._replay_errors(
        "q", (page,), base, [filler] * 3)[0]
    assert "regressed #13 -> #20" in driver._replay_errors(
        "q", (page,), [filler] * 12 + [{"path": page}], base)[0]
