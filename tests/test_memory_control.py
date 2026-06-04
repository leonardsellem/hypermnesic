"""First-class memory control center: owner-visible list/inspect/export/forget/revert/audit."""

from __future__ import annotations

import json
import subprocess

import pytest

from hypermnesic import audit_log as al
from hypermnesic import cli, index, memory_control, serialize


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo, rel, body, msg="update"):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)
    return _git(repo, "rev-parse", "HEAD")


def _setup(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({
        "notes/alpha.md": "# Alpha\n\nAgent wrote ALPHAMARK durable memory.\n",
        "sources/captures/raw.md": "# Raw\n\nCaptured raw source.\n",
        "dashboards/generated.md": (
            "---\ngenerated_by: hypermnesic\n---\n"
            "# Generated\n\nA generated dashboard.\n"
        ),
        "projects/scripts/blocked.md": "# Blocked\n\nprotected folder.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    log = al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test-node")
    log.append("create", "notes/alpha.md", None, _git(repo, "rev-parse", "HEAD"),
               "agent wrote alpha")
    return repo, idx, log


def test_list_and_inspect_show_git_file_provenance_without_body_leak(
        make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)

    listing = memory_control.list_memories(repo, idx, log=log, folder="notes/")
    assert listing["degraded_lexical_only"] is False
    assert listing["manual_reindex_recommended"] is False
    assert [item["path"] for item in listing["items"]] == ["notes/alpha.md"]
    item = listing["items"][0]
    assert item["title"] == "Alpha"
    assert item["last_commit"]
    assert item["actor"] == "tailnet:test-node"
    assert item["source_type"] == "authored"
    assert "ALPHAMARK" in item["snippet"]

    inspected = memory_control.inspect_memory(repo, idx, "notes/alpha.md", log=log)
    assert inspected["path"] == "notes/alpha.md"
    assert inspected["provenance"]["source"] == "git-file"
    assert inspected["provenance"]["last_commit"] == item["last_commit"]
    assert "full_body" not in inspected
    assert "Agent wrote ALPHAMARK durable memory.\n" not in json.dumps(inspected)
    idx.close()


def test_filters_and_write_scope_match_write_guard(make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)

    captured = memory_control.list_memories(repo, idx, source_type="captured")
    assert [item["path"] for item in captured["items"]] == ["sources/captures/raw.md"]

    generated = memory_control.list_memories(repo, idx, source_type="generated")
    assert [item["path"] for item in generated["items"]] == ["dashboards/generated.md"]

    protected = memory_control.list_memories(repo, idx, writable=False)
    by_path = {item["path"]: item for item in protected["items"]}
    assert by_path["projects/scripts/blocked.md"]["writable"] is False
    assert "scripts/" in by_path["projects/scripts/blocked.md"]["protected_reason"]

    scope = memory_control.write_scope(repo, idx, allowlist=["notes/"])
    folder_by_path = {folder["path"]: folder for folder in scope["folders"]}
    assert folder_by_path["notes/"]["writable"] is True
    assert folder_by_path["projects/"]["writable"] is False
    assert folder_by_path["projects/"]["protected_reason"] == "not in writable allowlist"
    assert scope["summary"]["mode"] == "allowlist"
    idx.close()


def test_export_preserves_markdown_layout_and_provenance_manifest(
        make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    dest = tmp_path / "export"

    result = memory_control.export_memories(repo, idx, dest, folder="notes/", log=log,
                                            exported_at="2026-06-04T00:00:00Z")

    assert result["status"] == "exported"
    assert result["count"] == 1
    assert (dest / "notes" / "alpha.md").read_text(encoding="utf-8").startswith("# Alpha")
    manifest = json.loads((dest / "hypermnesic-export-manifest.json").read_text())
    assert manifest["items"][0]["path"] == "notes/alpha.md"
    assert manifest["items"][0]["last_commit"]
    assert not (dest / ".hypermnesic").exists()

    empty = memory_control.export_memories(repo, idx, tmp_path / "empty", folder="missing/")
    assert empty["status"] == "empty"
    assert empty["count"] == 0
    idx.close()


def test_forget_preview_apply_audit_and_recall_verification(
        make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    before = _git(repo, "rev-parse", "HEAD")

    preview = memory_control.preview_forget(repo, idx, "notes/alpha.md")
    assert preview["stage"] == "preview"
    assert preview["target"]["path"] == "notes/alpha.md"
    assert preview["will_create_commit"] is True
    assert "git history" in preview["limits"][0].lower()
    assert _git(repo, "rev-parse", "HEAD") == before
    assert (repo / "notes" / "alpha.md").exists()

    result = memory_control.apply_forget(repo, idx, "notes/alpha.md", log=log)
    assert result["stage"] == "applied"
    assert result["commit"] and result["commit"] != before
    assert result["verification"]["source_exists"] is False
    assert result["verification"]["index_contains_path"] is False
    assert not (repo / "notes" / "alpha.md").exists()
    assert not any(idx.get_chunk(cid)["path"] == "notes/alpha.md"
                   for cid, _score in idx.lexical_search("ALPHAMARK", k=5))
    assert log.entries()[-1]["verb"] == "forget"
    idx.close()


def test_forget_refuses_protected_and_dirty_paths_without_partial_write(
        make_corpus, fake_embedder, tmp_path):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    head = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(serialize.WriteGuardError):
        memory_control.preview_forget(repo, idx, "AGENTS.md")
    assert _git(repo, "rev-parse", "HEAD") == head

    (repo / "scratch.md").write_text("# Scratch\n\nuncommitted\n", encoding="utf-8")
    with pytest.raises(serialize.DirtyTreeError):
        memory_control.apply_forget(repo, idx, "notes/alpha.md", log=log)
    assert (repo / "notes" / "alpha.md").exists()
    assert _git(repo, "rev-parse", "HEAD") == head
    idx.close()


def test_revert_recent_single_file_memory_write(make_corpus, fake_embedder, tmp_path):
    repo = make_corpus({"seed.md": "# Seed\n\nseed.\n"})
    write_sha = _commit(repo, "notes/bad.md", "# Bad\n\nBADMEMORY marker.\n", "bad memory")
    idx = index.build_index(repo, fake_embedder)
    log = al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test-node")
    log.append("create", "notes/bad.md", None, write_sha, "bad memory")

    preview = memory_control.preview_revert(repo, write_sha)
    assert preview["stage"] == "preview"
    assert preview["supported"] is True
    assert preview["paths"] == ["notes/bad.md"]

    result = memory_control.apply_revert(repo, idx, write_sha, log=log)
    assert result["stage"] == "applied"
    assert result["commit"] and result["commit"] != write_sha
    assert result["verification"]["paths_present"]["notes/bad.md"] is False
    assert log.entries()[-1]["verb"] == "revert"
    idx.close()


def test_audit_view_includes_refusals_without_raw_bodies_or_secrets(tmp_path):
    log = al.AuditLog(tmp_path / "audit.jsonl", actor_fn=lambda: "tailnet:test-node")
    log.append("create", "notes/a.md", None, "sha1", "short summary")
    log.append_refusal("commit_note", "AGENTS.md", "protected path",
                       summary="raw body sk-" + "D" * 24 + " " + "x" * 500)

    out = memory_control.audit_view(log)
    assert [entry["verb"] for entry in out["entries"]] == ["create", "refusal"]
    dumped = json.dumps(out)
    assert "sk-" not in dumped
    assert "x" * 200 not in dumped
    assert out["entries"][1]["category"] == "protected path"

    empty = memory_control.audit_view(al.AuditLog(tmp_path / "absent.jsonl"))
    assert empty["entries"] == []


def test_memory_cli_json_contract(make_corpus, fake_embedder, tmp_path, capsys):
    repo, idx, log = _setup(make_corpus, fake_embedder, tmp_path)
    idx.close()
    audit_path = str(log.path)

    assert cli.main(["memory", "inspect", str(repo), "notes/alpha.md",
                     "--audit-log", audit_path, "--json"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["path"] == "notes/alpha.md"
    assert inspected["actor"] == "tailnet:test-node"

    dest = tmp_path / "cli-export"
    assert cli.main(["memory", "export", str(repo), "--folder", "notes/",
                     "--dest", str(dest), "--audit-log", audit_path, "--json"]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["count"] == 1
    assert (dest / "notes" / "alpha.md").exists()

    assert cli.main(["memory", "write-scope", str(repo), "--allowlist", "notes/",
                     "--json"]) == 0
    scope = json.loads(capsys.readouterr().out)
    assert scope["summary"]["mode"] == "allowlist"
