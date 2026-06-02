"""Body-wikilink knowledge graph + ``build_context`` traversal.

Edges are **body** ``[[wikilinks]]`` only. Frontmatter ``related_to:`` /
``belongs_to:`` are deliberately NOT edges — and because :mod:`ingest` strips
frontmatter before chunking, the graph never even sees them. ``build_context``
walks both incoming and outgoing edges to a bounded depth.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path

from hypermnesic import ingest

_WIKILINK_RE = re.compile(r"\[\[([^\]]+?)\]\]")


def _link_target(raw: str) -> str:
    """Normalize a wikilink body to a comparable target key (no display, no anchor)."""
    target = raw.split("|", 1)[0].strip()
    target = target.split("#", 1)[0].strip()
    return target


class Graph:
    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self.out_edges: dict[str, set[str]] = {}
        self.in_edges: dict[str, set[str]] = {}
        # resolution helpers
        self._by_path: dict[str, str] = {}   # normalized posix path (no .md) -> path
        self._by_stem: dict[str, list[str]] = {}

    # --- construction ----------------------------------------------------
    @classmethod
    def from_pages(cls, pages: dict[str, str]) -> Graph:
        """Build from {repo-relative posix path: body text} (frontmatter stripped)."""
        g = cls()
        for path in pages:
            g.nodes.add(path)
            g.out_edges.setdefault(path, set())
            g.in_edges.setdefault(path, set())
            key = path[:-3] if path.endswith(".md") else path
            g._by_path[key.lower()] = path
            g._by_stem.setdefault(Path(path).stem.lower(), []).append(path)
        for path, text in pages.items():
            for raw in _WIKILINK_RE.findall(text):
                tgt = g._resolve(_link_target(raw))
                if tgt and tgt != path:
                    g.out_edges[path].add(tgt)
                    g.in_edges[tgt].add(path)
        return g

    @classmethod
    def from_repo(cls, repo: Path) -> Graph:
        pages: dict[str, list[str]] = {}
        for ch in ingest.iter_chunks(repo):
            pages.setdefault(ch.path, []).append(ch.text)
        return cls.from_pages({p: "\n\n".join(t) for p, t in pages.items()})

    @classmethod
    def from_index(cls, idx) -> Graph:
        pages: dict[str, list[str]] = {}
        for ch in idx.all_chunks():
            pages.setdefault(ch["path"], []).append(ch["text"])
        return cls.from_pages({p: "\n\n".join(t) for p, t in pages.items()})

    def _resolve(self, target: str) -> str | None:
        if not target:
            return None
        key = target.lower()
        if key in self._by_path:
            return self._by_path[key]
        if key.endswith(".md") and key[:-3] in self._by_path:
            return self._by_path[key[:-3]]
        stem = Path(target).stem.lower()
        matches = self._by_stem.get(stem)
        if matches and len(matches) == 1:
            return matches[0]
        return None  # ambiguous or nonexistent → dead link, tolerated

    # --- entity resolution (public) --------------------------------------
    def resolve(self, name: str) -> str | None:
        """Resolve an entity name to an existing page's repo-relative ``.md`` path.

        gbrain's ``get`` role, exposed as a first-class verb (U1): the caller (an
        ingest job doing entity resolution) strips ``.md`` to form a wikilink target.
        Uses the *same* exact-path / ``.md``-suffix / unambiguous-stem matching the
        body-wikilink resolver uses — including stripping a ``|display`` alias and a
        ``#anchor`` — so resolution is identical to how a ``[[name]]`` would bind.
        Ambiguous (stem shared by >1 page) or missing names return ``None`` rather
        than guessing — never a wrong wikilink target.
        """
        return self._resolve(_link_target(name))

    # --- traversal -------------------------------------------------------
    def neighbors(self, path: str) -> set[str]:
        return self.out_edges.get(path, set()) | self.in_edges.get(path, set())


def build_context(graph: Graph, start: str, depth: int = 1) -> list[str]:
    """Return pages reachable from ``start`` via in/out edges within ``depth`` hops.

    Cycle-safe (visited set); excludes the start page itself. Deterministic order
    (sorted) so results are reproducible.
    """
    seen: set[str] = {start}
    frontier: deque[tuple[str, int]] = deque([(start, 0)])
    found: set[str] = set()
    while frontier:
        node, d = frontier.popleft()
        if d >= depth:
            continue
        for nb in graph.neighbors(node):
            if nb not in seen:
                seen.add(nb)
                found.add(nb)
                frontier.append((nb, d + 1))
    return sorted(found)
