"""U9 — index as a pure projection of the git tree (delta-replay + overlay)."""

from __future__ import annotations

import subprocess

from hypermnesic import index as ix


def _commit(repo, msg="c"):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def _finds(idx, term, path):
    return any(idx.get_chunk(c)["path"] == path for c, _ in idx.lexical_search(term, k=10))


def test_delta_replay_only_changed_files(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha original.\n", "b.md": "# B\n\nbeta stuff.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cp0 = idx.get_checkpoint()
    (repo / "a.md").write_text("# A\n\nalpha UPDATEDWORD gamma.\n", encoding="utf-8")
    (repo / "c.md").write_text("# C\n\ncharlie NEWFILE.\n", encoding="utf-8")
    head = _commit(repo, "edit a, add c")
    res = ix.catch_up(idx, repo)
    assert res["status"] == "replayed" and idx.get_checkpoint() == head != cp0
    assert _finds(idx, "UPDATEDWORD", "a.md")        # edited content replayed
    assert _finds(idx, "NEWFILE", "c.md")            # new file added
    assert not _finds(idx, "original", "a.md")       # stale content replaced
    idx.close()


def test_deleted_file_removed_on_replay(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n", "b.md": "# B\n\nbetaword stuff.\n"})
    idx = ix.build_index(repo, fake_embedder)
    (repo / "b.md").unlink()
    _commit(repo, "rm b")
    ix.catch_up(idx, repo)
    assert "b.md" not in idx.all_paths()
    assert not _finds(idx, "betaword", "b.md")
    idx.close()


def test_working_tree_overlay_findable_before_commit(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = ix.build_index(repo, fake_embedder)
    cp = idx.get_checkpoint()
    (repo / "a.md").write_text("# A\n\nalpha WORKINGTREEONLY delta.\n", encoding="utf-8")
    (repo / "draft.md").write_text("# Draft\n\nuntracked DRAFTWORD.\n", encoding="utf-8")
    applied = ix.apply_working_tree_overlay(idx, repo)
    assert "a.md" in applied and "draft.md" in applied
    assert _finds(idx, "WORKINGTREEONLY", "a.md")    # uncommitted edit findable
    assert _finds(idx, "DRAFTWORD", "draft.md")      # untracked findable
    assert idx.get_checkpoint() == cp                # overlay does NOT advance checkpoint
    idx.close()


def test_replica_does_not_see_uncommitted(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha committed.\n"})
    idx = ix.build_index(repo, fake_embedder)
    (repo / "a.md").write_text("# A\n\nalpha UNCOMMITTEDSECRET.\n", encoding="utf-8")
    res = ix.catch_up(idx, repo)                     # replica: committed projection only
    assert res["status"] == "current"                # HEAD unchanged → nothing to replay
    assert not _finds(idx, "UNCOMMITTEDSECRET", "a.md")
    idx.close()


def test_absent_checkpoint_triggers_full_scan(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n", "b.md": "# B\n\nbeta.\n"})
    idx = ix.build_index(repo, fake_embedder)
    idx.set_checkpoint("0" * 40)                     # corrupt/unknown checkpoint
    res = ix.catch_up(idx, repo)
    assert res["full"] is True and res["replayed"] >= 2
    assert idx.get_checkpoint() == subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True).stdout.strip()
    idx.close()
