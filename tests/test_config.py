from __future__ import annotations

import pytest

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


def test_clear_cooldown_allows_one_retry_then_rearms(monkeypatch):
    """R2: the drain may clear the cooldown for one retry; a second 429 re-arms it."""
    from hypermnesic.embed import EmbeddingError, OpenAIEmbedder

    calls = {"n": 0}
    now = {"t": 1000.0}

    class RateLimited(Exception):
        status_code = 429

    class FakeEmbeddings:
        def create(self, **_kwargs):
            calls["n"] += 1
            raise RateLimited("no credits remaining")

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

    with pytest.raises(EmbeddingError) as first:
        emb.embed(["first"])
    assert first.value.reason == "rate_limited"
    assert calls["n"] == 1

    emb.clear_cooldown()                                  # the one permitted retry
    now["t"] = 1000.5
    with pytest.raises(EmbeddingError) as second:
        emb.embed(["second"])
    assert second.value.reason == "rate_limited"          # reached the provider again
    assert calls["n"] == 2

    with pytest.raises(EmbeddingError) as third:
        emb.embed(["third"])
    assert third.value.reason == "cooldown"                # re-armed by the second 429
    assert calls["n"] == 2                                 # no provider call in cooldown


def test_cloud_token_ttl_default_is_48_hours(monkeypatch):
    monkeypatch.delenv(config.TOKEN_TTL_ENV, raising=False)
    assert config.CLOUD_TOKEN_TTL_SECONDS == 48 * 60 * 60 == 172800
    assert config.cloud_token_ttl_seconds() == 172800


def test_cloud_token_ttl_env_override(monkeypatch):
    monkeypatch.setenv(config.TOKEN_TTL_ENV, "7200")
    assert config.cloud_token_ttl_seconds() == 7200


def test_cloud_token_ttl_explicit_override_wins_over_env(monkeypatch):
    monkeypatch.setenv(config.TOKEN_TTL_ENV, "7200")
    assert config.cloud_token_ttl_seconds(1800) == 1800


def test_cloud_token_ttl_rejects_non_positive_and_invalid_env(monkeypatch):
    monkeypatch.delenv(config.TOKEN_TTL_ENV, raising=False)
    with pytest.raises(config.ConfigError):
        config.cloud_token_ttl_seconds(0)
    monkeypatch.setenv(config.TOKEN_TTL_ENV, "nope")
    with pytest.raises(config.ConfigError):
        config.cloud_token_ttl_seconds()


# --- LS-4075 R4: sanitized provider metadata, never a billing verdict --------


class _SdkLike429(Exception):
    """Shape of an OpenAI SDK 429: status_code + a body dict."""

    status_code = 429

    def __init__(self, body):
        super().__init__("429 rate limit")
        self.body = body


class _RaisingClient:
    def __init__(self, exc):
        self._exc = exc

    @property
    def embeddings(self):
        return self

    def create(self, **kwargs):
        raise self._exc


def _failing_embedder(exc):
    from hypermnesic import embed as embed_mod

    emb = embed_mod.OpenAIEmbedder(api_key="unit-test-key", cooldown_seconds=0)
    emb._client = _RaisingClient(exc)
    return emb


def test_provider_code_is_preserved_without_billing_verdict():

    from hypermnesic import embed as embed_mod

    quota = _failing_embedder(_SdkLike429(
        {"error": {"code": "insufficient_quota", "type": "insufficient_quota"}}))
    with pytest.raises(embed_mod.EmbeddingError) as quota_info:
        quota.embed(["x"])
    quota_err = quota_info.value
    # A quota-named body keeps its code/type as *reported* provider metadata…
    assert quota_err.reason == "rate_limited"
    assert quota_err.provider_code == "insufficient_quota"
    assert quota_err.provider_type == "insufficient_quota"
    # …and the engine still asserts no account/billing verdict anywhere.
    assert not hasattr(quota_err, "account_state")
    assert "no credits" not in str(quota_err).lower()

    plain = _failing_embedder(_SdkLike429({"error": {"message": "slow down"}}))
    with pytest.raises(embed_mod.EmbeddingError) as plain_info:
        plain.embed(["x"])
    plain_err = plain_info.value
    # A plain 429 stays a plain retryable rate limit — no invented quota code.
    assert plain_err.reason == "rate_limited"
    assert plain_err.provider_code is None and plain_err.provider_type is None


def test_provider_code_redacts_untrusted_body():
    import json

    from hypermnesic import embed as embed_mod

    secret = "untrusted secret phrase 1234567890"
    body = {"error": {
        "code": f"{secret} input=customer private text",
        "type": {"nested": secret},
    }}
    emb = _failing_embedder(_SdkLike429(body))
    with pytest.raises(embed_mod.EmbeddingError) as info:
        emb.embed(["x"])
    err = info.value
    assert err.reason == "rate_limited"
    assert err.provider_code is None              # untrusted scalar is not echoed
    assert err.provider_type is None
    serialized = json.dumps({"provider_code": err.provider_code,
                             "provider_type": err.provider_type,
                             "reason": err.reason})
    assert secret not in serialized
    assert "customer private text" not in serialized

    long_code = "a" * 200
    emb2 = _failing_embedder(_SdkLike429({"error": {"code": long_code}}))
    with pytest.raises(embed_mod.EmbeddingError) as info2:
        emb2.embed(["x"])
    assert info2.value.provider_code is None      # bounded allowlisted scalars only
