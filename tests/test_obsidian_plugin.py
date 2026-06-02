"""Obsidian companion plugin: static read-only assertions. [Phase 2.5 Plan 2]

The plugin is TypeScript (outside the runtime pytest path), so its trust-critical
property — **issues only read calls, never writes the vault** — is verified by a
static scan here; a live Obsidian load is the manual verification.

The redesign splits the plugin into modules (KTD6), so the scan now covers the
whole source tree (``main.ts`` + ``src/``) and the read-only allowlist is pinned
in its module (``src/core.ts``). Keeping the scan target and the allowlist
location in lockstep with the code is the R-1 mitigation: the read-only proof must
not silently regress as code moves between modules.
"""

from __future__ import annotations

import json
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[1] / "obsidian-plugin"
_MAIN = _PLUGIN / "main.ts"
_CORE = _PLUGIN / "src" / "core.ts"
_TYPES = _PLUGIN / "src" / "types.ts"
_MANIFEST = _PLUGIN / "manifest.json"


def _all_sources() -> dict[str, str]:
    """``main.ts`` + every ``.ts`` under ``src/`` — the full surface the read-only
    guarantee must hold across."""
    files = [_MAIN, *sorted((_PLUGIN / "src").rglob("*.ts"))]
    return {
        str(p.relative_to(_PLUGIN)): p.read_text(encoding="utf-8")
        for p in files
        if p.exists()
    }


def test_plugin_files_exist():
    assert _MAIN.exists() and _MANIFEST.exists() and (_PLUGIN / "README.md").exists()
    # Build scaffolding so the committed plugin actually builds (U35).
    assert (_PLUGIN / "package.json").exists()
    assert (_PLUGIN / "esbuild.config.mjs").exists()
    assert (_PLUGIN / "tsconfig.json").exists()


def test_plugin_calls_only_read_tools():
    core = _CORE.read_text(encoding="utf-8")
    # Every MCP call routes through this allowlist; the read tools mirror the
    # server's READ_TOOL_NAMES ({search, build_context, think}). The write tool
    # commit_note is never listed (U39 added `think` in lockstep with this line).
    assert 'READ_ONLY_TOOLS = new Set(["search", "build_context", "think"])' in core
    # The write tool is never referenced as a string literal (prose mentions in
    # the read-only rationale are fine; a quoted "commit_note" would be a usage).
    assert '"commit_note"' not in core


def test_plugin_performs_no_vault_writes():
    # Match the CALL form (trailing "(") across the whole tree — the read-only
    # comments legitimately name these APIs in prose; only calls are forbidden.
    forbidden = [
        "vault.modify(",
        "vault.create(",
        "vault.delete(",
        "vault.append(",
        "vault.trash(",
        "adapter.write(",
        "adapter.append(",
        "adapter.remove(",
    ]
    offenders: list[str] = []
    for name, src in _all_sources().items():
        offenders += [f"{name}:{w}" for w in forbidden if w in src]
    assert offenders == [], f"plugin must not write the vault, found: {offenders}"


def test_plugin_performs_no_editor_or_cm_writes():
    # The link-insertion surface (U3) is the first place the plugin could mutate
    # the active note, so the read-only proof is widened beyond vault.*/adapter.*
    # to the full editor + CodeMirror mutation surface. Editor mutators stay
    # method-qualified so Setting.setValue (a settings control) is not a false
    # positive; the bare CodeMirror `.dispatch(` is the canonical CM6 write path
    # the gutter extension could otherwise reach. Extend this list as the
    # Obsidian/CM6 API surface grows.
    forbidden = [
        "editor.replaceSelection(",
        "editor.replaceRange(",
        "editor.setValue(",
        "editor.setLine(",
        "editor.transaction(",
        "editor.exec(",
        ".dispatch(",  # CodeMirror EditorView.dispatch — the CM6 write door
        "vault.process(",
        "vault.rename(",
        "vault.copy(",
        "fileManager.processFrontMatter(",
        "fileManager.renameFile(",
    ]
    offenders: list[str] = []
    for name, src in _all_sources().items():
        offenders += [f"{name}:{w}" for w in forbidden if w in src]
    assert offenders == [], f"plugin must not mutate notes, found: {offenders}"


def test_insertion_module_imports_no_codemirror_editor():
    # The reference module resolves/renders existing notes and produces link TEXT
    # for the user to paste/drop; it must never reach for a CodeMirror editor
    # module (drag/clipboard need neither). This keeps the insertion surface
    # structurally incapable of an editor write, not merely scanned for one.
    ref = (_PLUGIN / "src" / "surfaces" / "reference.ts").read_text(encoding="utf-8")
    assert "@codemirror/view" not in ref, "reference.ts must not import @codemirror/view"
    assert "@codemirror/state" not in ref, "reference.ts must not import @codemirror/state"


def test_default_mcp_url_is_empty_and_guarded():
    # DEP-R17: opt-in off-device send. The default URL is empty, and callTool
    # refuses to reach the network with no endpoint — so a fresh install
    # transmits nothing until the user configures it.
    types = _TYPES.read_text(encoding="utf-8")
    assert 'mcpUrl: ""' in types
    core = _CORE.read_text(encoding="utf-8")
    assert "!url.trim()" in core  # empty-URL guard before any requestUrl
    # The removed hardcoded default never reappears anywhere in source.
    for name, src in _all_sources().items():
        assert "100.64.0.55" not in src, f"hardcoded IP reappeared in {name}"


def test_plugin_follows_ui_guidelines():
    # Obsidian plugin guidelines: build DOM with createEl (never *HTML injection),
    # and ship no production console logging. Dotted matches so a prose mention of
    # "innerHTML" in a comment is not a false positive — only real `.innerHTML`
    # property access / call forms are forbidden.
    forbidden = [
        ".innerHTML",
        ".outerHTML",
        ".insertAdjacentHTML(",
        "console.log(",
        "console.debug(",
    ]
    offenders: list[str] = []
    for name, src in _all_sources().items():
        offenders += [f"{name}:{w}" for w in forbidden if w in src]
    assert offenders == [], f"plugin must follow UI guidelines, found: {offenders}"


def test_manifest_is_desktop_only_and_well_formed():
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["id"] == "hypermnesic-companion"
    # CodeMirror-6 mobile parity is deferred; the status-bar calm surface is
    # desktop-only, so the manifest stays desktop-only.
    assert manifest["isDesktopOnly"] is True
    assert "version" in manifest and "minAppVersion" in manifest
