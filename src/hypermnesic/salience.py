"""U21 — salience scoring + spaced-review digest. [R6/H4/F3/KTD2]

Scores each note from signals already in hand — **write-recency** (the audit log
is write-only; there is no read/access signal, and adding one would conflict with
the read-only-is-structural posture, so "recency" means recency-of-*write*),
**link-degree** (body-wikilink graph), and **embedding centrality** (mean cosine
to other notes, via the new ``Index.note_vectors`` stored-vector accessor) — then
emits a generated digest of salient-but-dormant notes, **proposed via U18**.

KTD2: no ``salience:`` field is ever written into a source note's frontmatter —
that churn is exactly what R10/AE3 forbid. The ranking lives in the generated
digest note only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from hypermnesic import generated
from hypermnesic import index as index_mod
from hypermnesic import propose as propose_mod

# Fixed weights → deterministic scores. (Tuning is an implementation-time concern.)
_W_LINK, _W_CENT, _W_REC = 0.4, 0.3, 0.3
DIGEST_REL = "dashboards/salience-digest.md"


@dataclass
class SalienceScore:
    path: str
    score: float
    link_degree: int
    centrality: float
    write_recency: float       # 0..1, 1 = most recently written
    dormant: bool


@dataclass
class SalienceReport:
    """Salience scores plus whether centrality was computed over a fully-embedded
    corpus (U30/FR-R40). Iterable/indexable so callers can treat it as the score
    list directly (``for s in report`` / ``report[0]`` / ``len(report)``)."""

    scores: list[SalienceScore]
    coverage_complete: bool

    def __iter__(self):
        return iter(self.scores)

    def __len__(self):
        return len(self.scores)

    def __getitem__(self, i):
        return self.scores[i]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _centralities(vectors: dict[str, list[float]]) -> dict[str, float]:
    """Mean cosine of each note to all others — a representativeness proxy."""
    paths = sorted(vectors)
    if len(paths) < 2:
        return {p: 0.0 for p in paths}
    out: dict[str, float] = {}
    for p in paths:
        sims = [_cosine(vectors[p], vectors[q]) for q in paths if q != p]
        out[p] = sum(sims) / len(sims)
    return out


def _write_recency(audit_log) -> dict[str, float]:
    """Per-path recency-of-write in [0,1] by last-write timestamp, min-max scaled.
    A path with no audit entry gets 0.0 (never written through the log → dormant)."""
    last: dict[str, str] = {}
    for e in audit_log.entries() if audit_log is not None else []:
        p = e.get("path")
        if p and e.get("ts"):
            if p not in last or e["ts"] > last[p]:
                last[p] = e["ts"]
    if not last:
        return {}
    ts_sorted = sorted(set(last.values()))
    lo, hi = ts_sorted[0], ts_sorted[-1]
    if lo == hi:
        return {p: 1.0 for p in last}
    # rank-normalise by position among distinct timestamps (monotone, scale-free)
    rank = {ts: i / (len(ts_sorted) - 1) for i, ts in enumerate(ts_sorted)}
    return {p: rank[ts] for p, ts in last.items()}


def score_notes(idx, graph, audit_log, *, embedder=None, repo=None,
                dormancy_threshold: float = 0.5) -> SalienceReport:
    """Deterministic salience over every indexed path, returned as a
    :class:`SalienceReport` (sorted by score desc, then path for stable ties).

    U30/FR-R39: when ``embedder`` and ``repo`` are given, a full unbudgeted embed
    runs first so embedding centrality is computed over every chunk rather than a
    half-embedded corpus; ``report.coverage_complete`` (FR-R40) is ``False`` if the
    embedder was unavailable/failed mid-fill (the centrality is then partial)."""
    coverage_complete = index_mod.ensure_full_coverage(idx, repo, embedder)
    paths = sorted(idx.all_paths())
    vectors = idx.note_vectors()
    centrality = _centralities(vectors)
    recency = _write_recency(audit_log)

    degrees = {p: len(graph.neighbors(p)) for p in paths} if graph is not None else {}
    max_deg = max(degrees.values(), default=0) or 1

    scores: list[SalienceScore] = []
    for p in paths:
        deg = degrees.get(p, 0)
        cent = centrality.get(p, 0.0)
        rec = recency.get(p, 0.0)
        score = _W_LINK * (deg / max_deg) + _W_CENT * cent + _W_REC * rec
        scores.append(SalienceScore(path=p, score=score, link_degree=deg,
                                    centrality=cent, write_recency=rec,
                                    dormant=rec < dormancy_threshold))
    scores.sort(key=lambda s: (-s.score, s.path))
    return SalienceReport(scores=scores, coverage_complete=coverage_complete)


def dormant_salient(scores, *, top_n: int = 10) -> list[SalienceScore]:
    """Salient-but-dormant: dormant notes ranked by structural importance
    (link + centrality, NOT recency — recency is what makes them dormant)."""
    dormant = [s for s in scores if s.dormant]
    dormant.sort(key=lambda s: (-(_W_LINK * s.link_degree + _W_CENT * s.centrality), s.path))
    return dormant[:top_n]


def build_digest_note(items: list[SalienceScore], *, now: str | None = None) -> str:
    """Render the generated digest markdown (demarcated; never mutates sources)."""
    fm = {"title": "Salience digest", "type": "dashboard"}
    if now:
        fm["generated_at"] = now
    if not items:
        body = "_Nothing dormant yet_ — every salient note has been touched recently."
    else:
        lines = ["Salient-but-dormant notes worth revisiting:", ""]
        for s in items:
            lines.append(
                f"- [[{s.path}]] — links={s.link_degree}, "
                f"centrality={s.centrality:.3f}, recency={s.write_recency:.2f}")
        body = "\n".join(lines)
    return generated.render(fm, body)


def digest_proposal(repo, idx, graph, audit_log, *, embedder=None, top_n: int = 10,
                    log=None, gh_create=None, now: str | None = None):
    """Emit the spaced-review digest as a review-gated U18 proposal (never silent,
    never a source-note mutation).

    Pass ``embedder`` so ``score_notes`` forces full convergence (U30/FR-R39) before
    reading ``note_vectors()`` — otherwise the digest's centrality is computed on a
    half-embedded corpus after a write. ``repo`` is already in hand."""
    items = dormant_salient(
        score_notes(idx, graph, audit_log, embedder=embedder, repo=repo), top_n=top_n)
    note = build_digest_note(items, now=now)
    return propose_mod.propose(
        repo, [propose_mod.Change(path=DIGEST_REL, body=note)],
        slug="salience-digest", summary="salience digest: salient-but-dormant notes",
        why="resurface structurally-salient notes you haven't touched (H4)",
        source="engine: write-recency + link-degree + embedding centrality",
        allowlist=["dashboards/"], log=log, gh_create=gh_create)
