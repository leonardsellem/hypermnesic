"""Multi-query expansion output parsing (offline)."""

from __future__ import annotations

from hypermnesic import expand


def test_parse_strips_numbering_dedups_and_caps():
    text = "1. how does X work\n2. X internals\n- how does X work\nwhat is X\n"
    out = expand._parse(text, query="how does X work?", n=2)
    assert out == ["how does X work", "X internals"]  # numbering stripped, capped at 2


def test_parse_drops_echo_of_query():
    out = expand._parse("the original query\na fresh variant", "The Original Query", n=5)
    assert "the original query" not in [s.lower() for s in out]
    assert "a fresh variant" in out


def test_parse_empty_is_empty():
    assert expand._parse("", "q", 3) == []
    assert expand._parse(None, "q", 3) == []
