#!/usr/bin/env python3
"""Build a PROVISIONAL frozen query set for the U5 parity harness.

Agent best-effort (operator chose this over hand-authored labels): a stratified
**known-item** set — pick real corpus docs across domains, derive a natural
topic query from each doc's title, and label that doc as the known-relevant
answer. Labels are gbrain-independent (the doc is chosen first, then a query is
written for it) but are AGENT-proposed, not human-judged — so the resulting
verdict is provisional and does NOT gate Phase 1 until an operator reviews the
labels (KTD6).

French queries come from French-titled docs (≥15 required). Output is
``queries.frozen.jsonl`` with {id, lang, query, relevant:[path], title, method}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

_FM_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.M)
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)
# Skip engine/config noise AND low-signal ingest channels (X timelines, readwise
# highlights) whose "titles" are numeric IDs — they make garbage known-item queries.
_SKIP = {".git", ".hypermnesic", ".obsidian", "node_modules", ".brv", "sources"}
_DIGIT_RUN = re.compile(r"\d{5,}")
_FRENCH_MARKERS = re.compile(
    r"\b(le|la|les|des|une|aux|pour|avec|être|était|français|réunion|compte|"
    r"entreprise|projet|cliente?|rappel|recherche|données|société|appel)\b", re.I)
_DATE_PREFIX = re.compile(r"^\d{4}[-\s]\d{2}[-\s]\d{2}\s*")
_TYPE_PREFIX = re.compile(r"^(feat|fix|chore|plan|docs?|refactor):\s*", re.I)


def _title(raw: str, path: Path) -> str:
    fm = _FM_TITLE.search(raw[:600])
    if fm:
        t = fm.group(1).strip().strip('"').strip("'")
        if t and t.lower() not in ("untitled",):
            return t
    h1 = _H1.search(raw)
    if h1:
        return h1.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ")


def _clean_query(title: str) -> str:
    q = _TYPE_PREFIX.sub("", title)
    q = _DATE_PREFIX.sub("", q)
    q = re.sub(r"^\d{2}-\d{2}\s+", "", q)       # leading MM-DD from meeting slugs
    q = re.sub(r"^[\s\-–—:]+", "", q)            # leading bullets/dashes/colons
    q = q.replace("→", "to").replace("/", " ").strip()
    q = re.sub(r"\s+", " ", q)
    return q


def _is_french(title: str, body: str) -> bool:
    sample = f"{title}\n{body[:400]}"
    markers = len(_FRENCH_MARKERS.findall(sample))
    accents = sum(sample.count(c) for c in "éèêàùçôîâ")
    return (markers >= 2) or (accents >= 4 and markers >= 1)


def build(corpus: Path, *, n_fr: int = 18, n_en: int = 14,
          seed_str: str = "hypermnesic") -> list[dict]:
    fr, en = [], []
    for p in sorted(corpus.rglob("*.md")):
        if any(part in _SKIP for part in p.relative_to(corpus).parts):
            continue
        raw = p.read_text(encoding="utf-8", errors="replace")
        body = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", raw, count=1, flags=re.S)
        if len(body.strip()) < 200:  # skip stubs — need a real answerable doc
            continue
        title = _title(raw, p)
        query = _clean_query(title)
        # substance gates: ≥3 words, ≥15 chars, no ID-like digit runs, <30% digits
        if len(query) < 15 or len(query.split()) < 3:
            continue
        if _DIGIT_RUN.search(query) or sum(c.isdigit() for c in query) > 0.3 * len(query):
            continue
        rel = p.relative_to(corpus).as_posix()
        top = rel.split("/", 1)[0]
        row = {"query": query, "relevant": [rel], "title": title, "_top": top}
        (fr if _is_french(title, body) else en).append(row)

    # deterministic stratified sample (stable seed via sha256, not salted hash())
    seed = int.from_bytes(hashlib.sha256(seed_str.encode()).digest()[:4], "big")
    rng = random.Random(seed)
    rng.shuffle(fr)
    rng.shuffle(en)

    def _diverse(rows: list[dict], n: int, per_dir_cap: int) -> list[dict]:
        counts: dict[str, int] = {}
        out = []
        for r in rows:
            if counts.get(r["_top"], 0) >= per_dir_cap:
                continue
            counts[r["_top"]] = counts.get(r["_top"], 0) + 1
            out.append(r)
            if len(out) >= n:
                break
        return out

    chosen = ([{**r, "lang": "fr"} for r in _diverse(fr, n_fr, 6)]
              + [{**r, "lang": "en"} for r in _diverse(en, n_en, 6)])

    # Expand each single-label known-item query to its equivalence class (KTD6
    # label-review move, applied systematically): content mirrors + same-event
    # meeting/source. Keeps relevant_primary for provenance.
    import corpus_equivalence
    classes = corpus_equivalence.equivalence_classes(corpus)

    out = []
    for i, r in enumerate(chosen, 1):
        primary = r["relevant"][0]
        relevant = classes.get(primary, [primary])
        out.append({"id": f"q{i:02d}", "lang": r["lang"], "query": r["query"],
                    "relevant": relevant, "relevant_primary": primary,
                    "title": r["title"],
                    "method": "known-item-provisional-agent-labeled+equivalence-expanded"})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-fr", type=int, default=18)
    ap.add_argument("--n-en", type=int, default=14)
    args = ap.parse_args(argv)
    rows = build(Path(args.corpus), n_fr=args.n_fr, n_en=args.n_en)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_fr = sum(1 for r in rows if r["lang"] == "fr")
    print(f"wrote {len(rows)} queries ({n_fr} fr / {len(rows) - n_fr} en) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
