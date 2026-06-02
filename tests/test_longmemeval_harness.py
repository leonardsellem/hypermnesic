"""LongMemEval V1 benchmark harness — offline tests + CI smoke (U5).

The whole Phase 1 pipeline (manifest → materialize → index/retrieve → diagnostic)
and the Phase 2 reader/judge/QA logic are exercised here with a ``FakeEmbedder``
and injected fake reader/judge callables — **no network, no API key, no spend**.
The committed CI ``pytest`` job runs this file; the paid 500-Q headline run is a
deliberate, manual step that lives outside CI (see ``harness/BENCHMARKS.md``).

``harness/`` is on ``sys.path`` (see ``conftest.py``), so the subpackage imports
as ``longmemeval`` by stem.
"""

from __future__ import annotations

import hashlib
import io
import json

import pytest
from longmemeval import manifest as mf

# ---------------------------------------------------------------------------
# U1 — dataset acquisition + reproducibility manifest
# ---------------------------------------------------------------------------

_REQUIRED_PINS = (
    "dataset_url", "dataset_sha256", "dataset_release", "dataset_variant",
    "embed_model", "embed_dim", "reader_models", "judge_model", "retrieval",
    "prompt_template_version", "seed", "phase1_embedding_cost_ceiling_usd",
)


def test_manifest_round_trips_with_all_required_pins():
    m = mf.default_manifest()
    d = m.to_dict()
    for pin in _REQUIRED_PINS:
        assert pin in d, f"manifest missing required pin: {pin}"
    # retrieval params carry k + fusion weights + lanes (R14/R19)
    assert "k" in d["retrieval"]
    assert "weights" in d["retrieval"] and len(d["retrieval"]["weights"]) == 3
    assert "use_doc_lane" in d["retrieval"]
    # round-trip through JSON is lossless
    parsed = mf.Manifest.from_json(m.to_json())
    assert parsed.to_dict() == d


def test_manifest_pins_production_embedding_config():
    # R12: the embedding stays the production config, not a benchmark-only embed.
    from hypermnesic import config

    m = mf.default_manifest()
    assert m.embed_model == config.EMBED_MODEL
    assert m.embed_dim == config.EMBED_DIM


def test_manifest_pins_both_reader_columns_and_the_canonical_judge():
    # Dual reader columns (GPT-4.1 lead + GPT-4o anchor) + cheap dev reader; the
    # judge is the canonical gpt-4o-2024-08-06 (R10/R11 + dual-column decision).
    m = mf.default_manifest()
    assert "gpt-4.1-2025-04-14" in m.reader_models
    assert "gpt-4o-2024-08-06" in m.reader_models
    assert m.judge_model == "gpt-4o-2024-08-06"


def test_manifest_records_phase1_cost_ceiling_from_explicit_assumptions():
    # The ceiling is a recorded number derived from stated assumptions, not a
    # magic constant (U1: "a recorded ceiling, not an assumption").
    m = mf.default_manifest()
    assert m.phase1_embedding_cost_ceiling_usd > 0
    d = m.to_dict()
    assert "cost_assumptions" in d
    for key in ("n_instances", "tokens_per_instance", "n_corpora",
                "price_per_million_tokens_usd"):
        assert key in d["cost_assumptions"]


def test_manifest_never_contains_the_api_key(monkeypatch):
    # Credential discipline: the key must never enter committed output.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRET-SENTINEL-must-not-leak")
    m = mf.default_manifest()
    blob = m.to_json()
    assert "sk-SECRET-SENTINEL-must-not-leak" not in blob
    assert "SECRET" not in blob


def test_download_verifies_sha256_and_writes_corpus(tmp_path):
    payload = b'{"question_id": "q1", "haystack_sessions": []}'
    digest = hashlib.sha256(payload).hexdigest()
    dest = tmp_path / "longmemeval_s_cleaned.json"

    res = mf.download_dataset(
        dest, url="https://example.invalid/ds.json", expected_sha256=digest,
        opener=lambda url: io.BytesIO(payload),
    )
    assert res.verified is True
    assert res.sha256 == digest
    assert dest.exists()
    assert dest.read_bytes() == payload


