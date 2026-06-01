#!/usr/bin/env python3
"""U6 — zero-infra portability probe (onboarding-quality validation).

Validates the ``clone && init`` drop-in over additional repos with **no**
per-repo Supabase / OAuth / infra: does the index build, do ``search`` /
``build_context`` answer, and does ``init`` leave the target's tracked files
untouched (only the gitignored ``.hypermnesic/`` state dir appears)?

Build-vs-trim is settled on product grounds (KTD11), so this is an
onboarding-quality verdict, **not** the build decision. A poor result drives
onboarding rework, not abandonment.

Trust boundary: probe targets must be operator-controlled or well-known repos —
the engine does not sanitize ingested content for prompt injection, and the
index seeds Phase 1 (a retrieval-poisoning vector noted in the threat model).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from hypermnesic import graph as graph_mod
from hypermnesic import index as index_mod
from hypermnesic import retrieve


def _tracked_file_hashes(repo: Path) -> dict[str, str]:
    """Map repo-relative path -> sha256 of every git-tracked file (working tree)."""
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"],
                         capture_output=True, check=True).stdout
    result = {}
    for rel in out.split(b"\0"):
        if not rel:
            continue
        p = repo / rel.decode()
        if p.is_file():
            result[rel.decode()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def _git_status_porcelain(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                          capture_output=True, text=True, check=True).stdout.strip()


def probe_repo(repo: Path, embedder, *, kind: str, queries: list[str],
               k: int = 5) -> dict:
    repo = Path(repo)
    before = _tracked_file_hashes(repo)

    builds = False
    n_chunks = 0
    try:
        idx = index_mod.build_index(repo, embedder)  # in-repo .hypermnesic (the design)
        n_chunks = idx.stats()["chunks"]
        builds = True
    except Exception as exc:  # noqa: BLE001 — probe records, never crashes the run
        return {"kind": kind, "repo": str(repo), "builds": False, "error": repr(exc),
                "answers": False, "zero_setup": True, "tracked_unchanged": None,
                "passed": False}

    # answers?
    answered = []
    any_degraded = False
    for q in queries:
        res = retrieve.search(idx, q, embedder=embedder, k=k)
        any_degraded = any_degraded or res.degraded
        answered.append(len(res.hits) > 0)
    g = graph_mod.Graph.from_index(idx)
    ctx_ok = False
    if g.nodes:
        # pick a node with outgoing edges if any, else just confirm traversal runs
        start = next((n for n in sorted(g.nodes) if g.out_edges.get(n)), sorted(g.nodes)[0])
        ctx_ok = isinstance(graph_mod.build_context(g, start, depth=1), list)
    idx.close()

    after = _tracked_file_hashes(repo)
    tracked_unchanged = before == after
    status = _git_status_porcelain(repo)
    # the only allowed working-tree delta is the ignored state dir (so git is clean)
    state_clean = ".hypermnesic" not in status

    answers = bool(answered) and all(answered) and ctx_ok
    passed = builds and answers and tracked_unchanged and state_clean
    return {
        "kind": kind, "repo": str(repo), "builds": builds, "chunks": n_chunks,
        "answers": answers, "per_query_answered": answered, "build_context_ok": ctx_ok,
        "dense_degraded": any_degraded, "zero_setup": True,
        "tracked_unchanged": tracked_unchanged,
        "git_clean_after_init": state_clean,
        "git_status_after": status,
        "passed": passed,
    }


def run_probe(targets: list[dict], embedder) -> dict:
    """targets: [{path, kind, queries}]. Returns a structured pass/fail verdict."""
    results = [probe_repo(Path(t["path"]), embedder, kind=t["kind"],
                          queries=t["queries"]) for t in targets]
    kinds = {r["kind"] for r in results if r["passed"]}
    overall = all(r["passed"] for r in results) and {"coding", "markdown"} <= kinds
    return {"targets": results, "covered_kinds": sorted(kinds), "passed": overall}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="hypermnesic zero-infra portability probe")
    p.add_argument("--targets", required=True,
                   help="JSON file: [{path, kind: coding|markdown, queries:[...]}]")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    from hypermnesic import embed
    embed.smoke_embed_or_die()
    embedder = embed.OpenAIEmbedder()
    targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
    result = run_probe(targets, embedder)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for r in result["targets"]:
            print(f"[{r['kind']}] {r['repo']}: passed={r['passed']} "
                  f"builds={r['builds']} answers={r['answers']} "
                  f"tracked_unchanged={r['tracked_unchanged']}")
        print(f"OVERALL portability: {'PASS' if result['passed'] else 'FAIL'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
