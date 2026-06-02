"""U28 — CLI read entrypoints converge before serving.

``retrieve`` (new) mirrors the MCP ``search`` hit shape; ``think`` converges
first. Tests run fully offline + deterministic: the key is neutralized so the
dense channel degrades to lexical (the index is still caught up to HEAD via the
lexical delta-replay, which needs no embedder).
"""

from __future__ import annotations

import json
import subprocess

from hypermnesic import cli, config, index


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