def test_download_hash_mismatch_raises_and_writes_no_corpus(tmp_path):
    payload = b"tampered or short download"
    dest = tmp_path / "longmemeval_s_cleaned.json"

    with pytest.raises(mf.DatasetIntegrityError):
        mf.download_dataset(
            dest, url="https://example.invalid/ds.json",
            expected_sha256="0" * 64,  # wrong hash
            opener=lambda url: io.BytesIO(payload),
        )
    assert not dest.exists()  # a mismatched download leaves no corpus behind


def test_download_capture_mode_reports_unverified_hash(tmp_path):
    # Before the real hash is pinned, capture mode computes + reports it but does
    # NOT certify the corpus as verified (a headline run requires a pinned hash).
    payload = b"freshly fetched, not yet pinned"
    dest = tmp_path / "ds.json"
    res = mf.download_dataset(
        dest, url="https://example.invalid/ds.json", expected_sha256="",
        opener=lambda url: io.BytesIO(payload),
    )
    assert res.verified is False
    assert res.sha256 == hashlib.sha256(payload).hexdigest()
    assert dest.exists()


# ---------------------------------------------------------------------------
# U2 — deterministic session→markdown materializer + gold reconstruction
# ---------------------------------------------------------------------------

from longmemeval import materialize as mat  # noqa: E402

from hypermnesic import index  # noqa: E402


def _instance(question_id="q1", question_type="single-session-user",
              answer_sessions=("s_answer",)):
    """A 3-session instance with exactly one evidence session (``s_answer``).

    The evidence session's single user turn carries ``has_answer: true``; the
    other two sessions are distractors.
    """
    return {
        "question_id": question_id,
        "question_type": question_type,
        "question": "What is my dog's name?",
        "answer": "Rex",
        "question_date": "2023-06-01",
        "haystack_session_ids": ["s_intro", "s_answer", "s_filler"],
        "haystack_dates": ["2023-05-01", "2023-05-20", "2023-05-25"],
        "haystack_sessions": [
            [{"role": "user", "content": "Hi there"},
             {"role": "assistant", "content": "Hello!"}],
            [{"role": "user", "content": "My dog Rex loves long walks", "has_answer": True},
             {"role": "assistant", "content": "Rex sounds lovely."}],
            [{"role": "user", "content": "What's the weather"},
             {"role": "assistant", "content": "Sunny"}],
        ],
        "answer_session_ids": list(answer_sessions),
    }


def test_parse_instance_fields_and_abstention_flag():
    inst = mat.parse_instance(_instance())
    assert inst.question_type == "single-session-user"
    assert len(inst.sessions) == 3
    assert inst.sessions[1].session_id == "s_answer"
    assert inst.sessions[1].date == "2023-05-20"
    assert inst.sessions[1].turns[0].has_answer is True
    assert inst.is_abstention is False
    assert mat.parse_instance(_instance(question_id="q9_abs")).is_abstention is True


def test_materialize_sessions_yields_per_session_files_verbatim_and_gold(tmp_path):
    inst = mat.parse_instance(_instance())
    m = mat.materialize_sessions(inst, tmp_path / "sessions")
    md_files = sorted((tmp_path / "sessions").glob("*.md"))
    assert len(md_files) == 3  # one file per session
    assert m.granularity == "session"
    assert m.gold_units == {"s_answer"}  # session-level gold from answer_session_ids
    assert set(m.path_to_unit.values()) == {"s_intro", "s_answer", "s_filler"}
    # verbatim content (R4) — the user's words are copied as-is, no summarization
    bodies = "\n".join(p.read_text(encoding="utf-8") for p in md_files)
    assert "My dog Rex loves long walks" in bodies
    assert "**user:**" in bodies and "**assistant:**" in bodies


def test_materialize_turns_yields_per_user_turn_files_and_turn_gold(tmp_path):
    inst = mat.parse_instance(_instance())
    m = mat.materialize_turns(inst, tmp_path / "turns")
    assert m.granularity == "turn"
    # one round per user turn; each session here has exactly one user turn → 3 rounds
    assert len(m.path_to_unit) == 3
    assert m.gold_units == {"s_answer_turn0"}  # the evidence round
    # turn→session derivation recovers the parent session (suffix-stripping)
    assert mat.turn_to_session("s_answer_turn0") == "s_answer"
    assert all(mat.turn_to_session(t) in {"s_intro", "s_answer", "s_filler"}
               for t in m.path_to_unit.values())


