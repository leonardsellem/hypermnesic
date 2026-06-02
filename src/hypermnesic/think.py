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

from dataclasses import dataclass, field

from hypermnesic import graph as graph_mod
from hypermnesic import retrieve


@dataclass
class ThinkResult:
    topic: str
    wrote: bool                 # always False — the observable no-write assertion (R7)
    related: list[dict]
    context: list[str]
    questions: list[str]
    tensions: list[str]
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
            "tensions": self.tensions,
            "degraded_lexical_only": self.degraded,
            "note": self.note,
        }


def _socratic(topic: str, hits) -> list[str]:
    """Heuristic thinking prompts from what's in hand — no LLM (use the kernel's
    own signals, per the ideation's 'graph must earn its cost' restraint)."""
    if not hits:
        return []
    qs = [
        f"What would change your mind about {topic}?",
        f"Where does {topic} break down — what's the strongest counter-case?",
    ]
    if len(hits) >= 2:
        qs.append(f"How do '{hits[0].heading}' and '{hits[1].heading}' inform each other?")
    return qs


def _tensions(graph, hits) -> list[str]:
    """Name potential tensions: top hits that surface together for the topic but
    are NOT linked in the graph — a candidate missing connection or a real
    disagreement worth examining (a read-only seed; U22 formalises the proposal)."""
    out: list[str] = []
    if graph is None or len(hits) < 2:
        return out
    top = hits[:4]
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            a, b = top[i].path, top[j].path
            linked = b in graph.neighbors(a)
            if not linked:
                out.append(
                    f"'{top[i].heading}' and '{top[j].heading}' both surface here but "
                    f"aren't linked — tension, or a missing connection?")
    return out[:3]


def think(idx, topic: str, *, embedder=None, graph=None, k: int = 8, depth: int = 1) -> ThinkResult:
    """Surface a thinking-partner view of ``topic`` over the read-only index.

    Never writes. Returns related notes (hybrid search), one-hop graph context
    around the top hit, Socratic prompts, and named tensions — with ``wrote: False``.
    Degrades gracefully: an empty/garbage topic returns no related notes and a
    "nothing relevant" note, still ``wrote: False``.
    """
    res = retrieve.search(idx, topic, embedder=embedder, k=k)
    related = [
        {"path": h.path, "heading": h.heading, "score": round(h.score, 6),
         "channels": sorted(h.channels), "snippet": h.text[:280]}
        for h in res.hits
    ]
    context: list[str] = []
    if graph is not None and res.hits:
        context = graph_mod.build_context(graph, res.hits[0].path, depth=depth)

    questions = _socratic(topic, res.hits)
    tensions = _tensions(graph, res.hits)
    note = "" if related else "nothing relevant yet — the index has no close match"

    return ThinkResult(topic=topic, wrote=False, related=related, context=context,
                       questions=questions, tensions=tensions, degraded=res.degraded,
                       note=note, _hits=res.hits)
