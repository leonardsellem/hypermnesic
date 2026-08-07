"""The release job builds GitHub release notes from CHANGELOG.md.

If this extractor silently returns the wrong slice, a release ships with someone
else's notes — so the failure modes that matter are "picked the wrong section"
and "returned nothing", not formatting.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "changelog_section.py"


def _load():
    spec = importlib.util.spec_from_file_location("changelog_section", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cs = _load()

_SAMPLE = """# Changelog

Preamble that must never leak into release notes.

## [Unreleased]

### Added
- Something not yet shipped.

## [0.2.0] - 2026-08-06

### Added
- The new thing.

### Fixed
- The broken thing.

## [0.1.0] - 2026-06-14

### Added
- The first thing.

[Unreleased]: https://example.com/compare/v0.2.0...HEAD
[0.2.0]: https://example.com/compare/v0.1.0...v0.2.0
"""


def test_extracts_only_the_requested_version():
    out = cs.section(_SAMPLE, "0.2.0")
    assert "The new thing." in out
    assert "The broken thing." in out
    assert "Something not yet shipped." not in out   # no bleed from [Unreleased]
    assert "The first thing." not in out             # no bleed from the older release
    assert "Preamble" not in out


def test_heading_itself_is_not_repeated_in_the_body():
    out = cs.section(_SAMPLE, "0.2.0")
    assert not out.startswith("## [0.2.0]")


def test_link_reference_footer_is_excluded():
    out = cs.section(_SAMPLE, "0.2.0")
    assert "https://example.com/compare" not in out


def test_last_section_stops_at_the_link_footer():
    out = cs.section(_SAMPLE, "0.1.0")
    assert "The first thing." in out
    assert "[Unreleased]:" not in out


def test_accepts_a_v_prefixed_tag():
    assert cs.section(_SAMPLE, "v0.2.0") == cs.section(_SAMPLE, "0.2.0")


def test_missing_version_raises_rather_than_returning_empty():
    with pytest.raises(SystemExit):
        cs.section(_SAMPLE, "9.9.9")


def test_unreleased_is_not_a_releasable_section():
    with pytest.raises(SystemExit):
        cs.section(_SAMPLE, "Unreleased")


def test_real_changelog_has_a_section_for_the_current_version():
    import tomllib
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    out = cs.section((ROOT / "CHANGELOG.md").read_text(), version)
    assert out.strip(), f"CHANGELOG.md has no [{version}] section to release from"
