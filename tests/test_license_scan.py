"""U6 (R9) — the license gate is dependency-scoped.

It excludes the project's OWN distribution before classifying, so flipping
hypermnesic's own license to AGPL-3.0 (the planned public license) does not trip
the gate — while a real AGPL/GPL/SSPL *dependency* is still rejected. Without this
self-exclusion, ``uv sync`` (which installs the root project into the env) would make
the gate reject the engine's own AGPL license the moment the flip lands.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "license_scan.py"


def _load():
    spec = importlib.util.spec_from_file_location("license_scan", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ls = _load()


def test_real_env_scan_passes():
    # The actual resolved environment stays copyleft-free.
    assert ls.scan()["passed"] is True


def test_project_name_reads_pyproject_authority():
    assert ls.project_name() == "hypermnesic"


def test_project_own_agpl_license_is_excluded_not_denied():
    # Regression: with the project's own license set to AGPL-3.0-only, the scan still
    # passes — the project's own dist is excluded; deps are unaffected.
    rows = [
        {"name": "hypermnesic", "version": "0.0.5", "license": "AGPL-3.0-only"},
        {"name": "openai", "version": "2.0", "license": "Apache-2.0"},
    ]
    res = ls.scan(rows=rows, self_name="hypermnesic")
    assert res["passed"] is True
    assert any(r["name"] == "hypermnesic" for r in res["self_excluded"])
    assert res["denied"] == []


def test_real_agpl_dependency_is_still_denied():
    # Guard: the self-exclusion keys on the project name only — it must not weaken the
    # dependency gate. A planted AGPL *dependency* is still rejected.
    rows = [
        {"name": "hypermnesic", "version": "0.0.5", "license": "AGPL-3.0-only"},
        {"name": "some-agpl-dep", "version": "1.0", "license": "AGPL-3.0-or-later"},
    ]
    res = ls.scan(rows=rows, self_name="hypermnesic")
    assert res["passed"] is False
    assert any(d["name"] == "some-agpl-dep" and d["reason"] == "AGPL" for d in res["denied"])


def test_gpl_and_sspl_dependencies_still_denied():
    rows = [
        {"name": "gpl-dep", "version": "1", "license": "GPL-3.0-only"},
        {"name": "sspl-dep", "version": "1", "license": "SSPL-1.0"},
    ]
    res = ls.scan(rows=rows, self_name="hypermnesic")
    reasons = {d["name"]: d["reason"] for d in res["denied"]}
    assert reasons["gpl-dep"] == "GPL" and reasons["sspl-dep"] == "SSPL"


def test_exclusion_keys_on_project_name_normalized():
    # Edge: the exclusion uses PEP 503 normalization, not a brittle exact string —
    # 'Hypermnesic' / 'hyper_mnesic' normalize-match the authority name.
    rows = [{"name": "Hypermnesic", "version": "0.0.5", "license": "AGPL-3.0-only"}]
    res = ls.scan(rows=rows, self_name="hypermnesic")
    assert res["passed"] is True and len(res["self_excluded"]) == 1


def test_lgpl_dependency_is_informational_not_denied():
    rows = [{"name": "lgpl-dep", "version": "1", "license": "LGPL-3.0-only"}]
    res = ls.scan(rows=rows, self_name="hypermnesic")
    assert res["passed"] is True
    assert any(r["name"] == "lgpl-dep" for r in res["lgpl_informational"])
