"""U1 smoke test: the package imports and exposes a version string."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import hypermnesic

_REPO = Path(__file__).resolve().parents[1]
_PRODUCT_SMOKE = _REPO / "scripts" / "product_smoke.py"


def _load_product_smoke():
    spec = importlib.util.spec_from_file_location("product_smoke", _PRODUCT_SMOKE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_package_imports_and_has_version():
    assert isinstance(hypermnesic.__version__, str)
    assert hypermnesic.__version__.count(".") >= 1


def test_cli_help_runs():
    from hypermnesic.cli import main

    assert main([]) == 0


def test_product_smoke_local_loop_passes(tmp_path):
    smoke = _load_product_smoke()
    out = smoke.run_product_smoke(tmp_path)

    assert out["status"] == "pass"
    assert out["degraded_capabilities"] == ["lexical-only"]
    stages = {stage["name"]: stage for stage in out["stages"]}
    for required in (
        "capture",
        "retrieve",
        "write_preview",
        "memory_inspect",
        "forget_preview",
        "recall_after_change",
        "doctor_status",
    ):
        assert stages[required]["status"] == "pass"
    assert out["first_class_loop"] == [
        "capture", "retrieve", "write_preview", "memory_inspect",
        "forget_preview", "recall_after_change", "doctor_status",
    ]
    assert all(not value.startswith("/") for stage in out["stages"]
               for value in stage.get("evidence", {}).values()
               if isinstance(value, str))


def test_product_smoke_failure_stops_and_names_stage(tmp_path):
    smoke = _load_product_smoke()
    out = smoke.run_product_smoke(tmp_path, fail_stage="retrieve")

    assert out["status"] == "fail"
    assert out["failed_stage"] == "retrieve"
    stages = {stage["name"]: stage for stage in out["stages"]}
    assert stages["capture"]["status"] == "pass"
    assert stages["retrieve"]["status"] == "fail"
    assert "write_preview" not in stages


def test_product_smoke_script_json_contract(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(_PRODUCT_SMOKE), "--work-dir", str(tmp_path), "--json"],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["status"] == "pass"
    assert "Local product smoke passed" not in proc.stdout
    assert str(tmp_path) not in proc.stdout
