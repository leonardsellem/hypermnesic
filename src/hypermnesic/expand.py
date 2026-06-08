"""Optional multi-query expansion for retrieval.

Generates alternative phrasings of a query (same language, varied wording, key
entities surfaced) so the dense channel can fuse several angles — the
ranking-precision aid gbrain gets from its own multi-query expansion. Expansion
is opt-in and **graceful**: any failure returns ``[]`` so retrieval falls back
to the un-expanded query.
"""

from __future__ import annotations

import re

from hypermnesic import config

_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def _parse(text: str, query: str, n: int) -> list[str]:
    """Parse model output into <=n distinct variant queries (offline-testable)."""
    out, seen = [], {query.strip().lower()}
    for line in (text or "").splitlines():
        s = _PREFIX.sub("", line).strip().strip('"').strip()
        key = s.lower()
        if s and key not in seen:
            seen.add(key)
            out.append(s)
    return out[:n]


class OpenAIExpander:
    """Callable ``(query, n) -> list[str]``. Returns [] on any failure."""

    def __init__(self, model: str | None = None, api_key: str | None = None, repo=None):
        self.model = model or config.EXPANSION_MODEL
        self._api_key = api_key
        self.repo = repo
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key or config.get_api_key(repo=self.repo))
        return self._client

    def __call__(self, query: str, n: int = 3) -> list[str]:
        system = (
            f"Generate {n} alternative search queries for the same information "
            "need. Keep the SAME language as the query. Vary the phrasing and "
            "surface key entities, names, and keywords. Return ONLY the queries, "
            "one per line, no numbering, no commentary."
        )
        try:
            resp = self._get_client().chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": query}],
            )
            text = resp.choices[0].message.content or ""
        except Exception:
            return []  # graceful — caller falls back to the un-expanded query
        return _parse(text, query, n)
