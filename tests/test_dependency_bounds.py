"""Runtime dependencies must be bounded below the next major.

`uv.lock` protects this repository. It is not shipped in the wheel or sdist, so it
protects no user: a fresh `uv tool install hypermnesic` resolves whatever PyPI
offers today. An unbounded `mcp>=1.2` therefore resolved mcp 2.0.0 — which dropped
`mcp.server.fastmcp` — and every clean install crash-looped on startup (LS-2550).

The fresh-install CI job proves the built package actually starts. This test is the
cheap, local half: it fails the moment a runtime dependency loses its upper bound,
without waiting for that dependency to publish a breaking major.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DEPS = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]

# Optional extras are developer-facing and may float; these ship to users.
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _name(spec: str) -> str:
    m = _NAME.match(spec)
    assert m, f"cannot parse dependency name from {spec!r}"
    return m.group(1)


def _has_upper_bound(spec: str) -> bool:
    """True when the spec cannot silently absorb the next major."""
    return any(op in spec for op in ("<", "~=", "==")) or ".*" in spec


@pytest.mark.parametrize("spec", RUNTIME_DEPS, ids=_name)
def test_runtime_dependency_has_an_upper_bound(spec):
    assert _has_upper_bound(spec), (
        f"runtime dependency {spec!r} has no upper bound. uv.lock does not ship to "
        f"users, so a fresh install would take the next major of {_name(spec)} "
        f"whenever it is published. Pin it below the next major (LS-2550)."
    )


def test_mcp_stays_below_2_while_the_server_uses_fastmcp():
    """mcp 2.x removed `mcp.server.fastmcp`, which mcp_server.py imports at module level."""
    server = (ROOT / "src" / "hypermnesic" / "mcp_server.py").read_text()
    if "from mcp.server.fastmcp" not in server:
        pytest.skip("mcp_server.py no longer imports mcp.server.fastmcp — revisit the bound")
    spec = next(d for d in RUNTIME_DEPS if _name(d) == "mcp")
    assert "<2" in spec.replace(" ", ""), (
        f"mcp is declared as {spec!r}; mcp 2.x dropped mcp.server.fastmcp, so the "
        f"server cannot start on it"
    )
