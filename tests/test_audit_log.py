"""U11 — append-only audit log: summaries-only, server-set actor, reconciler."""

from __future__ import annotations

import subprocess

from hypermnesic import audit_log as al


def _log(tmp_path):
    return al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test-node")


def test_append_records_entry_with_shas_and_summary(tmp_path):
    log = _log(tmp_path)
    log.append("commit_note", "notes/a.md", "sha0", "sha1", "added a note",
               ts="2026-06-01T00:00:00Z")
    ents = log.entries()
    assert len(ents) == 1
    e = ents[0]
    assert e["verb"] == "commit_note" and e["path"] == "notes/a.md"
    assert e["old_sha"] == "sha0" and e["new_sha"] == "sha1"
    assert e["summary"] == "added a note" and e["actor"] == "tailnet:test-node"


def test_caller_actor_is_ignored(tmp_path):
    log = _log(tmp_path)
    log.append("commit_note", "a.md", None, "s1", "x", actor="attacker-supplied")
    assert log.entries()[0]["actor"] == "tailnet:test-node"   # server-set, not caller's


def test_summary_truncated_no_body_leak(tmp_path):
    log = _log(tmp_path)
    body = "SECRET_BODY_" + "x" * 5000
    log.append("commit_note", "a.md", None, "s1", body)   # if a body were ever passed
    stored = log.entries()[0]["summary"]
    assert len(stored) == al.MAX_SUMMARY                   # capped
    # and the raw log file never contains the full body
    assert "x" * 5000 not in (tmp_path / "audit.jsonl").read_text()


def test_append_only_history_preserved(tmp_path):
    log = _log(tmp_path)
    log.append("commit_note", "a.md", None, "s1", "first")
    first_line = (tmp_path / "audit.jsonl").read_text()
    log.append("commit_note", "b.md", "s1", "s2", "second")
    after = (tmp_path / "audit.jsonl").read_text()
    assert after.startswith(first_line)                    # prior entry untouched
    assert len(log.entries()) == 2


def _commit(repo, msg):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def test_reconciler_backfills_staged_but_unlogged(make_corpus, tmp_path):
    repo = make_corpus({"a.md": "# A\n\nbody\n"})       # 1 commit
    sha0 = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True).stdout.strip()
    log = _log(tmp_path)
    log.append("commit_note", "a.md", None, sha0, "initial")
    # a commit that never got logged (the crash case)
    (repo / "b.md").write_text("# B\n\nbody\n", encoding="utf-8")
    sha1 = _commit(repo, "add b")
    assert log.reconcile(repo) == 1                        # back-fills exactly one
    ents = log.entries()
    assert ents[-1]["new_sha"] == sha1 and ents[-1]["verb"] == "reconcile"
    assert log.reconcile(repo) == 0                        # fully logged → no-op


def test_real_tailscale_actor_is_string():
    a = al.tailscale_actor()
    assert isinstance(a, str) and (a.startswith("tailnet:") or a == al._SENTINEL)
