#!/usr/bin/env python3
"""Transitive license gate for hypermnesic (KTD1 / U1 acceptance criterion).

Scans the *resolved* dependency tree of the active environment and fails on any
strong-copyleft license — **AGPL / GPL / SSPL** — that would reintroduce the
network-service (Affero §13) exposure the permissive-primitives pivot exists to
avoid. LGPL is reported informationally (not in the deny set per the plan), so a
human can still eyeball weak-copyleft deps.

This *verifies* the "permissive" claim rather than asserting it. CI runs it and
fails the build on any deny-set entry.

**Dependency-scoped (R9 / U6).** The gate governs *third-party dependencies*, NOT
hypermnesic's own license. ``uv sync`` installs the root project into the env, so
its own distribution shows up in the scan; it is excluded BEFORE classification
(keyed on ``[project].name`` from ``pyproject.toml``). Without this, flipping the
engine's own license to AGPL-3.0 (the planned public license) would make the gate
reject the project itself — a false failure. The self-exclusion keys on the project
name only, so it never weakens the dependency gate.

Usage::

    uv run python scripts/license_scan.py
    uv run python scripts/license_scan.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Deny set: strong copyleft. Matched against the human license string.
_SSPL_RE = re.compile(r"SSPL|Server Side Public License", re.IGNORECASE)
_AGPL_RE = re.compile(r"AGPL|Affero", re.IGNORECASE)
# "GPL" as a token but never "LGPL" (the L is a preceding letter).
_GPL_TOKEN_RE = re.compile(r"(?<![A-Za-z])A?GPL", re.IGNORECASE)
# Spelled-out GPL, excluding the Lesser/Library variants (LGPL).
_GPL_PHRASE_RE = re.compile(
    r"(?<!Lesser )(?<!Library )General Public License", re.IGNORECASE
)
_LGPL_RE = re.compile(r"LGPL|Lesser General Public License|Library General Public License",
                      re.IGNORECASE)


def classify(license_str: str) -> str | None:
    """Return a deny-reason label if the license is strong copyleft, else None."""
    s = (license_str or "").strip()
    if not s or s.upper() in {"UNKNOWN", "NONE"}:
        return None
    if _SSPL_RE.search(s):
        return "SSPL"
    if _AGPL_RE.search(s):
        return "AGPL"
    # LGPL is weak copyleft and allowed; strip it before the GPL check so the
    # GPL token/phrase matchers don't false-positive on "LGPL".
    without_lgpl = _LGPL_RE.sub("", s)
    if _GPL_TOKEN_RE.search(without_lgpl) or _GPL_PHRASE_RE.search(without_lgpl):
        return "GPL"
    return None


def _licenses_via_pip_licenses() -> list[dict] | None:
    """Preferred source: pip-licenses JSON over the resolved env. None if absent."""
    try:
        out = subprocess.run(
            ["pip-licenses", "--format=json", "--with-system"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    rows = json.loads(out)
    return [{"name": r.get("Name", ""), "version": r.get("Version", ""),
             "license": r.get("License", "")} for r in rows]


def _licenses_via_importlib() -> list[dict]:
    """Fallback: read license metadata directly from installed distributions."""
    rows: list[dict] = []
    for dist in importlib_metadata.distributions():
        meta = dist.metadata
        lic = meta.get("License", "") or ""
        if not lic or lic.strip().upper() in {"", "UNKNOWN"}:
            classifiers = meta.get_all("Classifier") or []
            lic = "; ".join(c for c in classifiers if c.startswith("License ::")) or lic
        rows.append({"name": meta.get("Name", "") or "", "version": meta.get("Version", "") or "",
                     "license": lic})
    return rows


def project_name(path: Path = PYPROJECT) -> str:
    """The project's own distribution name (``[project].name``) — excluded from the
    dependency gate so the scan never rejects hypermnesic's OWN license."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return data["project"]["name"]


def _normalize(name: str) -> str:
    """PEP 503 name normalization so 'hypermnesic' / 'Hypermnesic' / 'hyper_mnesic'
    all match the authority name — a stable key, not a brittle exact string."""
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def scan(rows: list[dict] | None = None, self_name: str | None = None) -> dict:
    source = "injected"
    if rows is None:
        rows = _licenses_via_pip_licenses()
        source = "pip-licenses"
        if rows is None:
            rows = _licenses_via_importlib()
            source = "importlib.metadata"
    if self_name is None:
        try:
            self_name = project_name()
        except (OSError, KeyError):
            self_name = None
    self_norm = _normalize(self_name) if self_name else None
    denied, lgpl, ok, self_excluded = [], [], [], []
    for r in rows:
        # The gate scopes to THIRD-PARTY deps. Exclude the project's own dist BEFORE
        # classifying (keyed on the normalized [project].name), so flipping
        # hypermnesic's own license to AGPL-3.0 does not trip the gate (R9 / U6).
        if self_norm and _normalize(r["name"]) == self_norm:
            self_excluded.append(r)
            continue
        reason = classify(r["license"])
        if reason:
            denied.append({**r, "reason": reason})
        elif _LGPL_RE.search(r["license"] or ""):
            lgpl.append(r)
        else:
            ok.append(r)
    return {"source": source, "total": len(rows), "self_excluded": self_excluded,
            "denied": denied, "lgpl_informational": lgpl, "ok_count": len(ok),
            "passed": len(denied) == 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="hypermnesic transitive license gate")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)
    result = scan()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"License scan via {result['source']}: {result['total']} packages, "
              f"{len(result['denied'])} copyleft (deny-set), "
              f"{len(result['lgpl_informational'])} LGPL (informational), "
              f"{len(result['self_excluded'])} self (dependency-scoped, excluded).")
        for s in result["self_excluded"]:
            print(f"  self [excluded] {s['name']} {s['version']} :: {s['license']}")
        for d in result["denied"]:
            print(f"  DENY [{d['reason']}] {d['name']} {d['version']} :: {d['license']}")
        for d in result["lgpl_informational"]:
            print(f"  note [LGPL] {d['name']} {d['version']} :: {d['license']}")
        print("PASS: zero AGPL/GPL/SSPL" if result["passed"]
              else "FAIL: strong-copyleft dependency present")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
