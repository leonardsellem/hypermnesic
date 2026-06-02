"""U19 — content-addressed multi-format sidecar extraction. [R13/#10/KD5/KTD4/KTD5]

Non-markdown sources (PDF/DOCX/XLSX/PPTX/PNG) get an indexed **markdown sidecar**
so they become retrievable. A router keyed on ``(extension, complexity)`` sends
complex/scanned/table/equation PDFs + images to **Docling** (MIT) and
DOCX/PPTX/simple-PDF/XLSX to **MarkItDown** (MIT); the scanned-vs-native + table
heuristic uses **permissive** ``pypdf``/``pdfplumber`` — never PyMuPDF (AGPL) or
Marker (GPL). The extractor libs are imported lazily so this module (and its
routing/hash-gate logic) loads without them.

Each sidecar is **content-addressed** (KTD5): it carries ``extracted_from`` /
``extracted_at`` / ``source_sha256`` / ``_extraction_quality`` (plus the extractor
+ version). Re-extraction fires only on a source-hash mismatch or an
extractor-version bump, and lands as a **review-gated U18 proposal** — never a
silent overwrite. The one-time cold-start over the whole corpus is **one batched
proposal**, not a PR per file (Risk R-1/R-5).

Untrusted-content boundary (SEC-001): sidecar text comes from arbitrary binaries
and is read by write-capable agents via the index. Every sidecar carries a
``source: sidecar`` trust tag; Phase-2 posture is **accept** (owner corpus,
tailnet), but the tag is present now so the Phase-3 threat model can restrict
sidecar chunks from write-capable tools.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from hypermnesic import frontmatter_gate as fg
from hypermnesic import propose as propose_mod

# Bump to force re-extraction of every sidecar (e.g. when an extractor improves).
EXTRACTOR_VERSION = "1"
# Generated sidecars live here — a NON-protected dir (views/ is guard-protected).
SIDECAR_DIR = "sidecars"

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"}
_MARKITDOWN_EXTS = {".docx", ".pptx", ".xlsx"}


# --- routing ------------------------------------------------------------------

def route(source_rel: str, complexity: dict | None = None) -> str:
    """Return the extractor for ``source_rel``: ``"docling"`` or ``"markitdown"``.

    Images and complex/scanned/table/equation PDFs → Docling; DOCX/PPTX/XLSX and
    simple native PDFs → MarkItDown. ``complexity`` (the permissive-lib probe) is
    injectable so routing is testable without the heavy extractor libs.
    """
    ext = Path(source_rel).suffix.lower()
    if ext in _IMAGE_EXTS:
        return "docling"                                   # layout/caption extraction
    if ext == ".pdf":
        c = complexity if complexity is not None else detect_complexity(source_rel)
        if c.get("scanned") or c.get("table_dense") or c.get("has_equations"):
            return "docling"
        return "markitdown"
    if ext in _MARKITDOWN_EXTS:
        return "markitdown"
    return "markitdown"                                    # safe permissive default


def detect_complexity(source_path) -> dict:
    """Permissive scanned-vs-native + table-density probe (``pypdf``/``pdfplumber``
    — NOT PyMuPDF). Imported lazily; returns a conservative default if unavailable."""
    try:
        import pdfplumber  # noqa: F401  (MIT)
        from pypdf import PdfReader  # (BSD)
    except Exception:
        return {"scanned": False, "table_dense": False, "has_equations": False}
    try:
        reader = PdfReader(str(source_path))
        text = "".join((p.extract_text() or "") for p in reader.pages[:3])
        scanned = len(text.strip()) < 32           # almost no extractable text → scanned
        table_dense = False
        import pdfplumber
        with pdfplumber.open(str(source_path)) as pdf:
            for page in pdf.pages[:3]:
                if page.find_tables():
                    table_dense = True
                    break
        return {"scanned": scanned, "table_dense": table_dense, "has_equations": False}
    except Exception:
        return {"scanned": False, "table_dense": False, "has_equations": False}


def _quality(route_to: str, ext: str, complexity: dict | None) -> str:
    """Honest fidelity flag: MarkItDown-on-PDF-with-tables → low; XLSX → partial
    (flattening loses structure); else ok. Equations are attempted only by Docling."""
    c = complexity or {}
    if route_to == "markitdown" and ext == ".pdf" and c.get("table_dense"):
        return "low"
    if ext == ".xlsx":
        return "partial"
    return "ok"


# --- content addressing -------------------------------------------------------

def source_sha256(source_path) -> str:
    return hashlib.sha256(Path(source_path).read_bytes()).hexdigest()


def sidecar_rel(source_rel: str) -> str:
    """The repo-relative path of the sidecar for ``source_rel`` (under SIDECAR_DIR)."""
    return f"{SIDECAR_DIR}/{source_rel}.md"


def trust_tag(rel_path: str, frontmatter: dict | None = None) -> str:
    """``"sidecar"`` for generated sidecars (by path convention or ``source:``
    frontmatter), else ``"source"`` — the SEC-001 boundary marker."""
    if rel_path.startswith(SIDECAR_DIR + "/"):
        return "sidecar"
    if frontmatter and frontmatter.get("source") == "sidecar":
        return "sidecar"
    return "source"


def _parse_frontmatter(text: str) -> dict:
    fm_inner, _ = fg.split_frontmatter(text)
    if fm_inner is None:
        return {}
    try:
        return dict(fg._yaml().load(fm_inner) or {})
    except Exception:
        return {}


def needs_extraction(source_path, sidecar_text: str | None) -> bool:
    """Hash-gate (KTD5): re-extract only if there is no sidecar, the source hash
    changed, or the extractor version bumped. Otherwise skip — no churn."""
    if not sidecar_text:
        return True
    fm = _parse_frontmatter(sidecar_text)
    if fm.get("source_sha256") != source_sha256(source_path):
        return True
    if str(fm.get("extractor_version")) != EXTRACTOR_VERSION:
        return True
    return False


# --- extraction ---------------------------------------------------------------

@dataclass
class SidecarResult:
    source_rel: str
    sidecar_rel: str
    route: str
    quality: str
    frontmatter: dict
    body: str
    text: str          # the full sidecar markdown (frontmatter + body)


def _default_extract(source_path, route_to: str) -> str:
    """Lazy-imported extraction. Docling/MarkItDown (both MIT). Heavy — never
    imported at module load; tests inject a fake ``extract_fn`` instead."""
    if route_to == "docling":
        from docling.document_converter import DocumentConverter
        return DocumentConverter().convert(str(source_path)).document.export_to_markdown()
    from markitdown import MarkItDown
    return MarkItDown().convert(str(source_path)).text_content


def build_sidecar(repo, source_rel: str, *, complexity: dict | None = None,
                  extract_fn=_default_extract, now: str | None = None) -> SidecarResult:
    """Extract one source into a content-addressed sidecar (in memory).

    Pure assembly: routes, extracts (via ``extract_fn``, injectable for tests),
    computes the hash + quality, and renders the provenance frontmatter. Does NOT
    write or propose — the caller routes the result through U18 (cold-start batch
    or per-file re-extraction proposal)."""
    repo = Path(repo)
    src_path = repo / source_rel
    ext = Path(source_rel).suffix.lower()
    route_to = route(source_rel, complexity)
    body = extract_fn(src_path, route_to)
    quality = _quality(route_to, ext, complexity)
    fm = {
        "source": "sidecar",                # SEC-001 trust tag
        "generated_by": "hypermnesic",      # demarcation (KD7/R10)
        "extracted_from": source_rel,
        "extracted_at": now or datetime.now(UTC).isoformat(),
        "source_sha256": source_sha256(src_path),
        "extractor": route_to,
        "extractor_version": EXTRACTOR_VERSION,
        "_extraction_quality": quality,
    }
    buf = StringIO()
    fg._yaml().dump(dict(fm), buf)
    text = "---\n" + buf.getvalue() + "---\n" + body
    return SidecarResult(source_rel, sidecar_rel(source_rel), route_to, quality,
                         fm, body, text)


# --- U18-routed writes (never silent) -----------------------------------------

def cold_start_proposal(repo, source_rels, *, slug="sidecar-cold-start", extract_fn,
                        complexity_by_src=None, log=None, gh_create=None, now=None):
    """One-time initial extraction over many sources as ONE batched U18 proposal
    (not a PR per file — Risk R-1/R-5)."""
    complexity_by_src = complexity_by_src or {}
    changes = []
    for src in source_rels:
        sc = build_sidecar(repo, src, complexity=complexity_by_src.get(src),
                            extract_fn=extract_fn, now=now)
        changes.append(propose_mod.Change(path=sc.sidecar_rel, body=sc.text))
    return propose_mod.propose(repo, changes, slug=slug,
                               summary="cold-start: extract sidecars for the corpus",
                               why="multi-format sources need indexed markdown (R13)",
                               source=f"{len(changes)} binaries",
                               allowlist=[SIDECAR_DIR + "/"], log=log, gh_create=gh_create)


def reextract_proposal(repo, source_rel, *, extract_fn, complexity=None, log=None,
                       gh_create=None, now=None):
    """A changed source → a review-gated re-extraction PROPOSAL (never a silent
    overwrite of the existing sidecar)."""
    sc = build_sidecar(repo, source_rel, complexity=complexity,
                       extract_fn=extract_fn, now=now)
    slug = propose_mod.safe_slug(f"reextract-{source_rel}")
    return propose_mod.propose(
        repo, [propose_mod.Change(path=sc.sidecar_rel, body=sc.text)],
        slug=slug, summary=f"re-extract sidecar for {source_rel}",
        why="source bytes changed (content-addressed hash mismatch)",
        source=source_rel, allowlist=[SIDECAR_DIR + "/"], log=log, gh_create=gh_create)
