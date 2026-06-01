#!/usr/bin/env python3
"""Label-review workflow for the parity harness (KTD6 human judgment).

`build`: for each query, write a checkbox markdown file listing the **union** of
hypermnesic's and gbrain's top-10 (with each doc's rank on both sides and a
snippet), pre-checking the current labels. The operator ticks every relevant
doc.

`apply`: parse the ticked file back into `queries.frozen.jsonl` (`relevant` =
ticked paths), marking the set human-reviewed. Then re-run the parity harness.

The review file contains queries, paths, and snippets from a private corpus →
it is **gitignored** (local-only), like the frozen query set and baseline.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from hypermnesic import retrieve

_CHECK = re.compile(r"^\s*-\s*\[([ xX])\]\s+`([^`]+)`")
_SECTION = re.compile(r"^##\s+(q\d+)\b")


def _snippet(text: str, n: int = 160) -> str:
    return " ".join((text or "").split())[:n]


def _dedup_docs(hits, k: int):
    seen, out = set(), []
    for h in hits:
        if h.path not in seen:
            seen.add(h.path)
            out.append(h)
        if len(out) >= k:
            break
    return out


def build_review(queries: list[dict], baseline: dict[str, list[str]], idx, embedder,
                 *, k: int = 10, expand: int = 0, expander=None) -> str:
    lines = [
        "# hypermnesic — label review (KTD6)",
        "",
        "Tick `[x]` every doc that genuinely answers the query (leave irrelevant ones",
        "`[ ]`). You may add `- [x] \\`path/to/doc.md\\`` lines. Save, then run:",
        "`uv run python harness/label_review.py apply --review <this file> "
        "--queries harness/queries.frozen.jsonl`",
        "",
    ]
    for q in queries:
        res = retrieve.search(idx, q["query"], embedder=embedder, k=max(k, 50),
                              expand=expand, expander=expander)
        hyp = {}
        for rank, h in enumerate(_dedup_docs(res.hits, k), 1):
            hyp.setdefault(h.path, (rank, _snippet(h.text)))
        gb = baseline.get(q["id"], [])[:k]
        gbrank = {p: i + 1 for i, p in enumerate(gb)}
        cur = list(q.get("relevant", []))
        order = (list(hyp) + [p for p in gb if p not in hyp]
                 + [p for p in cur if p not in hyp and p not in gbrank])
        lines += [f"## {q['id']} [{q.get('lang', 'en')}]",
                  f"**Query:** {q['query']}",
                  f"**Current primary:** `{q.get('relevant_primary', '?')}`", ""]
        for p in order:
            mark = "x" if p in cur else " "
            hr = hyp.get(p, (None,))[0]
            gr = gbrank.get(p)
            tag = (f"hyp#{hr}" if hr else "hyp—") + " " + (f"gbrain#{gr}" if gr else "gbrain—")
            lines.append(f"- [{mark}] `{p}` ({tag}) — {hyp.get(p, (None, ''))[1]}")
        lines.append("")
    return "\n".join(lines)


def parse_review(md: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur = None
    for line in md.splitlines():
        m = _SECTION.match(line)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        c = _CHECK.match(line)
        if c and cur is not None and c.group(1).lower() == "x":
            out[cur].append(c.group(2))
    return out


def apply_review(md: str, queries: list[dict]) -> tuple[list[dict], list[str]]:
    marks = parse_review(md)
    changes = []
    for q in queries:
        if q["id"] not in marks:
            continue
        new = sorted(dict.fromkeys(marks[q["id"]]))  # dedup, stable
        if not new:
            changes.append(f"{q['id']}: WARNING no docs ticked — left unchanged")
            continue
        old = set(q.get("relevant", []))
        prim = q.get("relevant_primary")
        q["relevant"] = new
        if prim not in new:
            q["relevant_primary"] = marks[q["id"]][0]
        q["method"] = "human-reviewed-known-item"
        added, removed = set(new) - old, old - set(new)
        if added or removed:
            changes.append(f"{q['id']}: +{sorted(added)} -{sorted(removed)}")
    return queries, changes


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _cmd_build(args) -> int:
    from hypermnesic import embed, index
    embed.smoke_embed_or_die()
    expander = None
    if args.expand:
        from hypermnesic import expand as expand_mod
        expander = expand_mod.OpenAIExpander()
    idx = index.Index(Path(args.index_db))
    md = build_review(_load_jsonl(args.queries), _load_baseline(args.baseline), idx,
                      embed.OpenAIEmbedder(), expand=args.expand, expander=expander)
    idx.close()
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"wrote review file → {args.out} ({len(_load_jsonl(args.queries))} queries)")
    return 0


def _cmd_apply(args) -> int:
    queries = _load_jsonl(args.queries)
    md = Path(args.review).read_text(encoding="utf-8")
    updated, changes = apply_review(md, queries)
    with open(args.queries, "w", encoding="utf-8") as fh:
        for q in updated:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"applied human labels to {args.queries}:")
    for c in changes:
        print("  " + c)
    if not changes:
        print("  (no label changes)")
    return 0


def _load_baseline(path: Path) -> dict[str, list[str]]:
    return {r["id"]: r["top10"] for r in _load_jsonl(path)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="parity label-review workflow")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write the checkbox review file")
    b.add_argument("--index-db", required=True)
    b.add_argument("--queries", required=True)
    b.add_argument("--baseline", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--expand", type=int, default=0)
    b.set_defaults(func=_cmd_build)
    a = sub.add_parser("apply", help="apply ticked labels back into the query set")
    a.add_argument("--review", required=True)
    a.add_argument("--queries", required=True)
    a.set_defaults(func=_cmd_apply)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
