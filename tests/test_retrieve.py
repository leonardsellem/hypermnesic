"""U3 — hybrid retrieval (RRF fusion), optional rerank, graceful degradation."""

from __future__ import annotations

import os
import subprocess

from hypermnesic import embed as embed_mod
from hypermnesic import index, retrieve


def _commit_dated(repo, rel, body, iso):
    """Commit ``rel`` with an explicit author+committer date so write-recency is
    deterministic (``git log --format=%ct`` reads the committer date)."""
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(body, encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_DATE": iso, "GIT_COMMITTER_DATE": iso}
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", rel],
                   env=env, check=True, capture_output=True)

NOTE_FR = """# Parité du rappel en français

La recherche dense doit égaler gbrain sur le rappel français. L'embedding
utilise text-embedding-3-large à 1536 dimensions.
"""
NOTE_EN = """# Hetzner homelab migration

We migrated the homelab from OVH to Hetzner and bound the MCP server to the
Tailscale interface address.
"""
NOTE_OTHER = "# Cooking\n\nA recipe for pancakes with flour and eggs.\n"


def _idx(make_corpus, fake_embedder):
    repo = make_corpus({"fr.md": NOTE_FR, "en.md": NOTE_EN, "other.md": NOTE_OTHER})
    return index.build_index(repo, fake_embedder)


