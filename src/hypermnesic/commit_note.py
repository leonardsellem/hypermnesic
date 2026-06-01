"""U7 — commit_note: the single sanctioned write primitive. [R7/R8/R14]

Ordered, no DB-first lane: **guard → frontmatter gate (U8) → write file → git
stage+commit → synchronous lexical+graph extract → append audit log (U11) →
return the git diff**. The durable effect is the file write + commit (git is the
only sync layer). Embedding is **async — never blocks** (AE5): the page is
findable lexically immediately; dense vectors catch up later. Idempotent on the
resulting content (a no-op edit neither commits nor logs).

Deviation note: the plan's sequence says "git stage"; this commits per note
(write+stage+commit) so the durable unit is a real commit — recoverable via the
U11 reconciler (HEAD-based) and the U9 SHA checkpoint, and matches "git is the
only sync layer". Recorded in implementation-notes.md.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from hypermnesic import frontmatter_gate as fg
from hypermnesic import ingest, serialize


@dataclass
class CommitResult:
    path: str
    created: bool
    new_sha: str | None
    diff: str
    noop: bool = False


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def _render_new(set_fields: dict, body: str) -> str:
    if not set_fields:
        return body
    y = fg._yaml()
    buf = StringIO()
    y.dump(dict(set_fields), buf)
    return "---\n" + buf.getvalue() + "---\n" + body


def commit_note(repo, rel_path: str, *, body: str | None = None,
                set_fields: dict | None = None, summary: str | None = None,
                idx=None, log=None, allowlist: list[str] | None = None) -> CommitResult:
    repo = Path(repo)
    rel = serialize.check(repo, rel_path, allowlist=allowlist)  # guard FIRST (R17)
    fpath = repo / rel
    existed = fpath.exists()

    if existed:
        original = fpath.read_text(encoding="utf-8")
        new_text = fg.gated_edit(original, body=body, set_fields=set_fields)  # diff-or-die (U8)
        if new_text == original:  # idempotent: identical content → no-op
            head = _git(repo, "rev-parse", "HEAD").stdout.strip() or None
            return CommitResult(rel, False, head, "", noop=True)
    else:
        new_text = _render_new(set_fields or {}, body or "")

    old_sha = _git(repo, "rev-parse", "HEAD").stdout.strip() or None
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(new_text, encoding="utf-8")
    _git(repo, "add", "--", rel)
    if _git(repo, "diff", "--cached", "--quiet").returncode == 0:  # nothing staged
        return CommitResult(rel, not existed, old_sha, "", noop=True)

    msg = summary or f"commit_note: {rel}"
    _git(repo, "commit", "-q", "-m", msg)
    new_sha = _git(repo, "rev-parse", "HEAD").stdout.strip() or None

    # synchronous lexical + graph extraction (embeddings are async — AE5)
    if idx is not None:
        idx.upsert_lexical(rel, ingest.chunks_for_text(rel, new_text))

    # append audit log — summaries only, server-set actor (U11)
    if log is not None:
        log.append(verb=("create" if not existed else "edit"), path=rel,
                   old_sha=old_sha, new_sha=new_sha, summary=summary or msg)

    diff = _git(repo, "show", "--format=", "--patch", new_sha).stdout
    return CommitResult(rel, not existed, new_sha, diff)
