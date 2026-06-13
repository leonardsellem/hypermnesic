"""U8 first-class readiness docs are release gates, not loose prose."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_remote_client_smoke_checklist_is_operator_runnable():
    text = _text("docs/guides/remote-client-smoke-checklist.md")
    required = [
        "OAuth discovery",
        "read-scoped client",
        "write refusal without write scope",
        "write-scoped client",
        "revocation",
        "ChatGPT",
        "Claude",
        "Claude Code",
        "Codex",
        "Obsidian",
        "https://<your-host>.ts.net/mcp",
        "scripts/<smoke-id>-protected-refusal.md",
        "local absolute paths",
        "private or `/mcp` endpoint URLs",
        "INCONCLUSIVE/FAIL",
        "tests/test_product_remote_smoke.py",
        "scripts/product_smoke.py",
    ]
    for phrase in required:
        assert phrase in text
    assert "Bearer " not in text and "sk-" not in text


def test_first_class_readiness_checklist_requires_current_u1_to_u8_evidence():
    text = _text("docs/launch/first-class-product-readiness-checklist.md")
    required = [
        "U1 Local-first value proof",
        "U2 Setup doctor/status",
        "U3 Memory control center",
        "U4 Consent/client trust",
        "U5 Plugin hook observability",
        "U6 Memory taxonomy/agent guidance",
        "U7 Daily human workflows",
        "U8 Product proof/launch readiness",
        "Command",
        "Expected evidence",
        "Recorded result",
        "Reviewer",
        "Date",
        "Release-blocking",
        "uv run python scripts/product_smoke.py",
        "uv run pytest tests/test_smoke.py tests/test_product_remote_smoke.py",
        "uv run pytest",
        "scripts/preflight_public_scan.py",
    ]
    for phrase in required:
        assert phrase in text
    assert "LongMemEval" in text
    assert "operability" in text
    assert "benchmark" in text.lower()


def test_public_docs_link_readiness_and_separate_benchmarks_from_product_proof():
    readme = _text("README.md")
    docs_index = _text("docs/README.md")
    getting_started = _text("docs/guides/getting-started.md")
    benchmarks = _text("harness/BENCHMARKS.md")

    for text in (readme, docs_index, getting_started):
        assert "remote-client smoke checklist" in text
        assert "first-class product readiness checklist" in text

    assert "LongMemEval measures retrieval quality" in readme
    assert "does not prove setup, consent, memory control, or remote-client operability" in readme
    assert "Product operability proof" in benchmarks
    assert "Benchmark scores are not a substitute for product readiness" in benchmarks
