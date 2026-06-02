"""U4 — the auto-query hook (Claude+Codex): relevance gate, bounded token-gated
lookup, graceful silent degradation, no-noise behavior. Test-first.

The hook is a standalone script (stdin JSON → stdout JSON) shipped in the plugin; it
is loaded here by path. The spec: SessionStart orients the agent to hypermnesic (not
gbrain); UserPromptSubmit relevance-gates then injects bounded hits, and stays silent on
an off-topic prompt, a lookup failure, a 401, or a missing token (never blocking the
turn); PreToolUse blocks the dangerous engine ops + gbrain daemon-re-arm (but not the
`gbrain delete` reconciliation needs); and the same script runs under --host claude and
--host codex. The token is never echoed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_PDIR = _ROOT / "plugin" / "plugins" / "hypermnesic" / "hooks"
_HOOK = _PDIR / "scripts" / "hypermnesic_agent_hook.py"
_HOOKS_JSON = _PDIR / "hooks.json"


def _load():
    spec = importlib.util.spec_from_file_location("hypermnesic_agent_hook", _HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hook():
    return _load()


def _ctx(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("additionalContext", "")


# --- wiring -----------------------------------------------------------------

def test_hooks_json_wires_events_with_plugin_root_and_no_gbrain():
    data = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    hooks = data["hooks"]
    assert {"SessionStart", "UserPromptSubmit", "PreToolUse"} <= set(hooks)
    blob = json.dumps(data)
    assert "${CLAUDE_PLUGIN_ROOT}" in blob and "hypermnesic_agent_hook.py" in blob
    # no hook *command* invokes gbrain (the description prose may say "never gbrain")
    commands = [h["command"] for group in data["hooks"].values()
                for entry in group for h in entry["hooks"]]
    assert commands and all("gbrain" not in c.lower() for c in commands)


# --- SessionStart orientation -----------------------------------------------

def test_session_start_orients_to_hypermnesic_not_gbrain(hook):
    out = hook.handle({"hook_event_name": "SessionStart"}, "claude", None)
    assert out["continue"] is True
    text = _ctx(out).lower()
    assert "hypermnesic" in text
    assert "gbrain" in text and "not" in text           # explicitly: do not use gbrain


# --- UserPromptSubmit: relevance gate + bounded lookup ----------------------

def test_relevant_prompt_injects_hits_and_never_echoes_token(hook, tmp_path, monkeypatch):
    fixture = tmp_path / "hits.json"
    fixture.write_text(json.dumps({"hits": [
        {"path": "infrastructure/hetzner.md", "heading": "Hetzner",
         "snippet": "the homelab box"}]}))
    monkeypatch.setenv("HYPERMNESIC_MCP_TOKEN", "SECRETTOKENVALUE")
    monkeypatch.setenv("HYPERMNESIC_HOOK_FIXTURE", str(fixture))
    out = hook.handle({"hook_event_name": "UserPromptSubmit",
                       "prompt": "what do we know about Hetzner"}, "claude", None)
    assert out["continue"] is True
    assert "hetzner" in _ctx(out).lower()               # the hit is surfaced
    assert "SECRETTOKENVALUE" not in json.dumps(out)    # token never echoed (V9)


def test_offtopic_prompt_is_silent(hook, monkeypatch):
    monkeypatch.setenv("HYPERMNESIC_MCP_TOKEN", "t")
    out = hook.handle({"hook_event_name": "UserPromptSubmit", "prompt": "hi"}, "claude", None)
    assert out["continue"] is True and _ctx(out) == ""  # no relevance → no noise


def test_lookup_failure_is_silent_never_blocks(hook, tmp_path, monkeypatch):
    fixture = tmp_path / "err.json"
    fixture.write_text(json.dumps({"error": "timeout"}))   # simulate a down/slow endpoint
    monkeypatch.setenv("HYPERMNESIC_MCP_TOKEN", "t")
    monkeypatch.setenv("HYPERMNESIC_HOOK_FIXTURE", str(fixture))
    out = hook.handle({"hook_event_name": "UserPromptSubmit",
                       "prompt": "background on Hetzner Cloud"}, "claude", None)
    assert out["continue"] is True and _ctx(out) == ""  # relevant, but failure → silent


def test_missing_token_degrades_like_401(hook, monkeypatch):
    monkeypatch.delenv("HYPERMNESIC_MCP_TOKEN", raising=False)
    out = hook.handle({"hook_event_name": "UserPromptSubmit",
                       "prompt": "background on Hetzner Cloud"}, "claude", None)
    assert out["continue"] is True and _ctx(out) == ""  # no token == 401 path: silent, non-blocking


# --- PreToolUse guard -------------------------------------------------------

def test_pre_tool_blocks_full_reindex_allows_isolated(hook):
    blocked = hook.handle({"hook_event_name": "PreToolUse",
                           "tool_input": {"command": "hypermnesic reindex /repo"}}, "claude", None)
    assert blocked.get("decision") == "block" and blocked.get("reason")
    ok = hook.handle({"hook_event_name": "PreToolUse",
                      "tool_input": {"command": "hypermnesic reindex /repo --isolated"}},
                     "claude", None)
    assert ok.get("decision") != "block" and ok["continue"] is True


def test_pre_tool_blocks_gbrain_daemon_rearm_but_not_delete(hook):
    for cmd in ("gbrain serve --http", "gbrain sync --watch", "gbrain autopilot --install",
                "gbrain init"):
        r = hook.handle({"hook_event_name": "PreToolUse", "tool_input": {"command": cmd}},
                        "claude", None)
        assert r.get("decision") == "block", f"{cmd!r} should be blocked"
    # gbrain delete / export are needed for U9 reconciliation + U10 snapshot → NOT blocked
    for cmd in ("gbrain delete some-slug", "gbrain export --restore-only", "gbrain stats"):
        r = hook.handle({"hook_event_name": "PreToolUse", "tool_input": {"command": cmd}},
                        "claude", None)
        assert r.get("decision") != "block", f"{cmd!r} should not be blocked"


def test_pre_tool_allows_safe_command(hook):
    r = hook.handle({"hook_event_name": "PreToolUse", "tool_input": {"command": "ls -la"}},
                    "claude", None)
    assert r.get("decision") != "block" and r["continue"] is True


# --- host parity + transport contract ---------------------------------------

def test_both_hosts_produce_orientation(hook):
    for host in ("claude", "codex"):
        out = hook.handle({"hook_event_name": "SessionStart"}, host, None)
        assert out["continue"] is True and "hypermnesic" in _ctx(out).lower()


def test_subprocess_stdin_stdout_contract():
    env = {**os.environ}
    env.pop("HYPERMNESIC_MCP_TOKEN", None)               # no token → SessionStart still fine
    proc = subprocess.run([sys.executable, str(_HOOK), "--host", "claude"],
                          input=json.dumps({"hook_event_name": "SessionStart"}),
                          text=True, capture_output=True, timeout=15, env=env)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["continue"] is True and "hypermnesic" in _ctx(out).lower()


def test_malformed_json_never_blocks(hook):
    # a malformed/empty payload must degrade to continue:true, never crash the turn
    out = hook.handle({}, "claude", None)
    assert out["continue"] is True
