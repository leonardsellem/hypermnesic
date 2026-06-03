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


def test_claude_manifest_does_not_redeclare_autoloaded_hooks():
    # Regression (reproduced live: `claude plugin list` → "✘ failed to load: Duplicate hooks
    # file detected: ./hooks/hooks.json ..."). Claude Code AUTO-loads the standard
    # hooks/hooks.json, so a manifest `hooks` key pointing at that same path is a duplicate that
    # fails the WHOLE plugin load — SKILL + hooks both go dead (Gate-A criteria 7/9). The standard
    # hook file must exist; the manifest must NOT re-reference it (manifest.hooks is for
    # *additional* hook files only, per the loader's own error message).
    cm = json.loads(_CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    assert (_PLUGIN_DIR / "hooks" / "hooks.json").exists()       # the auto-loaded file is present
    ref = cm.get("hooks")
    if ref is not None:                                          # absent (preferred) is fine
        refs = [ref] if isinstance(ref, str) else list(ref)
        assert not ({"./hooks/hooks.json", "hooks/hooks.json"} & set(refs)), (
            "manifest.hooks must not re-declare the auto-loaded standard hooks/hooks.json")


def test_skill_frontmatter_parses_and_names_only_real_tools():
    text = _SKILL.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert fm.get("name") == "hypermnesic-memory" and fm.get("description")
    for tool in _REAL_TOOLS:
        assert tool in text, f"SKILL must teach the real tool {tool!r}"
    # no invented tool names that the engine does not expose
    for fake in ("get_page", "put_page", "vector_search", "remember", "recall_all"):
        assert fake not in text, f"SKILL references nonexistent tool {fake!r}"


def test_skill_is_user_neutral_and_teaches_disk_first():
    # the plugin is distributed through a public repo, so the SKILL must be user-neutral: no
    # migration steering (gbrain) and no operator-specific hardcoded endpoint. It must still
    # teach the disk-first model.
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "gbrain" not in text                             # no migration steering
    assert "taildabf2" not in text and "homelab.tail" not in text   # no hardcoded endpoint
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
    assert entry["url"].startswith("https://homelab.taildabf2.ts.net")  # the preserved hostname
    assert entry["auth"]["type"] == "oauth2"
    assert entry["auth"]["token_env"] == "HYPERMNESIC_MCP_TOKEN"         # pointer, not a value
    # the issuer must be the hypermnesic AS, NOT honcho (U12: honcho can't be hypermnesic's AS —
    # no introspection/JWKS, audience hardwired to .../honcho/mcp, so it cannot mint a .../mcp
    # audience token the master would accept). Regression guard for the shipped honcho issuer.
    assert "honcho" not in entry["auth"]["issuer"].lower()
    assert entry["auth"]["resource"] == "https://homelab.taildabf2.ts.net/mcp"  # canonical audience
    blob = json.dumps(mcp)
    assert "HYPERMNESIC_MCP_TOKEN=" not in blob and "Bearer " not in blob # no inlined secret
