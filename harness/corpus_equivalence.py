#!/usr/bin/env python3
"""Detect equivalence classes of corpus docs (for fair parity scoring).

Two principled, narrow notions of "the same document":

1. **Exact content mirror** — identical frontmatter-stripped body at two paths
   (the corpus mirrors many docs under both ``docs/x`` and
   ``projects/.../docs/x``).
2. **Same-event representation** — a ``meetings/`` note and its ``sources/``
   transcript of the *same* event: identical ``YYYY-MM-DD-<slug>`` stem after
   stripping a trailing ``-<hex>`` source-id suffix. The date is KEPT so two
   different meetings that merely share a title (e.g. two "Point SAP" on
   different dates) are NOT merged.

Used by ``build_query_set`` (expand a single-label known-item query to its
equivalence class — the KTD6 label-review move, applied systematically, not
cherry-picked) and by ``parity_harness`` (collapse content-mirrors in the gbrain
baseline so the comparison is symmetric with hypermnesic's retrieval-time
dedup).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SKIP = {".git", ".hypermnesic", ".obsidian", "node_modules", ".brv"}
_FM = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_HEX_SUFFIX = re.compile(r"-[0-9a-f]{6,}$")
_MIN_EVENT_KEY = 18  # chars; avoid merging short/ambiguous stems


def _body_hash(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    body = _FM.sub("", raw, count=1)
    body = re.sub(r"\s+", " ", body).strip()
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _event_key(path: str) -> str | None:
    stem = Path(path).stem
    key = _HEX_SUFFIX.sub("", stem).lower()
    # require a date-prefixed, sufficiently specific stem
    if not re.match(r"^\d{4}-\d{2}-\d{2}-", key) or len(key) < _MIN_EVENT_KEY:
        return None
    return key


def _iter_md(corpus: Path):
    for p in sorted(corpus.rglob("*.md")):
        if not any(part in _SKIP for part in p.relative_to(corpus).parts):
            yield p


def body_hash_map(corpus: Path) -> dict[str, str]:
    """{repo-relative path: body content hash}."""
    return {p.relative_to(corpus).as_posix(): _body_hash(p) for p in _iter_md(Path(corpus))}


def equivalence_classes(corpus: Path) -> dict[str, list[str]]:
    """{path: sorted list of equivalent paths (incl. self)}."""
    corpus = Path(corpus)
    by_hash: dict[str, set[str]] = {}
    by_event: dict[str, set[str]] = {}
    paths = []
    for p in _iter_md(corpus):
        rel = p.relative_to(corpus).as_posix()
        paths.append(rel)
        by_hash.setdefault(_body_hash(p), set()).add(rel)
        ek = _event_key(rel)
        if ek:
            by_event.setdefault(ek, set()).add(rel)

    # union-find over the two groupings
    parent: dict[str, str] = {p: p for p in paths}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for group in list(by_hash.values()) + list(by_event.values()):
        g = sorted(group)
        for other in g[1:]:
            union(g[0], other)

    classes: dict[str, list[str]] = {}
    for p in paths:
        classes.setdefault(find(p), []).append(p)
    return {p: sorted(classes[find(p)]) for p in paths}
