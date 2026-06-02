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
    monkeypatch.setenv("OPENAI_API_KEY", "REDACTED_TOKEN_2")
    m = mf.default_manifest()
    blob = m.to_json()
    assert "REDACTED_TOKEN_2" not in blob
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
