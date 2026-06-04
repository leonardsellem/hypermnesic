#!/usr/bin/env python3
"""Version-consistency gate (U1 / R2 / R20).

One authority — ``pyproject.toml`` ``[project].version`` — and every distributed
version string must agree with it: the in-package mirror
(``src/hypermnesic/__init__.__version__``) and each plugin manifest
(``marketplace.json`` ``plugins[].version`` + the two ``plugin.json`` files).

The 0.0.4 ↔ 0.0.5 split happened because a release bump touched only the Python
package; the three plugin manifests drifted. This gate fails the build on any such
divergence, with a message that names the diverging file and both versions — so a
contributor knows exactly which file to sync.

This is assert-in-CI (the U1 chosen default), not derive-at-build: lowest churn, no
build-step coupling. If the team later prefers generating the manifests from the
authority, that is a drop-in replacement for this gate.

Usage::

    uv run python scripts/check_version_consistency.py
    uv run python scripts/check_version_consistency.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent

AUTHORITY = ROOT / "pyproject.toml"
INIT = ROOT / "src" / "hypermnesic" / "__init__.py"
MANIFESTS = (
    ROOT / "plugin" / ".claude-plugin" / "marketplace.json",
    ROOT / "plugin" / "plugins" / "hypermnesic" / ".claude-plugin" / "plugin.json",
    ROOT / "plugin" / "plugins" / "hypermnesic" / ".codex-plugin" / "plugin.json",
    ROOT / "plugin" / "hermes" / "plugin.yaml",
)


def authority_version(path: Path = AUTHORITY) -> str:
    """The single source of truth: ``[project].version`` in ``pyproject.toml``."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return data["project"]["version"]


def init_version(path: Path = INIT) -> str | None:
    """The in-package mirror ``__version__`` (None if it cannot be parsed)."""
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', Path(path).read_text(encoding="utf-8"))
    return m.group(1) if m else None


def manifest_versions(path: Path) -> list[str]:
    """Every version string a manifest declares — top-level ``version`` plus each
    ``plugins[].version`` (so the marketplace listing's nested slot is covered too)."""
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        data = YAML(typ="safe").load(raw) or {}
    else:
        data = json.loads(raw)
    out: list[str] = []
    if isinstance(data.get("version"), str):
        out.append(data["version"])
    for entry in data.get("plugins", []) or []:
        if isinstance(entry, dict) and isinstance(entry.get("version"), str):
            out.append(entry["version"])
    return out


def collect(root: Path = ROOT) -> list[tuple[str, str | None]]:
    """``(label, version)`` for the in-package mirror + every manifest version slot.

    A manifest with NO version slot yields ``(label, None)`` so the gate flags it
    clearly rather than silently passing a manifest that forgot to declare one.
    """
    items: list[tuple[str, str | None]] = [
        (INIT.relative_to(root).as_posix(), init_version()),
    ]
    for mf in MANIFESTS:
        rel = mf.relative_to(root).as_posix()
        versions = manifest_versions(mf)
        if not versions:
            items.append((rel, None))
        else:
            items.extend((rel, v) for v in versions)
    return items


def check(authority: str, items: list[tuple[str, str | None]]) -> list[str]:
    """Return a list of human-readable drift problems; empty means consistent."""
    problems: list[str] = []
    for label, version in items:
        if version is None:
            problems.append(f"{label}: no version declared (authority is {authority})")
        elif version != authority:
            problems.append(f"{label}: {version} != authority {authority}")
    return problems


def scan() -> dict:
    authority = authority_version()
    items = collect()
    problems = check(authority, items)
    return {"authority": authority, "slots": len(items),
            "problems": problems, "passed": not problems}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="hypermnesic version-consistency gate")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)
    result = scan()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    if result["passed"]:
        print(f"PASS: all {result['slots']} version slots agree with "
              f"pyproject.toml = {result['authority']}")
        return 0
    print(f"Version drift (authority pyproject.toml = {result['authority']}):")
    for p in result["problems"]:
        print(f"  DRIFT {p}")
    print("FAIL: sync the diverging file(s) to the authority version")
    return 1


if __name__ == "__main__":
    sys.exit(main())
