"""Hybrid retrieval: fuse FTS5 (lexical) + sqlite-vec (dense) into one ranking.

Fusion is Reciprocal Rank Fusion (parameter-light, scale-free). An **optional**
rerank stage lets the parity harness equalize the rerank level against gbrain
(KTD5) without pulling a proprietary reranker into the product core — default is
un-reranked.

Graceful degradation: if query embedding is unavailable (API down), the dense
channel is skipped and lexical+graph still answer — but the result is flagged
``dense_used=False`` so the parity harness can **void** (not FAIL) a run that
silently degraded to lexical-only (G6).
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from hypermnesic import embed as embed_mod

_RRF_K0 = 60

# R3: the measured review/snapshot subtrees (component boundaries, never a
# substring or blanket `artifacts/` match).
_REVIEW_SUBTREES = (
    "projects/homelab/artifacts/2026-10-06-native-goal-profile-candidate",
    "projects/homelab/artifacts/2026-10-09-replay-source-grooms",
    "projects/homelab/artifacts/ls2860-contract-candidate",
    "projects/homelab/services/hermes-agent-config-snapshot/identity/profiles",
)


def path_authority(path: str) -> str:
    """R3 authority class of a repo-relative path, first match wins.

    ``non_knowledge`` paths are excluded at admission and never reach retrieval;
    this classifier only tells a retained path's secondary class from ``primary``.
    """
    dirs = path.split("/")[:-1]
    if "_archive" in dirs:
        return "archive"
    if "jude-scratch" in dirs:
        return "review"
    if any(path.startswith(root + "/") for root in _REVIEW_SUBTREES):
        return "review"
    if dirs and dirs[0] in ("reports", "state"):
        return "reports_state"
    if "openwiki" in dirs:
        return "openwiki"
    return "primary"


def is_primary(path: str) -> bool:
    """True when ``path`` is authoritative knowledge (not an archive/review/generated copy)."""
    return path_authority(path) == "primary"


@dataclass
class Hit:
    chunk_id: int
    path: str
    heading: str
    text: str
    score: float
    channels: set[str] = field(default_factory=set)
    # U29: per-result write-recency — epoch seconds of the most recent commit that
    # touched ``path`` (KTD7: git commit time is canonical, the index being a git
    # projection). ``None`` when untracked / no commit metadata. Engine produces it;
    # Plan 2's companion consumes it for forgetting-curve ranking. No ranking effect here.
    recency: float | None = None


def git_commit_recency(repo) -> Callable[[str], float | None]:
    """Return a path → epoch-seconds resolver for the most recent commit touching
    a path (the write-recency source of truth, KTD7), or ``None`` when the path is
    untracked / has no commit. Access-recency is out of scope (no read logging).

    The path→time map is built lazily with a SINGLE ``git log`` pass on first lookup
    (not one subprocess per hit — that added ~k git forks to every search). A
    ``\\x1f`` (unit-separator) sentinel marks the timestamp line so a digit-only
    filename can't be misread as a timestamp; ``core.quotepath=false`` keeps
    non-ASCII paths raw so they match. Newest-first walk → first sighting wins."""
    repo = Path(repo)
    cache: dict[str, float] = {}
    built = False

    def _build() -> None:
        nonlocal built
        built = True
        try:
            out = subprocess.run(
                ["git", "-C", str(repo), "-c", "core.quotepath=false", "log",
                 "--format=\x1f%ct", "--name-only", "--no-renames"],
                capture_output=True, text=True, check=True).stdout
        except (FileNotFoundError, subprocess.CalledProcessError):
            return
        ts: float | None = None
        for line in out.splitlines():
            if line.startswith("\x1f"):
                try:
                    ts = float(line[1:])
                except ValueError:
                    ts = None
            elif line and ts is not None and line not in cache:
                cache[line] = ts          # first (newest) commit touching this path

    def _recency(path: str) -> float | None:
        if not built:
            _build()
        return cache.get(path)

    return _recency


@dataclass
class SearchResult:
    hits: list[Hit]
    dense_used: bool
    lexical_used: bool
    degraded_reason: str | None = None

    @property
    def degraded(self) -> bool:
        """True when the dense channel did not contribute (lexical-only)."""
        return not self.dense_used


def _rrf(rank: int) -> float:
    return 1.0 / (_RRF_K0 + rank)


def search(idx, query: str, embedder=None, *, k: int = 10, candidate_k: int = 50,
           rerank: Callable[[str, list[Hit]], list[Hit]] | None = None,
           collapse_duplicates: bool = True,
           exclude_path: str | None = None,
           expand: int = 0,
           expander: Callable[[str, int], list[str]] | None = None,
           use_doc_lane: bool = True,
           recency_fn: Callable[[str], float | None] | None = None,
           weights: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> SearchResult:
    """Hybrid search over ``idx``. Returns up to ``k`` fused hits.

    ``rerank`` (optional) reorders the fused top-``candidate_k`` *without changing
    membership* at fixed k.

    ``collapse_duplicates`` (default on): drop hits whose chunk text is byte-
    identical to a higher-ranked hit. Corpora routinely mirror the same document
    at two paths (e.g. ``docs/x`` and ``projects/.../docs/x``); without this they
    flood the result list and crowd out distinct docs (the q07 parity artifact)
    — and a user gets a half-duplicate list. Keeps the highest-ranked copy.

    ``expand`` / ``expander`` (optional multi-query expansion): generate up to
    ``expand`` alternative phrasings of the query and fuse the **dense** results
    of every variant via RRF. A doc that the target answers from several angles
    accumulates rank-fusion mass, which lifts ranking precision (the MRR gap vs
    gbrain, which runs its own multi-query expansion). Graceful: an expander
    failure falls back to no expansion. Lexical runs on the original query only
    (phrase-matching paraphrases is noisy).

    ``exclude_path`` (optional): drop every hit whose path equals it before
    truncating to ``k`` — used by ``think`` to stop a note matching itself. The
    ``candidate_k`` pool absorbs the drop, so a self-match does not shrink the
    result below ``k`` when other matches exist.
    """
    fused: dict[int, float] = {}
    channels: dict[int, set[str]] = {}

    # lexical channel (original query only)
    w_lex, w_dense, w_doc = weights
    lexical_used = True
    for rank, (cid, _bm25) in enumerate(idx.lexical_search(query, k=candidate_k)):
        fused[cid] = fused.get(cid, 0.0) + w_lex * _rrf(rank)
        channels.setdefault(cid, set()).add("lexical")

    # build the dense query set: original + expansion variants (graceful)
    queries = [query]
    if expand and expander is not None:
        try:
            variants = expander(query, expand)
        except Exception:  # any expander failure → no expansion, never crash
            variants = []
        queries += [v for v in (variants or []) if v and v.strip()]

    # dense channel (graceful degradation on embedding failure), fused across variants
    dense_used = False
    degraded_reason: str | None = "missing_embedder" if embedder is None else None
    orig_qvec = None
    for n, qi in enumerate(queries):
        try:
            qvec = embedder.embed([qi])[0] if embedder is not None else None
        except embed_mod.EmbeddingError as exc:
            degraded_reason = exc.reason
            qvec = None
        if qvec is None:
            continue
        dense_used = True
        degraded_reason = None
        if n == 0:
            orig_qvec = qvec
        for rank, (cid, _dist) in enumerate(idx.dense_search(qvec, k=candidate_k)):
            fused[cid] = fused.get(cid, 0.0) + w_dense * _rrf(rank)
            channels.setdefault(cid, set()).add("dense")

    # doc-level lane (UA): a doc-surface match lifts that doc via its representative
    # chunk — aligns "about this doc" NL queries with the right doc (MRR).
    if (use_doc_lane and orig_qvec is not None
            and getattr(idx, "has_doc_lane", lambda: False)()):
        for rank, (path, _dist) in enumerate(idx.doc_dense_search(orig_qvec, k=candidate_k)):
            cids = idx.chunks_for_path(path)
            if cids:
                fused[cids[0]] = fused.get(cids[0], 0.0) + w_doc * _rrf(rank)
                channels.setdefault(cids[0], set()).add("doc")

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    resolved: list[tuple[int, float, dict]] = []
    for cid, score in ranked[:candidate_k]:
        try:
            ch = idx.get_chunk(cid)
        except KeyError:
            # A concurrent projection update can leave stale FTS/vector candidates
            # visible to a reader briefly. The git tree remains source of truth, so
            # ignore orphaned index rows instead of failing recall.
            continue
        if exclude_path is not None and ch["path"] == exclude_path:
            continue                       # self-exclusion (U42); never its own match
        resolved.append((cid, score, ch))

    # R3: stably partition by authority BEFORE content dedup, so an identical
    # secondary copy can never consume the primary copy's slot.
    tiers: dict[bool, list[Hit]] = {True: [], False: []}
    seen_text: set[str] = set()
    for want_primary in (True, False):
        for cid, score, ch in resolved:
            if is_primary(ch["path"]) is not want_primary:
                continue
            if collapse_duplicates:
                th = hashlib.sha256(ch["text"].encode("utf-8")).hexdigest()
                if th in seen_text:
                    continue
                seen_text.add(th)
            tiers[want_primary].append(Hit(
                chunk_id=cid, path=ch["path"], heading=ch["heading"],
                text=ch["text"], score=score, channels=channels[cid],
                recency=recency_fn(ch["path"]) if recency_fn is not None else None))
    primary, secondary = tiers[True], tiers[False]

    if rerank is not None:
        # Rerank only WITHIN each tier's existing window: a secondary hit can
        # never move above a primary one (membership within a tier is preserved).
        primary = _rerank_window(rerank, query, primary, k)
        secondary = _rerank_window(rerank, query, secondary, k)

    if len(primary) >= 3:
        hits = primary + secondary          # secondary fills positions 4+
    elif primary:
        hits = primary                      # one/two primary: never padded with secondary
    else:
        hits = secondary                    # no primary: the secondary results answer

    if not dense_used and degraded_reason is None:
        degraded_reason = "embedding_error"
    return SearchResult(
        hits=hits[:k],
        dense_used=dense_used,
        lexical_used=lexical_used,
        degraded_reason=degraded_reason,
    )


def _rerank_window(rerank: Callable[[str, list[Hit]], list[Hit]], query: str,
                   hits: list[Hit], k: int) -> list[Hit]:
    """Apply the optional reranker to one tier's top-k window, preserving membership."""
    head = rerank(query, hits[:k])
    seen = {h.chunk_id for h in head}
    return head + [h for h in hits if h.chunk_id not in seen]
