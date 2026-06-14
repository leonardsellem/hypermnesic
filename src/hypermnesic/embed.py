"""OpenAI embeddings, pinned to ``text-embedding-3-large`` @ dimensions=1536.

The ``dimensions`` parameter is sent **explicitly** (the parameter Basic Memory
never forwarded — KTD2). The startup smoke embed fails fast and loudly on a
missing/invalid key (the 16-hour silent-failure scar): it never silently
proceeds with zero-vectors.
"""

from __future__ import annotations

import time

from hypermnesic import config


class EmbeddingError(RuntimeError):
    """Raised when embedding fails — never swallowed, never zero-filled."""

    def __init__(self, message: str, *, reason: str = "embedding_error"):
        super().__init__(message)
        self.reason = reason


def _embedding_failure_reason(exc: Exception) -> str:
    """Classify provider failures without depending on a concrete SDK response body."""
    status = getattr(exc, "status_code", None)
    if status == 429 or exc.__class__.__name__ == "RateLimitError":
        return "rate_limited"
    if status is not None:
        return "api_error"
    return "embedding_error"


class OpenAIEmbedder:
    """Calls the OpenAI embeddings API. Validates the returned dimension."""

    def __init__(self, api_key: str | None = None,
                 model: str = config.EMBED_MODEL, dim: int = config.EMBED_DIM,
                 repo=None, cooldown_seconds: float | None = None, now_fn=None):
        self.model = model
        self.dim = dim
        self.repo = repo
        self._api_key = api_key  # resolved lazily so construction never echoes
        self._client = None
        self.cooldown_seconds = (
            config.EMBED_FAILURE_COOLDOWN_SECONDS
            if cooldown_seconds is None else cooldown_seconds
        )
        self._now = now_fn or time.time
        self._cooldown_until = 0.0
        self._cooldown_reason: str | None = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise EmbeddingError(f"openai SDK not importable: {exc}") from exc
            key = self._api_key or config.get_api_key(repo=self.repo)
            self._client = OpenAI(api_key=key)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        now = self._now()
        if self._cooldown_until > now:
            remaining = max(0.0, self._cooldown_until - now)
            reason = self._cooldown_reason or "embedding_error"
            raise EmbeddingError(
                f"embedding temporarily disabled after {reason}; "
                f"retry after {remaining:.0f}s",
                reason="cooldown",
            )
        try:
            resp = self._get_client().embeddings.create(
                model=self.model, input=texts, dimensions=self.dim,
            )
        except config.ConfigError as exc:
            raise EmbeddingError(str(exc), reason="configuration") from exc
        except Exception as exc:  # surface as a clear top-level error
            reason = _embedding_failure_reason(exc)
            if reason == "rate_limited" and self.cooldown_seconds > 0:
                self._cooldown_until = now + self.cooldown_seconds
                self._cooldown_reason = reason
            raise EmbeddingError(f"embedding request failed: {exc}", reason=reason) from exc
        vectors = [d.embedding for d in resp.data]
        for v in vectors:
            if len(v) != self.dim:
                raise EmbeddingError(
                    f"embedding dim {len(v)} != pinned {self.dim} (model {self.model})"
                )
        return vectors


def smoke_embed_or_die(embedder: OpenAIEmbedder | None = None, repo=None) -> None:
    """Embed one vector at startup; raise EmbeddingError on any failure.

    This is the explicit read-vs-set check: it confirms the key is actually
    *read* by the SDK, not merely present in the environment.
    """
    try:
        key = config.get_api_key(repo=repo)
    except config.ConfigError as exc:
        raise EmbeddingError(str(exc)) from exc
    emb = embedder or OpenAIEmbedder(api_key=key, repo=repo)
    vecs = emb.embed(["hypermnesic startup smoke embed"])
    if not vecs or len(vecs[0]) != emb.dim:
        raise EmbeddingError("smoke embed returned no/short vector — refusing to proceed")
