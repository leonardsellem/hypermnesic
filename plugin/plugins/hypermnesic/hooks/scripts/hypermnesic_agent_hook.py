#!/usr/bin/env python3
"""hypermnesic auto-recall hook — proactive memory at prompt submit (Claude Code + Codex).

A single UserPromptSubmit hook: when a prompt looks memory-relevant, run ONE bounded search
over the configured hypermnesic MCP endpoint and inject the top hits as additionalContext. It
is silent and non-blocking on every other path — off-topic prompt, no endpoint configured, 401,
timeout, no hits, malformed payload — so it can never block or pollute a turn it has nothing to
add to.

Remote-device recall (U5/R11): Claude Code exposes no stored MCP OAuth token to hook subprocesses
(confirmed against the hooks docs — the UserPromptSubmit payload carries no credential), so the
hook cannot reuse the app's OAuth login. Its working remote path is the RETAINED tailnet read
route (an auth-off read companion reachable on any tailnet device): the hook needs only the URL.
The token (HYPERMNESIC_MCP_TOKEN) is therefore OPTIONAL — supplied for an authed read route, used
ONLY in the Authorization header, never written to stdout, stderr, or the injected text (V9).

User-neutral + distributable: no hardcoded endpoint (the URL comes from HYPERMNESIC_MCP_URL),
and no project- or migration-specific content.
"""
# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from hypermnesic_hook_status import (  # noqa: E402
    disabled_state,
    endpoint_category,
    make_record,
    recall as _recall,
    write_status,
)

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
    outcome, hits, _degraded = _recall(query, url, token)
    return hits if outcome in {"success", "degraded_lexical_only", "no_hits"} else None


def _flat(s: str) -> str:                       # one line per hit: neutralize injected newlines
    return (s or "").replace("\n", " ").replace("\r", " ")


def injection(prompt: str) -> str:
    """Relevance- + URL-gated recall → injection text. '' means stay silent. The URL is required
    (no endpoint configured → silent); the token is OPTIONAL (the auth-off tailnet read route
    needs none — U5/R11)."""
    if os.environ.get("HYPERMNESIC_HOOK_DISABLE_LOOKUP") == "1" or not relevant(prompt):
        return ""
    url = os.environ.get("HYPERMNESIC_MCP_URL", "")
    token = os.environ.get("HYPERMNESIC_MCP_TOKEN", "")
    if not url:                                 # no endpoint configured → silent, never blocks
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


def _injection_with_status(prompt: str, host: str) -> tuple[str, dict[str, Any]]:
    enabled, disabled_reason = disabled_state(host)
    if not enabled:
        outcome = "disabled_host" if disabled_reason == "host" else "disabled_global"
        return "", make_record(host=host, outcome=outcome)
    if not relevant(prompt):
        return "", make_record(host=host, outcome="off_topic")
    url = os.environ.get("HYPERMNESIC_MCP_URL", "")
    token = os.environ.get("HYPERMNESIC_MCP_TOKEN", "")
    if not url:
        return "", make_record(host=host, outcome="unconfigured_endpoint")
    if not token and endpoint_category(url) != "tailnet_read":
        return "", make_record(host=host, outcome="missing_credential")
    query = " ".join(prompt.split())[:220]
    if not query:
        return "", make_record(host=host, outcome="off_topic")
    outcome, hits, degraded = _recall(query, url, token)
    record = make_record(
        host=host,
        outcome=outcome,
        hit_count=len(hits),
        degraded_lexical_only=degraded,
    )
    if not hits:
        return "", record
    lines = ["hypermnesic memory hits:"]
    for h in hits[:5]:
        path = _flat(h.get("path", ""))
        heading = _flat(h.get("heading", ""))
        snippet = _flat(h.get("snippet", "")).strip()[:200]
        lines.append(f"- {path}: {heading} — {snippet}".rstrip(" —"))
    return "\n".join(lines), record


def handle(payload: dict[str, Any], host: str, event_override: str | None) -> dict[str, Any]:
    """Only UserPromptSubmit does anything; every other event is an inert continue."""
    event = event_override or str(
        payload.get("hook_event_name") or payload.get("hookEventName")
        or payload.get("event") or payload.get("type") or "")
    canon = event.lower().replace("_", "").replace("-", "")
    if canon not in {"userpromptsubmit", "messagepreprocessed", "messagereceived", ""}:
        return {"continue": True}
    text, record = _injection_with_status(_prompt_from(payload), host)
    write_status(None, record)
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
