from __future__ import annotations

from hypermnesic import config

_KEY_NAME = "OPENAI_" + "API_KEY"


def _dotenv_line(value: str) -> str:
    return f"{_KEY_NAME}={value}\n"


def test_api_key_status_finds_repo_dotenv_from_different_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    repo_key = "repo-test-key"
    repo = tmp_path / "vault"
    repo.mkdir()
    (repo / ".env").write_text(_dotenv_line(f"'{repo_key}'"), encoding="utf-8")
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(config, "_DOTENV_PATHS", [cwd / ".env"])

    status = config.api_key_status(repo)

    assert status.configured is True
    assert status.source == "repo_dotenv"
    assert config.get_api_key(repo) == repo_key
    assert repo_key not in repr(status)


def test_process_env_precedes_repo_dotenv(monkeypatch, tmp_path):
    repo_key = "repo-test-key"
    env_key = "env-test-key"
    repo = tmp_path / "vault"
    repo.mkdir()
    (repo / ".env").write_text(_dotenv_line(repo_key), encoding="utf-8")
    monkeypatch.setenv(_KEY_NAME, env_key)

    status = config.api_key_status(repo)

    assert status.configured is True
    assert status.source == "process_env"
    assert config.get_api_key(repo) == env_key
    assert repo_key not in repr(status)
    assert env_key not in repr(status)


def test_repo_context_does_not_fall_back_to_cwd_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    cwd_key = "cwd-test-key"
    repo = tmp_path / "vault"
    repo.mkdir()
    cwd_env = tmp_path / "cwd.env"
    cwd_env.write_text(_dotenv_line(cwd_key), encoding="utf-8")
    monkeypatch.setattr(config, "_DOTENV_PATHS", [cwd_env])

    status = config.api_key_status(repo)

    assert status.configured is False
    assert status.source == "missing"


def test_cwd_dotenv_fallback_when_no_repo_context(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    cwd_key = "cwd-test-key"
    cwd_env = tmp_path / "cwd.env"
    cwd_env.write_text(_dotenv_line(cwd_key), encoding="utf-8")
    monkeypatch.setattr(config, "_DOTENV_PATHS", [cwd_env])

    status = config.api_key_status(repo=None)

    assert status.configured is True
    assert status.source == "cwd_dotenv"
    assert config.get_api_key(repo=None) == cwd_key


def test_missing_key_reports_missing_without_paths_or_secret(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    repo = tmp_path / "vault"
    repo.mkdir()
    monkeypatch.setattr(config, "_DOTENV_PATHS", [tmp_path / "absent.env"])

    status = config.api_key_status(repo)

    assert status.configured is False
    assert status.source == "missing"
    assert str(tmp_path) not in repr(status)


def test_unreadable_repo_dotenv_is_distinguishable(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    repo = tmp_path / "vault"
    repo.mkdir()
    env = repo / ".env"
    env.write_text(_dotenv_line("repo-test-key"), encoding="utf-8")
    original_read_text = type(env).read_text

    def fake_read_text(self, *args, **kwargs):
        if self == env:
            raise OSError("nope")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(env), "read_text", fake_read_text)

    status = config.api_key_status(repo)

    assert status.configured is False
    assert status.source == "missing"
    assert status.error == "repo_dotenv_unreadable"
    assert str(repo) not in repr(status)


def test_openai_embedder_carries_repo_context(tmp_path):
    from hypermnesic.embed import OpenAIEmbedder

    repo = tmp_path / "vault"
    repo.mkdir()
    emb = OpenAIEmbedder(repo=repo)

    assert emb.repo == repo


def test_openai_embedder_uses_repo_context_for_lazy_key_lookup(monkeypatch, tmp_path):
    from hypermnesic.embed import OpenAIEmbedder

    repo = tmp_path / "vault"
    repo.mkdir()
    seen = {}

    def fake_get_api_key(*, repo=None):
        seen["repo"] = repo
        return "env-test-key"

    class FakeEmbeddings:
        def create(self, **_kwargs):
            item = type("Item", (), {"embedding": [0.0] * config.EMBED_DIM})()
            return type("Resp", (), {"data": [item]})()

    class FakeClient:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(config, "get_api_key", fake_get_api_key)
    monkeypatch.setattr("openai.OpenAI", FakeClient)

    OpenAIEmbedder(repo=repo).embed(["probe"])

    assert seen["repo"] == repo


def test_openai_embedder_rate_limit_enters_cooldown(monkeypatch):
    from hypermnesic.embed import EmbeddingError, OpenAIEmbedder

    calls = {"n": 0}
    now = {"t": 1000.0}

    class RateLimited(Exception):
        status_code = 429

    class FakeEmbeddings:
        def create(self, **_kwargs):
            calls["n"] += 1
            raise RateLimited("quota exhausted")

    class FakeClient:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr("openai.OpenAI", FakeClient)

    emb = OpenAIEmbedder(
        api_key="env-test-key",
        cooldown_seconds=60.0,
        now_fn=lambda: now["t"],
    )

    try:
        emb.embed(["first"])
    except EmbeddingError as exc:
        assert exc.reason == "rate_limited"
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected rate-limit failure")

    try:
        emb.embed(["second"])
    except EmbeddingError as exc:
        assert exc.reason == "cooldown"
        assert "rate_limited" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected cooldown failure")

    assert calls["n"] == 1

    now["t"] = 1061.0
    try:
        emb.embed(["third"])
    except EmbeddingError as exc:
        assert exc.reason == "rate_limited"

    assert calls["n"] == 2


def test_smoke_embed_or_die_uses_repo_context(monkeypatch, tmp_path):
    from hypermnesic import embed

    repo = tmp_path / "vault"
    repo.mkdir()
    seen = {}

    def fake_get_api_key(*, repo=None):
        seen["repo"] = repo
        return "env-test-key"

    class FakeEmbedder:
        dim = config.EMBED_DIM

        def embed(self, texts):
            assert texts
            return [[0.0] * self.dim]

    monkeypatch.setattr(config, "get_api_key", fake_get_api_key)

    embed.smoke_embed_or_die(embedder=FakeEmbedder(), repo=repo)

    assert seen["repo"] == repo
