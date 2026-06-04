#!/usr/bin/env python3
"""Status and test-recall helper for the hypermnesic proactive hook.

The hook stays silent in normal use. This companion script makes that silence inspectable without
recording prompts, endpoint URLs, headers, or credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_SNIPPET_CHARS = 200
OUTCOME_EXPLANATIONS = {
    "never_run": "The hook status file does not exist yet.",
    "off_topic": "The prompt did not look memory-relevant, so no lookup ran.",
    "disabled_global": "Auto-recall is disabled for this plugin install.",
    "disabled_host": "Auto-recall is disabled for this host.",
    "unconfigured_endpoint": "No hook endpoint URL is configured.",
    "missing_credential": "The configured hook route appears to require a credential.",
    "auth_expired": "The hook credential was refused or has expired.",
    "timeout": "The hook lookup timed out before it could return context.",
    "lookup_failed": "The hook lookup failed before returning usable results.",
    "no_hits": "The hook lookup completed but found no relevant notes.",
    "degraded_lexical_only": "Recall worked in lexical-only degraded mode.",
    "success": "Recall returned bounded context.",
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_status_file() -> Path:
    configured = os.environ.get("HYPERMNESIC_HOOK_STATUS_FILE")
    if configured:
        return Path(configured).expanduser()
    state_home = Path(os.environ.get("XDG_STATE_HOME", "~/.local/state")).expanduser()
    return state_home / "hypermnesic" / "hook-status.json"


def _flat(value: str) -> str:
    return (value or "").replace("\n", " ").replace("\r", " ")


def sanitize_hit(hit: dict[str, Any]) -> dict[str, str]:
    return {
        "path": _flat(str(hit.get("path", "")))[:240],
        "heading": _flat(str(hit.get("heading", "")))[:160],
        "snippet": _flat(str(hit.get("snippet", ""))).strip()[:MAX_SNIPPET_CHARS],
    }


def endpoint_category(url: str) -> str:
    if not url:
        return "unset"
    lowered = url.lower()
    if "localhost" in lowered or "127.0.0.1" in lowered:
        return "local"
    host = lowered.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    try:
        ip = ip_address(host)
    except ValueError:
        ip = None
    if ip and host.startswith("100."):
        return "tailnet_read"
    if lowered.startswith("https://"):
        return "public_https"
    return "other"


def credential_category(token: str, url: str) -> str:
    if token:
        return "token_present"
    if endpoint_category(url) == "tailnet_read":
        return "not_required_tailnet"
    return "missing"


def disabled_state(host: str) -> tuple[bool, str]:
    if os.environ.get("HYPERMNESIC_HOOK_DISABLE_LOOKUP") == "1":
        return False, "global"
    hosts = {
        item.strip().lower()
        for item in os.environ.get("HYPERMNESIC_HOOK_DISABLED_HOSTS", "").split(",")
        if item.strip()
    }
    if host.lower() in hosts:
        return False, "host"
    return True, ""


def base_status(host: str) -> dict[str, Any]:
    url = os.environ.get("HYPERMNESIC_MCP_URL", "")
    token = os.environ.get("HYPERMNESIC_MCP_TOKEN", "")
    enabled, disabled_reason = disabled_state(host)
    return {
        "schema_version": SCHEMA_VERSION,
        "hook": "hypermnesic_auto_recall",
        "host": host,
        "enabled": enabled,
        "disabled_reason": disabled_reason,
        "endpoint_configured": bool(url),
        "endpoint_category": endpoint_category(url),
        "credential_category": credential_category(token, url),
    }


def write_status(status_file: Path | None, record: dict[str, Any]) -> None:
    path = status_file or default_status_file()
    try:
        previous = {}
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(previous, dict):
                previous = {}
        merged = {**previous, **record}
        if not merged.get("last_recall_at") and previous.get("last_recall_at"):
            merged["last_recall_at"] = previous["last_recall_at"]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(merged, sort_keys=True, separators=(",", ":")) + "\n",
                       encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def read_status(status_file: Path | None = None, host: str = "claude") -> dict[str, Any]:
    path = status_file or default_status_file()
    current = base_status(host)
    if not path.exists():
        return {
            **current,
            "last_outcome": "never_run",
            "explanation": OUTCOME_EXPLANATIONS["never_run"],
            "last_run_at": None,
            "last_recall_at": None,
            "hit_count": 0,
            "degraded_lexical_only": False,
            "test_initiated": False,
        }
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    merged = {**current, **stored}
    merged.setdefault("explanation", OUTCOME_EXPLANATIONS.get(
        str(merged.get("last_outcome")), "Unknown hook outcome."))
    return merged


def classify_fixture_error(error: Any) -> str:
    text = str(error).lower()
    if "401" in text or "unauthorized" in text or "expired" in text:
        return "auth_expired"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    return "lookup_failed"


def recall(query: str, url: str, token: str) -> tuple[str, list[dict[str, str]], bool]:
    fixture = os.environ.get("HYPERMNESIC_HOOK_FIXTURE")
    if fixture:
        try:
            data = json.loads(Path(fixture).read_text(encoding="utf-8"))
        except Exception:
            return "lookup_failed", [], False
        if isinstance(data, dict) and "error" in data:
            return classify_fixture_error(data["error"]), [], False
        if isinstance(data, dict) and isinstance(data.get("hits"), list):
            hits = [sanitize_hit(hit) for hit in data["hits"][:5] if isinstance(hit, dict)]
            degraded = bool(data.get("degraded_lexical_only"))
            if degraded:
                return "degraded_lexical_only", hits, True
            return ("success" if hits else "no_hits"), hits, False
        return "lookup_failed", [], False

    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "search", "arguments": {"query": query, "k": 5}},
    }).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return ("auth_expired" if exc.code in {401, 403} else "lookup_failed"), [], False
    except TimeoutError:
        return "timeout", [], False
    except Exception:
        return "lookup_failed", [], False
    result = (payload or {}).get("result") or {}
    structured = result.get("structuredContent") or result
    hits_raw = structured.get("hits") if isinstance(structured, dict) else None
    if not isinstance(hits_raw, list):
        return "lookup_failed", [], False
    hits = [sanitize_hit(hit) for hit in hits_raw[:5] if isinstance(hit, dict)]
    degraded = bool(structured.get("degraded_lexical_only"))
    if degraded:
        return "degraded_lexical_only", hits, True
    return ("success" if hits else "no_hits"), hits, False


def make_record(
    *,
    host: str,
    outcome: str,
    hit_count: int = 0,
    degraded_lexical_only: bool = False,
    test_initiated: bool = False,
) -> dict[str, Any]:
    record = {
        **base_status(host),
        "last_outcome": outcome,
        "explanation": OUTCOME_EXPLANATIONS.get(outcome, "Unknown hook outcome."),
        "last_run_at": _now(),
        "hit_count": hit_count,
        "degraded_lexical_only": degraded_lexical_only,
        "test_initiated": test_initiated,
    }
    if outcome in {"success", "degraded_lexical_only"} and hit_count:
        record["last_recall_at"] = record["last_run_at"]
    return record


def _print_status(data: dict[str, Any], json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(data, sort_keys=True))
        return
    print(f"hypermnesic hook: {data.get('last_outcome', 'never_run')}")
    print(f"host: {data.get('host')} enabled: {data.get('enabled')}")
    print(
        f"endpoint: {data.get('endpoint_category')} "
        f"credential: {data.get('credential_category')}"
    )
    print(f"last run: {data.get('last_run_at') or 'never'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_status = sub.add_parser("status")
    p_status.add_argument("--host", choices=("claude", "codex"), default="claude")
    p_status.add_argument("--status-file", type=Path)
    p_status.add_argument("--json", action="store_true")
    p_test = sub.add_parser("test-recall")
    p_test.add_argument("query")
    p_test.add_argument("--host", choices=("claude", "codex"), default="claude")
    p_test.add_argument("--status-file", type=Path)
    p_test.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "status":
        _print_status(read_status(args.status_file, args.host), args.json)
        return 0

    url = os.environ.get("HYPERMNESIC_MCP_URL", "")
    token = os.environ.get("HYPERMNESIC_MCP_TOKEN", "")
    if not url:
        outcome, hits, degraded = "unconfigured_endpoint", [], False
    else:
        outcome, hits, degraded = recall(" ".join(args.query.split())[:220], url, token)
    record = make_record(
        host=args.host,
        outcome=outcome,
        hit_count=len(hits),
        degraded_lexical_only=degraded,
        test_initiated=True,
    )
    write_status(args.status_file, record)
    out = {**record, "hits": hits}
    _print_status(out, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
