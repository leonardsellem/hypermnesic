"""U25 — Obsidian companion plugin: scripted read-only assertion. [R6/H2/KD2]

The plugin is TypeScript (outside the runtime pytest path), so its trust-critical
property — **issues only read calls, never writes the vault** — is verified by a
static check here, as the plan prescribes ("a scripted check that it issues only
``search``/``build_context``"). A live Obsidian load is the manual verification.
"""

from __future__ import annotations

import json
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[1] / "obsidian-plugin"
_MAIN = _PLUGIN / "main.ts"
_MANIFEST = _PLUGIN / "manifest.json"


def test_plugin_files_exist():
    assert _MAIN.exists() and _MANIFEST.exists() and (_PLUGIN / "README.md").exists()


def test_plugin_calls_only_read_tools():
    src = _MAIN.read_text(encoding="utf-8")
    assert "search" in src and "build_context" in src
    # the hard allowlist that makes the client structurally read-only
    assert 'READ_ONLY_TOOLS = new Set(["search", "build_context"])' in src


def test_plugin_performs_no_vault_writes():
    src = _MAIN.read_text(encoding="utf-8")
    # match the actual CALL form (trailing "(") — the read-only-guarantee comment
    # legitimately names these APIs in prose.
    forbidden = [
        "vault.modify(", "vault.create(", "vault.delete(", "vault.append(",
        "vault.trash(", "adapter.write(", "adapter.append(",
    ]
    present = [w for w in forbidden if w in src]
    assert present == [], f"plugin must not write the vault, found: {present}"


def test_manifest_is_desktop_only_and_well_formed():
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["id"] == "hypermnesic-companion"
    assert manifest["isDesktopOnly"] is True          # CodeMirror-6 mobile parity is deferred
    assert "version" in manifest and "minAppVersion" in manifest
