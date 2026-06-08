"""Multi-query expansion output parsing (offline)."""

from __future__ import annotations

from hypermnesic import expand


def test_parse_strips_numbering_dedups_and_caps():
    text = "1. how does X work\n2. X internals\n- how does X work\nwhat is X\n"
    out = expand._parse(text, query="how does X work?", n=2)
    assert out == ["how does X work", "X internals"]  # numbering stripped, capped at 2


def test_parse_drops_echo_of_query():
    out = expand._parse("the original query\na fresh variant", "The Original Query", n=5)
    assert "the original query" not in [s.lower() for s in out]
    assert "a fresh variant" in out


def test_parse_empty_is_empty():
    assert expand._parse("", "q", 3) == []
    assert expand._parse(None, "q", 3) == []


def test_openai_expander_uses_repo_context_for_lazy_key_lookup(monkeypatch, tmp_path):
    from hypermnesic import config

    repo = tmp_path / "vault"
    repo.mkdir()
    seen = {}

    def fake_get_api_key(*, repo=None):
        seen["repo"] = repo
        return "env-test-key"

    class FakeClient:
        def __init__(self, *, api_key):
            self.api_key = api_key

    monkeypatch.setattr(config, "get_api_key", fake_get_api_key)
    monkeypatch.setattr("openai.OpenAI", FakeClient)

    expander = expand.OpenAIExpander(repo=repo)
    assert expander._get_client().api_key == "env-test-key"
    assert seen["repo"] == repo