def test_rematerialize_is_byte_identical(tmp_path):
    # Determinism (R5): same instance → byte-identical files (names + bytes).
    inst = mat.parse_instance(_instance())
    mat.materialize_sessions(inst, tmp_path / "a")
    mat.materialize_sessions(inst, tmp_path / "b")
    a = {p.name: p.read_bytes() for p in (tmp_path / "a").glob("*.md")}
    b = {p.name: p.read_bytes() for p in (tmp_path / "b").glob("*.md")}
    assert a == b and len(a) == 3


def test_session_date_is_in_body_and_survives_indexing(tmp_path, fake_embedder):
    # R6: the session date lives in the body (not frontmatter, which
    # ingest.strip_frontmatter removes), so it survives into the index.
    inst = mat.parse_instance(_instance())
    corpus = tmp_path / "sessions"
    mat.materialize_sessions(inst, corpus)
    idx = index.build_index(corpus, fake_embedder)
    indexed = " ".join(c["text"] for c in idx.all_chunks())
    idx.close()
    assert "2023-05-20" in indexed  # the evidence session's date is indexed


def test_abstention_instance_carries_no_retrieval_gold(tmp_path):
    # Covers AE1: an `_abs` instance is flagged abstention and has no retrieval
    # gold at either granularity (it is scored in the abstention bucket, not here).
    inst = mat.parse_instance(_instance(question_id="q9_abs"))
    assert inst.is_abstention is True
    ms = mat.materialize_sessions(inst, tmp_path / "s")
    mt = mat.materialize_turns(inst, tmp_path / "t")
    assert ms.gold_units == set()
    assert mt.gold_units == set()


# ---------------------------------------------------------------------------
# U3 — per-haystack index + retrieval adapter (+ content-hash embedding cache)
# ---------------------------------------------------------------------------

from longmemeval import adapter  # noqa: E402

from hypermnesic import embed as embed_mod  # noqa: E402
from hypermnesic.config import EMBED_DIM  # noqa: E402


class _CountingEmbedder:
    """Wraps an embedder and counts how many texts it is asked to embed."""

    def __init__(self, inner):
        self._inner = inner
        self.dim = inner.dim
        self.model = getattr(inner, "model", "counting")
        self.n_embedded = 0

    def embed(self, texts):
        self.n_embedded += len(texts)
        return self._inner.embed(texts)


class _DownEmbedder:
    """An embedder whose API is down — every embed call fails (R20/AE2)."""

    dim = EMBED_DIM
    model = "down"

    def embed(self, texts):
        raise embed_mod.EmbeddingError("API down")


def _other_instance():
    return mat.parse_instance({
        "question_id": "q2",
        "question_type": "multi-session",
        "question": "Which city did I move to?",
        "answer": "Berlin",
        "question_date": "2023-07-01",
        "haystack_session_ids": ["x_alpha", "x_answer"],
        "haystack_dates": ["2023-06-10", "2023-06-15"],
        "haystack_sessions": [
            [{"role": "user", "content": "Planning a relocation"},
             {"role": "assistant", "content": "Exciting!"}],
            [{"role": "user", "content": "I moved to Berlin last week", "has_answer": True},
             {"role": "assistant", "content": "Welcome to Berlin."}],
        ],
        "answer_session_ids": ["x_answer"],
    })


def test_retrieve_for_corpus_maps_hits_to_unit_ids(tmp_path, fake_embedder):
    inst = mat.parse_instance(_instance())
    m = mat.materialize_sessions(inst, tmp_path / "corpus")
    r = adapter.retrieve_for_corpus(m, inst.question, fake_embedder, state_dir=tmp_path / "st")
    assert r.degraded is False
    assert r.ranked_units  # the index answered with at least one hit
    assert set(r.ranked_units) <= {"s_intro", "s_answer", "s_filler"}
    # turn granularity maps to turn ids too
    mt = mat.materialize_turns(inst, tmp_path / "turns")
    rt = adapter.retrieve_for_corpus(mt, inst.question, fake_embedder, state_dir=tmp_path / "stt")
    assert set(rt.ranked_units) <= set(mt.path_to_unit.values())


