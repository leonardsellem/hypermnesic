"""Hermes Agent plugin entrypoint for hypermnesic CLI memory support."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_SKILL = _HERE / "skills" / "hypermnesic-memory" / "SKILL.md"

_MAX_QUERY_CHARS = 500
_MAX_SNIPPET_CHARS = 280
_MAX_CONTEXT_CHARS = 1400
_MAX_HITS = 3
_MAX_TIMEOUT_SECONDS = 3

_RELEVANCE_TERMS = (
    "remember",
    "recall",
    "memory",
    "know about",
    "prior context",
    "previous context",
    "background on",
    "what do we know",
    "hypermnesic",
)


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _is_relevant(message: str) -> bool:
    text = message.lower()
    if len(text.strip()) < 8:
        return False
    return any(term in text for term in _RELEVANCE_TERMS)


def _repo() -> str:
    return os.environ.get("HYPERMNESIC_REPO", "").strip()


def _index_db() -> str:
    return os.environ.get("HYPERMNESIC_INDEX_DB", "").strip()


def _build_command(repo: str, query: str) -> list[str]:
    cmd = ["hypermnesic", "retrieve", repo, query, "--k", str(_MAX_HITS), "--now", "--json"]
    index_db = _index_db()
    if index_db:
        cmd.extend(["--index-db", index_db])
    return cmd


def _format_hits(hits: list[dict[str, Any]]) -> str | None:
    lines = ["hypermnesic memory hits from local CLI recall:"]
    for hit in hits[:_MAX_HITS]:
        path = _clean(hit.get("path"), 180)
        heading = _clean(hit.get("heading"), 120)
        snippet = _clean(hit.get("snippet"), _MAX_SNIPPET_CHARS)
        if not (path or heading or snippet):
            continue
        label = path
        if heading:
            label = f"{path} - {heading}" if path else heading
        lines.append(f"- {label}: {snippet}")
    if len(lines) == 1:
        return None
    return "\n".join(lines)[:_MAX_CONTEXT_CHARS]


def recall(**kwargs) -> dict[str, str] | None:
    """Hermes pre_llm_call hook: bounded CLI recall, silent on every failure."""
    user_message = kwargs.get("user_message")
    if not isinstance(user_message, str) or not _is_relevant(user_message):
        return None
    repo = _repo()
    if not repo:
        return None
    query = _clean(user_message, _MAX_QUERY_CHARS)
    if not query:
        return None
    try:
        proc = subprocess.run(
            _build_command(repo, query),
            capture_output=True,
            text=True,
            timeout=_MAX_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    hits = payload.get("hits")
    if not isinstance(hits, list):
        return None
    context = _format_hits([h for h in hits if isinstance(h, dict)])
    return {"context": context} if context else None


def register(ctx) -> None:
    ctx.register_skill("hypermnesic-memory", _SKILL)
    if _enabled(os.environ.get("HYPERMNESIC_HERMES_RECALL")):
        ctx.register_hook("pre_llm_call", recall)
