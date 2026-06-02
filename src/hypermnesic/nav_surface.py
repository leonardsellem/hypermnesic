"""U23 — always-organized navigation surface: generated MOCs/dashboards + Bases.
[R6/H5/F3/AE4/KD7]

Auto-maintained (review-gated) entry points that stay correct as content changes:
a **MOC** markdown note and an Obsidian **`.base`** view config (Bases reads
frontmatter/metadata with no code, so the nav/dashboard surfaces cost zero plugin
code — KTD6). Every artifact is **proposed via U18**, demarcated (``generated_by``
+ visible managed-block marker), and lands in a **non-protected** dir
(``dashboards/`` — never the guard-protected ``views/``).

Idempotency + regeneration-on-change ride on a **content-hash slug**: identical
content → identical slug → U18 returns a no-op; changed content → new slug → a new
proposal that reflects the change. Upstream digest (U21) / connections (U22) links
are included only when supplied — generation never blocks on them (graceful).
"""

from __future__ import annotations

import hashlib
from io import StringIO

from ruamel.yaml import YAML

from hypermnesic import generated
from hypermnesic import propose as propose_mod

MOC_REL = "dashboards/MOC.md"
BASE_REL = "dashboards/overview.base"


def build_moc(idx, graph, *, audit_log=None, digest_rel=None, connections_rel=None,
              now: str | None = None) -> str:
    """Render the Map-of-Content note (demarcated). Lists entry-point notes, a
    what-changed section (from the audit log, if given), and links to the salience
    digest / connection suggestions when those exist."""
    paths = sorted(idx.all_paths())
    lines = ["## Notes", ""]
    lines += [f"- [[{p}]]" for p in paths] or ["_(no notes yet)_"]

    if audit_log is not None:
        recent = []
        seen = set()
        for e in reversed(audit_log.entries()):
            p = e.get("path")
            if p and p not in seen:
                seen.add(p)
                recent.append(p)
            if len(recent) >= 5:
                break
        if recent:
            lines += ["", "## Recently changed", ""] + [f"- [[{p}]]" for p in recent]

    if digest_rel:
        lines += ["", "## Resurfaced (salience)", "", f"See [[{digest_rel}]]."]
    if connections_rel:
        lines += ["", "## Suggested connections", "", f"See [[{connections_rel}]]."]

    fm = {"title": "Map of Content", "type": "dashboard"}
    if now:
        fm["generated_at"] = now
    return generated.render(fm, "\n".join(lines))


def build_base_config(*, now: str | None = None) -> str:
    """Render a valid Obsidian ``.base`` config: a single ``all:`` filter group +
    a table view. Carries ``generated_by`` (demarcation for a non-markdown file)."""
    config = {
        "generated_by": "hypermnesic",
        "filters": {"all": ['file.ext == "md"']},
        "views": [{"type": "table", "name": "All notes",
                   "order": ["file.name", "file.mtime"]}],
    }
    if now:
        config["generated_at"] = now
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    buf = StringIO()
    yaml.dump(config, buf)
    return "# generated_by: hypermnesic — regenerated; edits are overwritten\n" + buf.getvalue()


def nav_proposal(repo, idx, graph, *, audit_log=None, digest_rel=None,
                 connections_rel=None, log=None, gh_create=None, now: str | None = None):
    """Build the MOC + ``.base`` and emit them as ONE review-gated U18 proposal.

    The slug is content-addressed so an unchanged surface re-proposes to a no-op
    and a changed surface opens a fresh proposal."""
    moc = build_moc(idx, graph, audit_log=audit_log, digest_rel=digest_rel,
                    connections_rel=connections_rel, now=now)
    base = build_base_config(now=now)
    digest = hashlib.sha256((moc + base).encode("utf-8")).hexdigest()[:8]
    return propose_mod.propose(
        repo,
        [propose_mod.Change(path=MOC_REL, body=moc),
         propose_mod.Change(path=BASE_REL, body=base)],
        slug=f"nav-surface-{digest}",
        summary="navigation surface: regenerated MOC + Bases dashboard",
        why="keep the human entry point organized as content changes (H5/AE4)",
        source="engine: index + body-wikilink graph",
        allowlist=["dashboards/"], log=log, gh_create=gh_create)
