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

from collections.abc import Callable
from dataclasses import dataclass, field

from hypermnesic import embed as embed_mod

_RRF_K0 = 60


@dataclass
class Hit:
    chunk_id: int
    path: str
    heading: str
    text: str
    score: float
    channels: set[str] = field(default_factory=set)


@dataclass
class SearchResult:
    hits: list[Hit]
    dense_used: bool
    lexical_used: bool

    @property
    def degraded(self) -> bool:
        """True when the dense channel did not contribute (lexical-only)."""
        return not self.dense_used


def _rrf(rank: int) -> float:
    return 1.0 / (_RRF_K0 + rank)


def search(idx, query: str, embedder=None, *, k: int = 10, candidate_k: int = 50,
           rerank: Callable[[str, list[Hit]], list[Hit]] | None = None) -> SearchResult:
    """Hybrid search over ``idx``. Returns up to ``k`` fused hits.

    ``rerank`` (optional) reorders the fused top-``candidate_k`` *without changing
    membership* at fixed k.
    """
    fused: dict[int, float] = {}
    channels: dict[int, set[str]] = {}

    # lexical channel
    lexical_used = True
    for rank, (cid, _bm25) in enumerate(idx.lexical_search(query, k=candidate_k)):
        fused[cid] = fused.get(cid, 0.0) + _rrf(rank)
        channels.setdefault(cid, set()).add("lexical")

    # dense channel (graceful degradation on embedding failure)
    dense_used = False
    if embedder is not None:
        try:
            qvec = embedder.embed([query])[0]
            dense_used = True
        except embed_mod.EmbeddingError:
            qvec = None
        if qvec is not None:
            for rank, (cid, _dist) in enumerate(idx.dense_search(qvec, k=candidate_k)):
                fused[cid] = fused.get(cid, 0.0) + _rrf(rank)
                channels.setdefault(cid, set()).add("dense")

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    hits: list[Hit] = []
    for cid, score in ranked[:candidate_k]:
        ch = idx.get_chunk(cid)
        hits.append(Hit(chunk_id=cid, path=ch["path"], heading=ch["heading"],
                        text=ch["text"], score=score, channels=channels[cid]))

    if rerank is not None:
        head = rerank(query, hits[:k])
        # rerank reorders only the top-k window; membership at k is preserved
        seen = {h.chunk_id for h in head}
        tail = [h for h in hits if h.chunk_id not in seen]
        hits = head + tail

    return SearchResult(hits=hits[:k], dense_used=dense_used, lexical_used=lexical_used)
