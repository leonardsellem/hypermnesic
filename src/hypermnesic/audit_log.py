"""U11 — append-only audit log (summaries only, server-set actor). [R12/R17]

Every write appends one structured entry ``{ts, actor, verb, path, old_sha,
new_sha, summary}`` to a JSONL log. **Summaries only — never page bodies** (the
``--dry-run --json`` private-content-leak scar). The ``actor`` is **server-set**
(verified Tailscale node identity, or a fixed sentinel) and a caller-supplied
actor is ignored — never trusted. A **reconciler** back-fills entries for
staged-but-unlogged commits (the crash-between-stage-and-append case from U7), so
a gap is recoverable, not permanent.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from pathlib import Path

MAX_SUMMARY = 280  # summaries are short by contract; truncate defensively
_SENTINEL = "server:hypermnesic"


def _git(repo, *args) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""


def tailscale_actor() -> str:
    """Verified Tailscale node identity, or a fixed server sentinel."""
    try:
        out = subprocess.run(["tailscale", "status", "--json"],
                             capture_output=True, text=True, timeout=5, check=True).stdout
        self_node = json.loads(out).get("Self", {})
        name = self_node.get("DNSName", "").rstrip(".") or self_node.get("HostName", "")
        return f"tailnet:{name}" if name else _SENTINEL
    except Exception:
        return _SENTINEL


class AuditLog:
    def __init__(self, log_path, actor_fn=tailscale_actor):
        self.path = Path(log_path)
        self._actor_fn = actor_fn

    def _now(self) -> str:
        return _dt.datetime.now(_dt.UTC).isoformat()

    def append(self, verb: str, path: str, old_sha: str | None, new_sha: str | None,
               summary: str, *, ts: str | None = None, actor=None) -> dict:
        """Append one entry. ``actor`` is IGNORED — the log sets it (R17)."""
        entry = {
            "ts": ts or self._now(),
            "actor": self._actor_fn(),          # server-set; caller value ignored
            "verb": verb,
            "path": path,
            "old_sha": old_sha,
            "new_sha": new_sha,
            "summary": (summary or "")[:MAX_SUMMARY],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:  # append-only
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in
                self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def last_new_sha(self) -> str | None:
        ents = self.entries()
        for e in reversed(ents):
            if e.get("new_sha"):
                return e["new_sha"]
        return None

    def reconcile(self, repo, summarize=None) -> int:
        """Back-fill log entries for commits on HEAD not yet logged. Returns count."""
        head = _git(repo, "rev-parse", "HEAD")
        last = self.last_new_sha()
        if not head or head == last:
            return 0
        if last and _git(repo, "cat-file", "-t", last) == "commit":
            commits = _git(repo, "rev-list", "--reverse", f"{last}..HEAD").split()
        else:
            commits = [head]  # no usable checkpoint → record current HEAD only
        n = 0
        prev = last
        for c in commits:
            subject = _git(repo, "log", "-1", "--format=%s", c)
            self.append(verb="reconcile", path="", old_sha=prev, new_sha=c,
                        summary=(summarize(c) if summarize else subject))
            prev = c
            n += 1
        return n
