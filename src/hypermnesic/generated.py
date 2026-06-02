"""Shared demarcation for review-gated GENERATED artifacts (U21 digests, U23
MOCs/dashboards). [R10/KD7/R-4]

A generated file must be unmistakable as generated — even in Obsidian's reading
view where frontmatter is collapsed. So every generated artifact carries BOTH:
  - ``generated_by: hypermnesic`` frontmatter, and
  - a rendered, human-visible **managed-block marker** (a callout) whose region is
    explicit, so a human edit inside it is never a surprise overwrite (R10).

Generation is review-gated (every artifact flows through U18) and demarcated here
so it is never confused with a hand-authored note (KD7).
"""

from __future__ import annotations

from io import StringIO

from hypermnesic import frontmatter_gate as fg

MANAGED_BEGIN = "> [!hypermnesic] generated — edits below this marker are overwritten"
MANAGED_END = "<!-- /hypermnesic:generated -->"


def render(frontmatter: dict, body: str) -> str:
    """Render a generated note: provenance frontmatter + a visible managed block.

    ``generated_by: hypermnesic`` is forced into the frontmatter so demarcation can
    never be omitted by a caller."""
    fm = {"generated_by": "hypermnesic", **dict(frontmatter)}
    buf = StringIO()
    fg._yaml().dump(fm, buf)
    return ("---\n" + buf.getvalue() + "---\n"
            + MANAGED_BEGIN + "\n\n" + body.rstrip("\n") + "\n\n" + MANAGED_END + "\n")


def is_generated(text: str) -> bool:
    """True if ``text`` is a hypermnesic-generated artifact (frontmatter marker)."""
    fm_inner, _ = fg.split_frontmatter(text)
    return bool(fm_inner) and "generated_by: hypermnesic" in fm_inner
