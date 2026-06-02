"""U28 — CLI read entrypoints converge before serving.

``retrieve`` (new) mirrors the MCP ``search`` hit shape; ``think`` converges
first. Tests run fully offline + deterministic: the key is neutralized so the
dense channel degrades to lexical (the index is still caught up to HEAD via the
lexical delta-replay, which needs no embedder).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from hypermnesic import cli, config, index, install


def _neutralize_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config, "_DOTENV_PATHS", [tmp_path / "nope.env"])


def _commit(repo, rel, body, msg="add"):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)


def test_retrieve_matches_search_hit_shape(make_corpus, fake_embedder, monkeypatch,
                                           tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"hetzner.md": "# Hetzner\n\nHetzner homelab note.\n"})
    index.build_index(repo, fake_embedder).close()
    rc = cli.main(["retrieve", str(repo), "Hetzner", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["query"] == "Hetzner"
    assert out["degraded_lexical_only"] is True            # no key → lexical-only, well-formed
    assert any(h["path"] == "hetzner.md" for h in out["hits"])
    hit = out["hits"][0]
    assert {"path", "heading", "score", "channels", "snippet"}.issubset(hit)


def test_retrieve_converges_to_head_before_serving(make_corpus, fake_embedder, monkeypatch,
                                                   tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    _commit(repo, "fresh.md", "# Fresh\n\nCLIFRESHMARKER body.\n", "add fresh")
    cli.main(["retrieve", str(repo), "CLIFRESHMARKER", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert any(h["path"] == "fresh.md" for h in out["hits"])   # lexical catch-up before serving


def test_think_converges_to_head_before_serving(make_corpus, fake_embedder, monkeypatch,
                                                tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    _commit(repo, "topic.md", "# Topic\n\nTHINKMARKER discussion.\n", "add topic")
    cli.main(["think", str(repo), "THINKMARKER", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["wrote"] is False
    assert any(h["path"] == "topic.md" for h in out["related"])   # converged before thinking


def test_retrieve_human_output_is_nonempty(make_corpus, fake_embedder, monkeypatch,
                                           tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"hetzner.md": "# Hetzner\n\nHetzner homelab note.\n"})
    index.build_index(repo, fake_embedder).close()
    rc = cli.main(["retrieve", str(repo), "Hetzner"])          # non-JSON path
    assert rc == 0
    assert "retrieve: Hetzner" in capsys.readouterr().out


# --- U33: opt-in install-hooks + the converge command it calls ----------------

def _post_merge(repo):
    return repo / ".git" / "hooks" / "post-merge"


def test_install_hooks_fresh_repo(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    assert cli.main(["install-hooks", str(repo)]) == 0
    hook = _post_merge(repo)
    assert hook.exists() and os.access(hook, os.X_OK)          # installed + executable
    text = hook.read_text()
    assert install._MANAGED_BEGIN in text and "converge" in text


def test_install_hooks_idempotent(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    cli.main(["install-hooks", str(repo)])
    cli.main(["install-hooks", str(repo)])
    text = _post_merge(repo).read_text()
    assert text.count(install._MANAGED_BEGIN) == 1             # exactly one managed block


def test_install_hooks_preserves_existing_content(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    hook = _post_merge(repo)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho CUSTOMHOOKLINE\n")
    cli.main(["install-hooks", str(repo)])
    text = hook.read_text()
    assert "CUSTOMHOOKLINE" in text                            # operator content preserved
    assert install._MANAGED_BEGIN in text                      # managed block appended


def test_uninstall_hooks_removes_only_managed_block(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    hook = _post_merge(repo)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho CUSTOMHOOKLINE\n")
    cli.main(["install-hooks", str(repo)])
    cli.main(["install-hooks", str(repo), "--uninstall"])
    text = hook.read_text()
    assert "CUSTOMHOOKLINE" in text                            # operator content kept
    assert install._MANAGED_BEGIN not in text                 # managed block removed


def test_converge_command_catches_up_to_head(make_corpus, fake_embedder, monkeypatch,
                                             tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    _commit(repo, "warm.md", "# Warm\n\nWARMMARKER body.\n", "add warm")
    assert cli.main(["converge", str(repo), "--json"]) == 0
    idx = index.Index(index.state_dir_for(repo) / "index.db")
    assert "warm.md" in idx.all_paths()                        # convergence ran (lexical catch-up)
    idx.close()


# --- U1: serve --allowlist + repo/write plumb-through -------------------------

class _FakeSrv:
    def __init__(self): self.ran = False
    def run(self, **kw): self.ran = True


def _capture_build(monkeypatch):
    """Replace mcp_server.build_server with a capturing fake (no socket bind)."""
    captured: dict = {}
    srv = _FakeSrv()

    def fake_build(index_db, **kw):
        captured["index_db"] = index_db
        captured.update(kw)
        return srv

    from hypermnesic import mcp_server
    monkeypatch.setattr(mcp_server, "build_server", fake_build)
    return captured, srv


def test_serve_plumbs_repeatable_allowlist_repo_and_write(monkeypatch, tmp_path):
    captured, srv = _capture_build(monkeypatch)
    rc = cli.main(["serve", "--index-db", str(tmp_path / "i.db"), "--host", "100.64.0.1",
                   "--enable-write", "--allowlist", "projects/", "--allowlist", "memory/",
                   "--repo", str(tmp_path)])
    assert rc == 0 and srv.ran
    assert captured["write_allowlist"] == ["projects/", "memory/"]   # repeatable → list
    assert captured["write_enabled"] is True
    assert str(captured["repo"]) == str(tmp_path)                    # repo plumbed


def test_serve_no_allowlist_passes_none_for_default(monkeypatch, tmp_path):
    captured, _ = _capture_build(monkeypatch)
    rc = cli.main(["serve", "--index-db", str(tmp_path / "i.db"), "--host", "100.64.0.1",
                   "--enable-write"])
    assert rc == 0
    assert captured["write_allowlist"] is None      # None → build_server uses the default
    assert captured["repo"] is None                 # no --repo → build_server derives it


def test_serve_empty_allowlist_write_enabled_fails_loud(tmp_path, capsys):
    # Real build_server: an empty --allowlist on a write-enabled serve is refused at
    # startup → the CLI exits 1 with a clear message (no half-open server, no traceback).
    rc = cli.main(["serve", "--index-db", str(tmp_path / "i.db"), "--host", "100.64.0.1",
                   "--enable-write", "--allowlist", ""])
    assert rc == 1
    assert "serve failed" in capsys.readouterr().err.lower()


def test_installed_hook_execution_invokes_convergence(make_corpus, fake_embedder):
    # Simulated post-merge: execute the installed hook; it must run convergence so a
    # just-merged file is indexed. Runs the baked-in absolute hypermnesic path, offline.
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    cli.main(["install-hooks", str(repo)])
    _commit(repo, "merged.md", "# Merged\n\nMERGEDMARKER body.\n", "add merged")
    env = {**os.environ,
           "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")}
    env.pop("OPENAI_API_KEY", None)                            # offline → lexical catch-up
    subprocess.run(["sh", str(_post_merge(repo))], cwd=str(repo), env=env,
                   check=True, capture_output=True)
    idx = index.Index(index.state_dir_for(repo) / "index.db")
    assert "merged.md" in idx.all_paths()                      # the hook converged the index
    idx.close()


# --- U1: resolve verb + --now convergence-freshness knob + manual-reindex -----

def test_resolve_returns_path_and_slug_for_known_entity(make_corpus, fake_embedder,
                                                        monkeypatch, tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"infrastructure/hetzner.md": "# Hetzner\n\nThe homelab box.\n",
                        "notes/dup.md": "# D1\n\n", "archive/dup.md": "# D2\n\n"})
    index.build_index(repo, fake_embedder).close()
    rc = cli.main(["resolve", str(repo), "Hetzner", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["resolved"] == "infrastructure/hetzner.md"
    assert out["slug"] == "infrastructure/hetzner"             # caller wikilinks the slug


def test_resolve_ambiguous_and_missing_are_null(make_corpus, fake_embedder,
                                                monkeypatch, tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"notes/dup.md": "# D1\n\n", "archive/dup.md": "# D2\n\n"})
    index.build_index(repo, fake_embedder).close()
    cli.main(["resolve", str(repo), "dup", "--json"])
    assert json.loads(capsys.readouterr().out)["resolved"] is None       # ambiguous → null
    cli.main(["resolve", str(repo), "no-such-entity", "--json"])
    assert json.loads(capsys.readouterr().out)["resolved"] is None       # missing → null


def test_retrieve_now_forces_fresh_self_write_within_debounce(make_corpus, fake_embedder,
                                                             monkeypatch, tmp_path, capsys):
    # Covers AE1: a single `retrieve --now` makes a just-committed self-write recall-able
    # inside the 5 s debounce window; the default (debounced) path still skips it.
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    cli.main(["retrieve", str(repo), "alpha", "--json"])           # prime the debounce stamp
    capsys.readouterr()
    _commit(repo, "selfwrite.md", "# Self\n\nSELFWRITEMARKER body.\n", "add self")
    cli.main(["retrieve", str(repo), "SELFWRITEMARKER", "--json"])  # default: debounced skip
    debounced = json.loads(capsys.readouterr().out)
    assert not any(h["path"] == "selfwrite.md" for h in debounced["hits"])      # not yet caught up
    cli.main(["retrieve", str(repo), "SELFWRITEMARKER", "--now", "--json"])     # forced converge
    forced = json.loads(capsys.readouterr().out)
    assert any(h["path"] == "selfwrite.md" for h in forced["hits"])             # recall-able now


def test_retrieve_json_surfaces_manual_reindex_on_oversized_delta(make_corpus, fake_embedder,
                                                                 monkeypatch, tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "CONVERGE_MAX_DELTA_FILES", 2)     # small cap → trip oversized
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    for i in range(3):                                             # 3 > 2 → oversized delta
        _commit(repo, f"big{i}.md", f"# Big{i}\n\nbody {i}.\n", f"big {i}")
    cli.main(["retrieve", str(repo), "alpha", "--now", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["manual_reindex_recommended"] is True              # CLI surfaces it (was dropped)


def test_converge_now_forces_pass_within_debounce(make_corpus, fake_embedder,
                                                  monkeypatch, tmp_path):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    cli.main(["converge", str(repo), "--json"])                # writes a fresh debounce stamp
    _commit(repo, "warm2.md", "# W2\n\nWARM2MARKER.\n", "add warm2")
    cli.main(["converge", str(repo), "--json"])                # default → debounced, no catch-up
    idx = index.Index(index.state_dir_for(repo) / "index.db")
    assert "warm2.md" not in idx.all_paths()
    idx.close()
    cli.main(["converge", str(repo), "--now", "--json"])       # --now → forced catch-up
    idx = index.Index(index.state_dir_for(repo) / "index.db")
    assert "warm2.md" in idx.all_paths()
    idx.close()
