"""U20 — thinking-mode: a distinct "help me think before you write" surface.
[R7/H1/KD2/KTD7]

Composes the existing read-only retrieval (``retrieve.search``) + body-wikilink
graph context (``graph.build_context``) into a thinking-partner response —
related notes, Socratic prompts, and tensions surfaced from proximity — and
asserts an explicit ``wrote: false``.

The no-write boundary is **structural, not a flag** (KTD7): this module imports
*only* read surfaces (``retrieve``, ``graph``). It does not import — and cannot
reach — ``commit_note`` or ``propose``. The ``wrote: false`` field makes the
boundary observable to a caller (R7 demands the boundary be checkable, not an
implied behavioural difference).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from hypermnesic import graph as graph_mod
from hypermnesic import ingest as ingest_mod
from hypermnesic import retrieve

_ATX_LEADING = re.compile(r"^\s*#{1,6}\s+")


def _resolve_title(repo, path: str, cache: dict[str, str]) -> str:
    """Resolve a note's display title (U44) — the note's H1, never the matched
    chunk's section heading. Reads the note file (files are the source of truth)
    via ``ingest.note_title``; falls back to the de-kebabbed stem when ``repo`` is
    unknown or the file is unreadable. Memoised per ``think`` call."""
    if path in cache:
        return cache[path]
    raw = ""
    if repo is not None:
        try:
            raw = (Path(repo) / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
    cache[path] = title = ingest_mod.note_title(raw, path)
    return title


def _normalize_topic(topic: str) -> str:
    """Strip a leading Markdown ATX heading marker so the echoed topic and the
    generated prompts never carry a stray ``# `` (U43). Only a *leading* heading
    marker is removed — an inline ``#tag`` is left intact."""
    return _ATX_LEADING.sub("", topic, count=1).strip()


@dataclass
class ThinkResult:
    topic: str
    wrote: bool                 # always False — the observable no-write assertion (R7)
    related: list[dict]
    context: list[str]
    questions: list[str]
    unlinked: list[dict]        # related-but-not-yet-linked pairs (U45, was prose "tensions")
    degraded: bool
    note: str = ""
    _hits: list = field(default_factory=list, repr=False)

    def as_dict(self) -> dict:
        return {
            "topic": self.topic,
            "wrote": self.wrote,
            "related": self.related,
            "context": self.context,
            "questions": self.questions,
            "unlinked": self.unlinked,
            "degraded_lexical_only": self.degraded,
            "note": self.note,
        }


def _distinct_paths(hits, limit: int) -> list[str]:
    """The first ``limit`` distinct note paths from relevance-ordered hits — one
    entry per note, not per chunk. Both the Socratic prompt and the unlinked pairs
    reason over notes; without collapsing chunks, a note with two matching chunks
    double-counts (and emits a duplicate pair)."""
    paths: list[str] = []
    for h in hits:
        if h.path not in paths:
            paths.append(h.path)
            if len(paths) == limit:
                break
    return paths


def _socratic(hits, title_of) -> list[str]:
    """One note-grounded thinking prompt — no LLM, and no ungrounded boilerplate
    (U47). The two generic '{topic}' templates were dropped: they reference nothing
    the retrieval found and read as slop (the same unearned-prose defect as the old
    tensions). The surviving prompt names two *distinct* related notes by resolved
    title (U44) and fires only when there are ≥2 of them; otherwise it is empty —
    think degrades gracefully rather than padding with generic questions."""
    paths = _distinct_paths(hits, 2)
    if len(paths) < 2:
        return []
    return [f"How do '{title_of(paths[0])}' and '{title_of(paths[1])}' inform each other?"]


def _unlinked_pairs(graph, hits, title_of) -> list[dict]:
    """Top hits that surface together for the topic but are NOT linked in the
    graph — 'related, but you haven't linked these yet' (U45, replacing the old
    prose "tensions"). Each entry carries both paths and resolved titles (U44) so
    a client can render clickable navigation to either note. No conceptual-conflict
    claim is made — it is a candidate missing connection the writer can verify.
    Relevance gate = the already-relevance-ordered top-N hits (self-excluded
    upstream by U42); a U18 proposal — never a write — is how a link is added."""
    out: list[dict] = []
    if graph is None:
        return out
    notes = _distinct_paths(hits, 4)       # distinct notes, not chunks (no dup pairs)
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            a, b = notes[i], notes[j]
            if b in graph.neighbors(a):
                continue
            out.append({"a_path": a, "a_title": title_of(a),
                        "b_path": b, "b_title": title_of(b)})
    return out[:3]


def think(idx, topic: str, *, embedder=None, graph=None, k: int = 8, depth: int = 1,
          path: str | None = None, repo=None) -> ThinkResult:
    """Surface a thinking-partner view of ``topic`` over the read-only index.

    Never writes. Returns related notes (hybrid search), one-hop graph context
    around the top hit, a note-grounded Socratic prompt, and related-but-not-yet-
    linked pairs (``unlinked``) — with ``wrote: False``.
    Degrades gracefully: an empty/garbage topic returns no related notes and a
    "nothing relevant" note, still ``wrote: False``.

    ``path`` (optional): the active note's repo-relative path. When set, that note
    is excluded from its own results (U42) — a note never matches itself, so the
    related list, prompts, and pairs are about *other* notes.

    ``repo`` (optional): the repo root, used to resolve each note's display title
    from its H1 (U44). When absent, titles fall back to the de-kebabbed path stem.
    """
    topic = _normalize_topic(topic)        # U43: no stray '# ' in topic or prompts
    res = retrieve.search(idx, topic, embedder=embedder, k=k, exclude_path=path)
    title_cache: dict[str, str] = {}

    def title_of(p: str) -> str:           # U44: note identity, not chunk heading
        return _resolve_title(repo, p, title_cache)

    related = [
        {"path": h.path, "heading": h.heading, "title": title_of(h.path),
         "score": round(h.score, 6), "channels": sorted(h.channels),
         "snippet": h.text[:280]}
        for h in res.hits
    ]
    context: list[str] = []
    if graph is not None and res.hits:
        context = graph_mod.build_context(graph, res.hits[0].path, depth=depth)

    questions = _socratic(res.hits, title_of)
    unlinked = _unlinked_pairs(graph, res.hits, title_of)
    note = "" if related else "nothing relevant yet — the index has no close match"

    return ThinkResult(topic=topic, wrote=False, related=related, context=context,
                       questions=questions, unlinked=unlinked, degraded=res.degraded,
                       note=note, _hits=res.hits)
