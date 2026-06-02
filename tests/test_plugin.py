"""U3 — Claude+Codex plugin marketplace: static validation only.

The plugin is config + prose (manifests, a SKILL, hooks, MCP wiring) consumed by the
Claude/Codex harnesses, not by the engine runtime — so its correctness properties are
checked statically here: the marketplace lists the plugin with a real source, both
manifests parse with required fields, the SKILL frontmatter parses and names only real
engine tools (and tells agents NOT to use gbrain), and no secret is committed anywhere
in the plugin tree. A live install on both hosts is the Gate-A verification.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PLUGIN = _REPO / "plugin"
_MARKETPLACE = _PLUGIN / ".claude-plugin" / "marketplace.json"
_PLUGIN_DIR = _PLUGIN / "plugins" / "hypermnesic"
_CLAUDE_MANIFEST = _PLUGIN_DIR / ".claude-plugin" / "plugin.json"
_CODEX_MANIFEST = _PLUGIN_DIR / ".codex-plugin" / "plugin.json"
_SKILL = _PLUGIN_DIR / "skills" / "hypermnesic-memory" / "SKILL.md"
_README = _PLUGIN / "README.md"

# Real engine tool names (mcp_server.READ_TOOL_NAMES + the write tool). The SKILL must
# only teach these — a nonexistent tool name in the skill is a broken instruction.
_REAL_TOOLS = ("search", "build_context", "think", "resolve", "commit_note")


def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---"), "SKILL.md must open with a YAML frontmatter block"
    end = text.index("\n---", 3)
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def _all_plugin_files() -> list[Path]:
    return [p for p in _PLUGIN.rglob("*") if p.is_file()]


def test_marketplace_lists_hypermnesic_with_real_source():
    mp = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))
    assert mp.get("name")                                   # marketplace has a name
    entry = next(p for p in mp["plugins"] if p["name"] == "hypermnesic")
    assert entry["description"] and entry["version"]
    # the source path resolves to the real plugin dir (relative to the marketplace root)
    assert (_PLUGIN / entry["source"]).resolve() == _PLUGIN_DIR.resolve()


def test_claude_and_codex_manifests_parse_with_required_fields():
    cm = json.loads(_CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    assert cm["name"] == "hypermnesic" and cm["version"] and cm["description"]
    cd = json.loads(_CODEX_MANIFEST.read_text(encoding="utf-8"))
    assert cd["name"] == "hypermnesic" and "skills" in cd


def test_skill_frontmatter_parses_and_names_only_real_tools():
    text = _SKILL.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert fm.get("name") == "hypermnesic-memory" and fm.get("description")
    for tool in _REAL_TOOLS:
        assert tool in text, f"SKILL must teach the real tool {tool!r}"
    # no invented tool names that the engine does not expose
    for fake in ("get_page", "put_page", "vector_search", "remember", "recall_all"):
        assert fake not in text, f"SKILL references nonexistent tool {fake!r}"


def test_skill_teaches_disk_first_and_no_gbrain():
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "gbrain" in text                                 # explicitly addresses gbrain…
    assert "not" in text and "gbrain" in text               # …telling agents not to reach for it
    assert "git" in text and "source of truth" in text      # the disk-first model is taught


def test_no_secrets_committed_in_plugin_tree():
    secret_pat = re.compile(
        r"(sk-[A-Za-z0-9]{20,}"                              # OpenAI-style key
        r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"              # PEM private key
        r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"  # JWT
    )
    for p in _all_plugin_files():
        txt = p.read_text(encoding="utf-8", errors="ignore")
        assert not secret_pat.search(txt), f"possible secret material in {p}"
        # a token env var may be NAMED but never assigned an inline VALUE
        assert "HYPERMNESIC_MCP_TOKEN=" not in txt, f"inline token value in {p}"
        assert "GBRAIN_MCP_TOKEN" not in txt, f"stale gbrain token reference in {p}"


def test_plugin_readme_exists():
    assert _README.exists() and _README.read_text(encoding="utf-8").strip()


# --- U5: the plugin's self-hosted MCP wiring (OAuth2-aware, secret-free) ------

def test_plugin_mcp_json_is_oauth2_aware_and_secret_free():
    mcp = json.loads((_PLUGIN_DIR / ".mcp.json").read_text(encoding="utf-8"))
    entry = mcp["mcpServers"]["hypermnesic"]
    assert entry["type"] == "streamable-http"
    assert entry["url"].startswith("https://homelab.<tailnet-host>.ts.net")  # the preserved hostname
    assert entry["auth"]["type"] == "oauth2"
    assert entry["auth"]["token_env"] == "HYPERMNESIC_MCP_TOKEN"         # pointer, not a value
    blob = json.dumps(mcp)
    assert "HYPERMNESIC_MCP_TOKEN=" not in blob and "Bearer " not in blob # no inlined secret
