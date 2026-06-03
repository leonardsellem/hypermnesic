"""Phase-B gate (G6): the blocklist write-surface flip MUST NOT be live unless the
security-review delta is signed off.

This is the enforced (not advisory) sign-off gate. When ``_effective_write_surface(None)``
returns ``None`` (the blocklist default is live) the operator-signed delta
``docs/2026-06-03-blocklist-write-surface-security-review.md`` must exist and carry a
non-empty, non-``PENDING`` ``signed_off:`` frontmatter value. If the flip is live and the
delta is missing or unsigned this test FAILS — blocking merge/enable of the flip ahead of
sign-off. When the flip is NOT live (the 4-prefix escape-hatch is the default) the gate
imposes no requirement.
"""

from __future__ import annotations

import re
from pathlib import Path

from hypermnesic import mcp_server

_DELTA = (Path(__file__).resolve().parents[1] / "docs"
          / "2026-06-03-blocklist-write-surface-security-review.md")


def _signed_off_value() -> str | None:
    if not _DELTA.exists():
        return None
    m = re.search(r"^signed_off:\s*(.*)$", _DELTA.read_text(encoding="utf-8"), re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'") or None


def test_blocklist_flip_requires_signed_security_review():
    flip_live = mcp_server._effective_write_surface(None) is None
    if not flip_live:
        return  # the 4-prefix escape-hatch is the default → the gate imposes no requirement
    assert _DELTA.exists(), (
        f"blocklist write flip is LIVE but the security-review delta is missing: {_DELTA.name} "
        "(G6 — the flip must not enable without a signed delta)")
    val = _signed_off_value()
    assert val and val.upper() != "PENDING", (
        "blocklist write flip is LIVE but the security-review delta is not signed off "
        "(signed_off: is empty or PENDING). Operator sign-off is required before the flip may "
        "merge/enable (G6).")