def test_per_haystack_isolation_no_cross_instance_leak(tmp_path, fake_embedder):
    a, b = mat.parse_instance(_instance()), _other_instance()
    ma = mat.materialize_sessions(a, tmp_path / "A")
    mb = mat.materialize_sessions(b, tmp_path / "B")
    ra = adapter.retrieve_for_corpus(ma, a.question, fake_embedder, state_dir=tmp_path / "sa")
    rb = adapter.retrieve_for_corpus(mb, b.question, fake_embedder, state_dir=tmp_path / "sb")
    assert set(ra.ranked_units) <= {"s_intro", "s_answer", "s_filler"}
    assert set(rb.ranked_units) <= {"x_alpha", "x_answer"}
    assert not (set(ra.ranked_units) & set(rb.ranked_units))  # no leakage


def test_state_dir_lives_outside_corpus_which_is_unmodified(tmp_path, fake_embedder):
    inst = mat.parse_instance(_instance())
    corpus = tmp_path / "corpus"
    m = mat.materialize_sessions(inst, corpus)
    before = {p.name: p.read_bytes() for p in corpus.glob("*.md")}
    state = tmp_path / "state"
    adapter.retrieve_for_corpus(m, inst.question, fake_embedder, state_dir=state)
    after = {p.name: p.read_bytes() for p in corpus.glob("*.md")}
    assert before == after  # corpus tree untouched
    assert not (corpus / ".hypermnesic").exists()  # state dir is external
    assert (state / "index.db").exists()


def test_degraded_embedder_voids_the_run(tmp_path):
    # Covers AE2: when embeddings are unavailable, the run is voided, not scored.
    inst = mat.parse_instance(_instance())
    run = adapter.retrieve_instances([inst], tmp_path / "work", _DownEmbedder())
    assert run.void is True
    # a void run produces no scorable ranking
    assert all(res.session.degraded and res.turn.degraded for res in run.results)


def test_healthy_run_is_not_void(tmp_path, fake_embedder):
    inst = mat.parse_instance(_instance())
    run = adapter.retrieve_instances([inst], tmp_path / "work", fake_embedder)
    assert run.void is False
    assert len(run.results) == 1
    assert run.results[0].session.granularity == "session"
    assert run.results[0].turn.granularity == "turn"


def test_embedding_cache_avoids_re_embedding_identical_content(tmp_path, fake_embedder):
    # The content-hash cache (R12/R19 cost mitigation): a re-run over identical
    # chunk text issues no duplicate embed calls to the underlying embedder.
    counter = _CountingEmbedder(fake_embedder)
    cached = adapter.CachingEmbedder(counter)
    inst = mat.parse_instance(_instance())
    m = mat.materialize_sessions(inst, tmp_path / "corpus")
    r1 = adapter.retrieve_for_corpus(m, inst.question, cached, state_dir=tmp_path / "s1")
    first = counter.n_embedded
    assert first > 0
    r2 = adapter.retrieve_for_corpus(m, inst.question, cached, state_dir=tmp_path / "s2")
    assert counter.n_embedded == first  # nothing re-embedded on the re-run
    assert r1.ranked_units == r2.ranked_units


def test_sqlite_embedding_cache_round_trips(tmp_path, fake_embedder):
    store = adapter.SqliteEmbeddingCache(tmp_path / "cache.sqlite")
    cached = adapter.CachingEmbedder(fake_embedder, store=store)
    [v1] = cached.embed(["hello world"])
    assert "hello world" not in store  # store is keyed by content hash, not raw text
    [v2] = cached.embed(["hello world"])  # second call served from the store
    assert v1 == v2 and len(v1) == EMBED_DIM
    store.close()
    # a fresh store over the same file still holds the vector (persistence)
    reopened = adapter.SqliteEmbeddingCache(tmp_path / "cache.sqlite")
    assert reopened._count() >= 1
    reopened.close()


# ---------------------------------------------------------------------------
# U4 — retrieval diagnostic scorer (session + turn level)
# ---------------------------------------------------------------------------

from longmemeval import diagnostic as diag  # noqa: E402


def _hr(gran, ranked, gold):
    return adapter.HaystackResult("iid", gran, list(ranked), False, set(gold))


def _ir(inst_dict, *, session_ranked, session_gold, turn_ranked, turn_gold):
    inst = mat.parse_instance(inst_dict)
    return adapter.InstanceRetrieval(
        inst, _hr("session", session_ranked, session_gold),
        _hr("turn", turn_ranked, turn_gold))


