"""U22 — connection / serendipity proposals. [R6/H3/F3/AE4/KTD3]

Surfaces non-obvious connections — "these two notes grapple with the same idea
but aren't linked — connect them?" — from the existing dense vectors + body-
wikilink graph (KTD3: NOT new LLM knowledge-graph extraction, which is Phase 3).
A pair is a candidate when its cosine similarity is high AND no body-wikilink edge
already joins it.

High-precision by construction (noisy suggestions erode trust): a similarity
*threshold*, a near-duplicate exclusion (shared templates / raw captures /
boilerplate reach cosine ~1 but are not insight), and a per-run *cap*. The result
is a bounded, batched, review-gated U18 proposal — a generated suggestions note;
the link is **never written directly** into a source note (KTD2/R10).
"""

from __future__ import annotations

import math
from itertools import combinations

from hypermnesic import generated
from hypermnesic import index as index_mod
from hypermnesic import propose as propose_mod

SUGGESTIONS_REL = "dashboards/connection-suggestions.md"
_DEFAULT_THRESHOLD = 0.83
_DEFAULT_NEAR_DUP = 0.999
_DEFAULT_CAP = 20


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def candidate_pairs(vectors: dict[str, list[float]], graph, *,
                    threshold: float = _DEFAULT_THRESHOLD,
                    near_dup: float = _DEFAULT_NEAR_DUP,
                    cap: int = _DEFAULT_CAP) -> list[tuple[str, str, float]]:
    """Return ``(path_a, path_b, similarity)`` for similar-AND-unlinked pairs,
    sorted by similarity desc and bounded to ``cap``. Near-duplicates (``>=
    near_dup``) are excluded as boilerplate, not insight. Deterministic."""
    paths = sorted(vectors)
    out: list[tuple[str, str, float]] = []
    for a, b in combinations(paths, 2):
        sim = _cosine(vectors[a], vectors[b])
        if sim < threshold or sim >= near_dup:
            continue
        if graph is not None and b in graph.neighbors(a):   # already linked → not novel
            continue
        out.append((a, b, sim))
    out.sort(key=lambda t: (-t[2], t[0], t[1]))
    return out[:cap]


def build_suggestions_note(pairs: list[tuple[str, str, float]], *, now: str | None = None) -> str:
    """Render the generated suggestions markdown (demarcated; never mutates sources)."""
    fm = {"title": "Connection suggestions", "type": "dashboard"}
    if now:
        fm["generated_at"] = now
    if not pairs:
        body = "_No new connections suggested_ — nothing similar-yet-unlinked above threshold."
    else:
        lines = ["Notes that grapple with a similar idea but aren't linked — connect them?", ""]
        for a, b, sim in pairs:
            lines.append(f"- [[{a}]] ↔ [[{b}]] — similarity {sim:.3f}")
        body = "\n".join(lines)
    return generated.render(fm, body)


def connection_proposals(repo, *, graph, idx=None, vectors=None, embedder=None,
                         threshold: float = _DEFAULT_THRESHOLD,
                         near_dup: float = _DEFAULT_NEAR_DUP, cap: int = _DEFAULT_CAP,
                         log=None, gh_create=None, now: str | None = None):
    """Emit similar-but-unlinked connections as a bounded, batched U18 proposal.

    Returns the ``ProposalResult`` — or ``None`` when there is nothing to suggest
    (no noise). Never writes an edge directly into a note.

    U30/FR-R39: when vectors are derived from ``idx`` (not supplied directly), a
    full unbudgeted embed runs first so a similar-but-unlinked pair is never missed
    because one note's chunk was unembedded — ``note_vectors()`` sees every chunk."""
    if vectors is None:
        if idx is not None:
            index_mod.ensure_full_coverage(idx, repo, embedder)   # full embed before reading
            vectors = idx.note_vectors()
        else:
            vectors = {}
    pairs = candidate_pairs(vectors, graph, threshold=threshold, near_dup=near_dup, cap=cap)
    if not pairs:
        return None
    note = build_suggestions_note(pairs, now=now)
    return propose_mod.propose(
        repo, [propose_mod.Change(path=SUGGESTIONS_REL, body=note)],
        slug="connection-suggestions",
        summary=f"connection suggestions: {len(pairs)} similar-but-unlinked pair(s)",
        why="dense similarity + no existing wikilink edge (H3, KTD3) — never auto-linked",
        source="engine: stored note vectors + body-wikilink graph",
        allowlist=["dashboards/"], log=log, gh_create=gh_create)
