#!/usr/bin/env python3
"""U16 — cron-repoint dogfood preview (read-only).

Previews what routing one ingest writer through ``commit_note`` *would* do, as a
structured report for operator review — **never writes**. Each input is run
through ``commit_note(..., dry_run=True)``, so the diff-or-die gate and the
protected-path guard run exactly as live, but nothing is written, committed,
indexed, or logged. Pointing this at the live ``gbrain-brain`` is therefore safe
(dry-run is read-only). The report is the artifact the operator reviews before
authorizing the gated live cutover.

Inputs are operator-supplied ({path, body|set_fields, summary}); the harness does
not ingest arbitrary external content. The live cutover is OUT OF SCOPE.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hypermnesic import commit_note as cn
from hypermnesic import frontmatter_gate as fg
from hypermnesic import serialize


def preview_inputs(repo, inputs: list[dict], *, allowlist: list[str] | None = None) -> dict:
    """Dry-run every input; return a structured per-input report + a safety rollup."""
    repo = Path(repo)
    results = []
    for inp in inputs:
        path = inp.get("path", "")
        entry: dict = {"path": path}
        try:
            r = cn.commit_note(repo, path, body=inp.get("body"),
                               set_fields=inp.get("set_fields"), summary=inp.get("summary"),
                               allowlist=allowlist, dry_run=True)
            entry.update(verdict="ok", created=r.created, noop=r.noop,
                         planned_verb=("create" if r.created else "edit"),
                         diff_lines=r.diff.count("\n"))
        except serialize.WriteGuardError as exc:
            entry.update(verdict="refused", reason=str(exc))
        except fg.FrontmatterDriftError as exc:
            entry.update(verdict="gate-abort", diff=exc.diff)
        except FileNotFoundError as exc:
            entry.update(verdict="missing", reason=str(exc))
        except Exception as exc:  # noqa: BLE001 — preview records, never crashes the run
            entry.update(verdict="error", reason=repr(exc))
        results.append(entry)
    blocked = sum(1 for r in results if r["verdict"] != "ok")
    return {"repo": str(repo), "inputs": results, "blocked": blocked,
            "safe_to_cut_over": blocked == 0}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="commit_note dogfood preview (dry-run, read-only)")
    p.add_argument("--repo", required=True)
    p.add_argument("--inputs", required=True, help="JSON file: [{path, body|set_fields, summary}]")
    p.add_argument("--allowlist", nargs="*", default=None, help="writable-path prefixes")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    report = preview_inputs(args.repo, inputs, allowlist=args.allowlist)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for r in report["inputs"]:
            print(f"[{r['verdict']:9s}] {r['path']}"
                  + (f"  ({r.get('planned_verb')}, {r.get('diff_lines')} diff lines)"
                     if r["verdict"] == "ok" else f"  {r.get('reason', '')}"))
        print(f"safe_to_cut_over: {report['safe_to_cut_over']} ({report['blocked']} blocked)")
    return 0 if report["safe_to_cut_over"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
