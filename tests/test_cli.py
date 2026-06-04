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

import pytest

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


def test_think_human_output_runs_after_unlinked_rename(make_corpus, fake_embedder, monkeypatch,
                                                       tmp_path, capsys):
    # U45 regression: the non-JSON think path renders questions + unlinked pairs.
    # Before the rename it concatenated r.questions + r.tensions; after the rename
    # that attribute is gone, so this guards the cli.py consumer from AttributeError.
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"alpha.md": "# Alpha\n\nPAIRMARK shared.\n",
                        "beta.md": "# Beta\n\nPAIRMARK shared.\n"})
    index.build_index(repo, fake_embedder).close()
    rc = cli.main(["think", str(repo), "PAIRMARK shared"])         # non-JSON path
    assert rc == 0
    assert "thinking about: PAIRMARK shared" in capsys.readouterr().out


def test_retrieve_human_output_is_nonempty(make_corpus, fake_embedder, monkeypatch,
                                           tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"hetzner.md": "# Hetzner\n\nHetzner homelab note.\n"})
    index.build_index(repo, fake_embedder).close()
    rc = cli.main(["retrieve", str(repo), "Hetzner"])          # non-JSON path
    assert rc == 0
    assert "retrieve: Hetzner" in capsys.readouterr().out


# --- First-class product track U1: local-first value proof --------------------

