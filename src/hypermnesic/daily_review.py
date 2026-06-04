"""Daily workflow review surface.

Composes existing capture, audit, generated-surface, and cleanup primitives into one
review-gated markdown artifact. It does not move, delete, or rewrite source notes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from hypermnesic import capture, generated
from hypermnesic import propose as propose_mod

DAILY_REVIEW_REL = "dashboards/daily-review.md"
CLEANUP_ACTIONS = ["inspect", "export", "forget", "revert", "audit"]


def _link(path: str) -> str:
    return f"[[{path}]]"


def _recent_writes(audit_log, *, limit: int = 5) -> list[dict]:
    if audit_log is None:
        return []
    entries = [e for e in audit_log.entries() if e.get("path")]
    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return entries[:limit]


def build_daily_review(
    repo,
    *,
    capture_backlog: dict | None = None,
    audit_log=None,
    generated_surfaces: dict[str, str] | None = None,
    degraded: list[str] | None = None,
    now: str | None = None,
) -> str:
    """Render the owner-facing daily workflow review as generated markdown."""
    backlog = capture_backlog if capture_backlog is not None else capture.backlog(Path(repo))
    surfaces = generated_surfaces or {}
    degraded = degraded or []
    lines = [
        "## Daily loop",
        "",
        "Capture -> triage -> recall -> write -> review -> clean up.",
        "",
        "## Capture backlog",
        "",
    ]
    captures = backlog.get("captures", []) if isinstance(backlog, dict) else []
    if captures:
        for item in captures:
            lines.append(
                f"- {_link(item['path'])} — {item.get('stage', 'pending_triage')}: "
                f"{item.get('snippet', '')}"
            )
    else:
        lines.append("_No raw captures waiting for triage._")

    lines += ["", "## Recent writes", ""]
    recent = _recent_writes(audit_log)
    if recent:
        for entry in recent:
            summary = entry.get("summary", "")
            lines.append(f"- {_link(entry['path'])} — {entry.get('verb', 'write')}: {summary}")
    else:
        lines.append("_No recent audit-log writes were found._")

    lines += ["", "## Generated surfaces", ""]
    if surfaces:
        for label, rel in sorted(surfaces.items()):
            lines.append(f"- {label}: {_link(rel)}")
    else:
        lines.append("_No generated navigation, salience, or connection surfaces were provided._")

    lines += ["", "## Recall modes", ""]
    lines += [
        "- Search for direct topic or entity recall.",
        "- Build context around a known note path.",
        "- Think for related notes, questions, and unlinked pairs.",
        "- Resolve before wikilinking an entity; do not guess on null.",
    ]

    lines += ["", "## Clean up", ""]
    lines += [
        "- Inspect before changing: `hypermnesic memory inspect <repo> <path>`.",
        "- Export before handing off: `hypermnesic memory export <repo> --dest <dir>`.",
        "- Forget/delete with preview first: `hypermnesic memory forget <repo> <path>`.",
        "- Revert safe recent writes: `hypermnesic memory revert <repo> <commit>`.",
        "- Audit decisions and refusals: `hypermnesic memory audit <repo>`.",
    ]

    lines += ["", "## Offline / degraded", ""]
    if degraded:
        for item in degraded:
            lines.append(f"- {item}")
    else:
        lines.append("Lexical recall, capture, backlog review, and cleanup guidance still work "
                     "when dense retrieval is unavailable.")

    fm = {"title": "Daily Review", "type": "dashboard"}
    if now:
        fm["generated_at"] = now
    return generated.render(fm, "\n".join(lines))


def review_proposal(
    repo,
    idx=None,
    graph=None,
    *,
    audit_log=None,
    digest_rel: str | None = None,
    nav_rel: str | None = None,
    connections_rel: str | None = None,
    degraded: list[str] | None = None,
    log=None,
    gh_create=None,
    now: str | None = None,
):
    """Emit the daily review as a review-gated proposal under ``dashboards/``."""
    surfaces = {}
    if nav_rel:
        surfaces["navigation"] = nav_rel
    if digest_rel:
        surfaces["salience"] = digest_rel
    if connections_rel:
        surfaces["connections"] = connections_rel
    note = build_daily_review(
        repo,
        capture_backlog=capture.backlog(repo),
        audit_log=audit_log,
        generated_surfaces=surfaces,
        degraded=degraded,
        now=now,
    )
    digest = hashlib.sha256(note.encode("utf-8")).hexdigest()[:8]
    return propose_mod.propose(
        repo,
        [propose_mod.Change(path=DAILY_REVIEW_REL, body=note)],
        slug=f"daily-review-{digest}",
        summary="daily review: capture triage recall cleanup",
        why="owner-facing capture -> triage -> recall -> write -> review -> cleanup loop",
        source="engine: capture backlog + audit log + generated surfaces",
        allowlist=["dashboards/"],
        log=log,
        gh_create=gh_create,
    )
