"""U19 — content-addressed multi-format sidecar extraction. [R13/#10/KTD4/KTD5]

The spec is the hash-gate + routing + never-silent-write; extractor calls are
mocked (the libs are heavy). Provenance is content-addressed; re-extraction is a
U18 proposal, never a silent overwrite; sidecar chunks carry a trust tag.
"""

from __future__ import annotations

import subprocess

from hypermnesic import index as index_mod
from hypermnesic import sidecar


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True).stdout.strip()


def _branches(repo):
    return _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()


def _fake_extract(_path, route_to):
    return f"# Extracted ({route_to})\n\nwidgets and gadgets, table of contents.\n"


# --- provenance + content addressing ------------------------------------------

def test_new_binary_produces_sidecar_with_four_provenance_fields(make_corpus):
    repo = make_corpus({"docs/report.pdf": "%PDF-1.4 fake bytes\n"})
    sc = sidecar.build_sidecar(repo, "docs/report.pdf",
                               complexity={"scanned": False, "table_dense": False},
                               extract_fn=_fake_extract, now="2026-06-02T00:00:00+00:00")
    fm = sc.frontmatter
    assert fm["extracted_from"] == "docs/report.pdf"
    assert fm["extracted_at"] == "2026-06-02T00:00:00+00:00"
    assert fm["source_sha256"] == sidecar.source_sha256(repo / "docs/report.pdf")
    assert fm["_extraction_quality"] in {"ok", "partial", "low"}
    assert sc.sidecar_rel == "sidecars/docs/report.pdf.md"


def test_unchanged_source_hash_gate_skips(make_corpus):
    repo = make_corpus({"docs/report.pdf": "%PDF-1.4 fake bytes\n"})
    sc = sidecar.build_sidecar(repo, "docs/report.pdf",
                               complexity={}, extract_fn=_fake_extract)
    # same bytes, same extractor version → no re-extraction
    assert sidecar.needs_extraction(repo / "docs/report.pdf", sc.text) is False
    # no sidecar yet → must extract
    assert sidecar.needs_extraction(repo / "docs/report.pdf", None) is True


def test_changed_source_bytes_require_reextraction(make_corpus):
    repo = make_corpus({"docs/report.pdf": "%PDF-1.4 original\n"})
    sc = sidecar.build_sidecar(repo, "docs/report.pdf",
                               complexity={}, extract_fn=_fake_extract)
    (repo / "docs/report.pdf").write_text("%PDF-1.4 CHANGED bytes\n", encoding="utf-8")
    assert sidecar.needs_extraction(repo / "docs/report.pdf", sc.text) is True


def test_extractor_version_bump_requires_reextraction(make_corpus, monkeypatch):
    repo = make_corpus({"docs/report.pdf": "%PDF-1.4 fake\n"})
    sc = sidecar.build_sidecar(repo, "docs/report.pdf",
                               complexity={}, extract_fn=_fake_extract)
    assert sidecar.needs_extraction(repo / "docs/report.pdf", sc.text) is False
    monkeypatch.setattr(sidecar, "EXTRACTOR_VERSION", "2")
    assert sidecar.needs_extraction(repo / "docs/report.pdf", sc.text) is True


# --- routing ------------------------------------------------------------------

def test_routing_table_dense_pdf_to_docling_docx_to_markitdown():
    assert sidecar.route("a.pdf", {"scanned": False, "table_dense": True}) == "docling"
    assert sidecar.route("a.pdf", {"scanned": True, "table_dense": False}) == "docling"
    assert sidecar.route("a.pdf", {"scanned": False, "table_dense": False}) == "markitdown"
    assert sidecar.route("a.docx", {}) == "markitdown"
    assert sidecar.route("a.pptx", {}) == "markitdown"
    assert sidecar.route("scan.png", {}) == "docling"


def test_markitdown_pdf_with_tables_stamps_quality_low(make_corpus):
    repo = make_corpus({"docs/t.pdf": "%PDF fake\n"})
    # routed to markitdown (not table_dense for routing) yet tables detected → low
    sc = sidecar.build_sidecar(repo, "docs/t.pdf",
                               complexity={"scanned": False, "table_dense": True},
                               extract_fn=_fake_extract)
    # table_dense routes to docling; force the markitdown+tables case explicitly:
    q = sidecar._quality("markitdown", ".pdf", {"table_dense": True})
    assert q == "low"
    assert sc.route == "docling"          # routing still prefers docling for tables


# --- trust tag (SEC-001) ------------------------------------------------------

def test_sidecar_chunks_carry_trust_tag():
    assert sidecar.trust_tag("sidecars/docs/x.pdf.md") == "sidecar"
    assert sidecar.trust_tag("notes/hand.md") == "source"
    assert sidecar.trust_tag("notes/hand.md", {"source": "sidecar"}) == "sidecar"


# --- R13: a sidecar is indexed and retrievable --------------------------------

def test_sidecar_is_indexed_and_retrievable(make_corpus, fake_embedder):
    repo = make_corpus({"docs/report.pdf": "%PDF fake\n"})
    sc = sidecar.build_sidecar(repo, "docs/report.pdf", complexity={},
                               extract_fn=_fake_extract)
    (repo / sc.sidecar_rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / sc.sidecar_rel).write_text(sc.text, encoding="utf-8")
    idx = index_mod.build_index(repo, fake_embedder)
    hits = idx.lexical_search("widgets", k=5)
    assert any(idx.get_chunk(c)["path"] == sc.sidecar_rel for c, _ in hits)
    idx.close()


# --- never silent: cold-start is ONE batch; re-extraction is a proposal -------

def test_cold_start_is_one_batched_proposal_not_per_file(make_corpus):
    repo = make_corpus({
        "docs/a.pdf": "%PDF a\n", "docs/b.docx": "PK docx b\n", "docs/c.xlsx": "PK xlsx c\n",
    })
    res = sidecar.cold_start_proposal(
        repo, ["docs/a.pdf", "docs/b.docx", "docs/c.xlsx"],
        extract_fn=_fake_extract,
        complexity_by_src={"docs/a.pdf": {"scanned": False, "table_dense": False}},
        gh_create=None, now="2026-06-02T00:00:00+00:00")
    # exactly ONE proposal branch for all three sidecars (no per-file PR flood)
    proposal_branches = [b for b in _branches(repo) if b.startswith("hypermnesic/proposals/")]
    assert len(proposal_branches) == 1
    assert len(res.files) == 3
    for f in res.files:
        assert f.startswith("sidecars/")


def test_changed_source_reextraction_is_a_proposal_not_silent(make_corpus):
    repo = make_corpus({"docs/report.pdf": "%PDF original\n"})
    head_before = _git(repo, "rev-parse", "HEAD")
    res = sidecar.reextract_proposal(repo, "docs/report.pdf",
                                     extract_fn=_fake_extract, complexity={},
                                     gh_create=None, now="2026-06-02T00:00:00+00:00")
    # it's a proposal branch, NOT a silent commit to the working HEAD
    assert res.branch is not None and res.branch.startswith("hypermnesic/proposals/")
    assert _git(repo, "rev-parse", "HEAD") == head_before
    # the sidecar exists only on the proposal branch
    assert _git(repo, "show", f"{res.branch}:{res.files[0]}")
    idx_main = _git(repo, "ls-tree", "HEAD", "sidecars/")
    assert idx_main == ""                                  # nothing on main
