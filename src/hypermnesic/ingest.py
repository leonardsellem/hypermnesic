"""Walk a markdown corpus and chunk it for indexing.

Reads files defensively (non-UTF-8 bytes are replaced, never crash), strips
YAML frontmatter from the indexed body, and groups paragraphs into bounded
chunks while tracking the nearest preceding heading. Deterministic order
(sorted paths) so rebuilds are reproducible.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")

_SKIP_DIRS = {".git", ".hypermnesic", "node_modules", "__pycache__", ".obsidian"}
# Chunk target (chars). A hard cap well under the embedding model's 8192-token
# input limit: ~4000 chars ≈ ~1000 tokens worst case, so no chunk can overflow
# the API (the input[118] 8192-token failure on the first full index).
MAX_CHARS = 4000


def _split_oversized(block: str) -> list[str]:
    """Split a single block longer than MAX_CHARS into <=MAX_CHARS pieces.

    Prefers line boundaries; falls back to a hard character slice for a block
    with no usable whitespace (a giant table row, a base64 blob).
    """
    if len(block) <= MAX_CHARS:
        return [block]
    pieces: list[str] = []
    buf: list[str] = []
    size = 0
    for line in block.splitlines():
        while len(line) > MAX_CHARS:  # a single monstrous line
            if buf:
                pieces.append("\n".join(buf))
                buf, size = [], 0
            pieces.append(line[:MAX_CHARS])
            line = line[MAX_CHARS:]
        if size + len(line) + 1 > MAX_CHARS and buf:
            pieces.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        pieces.append("\n".join(buf))
    return [p for p in pieces if p.strip()]


@dataclass(frozen=True)
class Chunk:
    path: str          # repo-relative posix path
    ord: int           # 0-based chunk index within the file
    heading: str       # nearest preceding heading ("" if none)
    text: str


def strip_frontmatter(raw: str) -> str:
    return _FRONTMATTER_RE.sub("", raw, count=1)


def _iter_markdown_files(repo: Path) -> Iterator[Path]:
    for p in sorted(repo.rglob("*.md")):
        if any(part in _SKIP_DIRS for part in p.relative_to(repo).parts):
            continue
        yield p


def _chunk_body(body: str) -> Iterator[tuple[str, str]]:
    """Yield (heading, text) chunks from a markdown body."""
    heading = ""
    buf: list[str] = []
    size = 0

    def flush():
        nonlocal buf, size
        text = "\n\n".join(buf).strip()
        buf, size = [], 0
        return text

    for raw_block in re.split(r"\n\s*\n", body):
        raw_block = raw_block.strip()
        if not raw_block:
            continue
        lines = raw_block.splitlines()
        m = _HEADING_RE.match(lines[0])
        if m and len(lines) == 1:
            if buf:
                text = flush()
                if text:
                    yield heading, text
            heading = m.group(1).strip()
            continue
        for block in _split_oversized(raw_block):
            if size + len(block) > MAX_CHARS and buf:
                text = flush()
                if text:
                    yield heading, text
            buf.append(block)
            size += len(block)
    if buf:
        text = flush()
        if text:
            yield heading, text


_FM_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)


def doc_surface(raw: str, path: str = "") -> str:
    """A doc-level 'what is this about' surface for the doc embedding lane.

    Title (frontmatter `title:` or first H1, falling back to the slug) + all
    section headings + the lead paragraph, bounded to MAX_CHARS. This aligns with
    "about this document" NL queries better than any single mid-body chunk —
    a deterministic proxy for gbrain's compiled-summary representation.
    """
    title = ""
    fm = _FM_TITLE.search(raw[:600])
    if fm:
        title = fm.group(1).strip().strip('"').strip("'")
    body = strip_frontmatter(raw)
    headings = [m.group(1).strip() for m in re.finditer(r"^\s{0,3}#{1,6}\s+(.*)$", body, re.M)]
    if not title:
        title = headings[0] if headings else Path(path).stem.replace("-", " ")
    lead = ""
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if block and not _HEADING_RE.match(block.splitlines()[0]):
            lead = block
            break
    surface = f"{title}\n\n" + "\n".join(headings) + "\n\n" + lead
    return surface.strip()[:MAX_CHARS]


def iter_chunks(repo: Path) -> Iterator[Chunk]:
    repo = Path(repo)
    for fp in _iter_markdown_files(repo):
        raw = fp.read_text(encoding="utf-8", errors="replace")
        body = strip_frontmatter(raw)
        rel = fp.relative_to(repo).as_posix()
        for i, (heading, text) in enumerate(_chunk_body(body)):
            yield Chunk(path=rel, ord=i, heading=heading, text=text)


def chunks_for_text(path: str, raw: str) -> list[Chunk]:
    """Chunk a single document's raw text (frontmatter stripped) — for the
    synchronous lexical extraction in commit_note (U7)."""
    body = strip_frontmatter(raw)
    return [Chunk(path=path, ord=i, heading=h, text=t)
            for i, (h, t) in enumerate(_chunk_body(body))]


def iter_doc_surfaces(repo: Path) -> Iterator[tuple[str, str]]:
    """Yield (repo-relative path, doc surface) for every markdown file."""
    repo = Path(repo)
    for fp in _iter_markdown_files(repo):
        raw = fp.read_text(encoding="utf-8", errors="replace")
        rel = fp.relative_to(repo).as_posix()
        surface = doc_surface(raw, rel)
        if surface:
            yield rel, surface
