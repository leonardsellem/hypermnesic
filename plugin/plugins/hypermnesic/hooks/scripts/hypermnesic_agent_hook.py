#!/usr/bin/env python3
"""hypermnesic auto-query hook (Claude Code + Codex).

Makes hypermnesic memory automatic: orients the agent at session start, surfaces
relevant notes at prompt submit (relevance-gated, bounded, token-gated, silent on
failure), and guards the dangerous engine ops. It calls **hypermnesic, never gbrain**.

Protocol: reads the harness hook JSON on stdin, writes a hook JSON on stdout.
- SessionStart      → additionalContext orienting the agent to hypermnesic.
- UserPromptSubmit  → relevance gate → bounded hypermnesic search over the authenticated
                      MCP endpoint → inject hits as additionalContext. Stays silent (no
                      injection, never blocks) when the gate misses, the lookup times
                      out / 401s, or no token is configured.
- PreToolUse        → block a full in-place reindex (OOM scar) and gbrain daemon re-arm
                      (`init`/`serve`/`sync --watch`/`--install-cron`/`autopilot --install`);
                      `gbrain delete`/`export`/`stats` are NOT blocked (reconciliation/teardown).

Token hygiene (V9): the bearer token is read from HYPERMNESIC_MCP_TOKEN and used only in
the Authorization header — it is never written to stdout, stderr, or the injected context.
A missing/empty token degrades exactly like a 401 (silent), so the U8 auth cutover can
never turn the per-prompt hook into a turn-blocking 401 storm.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

ORIENTATION = (
    "hypermnesic is your memory layer. Use its MCP tools — search / build_context / "
    "think for recall, resolve for entity→wikilink — and the gated git-first commit_note "
    "to write notes (allowlist notes/ sources/ dashboards/ captures/). Git is the source "
    "of truth; the index is a rebuildable projection. Do NOT use gbrain (CLI or MCP): it "
    "is being decommissioned — reach for hypermnesic instead."
)

# Relevance signals: memory-ish phrasing OR a multi-word proper noun (likely an entity).
RELEVANCE_TERMS = (
    "remember", "recall", "memory", "context", "notes on", "background on",
    "what do we know", "who is", "project history", "durable", "knowledge",
    "entity", "decision", "prior art", "earlier", "last time",
)
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][A-Za-z0-9-]+(?:\s+[A-Z][A-Za-z0-9-]+)+\b")

DEFAULT_MCP_URL = "https://homelab.<tailnet-host>.ts.net/mcp"

# Dangerous ops the PreToolUse hook blocks. A full in-place reindex is the OOM scar; the
# gbrain patterns re-arm laptop daemons / rewrite the engine config / re-expose the MCP.
# `gbrain delete`/`export`/`stats` are deliberately absent — U9/U10 reconciliation needs them.
_REINDEX_RE = re.compile(r"\bhypermnesic\s+reindex\b")
_GBRAIN_REARM = (
    (re.compile(r"\bgbrain\s+init\b"),
     "`gbrain init` can rewrite the active engine config."),
    (re.compile(r"\bgbrain\s+serve\b"),
     "`gbrain serve` re-exposes gbrain as MCP (being decommissioned)."),
    (re.compile(r"\bgbrain\s+sync\b[^\n;|&]*--watch\b"),
     "`gbrain sync --watch` starts a continuous sync worker."),
    (re.compile(r"\bgbrain\s+sync\b[^\n;|&]*--install-cron\b"),
     "`gbrain sync --install-cron` installs a recurring job."),
    (re.compile(r"\bgbrain\s+autopilot\b[^\n;|&]*--install\b"),
     "`gbrain autopilot --install` installs a maintenance daemon."),
)


def emit(obj: dict[str, Any]) -> int:
    print(json.dumps(obj, separators=(",", ":")))
    return 0


def _event(payload: dict[str, Any], override: str | None) -> str:
    return override or str(
        payload.get("hook_event_name") or payload.get("hookEventName")
        or payload.get("event") or payload.get("type") or ""
    )


def hook_context(event: str, text: str) -> dict[str, Any]:
    return {"continue": True,
            "hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def _prompt_from(payload: dict[str, Any]) -> str:
    for key in ("prompt", "message", "body", "bodyForAgent", "user_prompt"):
        v = payload.get(key)
        if isinstance(v, str):
            return v
    ctx = payload.get("context")
    if isinstance(ctx, dict):
        for key in ("bodyForAgent", "prompt", "message", "body"):
            v = ctx.get(key)
            if isinstance(v, str):
                return v
    return ""


def _command_from(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("command", "cmd", "script", "input"):
            c = value.get(key)
            if isinstance(c, str):
                return c
        for c in value.values():
            found = _command_from(c)
            if found:
                return found
    if isinstance(value, list):
        for c in value:
            found = _command_from(c)
            if found:
                return found
    return ""


def relevant(prompt: str) -> bool:
    low = prompt.lower()
    if any(term in low for term in RELEVANCE_TERMS):
        return True
    return bool(_PROPER_NOUN_RE.search(prompt))


def _search_hits(query: str, token: str) -> list[dict] | None:
    """Return hypermnesic search hits, or None on any failure (timeout/401/down/parse).

    A test fixture (HYPERMNESIC_HOOK_FIXTURE → a JSON file with {"hits":[…]} or
    {"error":…}) injects behavior without network. Otherwise a single bounded JSON-RPC
    tools/call is made over the authenticated streamable-http endpoint. The token is used
    only in the Authorization header and is never logged."""
    fixture = os.environ.get("HYPERMNESIC_HOOK_FIXTURE")
    if fixture:
        try:
            data = json.loads(open(fixture, encoding="utf-8").read())
        except Exception:
            return None
        if isinstance(data, dict) and "hits" in data and "error" not in data:
            return data["hits"]
        return None
    import urllib.request
    url = os.environ.get("HYPERMNESIC_MCP_URL", DEFAULT_MCP_URL)
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "search", "arguments": {"query": query, "k": 5}}}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:   # bounded; 401 → HTTPError → None
            payload = json.loads(resp.read().decode())
    except Exception:
        return None
    result = (payload or {}).get("result") or {}
    structured = result.get("structuredContent") or result
    hits = structured.get("hits") if isinstance(structured, dict) else None
    return hits if isinstance(hits, list) else None


def bounded_lookup(prompt: str) -> str:
    """Relevance-gated, token-gated, silent-on-failure hypermnesic lookup → injection text."""
    if os.environ.get("HYPERMNESIC_HOOK_DISABLE_LOOKUP") == "1":
        return ""
    token = os.environ.get("HYPERMNESIC_MCP_TOKEN", "")
    if not token:                                   # missing token == 401 path: silent
        return ""
    query = " ".join(prompt.split())[:220]
    if not query:
        return ""
    hits = _search_hits(query, token)
    if not hits:                                    # None (failure) or [] (no hits) → silent
        return ""
    lines = ["", "", "hypermnesic memory hits (use these; do not call gbrain):"]
    for h in hits[:5]:
        path = h.get("path", "")
        heading = h.get("heading", "")
        snippet = (h.get("snippet") or "").strip().replace("\n", " ")[:200]
        lines.append(f"- {path}: {heading} — {snippet}".rstrip(" —"))
    return "\n".join(lines)


def _prompt_context(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    prompt = _prompt_from(payload)
    if not relevant(prompt):
        return {"continue": True}                   # no relevance → no noise
    injection = bounded_lookup(prompt)
    if not injection:
        return {"continue": True}                   # lookup failed/empty → silent, non-blocking
    return hook_context(event, injection.lstrip("\n"))


def _dangerous_reason(command: str) -> str | None:
    if _REINDEX_RE.search(command) and "--isolated" not in command:
        return ("Blocked a full in-place `hypermnesic reindex` (OOM scar). Rely on read-time "
                "convergence, or use `hypermnesic reindex --isolated` (worktree + atomic swap).")
    for pattern, reason in _GBRAIN_REARM:
        if pattern.search(command):
            return (f"Blocked {reason} gbrain is being decommissioned; use hypermnesic. "
                    "(Reconciliation `gbrain delete`/`export` is not blocked.)")
    return None


def _pre_tool(payload: dict[str, Any]) -> dict[str, Any]:
    command = _command_from(payload.get("tool_input") or payload.get("toolInput") or payload)
    reason = _dangerous_reason(command)
    if reason:
        return {"decision": "block", "reason": reason}
    return {"continue": True}


def handle(payload: dict[str, Any], host: str, event_override: str | None) -> dict[str, Any]:
    event = _event(payload, event_override)
    canon = event.lower().replace("_", "").replace("-", "")
    if canon in {"sessionstart", "instructionsloaded", "agentbootstrap"}:
        return hook_context(event or "SessionStart", ORIENTATION)
    if canon in {"userpromptsubmit", "messagepreprocessed", "messagereceived"}:
        return _prompt_context(event or "UserPromptSubmit", payload)
    if canon in {"pretooluse", "permissionrequest"}:
        return _pre_tool(payload)
    return {"continue": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=("claude", "codex"), default="claude")
    parser.add_argument("--event")
    args = parser.parse_args()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("hook payload must be a JSON object")
    except Exception as exc:
        print(f"malformed hook JSON: {exc}", file=sys.stderr)
        return emit({"continue": True})             # never block on a malformed payload
    return emit(handle(payload, args.host, args.event))


if __name__ == "__main__":
    raise SystemExit(main())
