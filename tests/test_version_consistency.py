"""U1 (R2/R20) — one version authority, every distributed manifest + __init__ agree.

``pyproject.toml`` ``[project].version`` is the source of truth; the in-package
``__version__``, plugin manifests, and citation metadata must match it. A CI step
(``scripts/check_version_consistency.py``) fails the build on drift, naming the
diverging file and both versions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_version_consistency.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_version_consistency", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cvc = _load()


def test_real_tree_is_consistent():
    # Happy path: the authority + every distributed manifest + __init__ agree.
    authority = cvc.authority_version()
    problems = cvc.check(authority, cvc.collect())
    assert problems == [], "version drift:\n" + "\n".join(problems)


def test_main_exits_zero_on_the_real_tree():
    assert cvc.main([]) == 0


def test_collect_covers_init_all_distributed_manifests_and_citation_metadata():
    labels = {label for label, _ in cvc.collect()}
    assert "src/hypermnesic/__init__.py" in labels
    assert "plugin/.claude-plugin/marketplace.json" in labels
    assert "plugin/plugins/hypermnesic/.claude-plugin/plugin.json" in labels
    assert "plugin/plugins/hypermnesic/.codex-plugin/plugin.json" in labels
    assert "plugin/hermes/plugin.yaml" in labels
    assert "docs/launch/CITATION.cff" in labels
    if (ROOT / "CITATION.cff").exists():
        assert "CITATION.cff" in labels


def test_diverging_manifest_is_flagged_with_file_and_both_versions():
    # Failure path: a manifest pinned to a different version fails with a message
    # naming the diverging file and both versions.
    problems = cvc.check("0.0.5", [("plugin/x.json", "0.0.4")])
    assert len(problems) == 1
    assert "plugin/x.json" in problems[0]
    assert "0.0.4" in problems[0] and "0.0.5" in problems[0]


def test_missing_version_key_fails_clearly_not_crash():
    # Edge: a manifest missing the version key fails clearly rather than raising.
    problems = cvc.check("0.0.5", [("plugin/x.json", None)])
    assert len(problems) == 1
    assert "no version" in problems[0].lower()
    assert "plugin/x.json" in problems[0]


def test_authority_version_matches_init_version():
    # The in-package mirror tracks the authority (already synced in #23).
    assert cvc.init_version() == cvc.authority_version()
