"""Equivalence-class detection: content mirrors + same-event meeting/source.

All fixtures use fictional names/slugs — no real corpus content.
"""

from __future__ import annotations

import corpus_equivalence as ce


def test_content_mirror_grouped(make_corpus):
    body = "---\ntitle: X\n---\n# X\n\nidentical body content here for both copies.\n"
    repo = make_corpus({
        "docs/final/x.md": body,
        "projects/teamspace/docs/final/x.md": body,   # exact mirror
        "docs/other.md": "# Other\n\ncompletely different content.\n",
    })
    cls = ce.equivalence_classes(repo)
    assert set(cls["docs/final/x.md"]) == {"docs/final/x.md", "projects/teamspace/docs/final/x.md"}
    assert cls["docs/other.md"] == ["docs/other.md"]


def test_meeting_source_same_event_grouped(make_corpus):
    stem = "2026-04-30-alex-rivera-quarterly-planning-sync-discussion"
    repo = make_corpus({
        f"meetings/{stem}.md": "# Planning sync\n\nmeeting note, processed summary.\n",
        f"sources/{stem}-76d8aebdd099.md": "# Planning sync\n\nraw transcript, verbatim long.\n",
        "meetings/2026-04-30-prep-rdv-alex-rivera-quarterly-planning.md":
            "# Prep\n\na DIFFERENT prep meeting, must not merge.\n",
    })
    cls = ce.equivalence_classes(repo)
    meeting = f"meetings/{stem}.md"
    source = f"sources/{stem}-76d8aebdd099.md"
    prep = "meetings/2026-04-30-prep-rdv-alex-rivera-quarterly-planning.md"
    assert source in cls[meeting]  # same event → grouped
    assert prep not in cls[meeting]        # different slug → not grouped


def test_same_title_different_dates_not_merged(make_corpus):
    repo = make_corpus({
        "meetings/2025-12-10-weekly-status-recurring-sync-meeting.md": "# Status\n\nDec meeting.\n",
        "meetings/2026-01-15-weekly-status-recurring-sync-meeting.md": "# Status\n\nJan meeting.\n",
    })
    cls = ce.equivalence_classes(repo)
    a = "meetings/2025-12-10-weekly-status-recurring-sync-meeting.md"
    b = "meetings/2026-01-15-weekly-status-recurring-sync-meeting.md"
    assert b not in cls[a]   # different dates → distinct events


def test_body_hash_map(make_corpus):
    repo = make_corpus({"a.md": "# A\n\nbody\n", "b.md": "# A\n\nbody\n", "c.md": "# C\n\nx\n"})
    h = ce.body_hash_map(repo)
    assert h["a.md"] == h["b.md"]
    assert h["a.md"] != h["c.md"]
