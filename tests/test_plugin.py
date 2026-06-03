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


# --- U4: the distributed plugin's MCP wiring is OAuth-discovery-only + distribution-generic ----

def test_plugin_mcp_json_is_discovery_only_and_distribution_generic():
    # KD7/R16: Claude Code performs OAuth discovery from {type, url} alone, and a static
    # Authorization header would SUPPRESS the OAuth fallback. So the distributed wiring carries no
    # `auth`/`token_env` block and no Authorization header — just an env-templated URL the user
    # points at their own endpoint. No operator hostname (a stranger must not hit the operator's
    # brain), no inlined secret.
    raw = (_PLUGIN_DIR / ".mcp.json").read_text(encoding="utf-8")
    mcp = json.loads(raw)
    entry = mcp["mcpServers"]["hypermnesic"]
    assert entry["type"] == "streamable-http"
    assert "${HYPERMNESIC_MCP_URL" in entry["url"]                # env-templated, not hardcoded
    assert "auth" not in entry                                    # OAuth via discovery, no block
    assert "token_env" not in raw                                 # no token pointer
    assert "Authorization" not in raw and "Bearer" not in raw     # no static header (kills OAuth)
    assert "taildabf2" not in raw and "homelab" not in raw.lower()  # no operator hostname
    assert "HYPERMNESIC_MCP_TOKEN=" not in raw                    # secret-free


def test_plugin_tree_carries_no_operator_specific_values():
    # AE6/R17: distribution-ready — a scan of the published plugin tree finds no homelab hostname,
    # tailnet IP, absolute home path, chezmoi reference, or device name. Author/identity metadata
    # in manifests (name/email/homepage) is permitted and is NOT scanned for here.
    op_pat = re.compile(
        r"(taildabf2|homelab\.tail|\b100\.103\.|\b100\.64\.|/home/[a-z]|chezmoi)", re.IGNORECASE)
    for p in _all_plugin_files():
        if p.suffix == ".pyc":
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        hit = op_pat.search(txt)
        assert hit is None, f"operator-specific value {hit.group(0)!r} in {p}"
