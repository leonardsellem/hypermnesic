"""U34 — role-aware installer (single | master | client).

Per the execution note, these assert the offline, deterministic parts only:
role routing, rendered service artifacts, config emission, env verification, and
idempotence. Live provisioning (``systemctl enable`` / ``docker compose up`` /
``hypermnesic init``) is returned as manual steps and verified by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypermnesic import config, index, install

_KEY = "sk-INSTALL-SENTINEL-must-not-leak"
TAILNET_IP = "100.64.0.1"   # CGNAT/Tailscale documentation range — not a real node


def _with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", _KEY)


def _no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config, "_DOTENV_PATHS", [tmp_path / "absent.env"])


# --- master / systemd -------------------------------------------------------

def test_master_systemd_renders_write_enabled_unit_and_config(make_corpus, monkeypatch):
    _with_key(monkeypatch)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    res = install.install("master", repo=repo, bind=TAILNET_IP, service="systemd")

    assert res["role"] == "master" and res["write_enabled"] is True
    unit = (repo / ".hypermnesic" / "hypermnesic.service").read_text()
    assert "serve" in unit and TAILNET_IP in unit and "--enable-write" in unit
    assert "OPENAI_API_KEY" in unit                       # the key is referenced by name…
    assert _KEY not in unit                                # …but its VALUE is never inlined
    cfg = json.loads((repo / ".hypermnesic" / "config.json").read_text())
    assert cfg["role"] == "master" and cfg["write_enabled"] is True and cfg["bind"] == TAILNET_IP
    assert (repo / ".git" / "hooks" / "post-merge").exists()   # convergence hook installed (U33)
    assert _KEY not in json.dumps(res)                    # never echoed in the result either


# --- master / docker --------------------------------------------------------

def test_master_docker_renders_compose_not_systemd(make_corpus, monkeypatch):
    _with_key(monkeypatch)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    res = install.install("master", repo=repo, bind=TAILNET_IP, service="docker")

    state = repo / ".hypermnesic"
    assert (state / "Dockerfile").exists()
    compose = (state / "compose.yaml").read_text()
    assert "serve" in compose and TAILNET_IP in compose and "--enable-write" in compose
    assert _KEY not in compose and _KEY not in (state / "Dockerfile").read_text()
    assert not (state / "hypermnesic.service").exists()   # docker flavor → no systemd unit
    assert res["service"] == "docker"


# --- client -----------------------------------------------------------------

def test_client_writes_mcp_config_no_engine(monkeypatch, tmp_path):
    cfg_path = tmp_path / "mcp" / "clients.json"
    url = f"http://{TAILNET_IP}:8848/mcp"
    res = install.install("client", master_url=url, mcp_config_path=str(cfg_path))

    assert res["role"] == "client"
    data = json.loads(cfg_path.read_text())
    assert data["mcpServers"]["hypermnesic"]["url"] == url
    assert data["mcpServers"]["hypermnesic"]["type"] == "streamable-http"
    # no engine: client writes no index and no role config
    assert not (tmp_path / index.STATE_DIRNAME).exists()


def test_client_patch_preserves_existing_servers(monkeypatch, tmp_path):
    cfg_path = tmp_path / "clients.json"
    cfg_path.write_text(json.dumps({"mcpServers": {"other": {"url": "http://x/mcp"}}}))
    url = f"http://{TAILNET_IP}:8848/mcp"
    install.install("client", master_url=url, mcp_config_path=str(cfg_path))
    data = json.loads(cfg_path.read_text())
    assert data["mcpServers"]["other"]["url"] == "http://x/mcp"     # preserved
    assert data["mcpServers"]["hypermnesic"]["url"] == url          # added


def test_client_requires_master_url_and_config(monkeypatch, tmp_path):
    with pytest.raises(install.InstallError):
        install.install("client", master_url=None, mcp_config_path=str(tmp_path / "c.json"))
    with pytest.raises(install.InstallError):
        install.install("client", master_url="http://m/mcp", mcp_config_path=None)


# --- single -----------------------------------------------------------------

def test_single_binds_localhost_no_remote_exposure(make_corpus, monkeypatch):
    _with_key(monkeypatch)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    res = install.install("single", repo=repo, service="systemd")

    assert res["bind"] == "127.0.0.1"
    cfg = json.loads((repo / ".hypermnesic" / "config.json").read_text())
    assert cfg["role"] == "single" and cfg["bind"] == "127.0.0.1"
    unit = (repo / ".hypermnesic" / "hypermnesic.service").read_text()
    assert "127.0.0.1" in unit and TAILNET_IP not in unit       # localhost only, no remote addr


# --- fail-loud + idempotence ------------------------------------------------

def test_engine_role_without_key_fails_loud_no_artifacts(make_corpus, monkeypatch, tmp_path):
    _no_key(monkeypatch, tmp_path)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    with pytest.raises(install.InstallError):
        install.install("master", repo=repo, bind=TAILNET_IP)
    # no half-provisioned state: neither a service unit nor a role config was written
    assert not (repo / ".hypermnesic" / "hypermnesic.service").exists()
    assert not (repo / ".hypermnesic" / "config.json").exists()


def test_master_requires_bind(make_corpus, monkeypatch):
    _with_key(monkeypatch)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    with pytest.raises(install.InstallError):
        install.install("master", repo=repo, bind=None)


def test_install_is_idempotent(make_corpus, monkeypatch):
    _with_key(monkeypatch)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    install.install("master", repo=repo, bind=TAILNET_IP)
    cfg1 = (repo / ".hypermnesic" / "config.json").read_text()
    install.install("master", repo=repo, bind=TAILNET_IP)
    cfg2 = (repo / ".hypermnesic" / "config.json").read_text()
    assert cfg1 == cfg2                                          # config stable
    hook = (repo / ".git" / "hooks" / "post-merge").read_text()
    assert hook.count(install._MANAGED_BEGIN) == 1              # exactly one managed block


def test_unknown_role_rejected(monkeypatch):
    with pytest.raises(install.InstallError):
        install.install("bogus", repo=None)


# --- CLI wrapper: routing + fail-loud exit code -----------------------------

def test_cli_install_master_succeeds(make_corpus, monkeypatch, capsys):
    from hypermnesic import cli
    _with_key(monkeypatch)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    rc = cli.main(["install", str(repo), "--role", "master", "--bind", TAILNET_IP, "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["role"] == "master" and _KEY not in json.dumps(out)


def test_cli_install_engine_role_without_key_returns_1(make_corpus, monkeypatch, tmp_path, capsys):
    from hypermnesic import cli
    _no_key(monkeypatch, tmp_path)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    rc = cli.main(["install", str(repo), "--role", "master", "--bind", TAILNET_IP])
    assert rc == 1                                              # fail loud, clean non-zero exit
    assert "install failed" in capsys.readouterr().err


# --- review fixes -----------------------------------------------------------

def test_engine_role_on_non_git_repo_fails_loud_no_artifacts(make_corpus, monkeypatch):
    # Review #4: a non-git repo must fail BEFORE any artifact is written (no half-provision)
    # and as InstallError (not a raw FileNotFoundError from install_hooks).
    _with_key(monkeypatch)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"}, git=False)
    with pytest.raises(install.InstallError):
        install.install("master", repo=repo, bind=TAILNET_IP)
    assert not (repo / ".hypermnesic" / "hypermnesic.service").exists()
    assert not (repo / ".hypermnesic" / "config.json").exists()


def test_cli_install_non_git_returns_1_not_traceback(make_corpus, monkeypatch, tmp_path, capsys):
    from hypermnesic import cli
    _with_key(monkeypatch)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"}, git=False)
    rc = cli.main(["install", str(repo), "--role", "master", "--bind", TAILNET_IP])
    assert rc == 1 and "install failed" in capsys.readouterr().err


def test_client_resets_malformed_mcpservers(monkeypatch, tmp_path):
    # Review #7: an existing config whose mcpServers is a non-dict must not raise TypeError.
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"mcpServers": ["oops"]}))
    url = "http://m/mcp"
    install.install("client", master_url=url, mcp_config_path=str(cfg))
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["hypermnesic"]["url"] == url     # reset to a dict, no crash


def test_strip_managed_preserves_content_when_end_marker_missing():
    # Review #9: a managed block with no END marker (truncated/corrupt) must not delete
    # the operator's trailing content.
    text = f"#!/bin/sh\necho keep-me\n{install._MANAGED_BEGIN}\nmanaged line\n"
    out = install._strip_managed(text)
    assert "keep-me" in out and "managed line" in out


def test_managed_block_shell_quotes_repo_path():
    # Review #6: a repo path with shell metacharacters is shlex-quoted in the hook command.
    block = install._managed_block(Path("/tmp/has space/repo"))
    assert "converge '/tmp/has space/repo'" in block
