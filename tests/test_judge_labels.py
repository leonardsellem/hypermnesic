"""LLM-as-judge labeling: judging mechanics with a fake (system-blind) judge."""

from __future__ import annotations

import judge_labels as jl

from hypermnesic import index

CORPUS = {
    "rel1.md": "# R1\n\nwidget assembly throughput improvements and retooling.\n",
    "rel2.md": "# R2\n\nmore on widget assembly line throughput metrics.\n",
    "irrel.md": "# X\n\na cooking recipe for pancakes, unrelated.\n",
}


def test_judge_query_maps_indices_to_paths():
    cands = [("a.md", "ex a"), ("b.md", "ex b"), ("c.md", "ex c")]

    def fake_judge(query, excerpts):
        assert len(excerpts) == 3          # judge sees content, not paths/ranks
        return [1, 3]

    assert jl.judge_query("q", cands, fake_judge) == ["a.md", "c.md"]


def test_judge_query_ignores_out_of_range_indices():
    cands = [("a.md", "x")]
    assert jl.judge_query("q", cands, lambda q, e: [1, 5, 0]) == ["a.md"]


def test_build_labels_pools_both_sides_and_judges_content(make_corpus, fake_embedder):
    repo = make_corpus(CORPUS)
    idx = index.build_index(repo, fake_embedder)
    queries = [{"id": "q01", "lang": "en", "query": "widget assembly throughput",
                "relevant": ["rel1.md"], "relevant_primary": "rel1.md"}]
    baseline = {"q01": ["rel2.md", "irrel.md"]}

    # content-based fake judge: relevant iff excerpt mentions "widget"
    def fake_judge(query, excerpts):
        return [i + 1 for i, e in enumerate(excerpts) if "widget" in e.lower()]

    updated, report = jl.build_labels(queries, baseline, idx, fake_embedder, repo,
                                      fake_judge, k=10)
    rel = set(updated[0]["relevant"])
    assert rel == {"rel1.md", "rel2.md"}          # both widget docs judged relevant
    assert "irrel.md" not in rel                   # cooking doc rejected
    assert updated[0]["method"] == "llm-judged-pooled-system-blind"
    idx.close()


def test_build_labels_keeps_primary_when_judge_empty(make_corpus, fake_embedder):
    repo = make_corpus(CORPUS)
    idx = index.build_index(repo, fake_embedder)
    queries = [{"id": "q01", "query": "widget", "relevant": ["rel1.md"],
                "relevant_primary": "rel1.md"}]
    updated, _ = jl.build_labels(queries, {"q01": []}, idx, fake_embedder, repo,
                                 lambda q, e: [], k=10)
    assert updated[0]["relevant"] == ["rel1.md"]   # safety: not wiped
    idx.close()


def test_codex_agent_message_extraction_and_parse():
    jsonl = (
        '{"type":"thread.started","thread_id":"x"}\n'
        '{"type":"item.completed","item":{"type":"error","message":"ignoring foo"}}\n'
        '{"type":"item.completed","item":{"type":"agent_message","text":"[1, 3]"}}\n'
        '{"type":"turn.completed","usage":{}}\n'
        "not json\n"
    )
    msg = jl._codex_agent_message(jsonl)
    assert msg == "[1, 3]"
    assert jl._parse_indices(msg) == [1, 3]


def test_parse_indices_handles_noise_and_empties():
    assert jl._parse_indices("relevant: [2,4] done") == [2, 4]
    assert jl._parse_indices("none") == []
    assert jl._parse_indices("[]") == []


def test_shuffled_is_deterministic_and_source_independent():
    a = jl._shuffled(["z.md", "a.md", "m.md"])
    b = jl._shuffled(["a.md", "m.md", "z.md"])
    assert a == b   # order depends only on path hash, not input order (no source leak)
