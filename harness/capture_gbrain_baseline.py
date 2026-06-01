#!/usr/bin/env python3
"""Capture the FROZEN gbrain baseline (un-reranked) for the parity harness.

Runs the homelab ``gbrain search`` per query and records the top-10 DOC paths.
Empirically verified (2026-06-01): ``gbrain search`` output is identical with
``search.reranker.enabled`` true vs false — i.e. ``search`` returns the
un-reranked retrieval (the ZeroEntropy reranker is applied by the ``query``/RAG
path, not ``search``). So this baseline is at the un-reranked level (KTD5)
without changing the shared service's global config.

gbrain emits lowercased slugs without ``.md``; we resolve each to the actual
repo-relative file path (case-insensitive) so baseline paths match hypermnesic's
path format and the human-judged labels (the Class-B case-variant issue).

Run on the homelab (where the CLI shares the MCP backend, config, and
ZeroEntropy key — the Mac CLI is version-behind and unsuitable, KTD5).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

_LINE = re.compile(r"^\[[0-9.]+\]\s+(\S+)\s+--")
_SKIP = {".git", ".hypermnesic", ".obsidian", "node_modules", ".brv"}


def slug_to_path_map(corpus: Path) -> dict[str, str]:
    m: dict[str, str] = {}
    for p in sorted(corpus.rglob("*.md")):
        if any(part in _SKIP for part in p.relative_to(corpus).parts):
            continue
        rel = p.relative_to(corpus).as_posix()
        m[rel[:-3].lower()] = rel  # key: path without .md, lowercased
    return m


def capture_query(gbrain: str, query: str, limit: int = 50) -> list[str]:
    out = subprocess.run([gbrain, "search", query, "--limit", str(limit)],
                         capture_output=True, text=True, timeout=120).stdout
    slugs = []
    for line in out.splitlines():
        m = _LINE.match(line)
        if m:
            slugs.append(m.group(1))
    return slugs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gbrain", default="/usr/local/bin/gbrain")
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args(argv)

    smap = slug_to_path_map(Path(args.corpus))
    lines = Path(args.queries).read_text(encoding="utf-8").splitlines()
    queries = [json.loads(line) for line in lines if line.strip()]
    rows = []
    for q in queries:
        slugs = capture_query(args.gbrain, q["query"])
        seen, docs = set(), []
        for s in slugs:
            path = smap.get(s.lower(), f"{s}.md")  # resolve case; else best-effort
            if path not in seen:
                seen.add(path)
                docs.append(path)
            if len(docs) >= args.k:
                break
        rows.append({"id": q["id"], "top10": docs})
        print(f"{q['id']} [{q['lang']}] {len(docs)} docs  q={q['query'][:48]!r}")
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} baseline rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
