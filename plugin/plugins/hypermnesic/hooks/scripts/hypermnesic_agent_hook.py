#!/usr/bin/env python3
"""hypermnesic auto-recall hook — proactive memory at prompt submit (Claude Code + Codex).

A single UserPromptSubmit hook: when a prompt looks memory-relevant, run ONE bounded,
URL+token-gated search over the configured hypermnesic MCP endpoint and inject the top hits
as additionalContext. It is silent and non-blocking on every other path — off-topic prompt,
no endpoint/token configured, 401, timeout, no hits, malformed payload — so it can never
block or pollute a turn it has nothing to add to.

User-neutral + distributable: no hardcoded endpoint (the URL comes from HYPERMNESIC_MCP_URL),
and no project- or migration-specific content. The token (HYPERMNESIC_MCP_TOKEN) is used only
in the Authorization header — never written to stdout, stderr, or the injected text (V9).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

# Relevance signals: memory-ish phrasing OR a multi-word proper noun (a likely entity).
RELEVANCE_TERMS = (
    "remember", "recall", "memory", "context", "notes on", "background on",
    "what do we know", "who is", "project history", "prior art", "earlier",
    "last time", "decision", "knowledge", "durable",
)
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][A-Za-z0-9-]+(?:\s+[A-Z][A-Za-z0-9-]+)+\b")


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


def relevant(prompt: str) -> bool:
    low = prompt.lower()
    return any(t in low for t in RELEVANCE_TERMS) or bool(_PROPER_NOUN_RE.search(prompt))


def _search_hits(query: str, url: str, token: str) -> list[dict] | None:
    """One bounded search over the MCP endpoint; None on ANY failure (timeout/401/down/parse).
    A test fixture (HYPERMNESIC_HOOK_FIXTURE → a JSON file with {"hits":[…]} or {"error":…})
    stands in for the network. The token is used only in the Authorization header."""
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


def _flat(s: str) -> str:                       # one line per hit: neutralize injected newlines
    return (s or "").replace("\n", " ").replace("\r", " ")


def injection(prompt: str) -> str:
    """Relevance- + URL- + token-gated recall → injection text. '' means stay silent."""
    if os.environ.get("HYPERMNESIC_HOOK_DISABLE_LOOKUP") == "1" or not relevant(prompt):
        return ""
    url = os.environ.get("HYPERMNESIC_MCP_URL", "")
    token = os.environ.get("HYPERMNESIC_MCP_TOKEN", "")
    if not url or not token:                    # unconfigured == 401 path: silent, never blocks
        return ""
    query = " ".join(prompt.split())[:220]
    hits = _search_hits(query, url, token) if query else None
    if not hits:                                # None (failure) or [] (no hits) → silent
        return ""
    lines = ["hypermnesic memory hits:"]
    for h in hits[:5]:
        path = _flat(h.get("path", ""))
        heading = _flat(h.get("heading", ""))
        snippet = _flat(h.get("snippet", "")).strip()[:200]
        lines.append(f"- {path}: {heading} — {snippet}".rstrip(" —"))
    return "\n".join(lines)


def handle(payload: dict[str, Any], host: str, event_override: str | None) -> dict[str, Any]:
    """Only UserPromptSubmit does anything; every other event is an inert continue."""
    event = event_override or str(
        payload.get("hook_event_name") or payload.get("hookEventName")
        or payload.get("event") or payload.get("type") or "")
    canon = event.lower().replace("_", "").replace("-", "")
    if canon not in {"userpromptsubmit", "messagepreprocessed", "messagereceived", ""}:
        return {"continue": True}
    text = injection(_prompt_from(payload))
    if not text:
        return {"continue": True}
    return {"continue": True,
            "hookSpecificOutput": {"hookEventName": event or "UserPromptSubmit",
                                   "additionalContext": text}}


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
        print(json.dumps({"continue": True}))           # never block on a malformed payload
        return 0
    print(json.dumps(handle(payload, args.host, args.event), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