def test_recall_all_requires_every_gold_in_topk():
    assert diag.recall_all_at_k(["a", "b", "c"], {"a", "b"}, 5) == 1.0
    assert diag.recall_all_at_k(["a", "x", "y"], {"a", "b"}, 5) == 0.0  # b missing
    assert diag.recall_all_at_k(["a", "b"], {"a", "b"}, 1) == 0.0       # b outside top-1


def test_recall_any_is_at_least_one_in_topk():
    assert diag.recall_any_at_k(["a", "x"], {"a", "b"}, 5) == 1.0
    assert diag.recall_any_at_k(["x", "y"], {"a", "b"}, 5) == 0.0


def test_recall_all_and_any_diverge_on_partial_gold():
    # Distinct metrics: only some gold present → recall_all 0, recall_any 1.
    ranked, gold = ["a", "x", "y"], {"a", "b"}
    assert diag.recall_all_at_k(ranked, gold, 5) == 0.0
    assert diag.recall_any_at_k(ranked, gold, 5) == 1.0


def test_ndcg_any_rewards_higher_rank_and_is_perfect_on_top():
    assert diag.ndcg_any_at_k(["g", "x", "y"], {"g"}, 5) == 1.0
    low = diag.ndcg_any_at_k(["x", "y", "g"], {"g"}, 5)
    assert 0.0 < low < 1.0
    assert diag.ndcg_any_at_k(["a", "b", "x"], {"a", "b"}, 5) == 1.0  # all gold on top


def test_score_excludes_abstention_from_retrieval_aggregates():
    # Edge: `_abs` instances are excluded from retrieval aggregates.
    run = adapter.RetrievalRun(results=[
        _ir(_instance(question_id="q1"),
            session_ranked=["s_answer"], session_gold={"s_answer"},
            turn_ranked=["s_answer_turn0"], turn_gold={"s_answer_turn0"}),
        _ir(_instance(question_id="q2_abs"),
            session_ranked=[], session_gold=set(),
            turn_ranked=[], turn_gold=set()),
    ])
    out = diag.score_diagnostic(run)
    assert out["void"] is False and out["verdict"] == "reported"
    assert out["n_instances"] == 1
    assert out["n_excluded_abstention"] == 1
    assert out["session"]["recall_all@5"] == 1.0
    assert out["session"]["recall_all@10"] == 1.0


def test_void_run_reports_no_numbers():
    # Covers AE2 at the scoring boundary: a void run yields no metrics.
    run = adapter.RetrievalRun(results=[], void=True)
    out = diag.score_diagnostic(run)
    assert out["void"] is True
    assert out["verdict"] == "void"
    assert "session" not in out


def test_turn_ranking_derives_session_recall():
    # Edge: turn→session derivation. The session ranking misses the gold session,
    # but the turn ranking holds the evidence round → derived session recall = 1.0.
    run = adapter.RetrievalRun(results=[
        _ir(_instance(),
            session_ranked=["s_intro"], session_gold={"s_answer"},
            turn_ranked=["s_answer_turn0", "s_intro_turn0"], turn_gold={"s_answer_turn0"}),
    ])
    out = diag.score_diagnostic(run)
    assert out["session"]["recall_all@5"] == 0.0
    assert out["turn_derived_session"]["recall_all@5"] == 1.0


def test_date_sensitive_abilities_report_recall_any_and_gold_size():
    # Edge: knowledge-update / temporal-reasoning report recall_any@k beside
    # recall_all@k plus the gold-set-size distribution, so a low recall_all reads
    # as date-blind ranking / metric strictness, not a genuine miss.
    run = adapter.RetrievalRun(results=[
        _ir(_instance(question_id="q1", question_type="knowledge-update"),
            session_ranked=["s_answer", "s_intro"], session_gold={"s_answer", "s_filler"},
            turn_ranked=["s_answer_turn0"], turn_gold={"s_answer_turn0"}),
        _ir(_instance(question_id="q2", question_type="single-session-user"),
            session_ranked=["s_answer"], session_gold={"s_answer"},
            turn_ranked=["s_answer_turn0"], turn_gold={"s_answer_turn0"}),
    ])
    out = diag.score_diagnostic(run)
    ku = out["per_ability"]["knowledge-update"]
    assert ku["session"]["recall_all@5"] == 0.0           # s_filler missing → strict miss
    assert ku["recall_any"]["session"]["recall_any@5"] == 1.0  # but s_answer was found
    assert ku["gold_set_size"]["mean"] == 2
    assert ku["date_sensitive"] is True
    assert out["per_ability"]["single-session-user"]["date_sensitive"] is False