def test_local_proof_cli_json_contract_existing_vault(make_corpus, monkeypatch, tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({
        "notes/alpha.md": (
            "# Alpha\n\n"
            "Question answered: what should Hypermnesic remember about CLI proof\n\n"
            "The CLI proof returns a source-grounded markdown path.\n"
        )
    })

    rc = cli.main([
        "local-proof",
        str(repo),
        "--query",
        "what should Hypermnesic remember about CLI proof",
        "--json",
    ])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "local_memory_works"
    assert {"status", "completed_milestones", "degraded_capabilities", "source_path",
            "next_action", "error"}.issubset(out)
    assert out["source_path"] == "notes/alpha.md"
    assert out["error"] is None
    assert str(repo) not in json.dumps(out)


def test_local_proof_cli_human_output_starts_with_local_value(make_corpus, monkeypatch,
                                                              tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({
        "notes/local.md": (
            "# Local\n\n"
            "Question answered: what should Hypermnesic remember about local first\n\n"
            "Local-first proof comes before network setup.\n"
        )
    })

    rc = cli.main([
        "local-proof",
        str(repo),
        "--query",
        "what should Hypermnesic remember about local first",
    ])

    assert rc == 0
    lines = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines[0] == "Local memory works"
    proof_text = "\n".join(lines[:5]).lower()
    for advanced_term in ("oauth", "tailscale", "resource-server", "funnel", "mcp"):
        assert advanced_term not in proof_text


def test_local_proof_cli_demo_dir_creates_demo_vault(monkeypatch, tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    demo = tmp_path / "demo"

    rc = cli.main(["local-proof", "--demo-dir", str(demo), "--json"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "demo"
    assert out["source_path"] == "memory/local-proof-memory.md"
    assert (demo / "memory" / "local-proof-memory.md").exists()
    assert str(demo) not in json.dumps(out)


def test_local_proof_cli_non_git_error_is_actionable(tmp_path, capsys):
    repo = tmp_path / "not-git"
    repo.mkdir()

    rc = cli.main(["local-proof", str(repo)])

    assert rc == 1
    err = capsys.readouterr().err
    assert "local-proof failed" in err
    assert "git repo" in err
    assert "traceback" not in err.lower()


def test_local_proof_is_listed_in_help(capsys):
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["local-proof", "--help"])

    assert excinfo.value.code == 0
    assert "prove local memory works" in capsys.readouterr().out


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


def test_serve_allow_tailnet_write_plumbs_trust_flag(monkeypatch, tmp_path):
    captured, srv = _capture_build(monkeypatch)
    rc = cli.main(["serve", "--index-db", str(tmp_path / "i.db"), "--host", "100.64.0.1",
                   "--enable-write", "--allow-tailnet-write"])
    assert rc == 0 and srv.ran
    assert captured["trust_tailnet_write"] is True       # opt-in plumbed through
    assert captured["write_enabled"] is True


def test_serve_default_does_not_trust_tailnet_write(monkeypatch, tmp_path):
    captured, _ = _capture_build(monkeypatch)
    rc = cli.main(["serve", "--index-db", str(tmp_path / "i.db"), "--host", "100.64.0.1"])
    assert rc == 0 and captured["trust_tailnet_write"] is False   # safe-by-default


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


# --- U4: list-folders CLI parity ---------------------------------------------

def test_list_folders_cli_json_shape_matches_mcp(make_corpus, fake_embedder,
                                                 monkeypatch, tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"notes/n.md": "# N\n\nbody.\n", "projects/acme/a.md": "# A\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    rc = cli.main(["list-folders", str(repo), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    # exact parity with the MCP ListFoldersOutput shape
    assert set(out) == {"root", "depth", "folders", "truncated", "omitted",
                        "manual_reindex_recommended"}
    by = {e["path"]: e for e in out["folders"]}
    assert {"notes/", "projects/"} <= set(by)
    assert {"path", "writable", "protected_reason", "note_count"} <= set(by["notes/"])
    assert by["notes/"]["writable"] is True                # Phase A: 4-prefix default
    assert by["notes/"]["note_count"] == 1


def test_list_folders_cli_drill_down(make_corpus, fake_embedder, monkeypatch, tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"projects/acme/a.md": "# A\n\nbody.\n",
                        "projects/hermes/b.md": "# B\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    cli.main(["list-folders", str(repo), "--root", "projects/", "--depth", "1", "--json"])
    by = {e["path"]: e for e in json.loads(capsys.readouterr().out)["folders"]}
    assert set(by) == {"projects/acme/", "projects/hermes/"}


def test_list_folders_cli_allowlist_preview_narrows(make_corpus, fake_embedder,
                                                   monkeypatch, tmp_path, capsys):
    # AE3: --allowlist previews writability under a narrowed surface — discovery agrees with a
    # narrowed guard (notes/ writable, projects/ non-writable). Verification of R7/R12 from the CLI.
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"notes/n.md": "# N\n\nbody.\n", "projects/p.md": "# P\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    cli.main(["list-folders", str(repo), "--allowlist", "notes/", "--json"])
    by = {e["path"]: e for e in json.loads(capsys.readouterr().out)["folders"]}
    assert by["notes/"]["writable"] is True
    assert by["projects/"]["writable"] is False
    assert by["projects/"]["protected_reason"] == "not in writable allowlist"


def test_list_folders_cli_human_output_is_nonempty(make_corpus, fake_embedder,
                                                  monkeypatch, tmp_path, capsys):
    _neutralize_key(monkeypatch, tmp_path)
    repo = make_corpus({"notes/n.md": "# N\n\nbody.\n"})
    index.build_index(repo, fake_embedder).close()
    rc = cli.main(["list-folders", str(repo)])                 # non-JSON path
    assert rc == 0
    assert "notes/" in capsys.readouterr().out


# --- U2: serve OAuth2 flags plumb a verifier + AuthSettings into build_server --

_ISS = "https://example.ts.net/honcho/"
_RES = "https://example.ts.net/mcp"


def test_serve_auth_flags_plumb_verifier_and_settings(monkeypatch, tmp_path):
    captured, srv = _capture_build(monkeypatch)
    from hypermnesic import auth
    # stub discovery so no network is touched at serve-build time
    monkeypatch.setattr(auth, "verify_raw_from_discovery", lambda **k: (lambda t: None))
    rc = cli.main(["serve", "--index-db", str(tmp_path / "i.db"), "--host", "100.64.0.1",
                   "--enable-write", "--auth-issuer-url", _ISS, "--auth-resource-url", _RES,
                   "--required-scope", "write"])
    assert rc == 0 and srv.ran
    assert captured["auth"] is not None
    assert str(captured["auth"].resource_server_url).rstrip("/") == _RES
    assert captured["auth"].required_scopes == ["write"]
    assert captured["token_verifier"] is not None
    assert captured["write_enabled"] is True


def test_serve_issuer_without_resource_refused(tmp_path, capsys):
    # enabling auth requires BOTH issuer and resource URLs → fail loud, exit 1
    rc = cli.main(["serve", "--index-db", str(tmp_path / "i.db"), "--host", "100.64.0.1",
                   "--auth-issuer-url", _ISS])
    assert rc == 1
    assert "auth" in capsys.readouterr().err.lower()


def test_serve_no_auth_flags_unchanged(monkeypatch, tmp_path):
    captured, srv = _capture_build(monkeypatch)
    rc = cli.main(["serve", "--index-db", str(tmp_path / "i.db"), "--host", "100.64.0.1"])
    assert rc == 0
    assert captured.get("auth") is None and captured.get("token_verifier") is None


# --- U7: the tailnet client_credentials AS (:8849) is retired ----------------

def test_retired_as_commands_are_gone():
    # U7: the :8849 client_credentials AS (serve-auth + auth-add-client) folds into the unified
    # endpoint and is removed. The subcommands no longer exist — a fresh deploy can't provision it.
    import argparse

    parser = cli.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert "serve-auth" not in sub.choices and "auth-add-client" not in sub.choices
    # the unified write lane (serve-cloud) and the retained read lane (serve) remain
    assert "serve-cloud" in sub.choices and "serve" in sub.choices and "setup" in sub.choices


# --- cloud OAuth MCP: serve-cloud reads the approval token from env, never a flag ---

def test_serve_cloud_requires_approval_token_env(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("HYPERMNESIC_CLOUD_APPROVAL_TOKEN", raising=False)
    rc = cli.main(["serve-cloud", "--index-db", str(tmp_path / "i.db"),
                   "--public-url", "https://h/cloud", "--resource", "https://h/cloud/mcp"])
    assert rc == 1 and "approval" in capsys.readouterr().err.lower()


def test_serve_cloud_plumbs_to_build_cloud_server(tmp_path, monkeypatch):
    monkeypatch.setenv("HYPERMNESIC_CLOUD_APPROVAL_TOKEN", "op-secret-token-24-chars-or-more")
    captured: dict = {}
    srv = _FakeSrv()

    def fake_cloud(index_db, **kw):
        captured["index_db"] = index_db
        captured.update(kw)
        return srv

    from hypermnesic import mcp_server
    monkeypatch.setattr(mcp_server, "build_cloud_server", fake_cloud)
    rc = cli.main(["serve-cloud", "--index-db", str(tmp_path / "i.db"),
                   "--public-url", "https://h/cloud", "--resource", "https://h/cloud/mcp",
                   "--token-ttl", "1800"])
    assert rc == 0 and srv.ran
    assert captured["resource"] == "https://h/cloud/mcp" and captured["public_url"] == "https://h/cloud"
    assert captured["approval_token"] == "op-secret-token-24-chars-or-more"   # from env
    assert captured["token_ttl_seconds"] == 1800


def test_serve_cloud_plumbs_default_client_scopes_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("HYPERMNESIC_CLOUD_APPROVAL_TOKEN", "op-secret-token-24-chars-or-more")
    captured: dict = {}
    srv = _FakeSrv()

    def fake_cloud(index_db, **kw):
        captured.update(kw)
        return srv

    from hypermnesic import mcp_server
    monkeypatch.setattr(mcp_server, "build_cloud_server", fake_cloud)
    rc = cli.main(["serve-cloud", "--index-db", str(tmp_path / "i.db"),
                   "--public-url", "https://h/cloud", "--resource", "https://h/cloud/mcp",
                   "--default-client-scopes", "read", "write"])
    assert rc == 0 and srv.ran
    assert captured["default_client_scopes"] == ["read", "write"]


def test_serve_cloud_plumbs_default_client_scopes_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HYPERMNESIC_CLOUD_APPROVAL_TOKEN", "op-secret-token-24-chars-or-more")
    monkeypatch.setenv("HYPERMNESIC_DEFAULT_CLIENT_SCOPES", "read,write")
    captured: dict = {}
    srv = _FakeSrv()

    def fake_cloud(index_db, **kw):
        captured.update(kw)
        return srv

    from hypermnesic import mcp_server
    monkeypatch.setattr(mcp_server, "build_cloud_server", fake_cloud)
    rc = cli.main(["serve-cloud", "--index-db", str(tmp_path / "i.db"),
                   "--public-url", "https://h/cloud", "--resource", "https://h/cloud/mcp"])
    assert rc == 0 and srv.ran
    assert captured["default_client_scopes"] == ["read", "write"]


def test_serve_cloud_refuses_weak_approval_token(tmp_path, capsys, monkeypatch):
    # a public WRITE surface gated by a single token needs an entropy floor (online-brute-force)
    monkeypatch.setenv("HYPERMNESIC_CLOUD_APPROVAL_TOKEN", "short")
    rc = cli.main(["serve-cloud", "--index-db", str(tmp_path / "i.db"),
                   "--public-url", "https://h/cloud", "--resource", "https://h/cloud/mcp"])
    assert rc == 1
    err = capsys.readouterr().err.lower()
    assert "approval" in err and ("24" in err or "characters" in err or "weak" in err)


# --- U3: `hypermnesic setup` — one-command bring-up plumbs to install.setup ---

def test_setup_cli_plumbs_to_install_setup(tmp_path, capsys, monkeypatch):
    captured: dict = {}

    def fake_setup(repo, **kw):
        captured["repo"] = repo
        captured.update(kw)
        return {"service": "hypermnesic-cloud", "public_url": kw["public_url"],
                "resource": kw["resource"], "unit_path": "/x/u.service",
                "env_file": "/x/cloud.env", "secret_generated": True,
                "funnel_routes": [("/mcp", "http://127.0.0.1:8850")],
                "discovery": {"ok": True, "checks": {}}, "converged": False,
                "next_steps": ["add https://h/mcp to your apps", "log in once"]}

    from hypermnesic import install
    monkeypatch.setattr(install, "setup", fake_setup)
    rc = cli.main(["setup", str(tmp_path), "--public-url", "https://h/mcp",
                   "--resource", "https://h/mcp", "--port", "8850",
                   "--default-client-scopes", "read", "write"])
    out = capsys.readouterr().out
    assert rc == 0
    assert captured["public_url"] == "https://h/mcp" and captured["resource"] == "https://h/mcp"
    assert captured["default_client_scopes"] == ["read", "write"]
    assert "https://h/mcp" in out                                 # the URL is printed
    assert "log in" in out.lower() or "authorize" in out.lower()  # login instructions printed


def test_setup_cli_defaults_resource_to_public_url(tmp_path, capsys, monkeypatch):
    captured: dict = {}

    def fake_setup(repo, **kw):
        captured["repo"] = repo
        captured.update(kw)
        return {"service": "hypermnesic-cloud", "public_url": kw["public_url"],
                "resource": kw["resource"], "unit_path": "state/u.service",
                "env_file": "state/cloud.env", "secret_generated": False,
                "funnel_routes": [], "discovery": {"ok": True, "checks": {}},
                "converged": True, "milestones": [],
                "what_this_means": "Remote setup is ready.",
                "client_next_actions": {"remote_mcp": {"summary": "Add the endpoint."}},
                "next_steps": ["add https://h/mcp to your apps"]}

    from hypermnesic import install
    monkeypatch.setattr(install, "setup", fake_setup)
    rc = cli.main(["setup", str(tmp_path), "--public-url", "https://h/mcp", "--json"])

    assert rc == 0
    assert captured["resource"] == "https://h/mcp"
    out = json.loads(capsys.readouterr().out)
    assert out["resource"] == "https://h/mcp"
    assert out["what_this_means"] == "Remote setup is ready."


def test_setup_cli_fails_loud_on_install_error(tmp_path, capsys, monkeypatch):
    from hypermnesic import install

    def boom(repo, **kw):
        raise install.InstallError("Tailscale not logged in")

    monkeypatch.setattr(install, "setup", boom)
    rc = cli.main(["setup", str(tmp_path), "--public-url", "https://h/mcp",
                   "--resource", "https://h/mcp"])
    assert rc == 1 and "tailscale" in capsys.readouterr().err.lower()


def test_clients_cli_lists_and_revokes_grants(tmp_path, capsys):
    from hypermnesic import client_control

    repo = tmp_path / "repo"
    repo.mkdir()
    store = tmp_path / "client-grants.json"
    client_control.upsert_grant(store, {
        "grant_id": "grant-1",
        "client_id": "cid-1",
        "client_name": "ChatGPT",
        "redirect_uri": "https://chatgpt.com/connector_platform_oauth_redirect",
        "redirect_origin": "https://chatgpt.com",
        "scopes": ["read", "write"],
        "write_enabled": True,
        "issued_at": 1_000_000,
        "updated_at": 1_000_000,
        "access_expires_at": 1_003_600,
        "refresh_expires_at": 1_086_400,
        "status": "active",
        "active": True,
        "revoked_at": None,
    })
    rc = cli.main(["clients", "list", str(repo), "--grant-store", str(store), "--json"])
    assert rc == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["grants"][0]["write_enabled"] is True
    rc = cli.main(["clients", "revoke", str(repo), "grant-1", "--grant-store", str(store),
                   "--apply", "--json"])
    assert rc == 0
    revoked = json.loads(capsys.readouterr().out)
    assert revoked["status"] == "revoked"
    assert "token" not in json.dumps(revoked).lower()
