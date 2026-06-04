from __future__ import annotations

import json
import subprocess

from hypermnesic import config, doctor, index

PUBLIC_URL = "https://example.ts.net/mcp"


def _head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


class _DoctorOps:
    def __init__(self, *, tailscale_ready=True, verify_ok=True):
        self._tailscale_ready = tailscale_ready
        self._verify_ok = verify_ok
        self.verify_calls: list[tuple[str, str]] = []
        self.mutating_calls: list[str] = []

    def tailscale_ready(self) -> bool:
        return self._tailscale_ready

    def verify_discovery(self, public_url: str, resource: str) -> dict:
        self.verify_calls.append((public_url, resource))
        return {
            "ok": self._verify_ok,
            "checks": {
                "protected_resource": self._verify_ok,
                "as_metadata": self._verify_ok,
                "unauth_401": self._verify_ok,
            },
        }

    def apply_funnel_route(self, *_args):
        self.mutating_calls.append("apply_funnel_route")

    def install_and_start_service(self, *_args):
        self.mutating_calls.append("install_and_start_service")


def _build_index(repo, fake_embedder):
    idx = index.build_index(repo, fake_embedder)
    idx.close()


def test_doctor_reports_local_remote_oauth_auth_write_and_next_action(
        make_corpus, fake_embedder, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "D" * 24)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    _build_index(repo, fake_embedder)
    env_file = tmp_path / "cloud.env"
    env_file.write_text("HYPERMNESIC_CLOUD_APPROVAL" + "_TOKEN=stub\n")
    env_file.chmod(0o600)
    ops = _DoctorOps()

    result = doctor.run_doctor(
        repo,
        public_url=PUBLIC_URL,
        resource=PUBLIC_URL,
        env_file=env_file,
        ops=ops,
    ).as_dict()

    assert result["status"] == "ready"
    assert result["what_this_means"]
    checks = {c["id"]: c for c in result["checks"]}
    for cid in (
        "local_git_repo",
        "local_index",
        "dense_retrieval",
        "tailscale",
        "service_unit",
        "oauth_discovery",
        "auth_challenge",
        "write_availability",
    ):
        assert cid in checks
        assert checks[cid]["category"] in {"local", "remote", "oauth", "auth", "write"}
        assert checks[cid]["next_action"]["code"]
        assert checks[cid]["summary"]
    assert checks["oauth_discovery"]["status"] == "pass"
    assert checks["auth_challenge"]["status"] == "pass"
    assert checks["write_availability"]["status"] == "pass"
    assert result["next_actions"]["remote_mcp"]["url"] == PUBLIC_URL
    assert ops.verify_calls == [(PUBLIC_URL, PUBLIC_URL)]


def test_doctor_without_public_url_keeps_local_health_separate(make_corpus, fake_embedder,
                                                               monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config, "_DOTENV_PATHS", [tmp_path / "absent.env"])
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    _build_index(repo, fake_embedder)
    ops = _DoctorOps(tailscale_ready=False)

    out = doctor.run_doctor(repo, ops=ops).as_dict()
    checks = {c["id"]: c for c in out["checks"]}

    assert out["status"] == "needs_attention"
    assert checks["local_git_repo"]["status"] == "pass"
    assert checks["local_index"]["status"] == "pass"
    assert checks["remote_url"]["status"] == "skipped"
    assert checks["oauth_discovery"]["status"] == "skipped"
    assert checks["dense_retrieval"]["next_action"]["code"] == "configure_key"
    assert ops.verify_calls == []


def test_doctor_tailscale_missing_maps_to_action_category(make_corpus, fake_embedder, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "D" * 24)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    _build_index(repo, fake_embedder)
    ops = _DoctorOps(tailscale_ready=False)

    out = doctor.run_doctor(repo, public_url=PUBLIC_URL, ops=ops).as_dict()
    checks = {c["id"]: c for c in out["checks"]}

    assert checks["tailscale"]["status"] == "fail"
    assert checks["tailscale"]["next_action"]["code"] == "authenticate_tailscale"
    assert "tailscale up" in checks["tailscale"]["next_action"]["command"]


def test_doctor_is_non_mutating(make_corpus, fake_embedder, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "D" * 24)
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    _build_index(repo, fake_embedder)
    before_head = _head(repo)
    before_files = sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file())
    env_file = tmp_path / "missing.env"
    ops = _DoctorOps()

    doctor.run_doctor(repo, public_url=PUBLIC_URL, env_file=env_file, ops=ops)

    after_files = sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file())
    assert _head(repo) == before_head
    assert after_files == before_files
    assert not env_file.exists()
    assert ops.mutating_calls == []


def test_doctor_output_is_secret_free(make_corpus, fake_embedder, monkeypatch, tmp_path):
    secret = "op-secret-value-that-must-not-leak"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "D" * 24)
    repo = make_corpus({
        "secret.md": "# Secret\n\nPRIVATE-BODY-VALUE should not appear in diagnostics.\n"
    })
    _build_index(repo, fake_embedder)
    env_file = tmp_path / "cloud.env"
    env_file.write_text("HYPERMNESIC_CLOUD_APPROVAL" + f"_TOKEN={secret}\n")
    env_file.chmod(0o600)

    out = doctor.run_doctor(
        repo,
        public_url=PUBLIC_URL,
        env_file=env_file,
        ops=_DoctorOps(),
    ).as_dict()
    text = json.dumps(out)

    assert secret not in text
    assert "PRIVATE-BODY-VALUE" not in text
    assert "HYPERMNESIC_CLOUD_APPROVAL" + "_TOKEN=" not in text
    assert str(env_file) not in text
    assert "/home/" + "ubuntu" not in text


def test_doctor_cli_json_and_status_alias(make_corpus, fake_embedder, monkeypatch, capsys):
    from hypermnesic import cli

    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    _build_index(repo, fake_embedder)

    rc = cli.main(["doctor", str(repo), "--json"])
    doctor_out = json.loads(capsys.readouterr().out)
    rc2 = cli.main(["status", str(repo), "--json"])
    status_out = json.loads(capsys.readouterr().out)

    assert rc == 0 and rc2 == 0
    assert doctor_out["status"] in {"ready", "needs_attention"}
    assert status_out["checks"] == doctor_out["checks"]


def test_doctor_human_output_is_actionable(make_corpus, fake_embedder, monkeypatch, capsys):
    from hypermnesic import cli

    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    _build_index(repo, fake_embedder)

    rc = cli.main(["doctor", str(repo)])
    out = capsys.readouterr().out.lower()

    assert rc == 0
    assert "what this means" in out
    assert "next:" in out
    assert "traceback" not in out
