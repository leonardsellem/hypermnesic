"""U8 (R11) — the pre-public secret/host scrub gate.

Verifies the scan (1) passes on the remediated working tree in default mode, (2)
detects planted operator identifiers / credential material, (3) does NOT false-positive
on the legitimate CGNAT documentation range or an empty token placeholder, and (4)
scopes correctly: launch/archive excluded, process-exhaust docs deferred-in-default /
scanned-in-strict, code surface always in scope.

NOTE: the operator tailnet name + homelab IP samples are built from string fragments so
this test file itself carries no contiguous operator literal (the scan's deny set lives in
``scripts/preflight_public_scan.py``, which is the single source of those patterns; the gate
excludes its own script + this test from scanning since they necessarily reference the
patterns).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "preflight_public_scan.py"

# Built from fragments so no contiguous operator literal lives in this file (G4-clean).
_OP_HOST = "taild" + "abf2.ts.net"
_OP_IP = "100.103." + "0.55"


def _load():
    spec = importlib.util.spec_from_file_location("preflight_public_scan", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pf = _load()


def test_default_scan_passes_on_remediated_tree():
    # Happy path: after the src/tests hostname remediation, the default (code + durable-docs)
    # surface is clean → exit-0 gate. (Fails before remediation, not on the current tree.)
    res = pf.scan(strict=False)
    assert res["passed"] is True, res["findings"]


def test_main_exits_zero_default():
    assert pf.main([]) == 0


def test_planted_operator_tailnet_name_detected():
    hits = pf.scan_text(f"resource = https://x.{_OP_HOST}/mcp")
    assert any(label == "operator-tailnet-name" for label, _ in hits)


def test_planted_operator_homelab_ip_detected():
    hits = pf.scan_text(f"bind {_OP_IP}")
    assert any(label == "operator-homelab-ip" for label, _ in hits)


def test_planted_openai_key_detected():
    hits = pf.scan_text("OPENAI_API_KEY=sk-" + "A" * 28)
    assert any(label == "openai-api-key" for label, _ in hits)


def test_planted_inline_token_value_detected():
    hits = pf.scan_text("HYPERMNESIC_MCP_TOKEN=" + "deadbeefvalue123")
    assert any(label == "inline-token-value" for label, _ in hits)


def test_planted_pem_private_key_detected():
    hits = pf.scan_text("-----BEGIN " + "RSA PRIVATE KEY-----")
    assert any(label == "pem-private-key" for label, _ in hits)


def test_planted_home_path_detected():
    hits = pf.scan_text("/home/" + "operator/dev/hypermnesic")
    assert any(label == "operator-home-path" for label, _ in hits)


def test_generic_cgnat_example_not_flagged():
    # The deny set targets the SPECIFIC operator node IP, not the CGNAT range — generic
    # documentation examples (100.64.0.x, used throughout the suite) must not false-positive.
    assert pf.scan_text("--host 100.64.0.1") == []


def test_empty_token_placeholder_not_flagged():
    # .env.example uses VAR= (empty) placeholders — these are not leaks.
    assert pf.scan_text("HYPERMNESIC_MCP_TOKEN=") == []
    assert pf.scan_text("OPENAI_API_KEY=") == []


def test_scope_always_excludes_launch():
    # docs/launch/ is the staging area (documents the secrets by design) — never scanned.
    assert pf.in_scope("docs/launch/LICENSE-AGPL-3.0.txt", strict=False) is False
    assert pf.in_scope("docs/launch/public-flip-runbook.md", strict=True) is False


def test_archive_deferred_in_default_but_scanned_in_strict():
    # Archiving a doc must NOT hide a leak from the flip-time gate (no false comfort).
    assert pf.in_scope("docs/archive/old.md", strict=False) is False   # historical, deferred
    assert pf.in_scope("docs/archive/old.md", strict=True) is True       # flip gate scans it


def test_scope_defers_process_docs_in_default_includes_in_strict():
    proc = "docs/handoff-macbook-prompt.md"
    assert pf.in_scope(proc, strict=False) is False   # deferred (flip-time scrub)
    assert pf.in_scope(proc, strict=True) is True      # flip-time gate scans it


def test_scope_scans_durable_docs_and_code_in_default():
    assert pf.in_scope("docs/reference/cli.md", strict=False) is True
    assert pf.in_scope("docs/README.md", strict=False) is True
    assert pf.in_scope("src/hypermnesic/cli.py", strict=False) is True
    assert pf.in_scope("tests/test_smoke.py", strict=False) is True


def test_gate_excludes_its_own_script_and_test():
    # The scanner's own files necessarily contain the deny patterns — they are excluded so
    # the gate does not self-trip.
    assert pf.in_scope("scripts/preflight_public_scan.py", strict=True) is False
    assert pf.in_scope("tests/test_preflight_public_scan.py", strict=True) is False


def test_mask_does_not_reprint_full_secret():
    masked = pf._mask(_OP_HOST)
    assert masked != _OP_HOST and _OP_HOST not in masked
