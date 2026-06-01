#!/usr/bin/env python3
"""Read-only pre-cutover audit of the diff-or-die gate + protected-path guard.

**Writes nothing.** Two questions a live cutover hinges on, answered against a
real corpus:

1. **Gate compatibility** — would editing one frontmatter field churn the others?
   For each doc with frontmatter, set one existing top-level field to its *current*
   value (a no-op field write that still forces ruamel to reload+dump the block)
   and record whether the gate returns clean or **aborts** (an untouched key would
   reflow — scalar date → ISO, indent, quotes). The abort rate is the practical
   usability signal for the write kernel on this corpus.
2. **Guard classification** — does `serialize.protected_reason` refuse the
   governance files (CLAUDE.md/AGENTS.md incl. symlinks, .github/workflows, etc.)
   and *not* false-positive on ordinary notes?
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hypermnesic import frontmatter_gate as fg
from hypermnesic import serialize

_SKIP = {".git", ".hypermnesic", ".obsidian", "node_modules", ".brv"}


def _iter_md(corpus: Path):
    for p in sorted(corpus.rglob("*.md")):
        if not any(part in _SKIP for part in p.relative_to(corpus).parts):
            yield p


def _first_top_key(fm_inner: str):
    """(key, value) of the first top-level scalar field, or None. Raises on
    unparseable YAML so the caller can bucket it."""
    data = fg._yaml().load(fm_inner)
    if not hasattr(data, "items"):
        return None
    for k, v in data.items():
        if not isinstance(v, (dict, list)):   # scalar-ish (str/int/float/bool/date/None)
            return k, v
    return None


def gate_compat(corpus: Path) -> dict:
    clean = abort = unparseable = no_scalar = no_fm = 0
    aborts: list[dict] = []
    for p in _iter_md(Path(corpus)):
        raw = p.read_text(encoding="utf-8", errors="replace")
        fm, _ = fg.split_frontmatter(raw)
        rel = p.relative_to(corpus).as_posix()
        if fm is None:
            no_fm += 1
            continue
        try:
            kv = _first_top_key(fm)
        except Exception:
            unparseable += 1
            continue
        if kv is None:
            no_scalar += 1
            continue
        try:
            fg.gated_edit(raw, set_fields={kv[0]: kv[1]})   # no-op field set
            clean += 1
        except fg.FrontmatterDriftError as exc:
            abort += 1
            if len(aborts) < 20:
                aborts.append({"path": rel, "drifted_keys": sorted(exc.keys)})
        except Exception as exc:  # noqa: BLE001 — audit records, never crashes
            unparseable += 1
            if len(aborts) < 20:
                aborts.append({"path": rel, "error": type(exc).__name__})
    editable = clean + abort
    return {"total_md": clean + abort + unparseable + no_scalar + no_fm,
            "with_frontmatter": clean + abort + unparseable + no_scalar,
            "clean": clean, "abort": abort, "unparseable": unparseable,
            "no_scalar_key": no_scalar, "no_frontmatter": no_fm,
            "abort_rate": round(abort / editable, 4) if editable else 0.0,
            "sample_aborts": aborts}


def guard_audit(corpus: Path) -> dict:
    corpus = Path(corpus)
    governance = ["CLAUDE.md", "AGENTS.md", ".github/workflows/ci.yml", ".obsidian/app.json",
                  "skills/x/SKILL.md", "scripts/ops/tool.py", "views/projects.yml",
                  ".gitignore", "install_for_agents.md", "projects/x/AGENTS.md"]
    gov = {}
    for g in governance:
        try:
            serialize.check(corpus, g)
            gov[g] = "WRITABLE (!)"            # unexpected — a governance file left writable
        except serialize.WriteGuardError as exc:
            gov[g] = f"refused: {str(exc).split(':', 1)[-1].strip()}"
    # false positives: ordinary notes the guard wrongly refuses
    false_pos = []
    checked = 0
    for p in _iter_md(corpus):
        rel = p.relative_to(corpus).as_posix()
        checked += 1
        reason = serialize.protected_reason(rel)
        if reason:
            false_pos.append({"path": rel, "reason": reason})
    return {"governance_classification": gov,
            "notes_checked": checked,
            "protected_note_count": len(false_pos),
            "protected_notes_sample": false_pos[:30]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="read-only gate + guard audit of a corpus")
    p.add_argument("--corpus", required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    report = {"gate": gate_compat(Path(args.corpus)), "guard": guard_audit(Path(args.corpus))}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        g = report["gate"]
        print(f"GATE: {g['clean']} clean / {g['abort']} abort / {g['unparseable']} unparseable "
              f"of {g['with_frontmatter']} with frontmatter — abort_rate={g['abort_rate']}")
        gd = report["guard"]
        print(f"GUARD: {gd['protected_note_count']} of {gd['notes_checked']} "
              f"notes flagged protected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
