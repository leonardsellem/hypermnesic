"""Label-review build / parse / apply round-trip (offline)."""

from __future__ import annotations

import label_review as lr

from hypermnesic import index

CORPUS = {
    "a.md": "# A\n\nalpha alpha widget assembly throughput.\n",
    "b.md": "# B\n\nbeta beta retrieval recall topic.\n",
    "c.md": "# C\n\ngamma gamma unrelated cooking.\n",
}


def test_build_review_lists_candidates_and_prechecks_labels(make_corpus, fake_embedder):
    repo = make_corpus(CORPUS)
    idx = index.build_index(repo, fake_embedder)
    queries = [{"id": "q01", "lang": "en", "query": "alpha widget",
                "relevant": ["a.md"], "relevant_primary": "a.md"}]
    baseline = {"q01": ["a.md", "c.md"]}
    md = lr.build_review(queries, baseline, idx, fake_embedder, k=5)
    assert "## q01 [en]" in md
    assert "alpha widget" in md
    assert "- [x] `a.md`" in md          # current label pre-checked
    assert "`c.md`" in md                 # gbrain-only candidate present
    idx.close()


def test_parse_review_reads_ticked_paths():
    md = (
        "## q01 [en]\n"
        "- [x] `a.md` (hyp#1 gbrain#1) — snip\n"
        "- [ ] `c.md` (hyp— gbrain#2) — snip\n"
        "- [X] `d.md` (hyp#3 gbrain—) — snip\n"
        "## q02 [fr]\n"
        "- [ ] `e.md` — snip\n"
    )
    parsed = lr.parse_review(md)
    assert parsed["q01"] == ["a.md", "d.md"]   # [x] and [X], not [ ]
    assert parsed["q02"] == []


def test_apply_review_updates_labels_and_primary():
    queries = [{"id": "q01", "lang": "en", "query": "q", "relevant": ["a.md"],
                "relevant_primary": "a.md", "method": "agent"}]
    md = ("## q01 [en]\n"
          "- [ ] `a.md` — snip\n"          # operator UNCHECKED the old label
          "- [x] `b.md` — snip\n"          # and checked a different doc
          "- [x] `d.md` — snip\n")
    updated, changes = lr.apply_review(md, queries)
    assert updated[0]["relevant"] == ["b.md", "d.md"]
    assert updated[0]["relevant_primary"] == "b.md"   # old primary gone → first ticked
    assert updated[0]["method"] == "human-reviewed-known-item"
    assert changes and "q01" in changes[0]


def test_apply_review_empty_ticks_left_unchanged():
    queries = [{"id": "q01", "query": "q", "relevant": ["a.md"], "relevant_primary": "a.md"}]
    md = "## q01 [en]\n- [ ] `a.md` — snip\n"
    updated, changes = lr.apply_review(md, queries)
    assert updated[0]["relevant"] == ["a.md"]   # not wiped when nothing ticked
    assert any("WARNING" in c for c in changes)
