#!/usr/bin/env python3
"""Print one release's section of CHANGELOG.md, for GitHub release notes.

The release job feeds this to ``gh release create --notes-file``. CHANGELOG.md is
already the record of what shipped (AGENTS.md makes a dated entry mandatory for any
user-visible change), so the release notes are derived from it rather than written
twice and allowed to disagree.

Exits non-zero when the requested version has no section — a release with empty or
wrong notes is worse than a release job that stops and says why.

    python scripts/changelog_section.py v0.2.0 [--changelog CHANGELOG.md]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"


def section(text: str, version: str) -> str:
    """Return the body of the ``## [version]`` section, without its heading.

    ``version`` may carry a leading ``v``. ``Unreleased`` is refused: it is a
    staging area, not something that can be released.
    """
    wanted = version.lstrip("vV").strip()
    if wanted.lower() == "unreleased":
        sys.exit("refusing to build release notes from [Unreleased] — cut it to a "
                 "dated version section first")

    # Stop at the next '## [' heading, or at the link-reference footer, or EOF.
    pattern = (
        rf"^## \[{re.escape(wanted)}\][^\n]*\n"
        r"(?P<body>.*?)"
        r"(?=^## \[|^\[[^\]]+\]:\s*http|\Z)"
    )
    m = re.search(pattern, text, re.S | re.M)
    if m is None:
        sys.exit(f"no [{wanted}] section found in the changelog")

    body = m.group("body").strip()
    if not body:
        sys.exit(f"the [{wanted}] section is empty — nothing to release")
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="version or tag, e.g. 0.2.0 or v0.2.0")
    parser.add_argument("--changelog", type=Path, default=CHANGELOG)
    args = parser.parse_args(argv)
    print(section(args.changelog.read_text(encoding="utf-8"), args.version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