def test_load_dataset_parses_instance_list(tmp_path):
    ds = tmp_path / "ds.json"
    ds.write_text(json.dumps([_instance(question_id="q1"), _instance(question_id="q2_abs")]),
                  encoding="utf-8")
    insts = mat.load_dataset(ds)
    assert [i.question_id for i in insts] == ["q1", "q2_abs"]
    assert insts[1].is_abstention is True


# ---------------------------------------------------------------------------
# U5 — offline pipeline tests + CI smoke subset
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

SMOKE_PATH = Path(__file__).resolve().parents[1] / "harness/longmemeval/smoke.example.jsonl"


def _smoke_rows():
    return [json.loads(line) for line in
            SMOKE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_smoke_subset_spans_five_abilities_and_is_synthetic():
    rows = _smoke_rows()
    types = {r["question_type"] for r in rows}
    # 4 retrieval abilities + abstention = the 5 V1 abilities
    assert {"single-session-user", "multi-session", "knowledge-update",
            "temporal-reasoning"} <= types
    assert any(r["question_id"].endswith("_abs") for r in rows)  # abstention
    # synthetic guard: committed smoke data must never look like a real corpus
    blob = SMOKE_PATH.read_text(encoding="utf-8")
    assert "@" not in blob and "/home/" not in blob and "/Users/" not in blob


def test_full_phase1_pipeline_runs_offline_on_smoke_set(tmp_path, fake_embedder):
    # Happy path: the whole Phase-1 pipeline (materialize → index → retrieve →
    # score) runs end-to-end on the synthetic set with FakeEmbedder, no key.
    instances = [mat.parse_instance(r) for r in _smoke_rows()]
    result = diag.run_diagnostic(instances, tmp_path / "work", fake_embedder, headline=False)
    assert result["void"] is False
    assert "session" in result and "turn" in result
    n_non_abs = sum(1 for r in _smoke_rows() if not r["question_id"].endswith("_abs"))
    assert result["n_instances"] == n_non_abs
    for ability in ("single-session-user", "multi-session",
                    "knowledge-update", "temporal-reasoning"):
        assert ability in result["per_ability"]


def test_smoke_run_is_labeled_non_headline(tmp_path, fake_embedder):
    # Covers AE4: a subset run is labeled non-headline and is never the headline.
    instances = [mat.parse_instance(r) for r in _smoke_rows()]
    result = diag.run_diagnostic(instances, tmp_path / "work", fake_embedder, headline=False)
    assert result["headline"] is False
    assert result["n_instances_total"] == len(instances)
    assert result["n_instances_total"] < 500  # the smoke set is not the full `_s` set


def test_abstention_scored_in_its_own_bucket_not_folded(tmp_path, fake_embedder):
    # Covers AE1: the abstention instance is counted separately and excluded from
    # the retrieval aggregates (never folded into another ability).
    instances = [mat.parse_instance(r) for r in _smoke_rows()]
    result = diag.run_diagnostic(instances, tmp_path / "work", fake_embedder, headline=False)
    assert result["n_excluded_abstention"] == 1
    # the abstention instance's question_type bucket must not absorb it as scorable
    abst = next(r for r in _smoke_rows() if r["question_id"].endswith("_abs"))
    bucket = result["per_ability"].get(abst["question_type"])
    n_real_in_bucket = sum(1 for r in _smoke_rows()
                           if r["question_type"] == abst["question_type"]
                           and not r["question_id"].endswith("_abs"))
    assert (bucket["n"] if bucket else 0) == n_real_in_bucket


def test_smoke_run_voids_on_degraded_embedder(tmp_path):
    # Covers AE2: a degraded embedder voids the whole run rather than scoring.
    instances = [mat.parse_instance(r) for r in _smoke_rows()]
    result = diag.run_diagnostic(instances, tmp_path / "work", _DownEmbedder(), headline=False)
    assert result["void"] is True
    assert result["verdict"] == "void"
