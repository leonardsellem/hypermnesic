"""U24 — frictionless capture → deferred thinking-triage. [R6/H6/F5]

Splits low capture-friction from generative processing-friction *in time*:

  - **capture** lands raw text in ``sources/`` via U18's immutable free-append
    fast path — committed immediately, zero organization demanded, no PR in the
    moment (so the thought is never lost to friction).
  - **triage** (later) reuses U20's read-only ``think`` over the captured item to
    PROPOSE a placement + connections + a one-line grapple prompt via U18. It never
    auto-moves or auto-files the note — placement is a proposal the owner approves.
"""

from __future__ import annotations

import hashlib
import posixpath
from pathlib import Path

from hypermnesic import generated
from hypermnesic import propose as propose_mod
from hypermnesic import think as think_mod


def capture(repo, text: str, *, name: str | None = None, now: str | None = None,
            idx=None, log=None):
    """Land ``text`` raw under ``sources/`` (free-append fast path). Returns the
    ``ProposalResult`` (``fast_path=True``, committed to HEAD — no proposal branch)."""
    body = text if text.endswith("\n") else text + "\n"
    if name is None:
        stamp = (now or "capture").replace(":", "").replace("-", "")
        sha6 = hashlib.sha256(body.encode("utf-8")).hexdigest()[:6]
        name = f"captures/{stamp}-{sha6}.md"
    rel = f"sources/{name}"
    return propose_mod.propose(
        repo, [propose_mod.Change(path=rel, body=body)],
        slug="capture", summary="capture: raw note",
        allowlist=["sources/"], idx=idx, log=log)


def _suggest_placement(related: list[str]) -> str:
    if not related:
        return "(undetermined — no close neighbours yet)"
    folder = posixpath.dirname(related[0])
    return f"`{folder}/`" if folder else "(vault root)"


def backlog(repo) -> dict:
    """List raw captures under ``sources/`` without mutating them."""
    root = Path(repo)
    captures = []
    for path in sorted((root / "sources").rglob("*.md")) if (root / "sources").exists() else []:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        first = " ".join(text.split())[:200]
        triage_slug = propose_mod.safe_slug(rel)
        proposed = (root / "dashboards" / f"triage-{triage_slug}.md").exists()
        captures.append({
            "path": rel,
            "stage": "triage_proposed" if proposed else "pending_triage",
            "snippet": first,
            "bytes": path.stat().st_size,
        })
    return {"count": len(captures), "captures": captures}


def triage(repo, idx, graph, captured_rel: str, *, embedder=None, log=None,
           gh_create=None, now: str | None = None):
    """Propose a placement + connections + grapple prompt for a captured note —
    analysed via the read-only ``think`` path, emitted as a U18 proposal, never
    auto-moving the note. The returned result carries ``thought_wrote`` (the
    observable proof the analysis step wrote nothing)."""
    captured_path = repo / captured_rel
    if not captured_path.exists():
        return {"status": "not_found", "path": captured_rel, "proposed": False}
    text = captured_path.read_text(encoding="utf-8")
    thought = think_mod.think(idx, text.strip(), embedder=embedder, graph=graph)
    related = [h["path"] for h in thought.related if h["path"] != captured_rel][:5]
    grapple = thought.questions[0] if thought.questions else \
        "What does this capture connect to, and why did it matter?"

    lines = [f"## Triage for [[{captured_rel}]]", "",
             f"**Suggested placement:** {_suggest_placement(related)}", ""]
    if related:
        lines += ["## Connections", ""] + [f"- [[{p}]]" for p in related]
    lines += ["", "## Grapple", "", f"- {grapple}"]
    note = generated.render({"title": f"Triage: {captured_rel}", "type": "triage"},
                            "\n".join(lines))

    slug = f"triage-{propose_mod.safe_slug(captured_rel)}"
    res = propose_mod.propose(
        repo, [propose_mod.Change(path=f"dashboards/{slug}.md", body=note)],
        slug=slug, summary=f"triage: placement + connections for {captured_rel}",
        why="deferred thinking-triage of a frictionless capture (H6) — never auto-placed",
        source=captured_rel, allowlist=["dashboards/"], log=log, gh_create=gh_create)
    res.thought_wrote = thought.wrote                  # carry the read-only proof (R7)
    return res
