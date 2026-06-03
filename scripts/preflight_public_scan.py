#!/usr/bin/env python3
"""Pre-public secret/host scrub gate (U8 / R11).

Scans the to-be-public tree for operator-private values — the operator's tailnet
name + homelab node IP, credential material (OpenAI keys, JWTs, PEM private keys,
inline token VALUES), and operator home paths — so none ships when the repo flips
public. A hit fails the run (exit 1) with file + line + pattern; the matched VALUE is
masked in output so the scan never re-prints a secret to the console / CI log.

Scope:
  - Scans git-TRACKED files (the to-be-public set; gitignored corpus/private data is
    excluded by construction).
  - Always EXCLUDES ``docs/launch/`` (the staging area — it documents the very
    secrets/decisions being prepared) and the gate's own script + test (they
    necessarily reference the deny patterns, so scanning them would self-trip).
    ``docs/archive/`` is NOT always-excluded: it is deferred in default mode but
    scanned by ``--strict``, so archiving a doc never hides a leak from the flip gate.
  - **Default mode** (the now / CI gate) additionally DEFERS the inherited
    *process-exhaust* docs (handoffs, gate-artifacts, brainstorms, plans, deploy
    runbooks, dated security reviews, threat model, gbrain-decommission state). These
    predate the public-prep work, are inert while the repo is private, and are
    scrubbed-or-pruned AT FLIP TIME (see ``docs/launch/public-launch-checklist.md``).
    They are NOT silently dropped — the run reports how many it deferred.
  - ``--strict`` scans ALL tracked files except launch/archive (+ the gate's own
    files): the FLIP-TIME gate that fails until the process-exhaust docs are
    scrubbed/pruned and history is resolved.
  - ``--history`` additionally scans ``git log -p --all`` (informational only; never
    fails the gate): the operator IP/hostname persist in historical commit diffs, and
    the rewrite-vs-accept decision is recorded in
    ``docs/launch/public-flip-runbook.md``, NOT executed here.

Usage::

    uv run python scripts/preflight_public_scan.py           # default now-gate
    uv run python scripts/preflight_public_scan.py --strict   # flip-time working-tree gate
    uv run python scripts/preflight_public_scan.py --history  # + informational history scan
    uv run python scripts/preflight_public_scan.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Operator-private deny set. Targets SPECIFIC operator identifiers + credential
# classes — NOT generic categories that have legitimate documentation uses (the CGNAT
# range 100.64.0.0/10 is allowed; only the specific homelab node IP is denied).
_DENY: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("operator-tailnet-name", re.compile(r"tail" r"dabf2")),
    ("operator-homelab-ip", re.compile(r"\b100\.103\.0\.55\b")),
    ("openai-api-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("pem-private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # a token env var assigned a REAL (≥12-char) value — not an empty `VAR=`
    # placeholder, a string-literal boundary (`TOKEN="`), or a `"…TOKEN=" not in` guard.
    ("inline-token-value",
     re.compile(r"[A-Z0-9_]*" r"TOKEN" r"\s*=\s*[\"']?[A-Za-z0-9][A-Za-z0-9_\-]{11,}")),
    ("operator-home-path", re.compile(r"/home/[a-z][a-z0-9_-]*/")),
)

# Always excluded — both default and --strict:
#  - docs/launch/ is the staging area; it documents the very secrets/decisions being
#    prepared (the flip runbook names the operator IP/host for the git-history decision),
#    so scanning it is wrong by construction.
#  - the gate's own script + test necessarily reference the deny patterns.
# NOTE: docs/archive/ is deliberately NOT here. Archived docs are deferred in default
# mode (historical) but ARE scanned by --strict, so archiving a doc never hides a leak
# from the flip-time gate (no false comfort — U21 ↔ U8 coordination).
_EXCLUDE_ALWAYS = (
    "docs/launch/",
    "scripts/preflight_public_scan.py",
    "tests/test_preflight_public_scan.py",
)

# Durable, net-new docs authored clean — scanned even in default mode.
_DURABLE_DOC_PREFIXES = ("docs/reference/", "docs/guides/")
_DURABLE_DOC_FILES = ("docs/README.md", "docs/why-hypermnesic.md")


def in_scope(path: str, *, strict: bool) -> bool:
    """Whether ``path`` (a repo-relative tracked file) is scanned in this mode."""
    if any(path == e or path.startswith(e) for e in _EXCLUDE_ALWAYS):
        return False
    if not path.startswith("docs/"):
        return True                                   # all code/config/root docs
    if strict:
        return True                                   # flip-time: scan all of docs/
    # default: only the durable, net-new docs under docs/ — the rest is process exhaust
    # deferred to the flip-time scrub.
    return path in _DURABLE_DOC_FILES or any(
        path.startswith(p) for p in _DURABLE_DOC_PREFIXES)


def _mask(s: str) -> str:
    """Mask a matched value so the scan never re-prints a secret verbatim."""
    s = s.strip()
    if len(s) <= 4:
        return (s[0] + "…") if s else "…"
    return f"{s[:3]}…{s[-2:]}"


def scan_text(text: str) -> list[tuple[str, str]]:
    """Return ``(label, masked_value)`` for every deny-set hit in ``text``."""
    hits: list[tuple[str, str]] = []
    for label, rx in _DENY:
        for m in rx.finditer(text):
            hits.append((label, _mask(m.group(0))))
    return hits


def _tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"],
                         capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def _scan_history(root: Path) -> list[dict]:
    """Informational: count deny-set occurrences across all historical commit diffs."""
    out = subprocess.run(["git", "-C", str(root), "log", "-p", "--all", "--no-color"],
                         capture_output=True, text=True).stdout
    found: list[dict] = []
    for label, rx in _DENY:
        n = len(rx.findall(out))
        if n:
            found.append({"pattern": label, "occurrences": n})
    return found


def scan(root: Path = ROOT, *, strict: bool = False, include_history: bool = False) -> dict:
    root = Path(root)
    tracked = _tracked_files(root)
    scanned = [f for f in tracked if in_scope(f, strict=strict)]
    deferred = [f for f in tracked
                if not in_scope(f, strict=strict)
                and not any(f == e or f.startswith(e) for e in _EXCLUDE_ALWAYS)]
    findings: list[dict] = []
    for rel in scanned:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                                  # binary/unreadable — no text secrets
        for ln, line in enumerate(text.splitlines(), 1):
            for label, masked in scan_text(line):
                findings.append({"file": rel, "line": ln, "pattern": label, "match": masked})
    history = _scan_history(root) if include_history else []
    return {"scanned": len(scanned), "deferred": len(deferred), "strict": strict,
            "findings": findings, "history_findings": history, "passed": not findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="hypermnesic pre-public secret/host scrub gate")
    parser.add_argument("--strict", action="store_true",
                        help="flip-time: scan ALL tracked files (incl. process-exhaust docs)")
    parser.add_argument("--history", action="store_true",
                        help="also scan git history (informational; never fails the gate)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)
    result = scan(strict=args.strict, include_history=args.history)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    mode = "strict" if args.strict else "default"
    print(f"Preflight public scan ({mode}): {result['scanned']} files scanned, "
          f"{result['deferred']} deferred (flip-time scrub — see "
          f"docs/launch/public-launch-checklist.md).")
    for f in result["findings"]:
        print(f"  LEAK [{f['pattern']}] {f['file']}:{f['line']} :: {f['match']}")
    if result["history_findings"]:
        print("  --- git history (informational; rewrite-vs-accept recorded in the runbook) ---")
        for h in result["history_findings"]:
            print(f"  hist [{h['pattern']}] {h['occurrences']} occurrence(s) in commit diffs")
    print("PASS: no operator secret/host in the scanned to-be-public surface"
          if result["passed"] else
          "FAIL: operator secret/host present — scrub before the public flip")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