def test_english_proper_noun_query(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    res = retrieve.search(idx, "Hetzner", embedder=fake_embedder, k=3)
    assert res.hits
    assert res.hits[0].path == "en.md"
    assert res.dense_used is True
    idx.close()


def test_french_query(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    res = retrieve.search(idx, "rappel français parité", embedder=fake_embedder, k=3)
    assert any(h.path == "fr.md" for h in res.hits)
    idx.close()


def test_graceful_degradation_when_embedding_down(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)

    class DownEmbedder:
        dim = fake_embedder.dim

        def embed(self, texts):
            raise embed_mod.EmbeddingError("API down")

    res = retrieve.search(idx, "Hetzner", embedder=DownEmbedder(), k=3)
    assert res.dense_used is False
    assert res.degraded is True          # harness must VOID, not FAIL
    assert res.lexical_used is True
    assert any(h.path == "en.md" for h in res.hits)  # lexical still answers
    idx.close()


def test_collapses_exact_content_duplicates(make_corpus, fake_embedder):
    # Mirror-flooding: the same content at two paths must not consume two result
    # slots — collapse to the highest-ranked representative so distinct docs
    # surface. (Synthetic fixture; no real corpus content.)
    mirror_body = "# Widget brief\n\nalpha widget assembly brief content here.\n"
    repo = make_corpus({
        "docs/briefs/x.md": mirror_body,
        "projects/teamspace/docs/briefs/x.md": mirror_body,   # exact mirror of the above
        "docs/distinct.md": "# Widget distinct\n\nalpha widget a distinct document.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    res = retrieve.search(idx, "alpha widget", embedder=fake_embedder, k=10)
    paths = [h.path for h in res.hits]
    mirror_hits = [p for p in paths if p.endswith("briefs/x.md")]
    assert len(mirror_hits) == 1, f"mirror not collapsed: {paths}"
    # collapse is opt-out
    res_raw = retrieve.search(idx, "alpha widget", embedder=fake_embedder, k=10,
                              collapse_duplicates=False)
    raw_mirror = [p for p in (h.path for h in res_raw.hits) if p.endswith("briefs/x.md")]
    assert len(raw_mirror) == 2
    idx.close()


def test_expansion_fuses_variant_results(make_corpus, fake_embedder):
    # Multi-query expansion: a variant query surfaces docs the original misses.
    # (With the deterministic embedder, a variant equal to a doc's text retrieves
    # that doc at distance 0 — exercises the fan-out + RRF fusion mechanics.)
    repo = make_corpus({
        "a.md": "# A\n\nalpha alpha alpha topic one.\n",
        "b.md": "# B\n\nbeta beta beta topic two.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    calls = []

    def expander(query, n):
        calls.append((query, n))
        return ["beta beta beta topic two."]  # variant == b.md chunk text

    res = retrieve.search(idx, "alpha", embedder=fake_embedder, k=5,
                          expand=1, expander=expander)
    assert calls and calls[0][1] == 1
    assert any(h.path == "b.md" for h in res.hits)  # surfaced via the variant
    idx.close()


def test_expansion_graceful_on_expander_failure(make_corpus, fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha alpha alpha.\n"})
    idx = index.build_index(repo, fake_embedder)

    def bad_expander(query, n):
        raise RuntimeError("LLM unavailable")

    res = retrieve.search(idx, "alpha", embedder=fake_embedder, k=5,
                          expand=2, expander=bad_expander)
    assert res.hits and res.dense_used is True  # no crash; behaves as expand=0
    idx.close()


def test_doc_lane_lifts_doc_by_surface(make_corpus, fake_embedder):
    # A doc whose SURFACE (title) matches the query but whose body chunks don't
    # should be lifted by the doc lane. (Deterministic embedder: query == the
    # doc's surface → doc-lane returns it at distance 0.)
    from hypermnesic import index as index_mod
    from hypermnesic import ingest
    note = "# zeta unique surface marker\n\nbody discusses unrelated omega omega.\n"
    repo = make_corpus({"target.md": note, "other.md": "# Other\n\nomega omega omega.\n"})
    idx = index_mod.build_index(repo, fake_embedder)
    surface = ingest.doc_surface(note, "target.md")
    res = retrieve.search(idx, surface, embedder=fake_embedder, k=5)
    target = [h for h in res.hits if h.path == "target.md"]
    assert target and "doc" in target[0].channels   # surfaced via the doc lane
    # turning the doc lane off must not credit the doc lane
    res_off = retrieve.search(idx, surface, embedder=fake_embedder, k=5, use_doc_lane=False)
    assert all("doc" not in h.channels for h in res_off.hits)
    idx.close()


def test_rerank_changes_order_not_membership(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    base = retrieve.search(idx, "homelab français Hetzner recipe", embedder=fake_embedder, k=3)
    assert len(base.hits) >= 2

    def reverse_rerank(query, hits):
        return list(reversed(hits))

    rer = retrieve.search(idx, "homelab français Hetzner recipe", embedder=fake_embedder,
                          k=3, rerank=reverse_rerank)
    assert {h.chunk_id for h in base.hits} == {h.chunk_id for h in rer.hits}  # membership
    assert [h.chunk_id for h in base.hits] != [h.chunk_id for h in rer.hits]  # order
    idx.close()


# --- U29: per-Hit write-recency (engine-only; no ranking change) --------------

def test_hit_recency_orders_recent_above_old(make_corpus, fake_embedder):
    repo = make_corpus({"seed.md": "# Seed\n\nseed body.\n"})
    _commit_dated(repo, "old.md", "# Old\n\nRECENCYMARKER older note.\n", "2020-01-01T00:00:00")
    _commit_dated(repo, "new.md", "# New\n\nRECENCYMARKER newer note.\n", "2026-01-01T00:00:00")
    idx = index.build_index(repo, fake_embedder)
    rfn = retrieve.git_commit_recency(repo)
    res = retrieve.search(idx, "RECENCYMARKER", embedder=fake_embedder, k=10, recency_fn=rfn)
    by_path = {h.path: h.recency for h in res.hits}
    assert by_path.get("old.md") is not None and by_path.get("new.md") is not None
    assert by_path["new.md"] > by_path["old.md"]            # more-recent commit → larger epoch
    idx.close()


def test_hit_recency_is_none_without_recency_fn(make_corpus, fake_embedder):
    idx = _idx(make_corpus, fake_embedder)
    res = retrieve.search(idx, "Hetzner", embedder=fake_embedder, k=3)   # no recency_fn
    assert res.hits and all(h.recency is None for h in res.hits)         # None-safe default
    idx.close()


def test_hit_recency_none_for_untracked_path(make_corpus, fake_embedder):
    # an indexed-but-uncommitted path (overlay) has no commit metadata → recency None,
    # and a result is still produced (absent-safe).
    repo = make_corpus({"a.md": "# A\n\nUNTRACKEDMARKER committed.\n"})
    idx = index.build_index(repo, fake_embedder)
    from hypermnesic import ingest
    idx.upsert_lexical("ghost.md",
                       ingest.chunks_for_text("ghost.md", "# Ghost\n\nUNTRACKEDMARKER overlay.\n"))
    rfn = retrieve.git_commit_recency(repo)
    res = retrieve.search(idx, "UNTRACKEDMARKER", embedder=fake_embedder, k=10, recency_fn=rfn)
    by_path = {h.path: h.recency for h in res.hits}
    assert "ghost.md" in by_path and by_path["ghost.md"] is None          # no commit → None
    idx.close()


def test_recency_uses_a_single_git_pass_not_one_per_hit(make_corpus, fake_embedder, monkeypatch):
    # Perf guard (review #1): the path→time map is built in ONE git log, regardless of
    # how many hits the search returns — not one `git log` subprocess per hit path.
    repo = make_corpus({"a.md": "# A\n\nMARK alpha.\n", "b.md": "# B\n\nMARK beta.\n",
                        "c.md": "# C\n\nMARK gamma.\n", "d.md": "# D\n\nMARK delta.\n"})
    idx = index.build_index(repo, fake_embedder)
    calls = {"log": 0}
    orig = retrieve.subprocess.run

    def counting(cmd, *a, **k):
        if isinstance(cmd, (list, tuple)) and "log" in cmd:
            calls["log"] += 1
        return orig(cmd, *a, **k)

    monkeypatch.setattr(retrieve.subprocess, "run", counting)
    rfn = retrieve.git_commit_recency(repo)
    res = retrieve.search(idx, "MARK", embedder=fake_embedder, k=10, recency_fn=rfn)
    assert len(res.hits) >= 3
    assert calls["log"] == 1                          # one batched pass, not one-per-hit
    idx.close()


def test_search_exclude_path_omits_note_and_preserves_k(make_corpus, fake_embedder):
    # U42: self-exclusion. The active note must not appear in its own results,
    # and excluding it must NOT shrink the result set below k — the candidate
    # pool (candidate_k=50) absorbs the dropped path.
    repo = make_corpus({
        "a.md": "# A\n\nSHARED topic alpha.\n",
        "b.md": "# B\n\nSHARED topic beta.\n",
        "c.md": "# C\n\nSHARED topic gamma.\n",
        "d.md": "# D\n\nSHARED topic delta.\n",
        "e.md": "# E\n\nSHARED topic epsilon.\n",
    })
    idx = index.build_index(repo, fake_embedder)
    res = retrieve.search(idx, "SHARED topic", embedder=fake_embedder, k=3, exclude_path="a.md")
    paths = [h.path for h in res.hits]
    assert "a.md" not in paths                 # active note excluded
    assert len(res.hits) == 3                   # 5 matches − self = 4 ≥ k, so k preserved
    # default (no exclusion) is byte-for-byte unchanged and can include a.md
    res_all = retrieve.search(idx, "SHARED topic", embedder=fake_embedder, k=5)
    assert "a.md" in [h.path for h in res_all.hits]
    idx.close()


def test_recency_resolves_non_ascii_path(make_corpus, fake_embedder):
    # The batched parse uses core.quotepath=false so non-ASCII paths in the log output match.
    repo = make_corpus({"a.md": "# A\n\nseed.\n"})
    _commit_dated(repo, "notes/café.md", "# Café\n\nACCENTMARK body.\n", "2026-01-01T00:00:00")
    idx = index.build_index(repo, fake_embedder)
    rfn = retrieve.git_commit_recency(repo)
    res = retrieve.search(idx, "ACCENTMARK", embedder=fake_embedder, k=10, recency_fn=rfn)
    by_path = {h.path: h.recency for h in res.hits}
    assert by_path.get("notes/café.md") is not None       # non-ASCII path resolved, not dropped
    idx.close()
