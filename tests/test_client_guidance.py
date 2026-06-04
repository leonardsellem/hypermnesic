from __future__ import annotations

import json

from hypermnesic.client_guidance import client_next_actions


def test_client_guidance_distinguishes_local_and_remote_clients():
    actions = client_next_actions("https://example.ts.net/mcp")
    by_id = {a["id"]: a for a in actions}

    assert by_id["local_cli"]["mode"] == "local"
    assert "hypermnesic retrieve" in by_id["local_cli"]["command"]
    assert by_id["remote_mcp"]["mode"] == "remote"
    assert by_id["remote_mcp"]["url"] == "https://example.ts.net/mcp"
    assert "OAuth" in by_id["claude_codex_plugin"]["summary"]
    assert "tailnet read route" in by_id["obsidian_companion"]["summary"]


def test_client_guidance_without_public_url_is_local_first():
    actions = client_next_actions(None)
    by_id = {a["id"]: a for a in actions}

    assert by_id["local_cli"]["available"] is True
    assert by_id["remote_mcp"]["available"] is False
    assert "Run setup" in by_id["remote_mcp"]["next_action"]


def test_client_guidance_is_secret_free():
    text = json.dumps(client_next_actions("https://example.ts.net/mcp"))

    assert "Authorization" not in text
    assert "Bearer " not in text
    assert "token=" not in text.lower()
    assert "HYPERMNESIC_CLOUD_APPROVAL" + "_TOKEN=" not in text
