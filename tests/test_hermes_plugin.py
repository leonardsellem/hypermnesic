"""Hermes Agent plugin pack: static validation only.

Hermes support is a sibling surface to the Claude/Codex marketplace plugin. It is
CLI-first: Hermes uses the local ``hypermnesic`` command, not the hypermnesic MCP
server, Claude/Codex manifests, or Claude's hook protocol.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from ruamel.yaml import YAML

_REPO = Path(__file__).resolve().parents[1]
_PLUGIN = _REPO / "plugin"
_HERMES = _PLUGIN / "hermes"
_MANIFEST = _HERMES / "plugin.yaml"
_ENTRYPOINT = _HERMES / "__init__.py"
_SKILL = _HERMES / "skills" / "hypermnesic-memory" / "SKILL.md"
_FLAT_SKILL = _HERMES / "flat-skill" / "hypermnesic-memory" / "SKILL.md"
_README = _HERMES / "README.md"
_PLUGIN_README = _PLUGIN / "README.md"

_CLI_COMMANDS = ("retrieve", "think", "resolve", "list-folders", "capture", "commit-note")


def _yaml(path: Path) -> dict:
    return dict(YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {})


def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---"), "SKILL.md must open with a YAML frontmatter block"
    end = text.index("\n---", 3)
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def _all_hermes_files() -> list[Path]:
    return [p for p in _HERMES.rglob("*") if p.is_file() and p.suffix != ".pyc"]


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("hypermnesic_hermes_plugin", _ENTRYPOINT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_hermes_manifest_parses_with_required_fields():
    data = _yaml(_MANIFEST)
    assert data["name"] == "hypermnesic"
    assert data["version"] and data["description"]
    assert "CLI" in data["description"] or "cli" in data["description"]
    assert "pre_llm_call" in data.get("provides_hooks", [])


def test_hermes_entrypoint_registers_skill_and_uses_hermes_api(monkeypatch):
    monkeypatch.delenv("HYPERMNESIC_HERMES_RECALL", raising=False)
    mod = _load_entrypoint()
    assert callable(mod.register)

    class Ctx:
        def __init__(self):
            self.skills: list[tuple[str, Path, str]] = []
            self.hooks: list[tuple[str, object]] = []

        def register_skill(self, name, path, description=""):
            self.skills.append((name, Path(path), description))

        def register_hook(self, name, callback):
            self.hooks.append((name, callback))

    ctx = Ctx()
    mod.register(ctx)
    assert ctx.skills == [("hypermnesic-memory", _SKILL, "")]
    assert ctx.hooks == []

    src = _ENTRYPOINT.read_text(encoding="utf-8")
    assert "register_skill" in src
    assert ".claude-plugin" not in src and ".codex-plugin" not in src
    assert "UserPromptSubmit" not in src


def test_hermes_plugin_registers_optional_pre_llm_call_hook(monkeypatch):
    monkeypatch.setenv("HYPERMNESIC_HERMES_RECALL", "1")
    mod = _load_entrypoint()

    class Ctx:
        def __init__(self):
            self.skills = []
            self.hooks = []

        def register_skill(self, name, path, description=""):
            self.skills.append((name, path, description))

        def register_hook(self, name, callback):
            self.hooks.append((name, callback))

    ctx = Ctx()
    mod.register(ctx)
    assert ctx.hooks and ctx.hooks[0][0] == "pre_llm_call"


def test_hermes_skill_frontmatter_and_cli_command_contract():
    text = _SKILL.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert fm.get("name") == "hypermnesic-memory"
    assert fm.get("description")
    for command in _CLI_COMMANDS:
        assert command in text, f"Hermes skill must teach CLI command {command!r}"
    assert "git" in text.lower() and "source of truth" in text.lower()
    assert "dry-run" in text.lower() and "commit-note" in text
    assert "capture" in text and "commits" in text.lower()


def test_flat_skill_matches_plugin_skill_body():
    assert _FLAT_SKILL.read_text(encoding="utf-8") == _SKILL.read_text(encoding="utf-8")


def test_hermes_package_has_no_mcp_transport_or_claude_codex_loader_assumptions():
    forbidden = (
        ".mcp.json",
        "hermes mcp add",
        "hermes mcp login",
        "hermes mcp test",
        "mcp_hypermnesic_",
        "HYPERMNESIC_MCP_TOKEN",
        "Authorization",
        "Bearer ",
        "UserPromptSubmit",
        ".claude-plugin",
        ".codex-plugin",
    )
    for p in _all_hermes_files():
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for needle in forbidden:
            assert needle not in txt, f"{needle!r} must not appear in Hermes package file {p}"


def test_hermes_package_carries_no_operator_specific_values_or_secrets():
    op_pat = re.compile(
        r"(\.ts\.net|homelab\.tail|\b100\.103\.|\b100\.64\.|/home/[a-z]|chezmoi|gbrain)",
        re.IGNORECASE,
    )
    secret_pat = re.compile(
        r"(sk-[A-Za-z0-9]{20,}"
        r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
        r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
        r"|[A-Z0-9_]*TOKEN\s*=\s*[\"']?[A-Za-z0-9][A-Za-z0-9_\-]{11,})"
    )
    for p in _all_hermes_files():
        txt = p.read_text(encoding="utf-8", errors="ignore")
        assert not op_pat.search(txt), f"operator-specific value in {p}"
        assert not secret_pat.search(txt), f"possible secret material in {p}"


def test_hermes_readme_and_plugin_readme_explain_surface_split():
    hermes = _README.read_text(encoding="utf-8")
    assert "hypermnesic CLI" in hermes
    assert "HYPERMNESIC_REPO" in hermes
    assert "HYPERMNESIC_HERMES_RECALL" in hermes
    assert "flat skill" in hermes.lower()
    assert "capture" in hermes and "commit-note" in hermes and "dry-run" in hermes.lower()

    plugin_readme = _PLUGIN_README.read_text(encoding="utf-8")
    assert "Hermes" in plugin_readme and "plugin/hermes" in plugin_readme
    assert "Claude Code + Codex" in plugin_readme


def test_hermes_skills_route_memory_taxonomy_without_preference_overreach():
    for path in (_SKILL, _FLAT_SKILL):
        text = path.read_text(encoding="utf-8").lower()
        assert "durable project memory" in text
        assert "user likes terse replies" in text
        assert "honcho" in text and "behavioural" in text
        assert "do not write" in text and "secrets" in text and "credentials" in text
        assert "list-folders" in text and "writable" in text
        assert "source paths" in text and "preserve raw evidence" in text
        assert "refusals are control signals" in text
