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

import difflib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from hypermnesic import frontmatter_gate as fg
from hypermnesic import ingest, serialize

# Bounded retry when the shared remote advances non-fast-forward between our
# fetch+ff and our push (multiple pushers on origin/main). Module-level so tests
# can shrink it; small because contention on a single-note write is brief.
_PUSH_MAX_ATTEMPTS = 5


class GitCoordinationError(Exception):
    """A coordinated write could not reach the shared remote (fetch/ff/push failed
    or the non-ff retry was exhausted). Surfaced as a refusal — never swallowed —
    after the local-ahead commit is dropped so it cannot wedge ``gbrain-pull --ff-only``."""


@dataclass
class CommitResult:
    path: str
    created: bool
    new_sha: str | None
    diff: str
    noop: bool = False
    dry_run: bool = False


def _preview_diff(rel: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        f"a/{rel}", f"b/{rel}"))


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def _git_checked(repo, *args) -> subprocess.CompletedProcess:
    """``_git`` that raises on a non-zero return code, so a failed stage/commit/push
    surfaces as a refusal instead of a silent success (U11)."""
    cp = _git(repo, *args)
    if cp.returncode != 0:
        raise GitCoordinationError(
            f"git {' '.join(args)} failed (rc={cp.returncode}): {cp.stderr.strip()}")
    return cp


def _head(repo) -> str | None:
    return _git(repo, "rev-parse", "HEAD").stdout.strip() or None


def _current_branch(repo) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"


def _default_remote(repo) -> str | None:
    """The push target — ``origin`` when present, else the first remote, else None
    (a local-only / portable checkout, which skips coordination entirely)."""
    remotes = _git(repo, "remote").stdout.split()
    if "origin" in remotes:
        return "origin"
    return remotes[0] if remotes else None


def _looks_non_ff(text: str) -> bool:
    t = text.lower()
    return any(s in t for s in ("non-fast-forward", "fetch first",
                                "failed to push some refs", "[rejected]", " rejected"))


def _fetch_and_ff(repo, remote, branch) -> None:
    """Fetch the shared remote and fast-forward the local branch to its tip. We hold
    no local commit yet, so this is a clean ff or a no-op; a divergence we cannot
    ff is a refusal. Pairs with the post-fetch ``preflight(expected_head=base)`` drift
    guard (V8 mitigation: fetch+ff before preflight)."""
    if _git(repo, "fetch", remote).returncode != 0:
        raise GitCoordinationError(f"git fetch {remote} failed (remote unreachable?)")
    tracking = f"{remote}/{branch}"
    if _git(repo, "rev-parse", "--verify", "--quiet", tracking).returncode != 0:
        return                                  # remote has no such branch yet → push creates it
    cp = _git(repo, "merge", "--ff-only", tracking)
    if cp.returncode != 0:
        raise GitCoordinationError(
            f"cannot fast-forward {branch} to {tracking}: {cp.stderr.strip()}")


def _push_with_retry(repo, remote, branch) -> None:
    """Push the local commit to the shared remote, retrying on non-fast-forward by
    fetching + rebasing our single commit onto the advanced tip. On an unrecoverable
    failure (conflict, auth/network, exhausted retries) drop the local-ahead commit
    (``reset --hard`` to the remote tip) and raise — never leave an un-pushed commit."""
    for _ in range(_PUSH_MAX_ATTEMPTS):
        cp = _git(repo, "push", remote, branch)
        if cp.returncode == 0:
            return
        if not _looks_non_ff(cp.stderr + cp.stdout):
            break                               # auth/network/hook reject → unrecoverable
        if _git(repo, "fetch", remote).returncode != 0:
            break
        rb = _git(repo, "rebase", f"{remote}/{branch}")
        if rb.returncode != 0:
            _git(repo, "rebase", "--abort")     # conflicting change → cannot converge cleanly
            break
    # unrecoverable / exhausted → restore a clean, non-local-ahead tree, then refuse.
    _git(repo, "fetch", remote)
    _git(repo, "reset", "--hard", f"{remote}/{branch}")
    raise GitCoordinationError(
        f"push to {remote}/{branch} did not succeed; aborted with no local-ahead commit")


def _render_new(set_fields: dict, body: str) -> str:
    if not set_fields:
        return body
    y = fg._yaml()
    buf = StringIO()
    y.dump(dict(set_fields), buf)
    return "---\n" + buf.getvalue() + "---\n" + body


def commit_note(repo, rel_path: str, *, body: str | None = None,
                set_fields: dict | None = None, summary: str | None = None,
                idx=None, log=None, allowlist: list[str] | None = None,
                dry_run: bool = False) -> CommitResult:
    repo = Path(repo)
    rel = serialize.check(repo, rel_path, allowlist=allowlist)  # guard FIRST (R17)
    if dry_run:
        fpath = repo / rel
        existed = fpath.exists()
        original = fpath.read_text(encoding="utf-8") if existed else ""
        new_text = (fg.gated_edit(original, body=body, set_fields=set_fields) if existed
                    else _render_new(set_fields or {}, body or ""))  # gate may abort
        return CommitResult(rel, created=not existed, new_sha=None,
                            diff=_preview_diff(rel, original, new_text),
                            noop=(new_text == original), dry_run=True)
    lock = serialize.index_write_lock(repo).acquire()           # single-writer (KTD9/R13)
    try:
        return _commit_locked(repo, rel, body, set_fields, summary, idx, log)
    finally:
        lock.release()


def _commit_locked(repo, rel, body, set_fields, summary, idx, log) -> CommitResult:
    fpath = repo / rel
    existed = fpath.exists()

    if existed:
        original = fpath.read_text(encoding="utf-8")
        new_text = fg.gated_edit(original, body=body, set_fields=set_fields)  # diff-or-die (U8)
        if new_text == original:  # idempotent: identical content → no-op
            return CommitResult(rel, False, _head(repo), "", noop=True)
    else:
        new_text = _render_new(set_fields or {}, body or "")

    # --- multi-host coordination (U11): on a shared remote, converge BEFORE writing
    # so a stale-base edit aborts clean (no clobber), and push so we never commit
    # local-only (which would wedge gbrain-pull --ff-only). No remote → solo path.
    remote = _default_remote(repo)
    branch = _current_branch(repo)
    base = _head(repo)                                      # base captured at edit base-read
    if remote is not None:
        _fetch_and_ff(repo, remote, branch)                # fetch + fast-forward (raises)
        serialize.preflight(repo, expected_head=base)      # HeadDriftError on base drift

    old_sha = base
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(new_text, encoding="utf-8")
    _git_checked(repo, "add", "--", rel)
    # Path-scoped throughout (coexistence): on a shared checkout another committer may
    # have unrelated changes staged in the index. Scope both the noop check and the
    # commit to THIS note's path so we never sweep a fleet committer's staged work into
    # our commit (and push it). The process-local index_write_lock gives no cross-process
    # exclusion, so the pathspec — not the lock — is what isolates our write.
    if _git(repo, "diff", "--cached", "--quiet", "--", rel).returncode == 0:  # nothing staged
        return CommitResult(rel, not existed, old_sha, "", noop=True)

    msg = summary or f"commit_note: {rel}"
    _git_checked(repo, "commit", "-q", "-m", msg, "--", rel)
    if remote is not None:
        _push_with_retry(repo, remote, branch)             # push, retry on non-ff; raises
    new_sha = _head(repo)                                  # re-read: a retry rebase rewrites it

    # synchronous lexical + graph extraction (embeddings are async — AE5)
    if idx is not None:
        idx.upsert_lexical(rel, ingest.chunks_for_text(rel, new_text))

    # append audit log — summaries only, server-set actor (U11). Only after the write
    # has reached the shared remote (or is purely local) — never on a refused push.
    if log is not None:
        log.append(verb=("create" if not existed else "edit"), path=rel,
                   old_sha=old_sha, new_sha=new_sha, summary=summary or msg)

    diff = _git(repo, "show", "--format=", "--patch", new_sha).stdout
    return CommitResult(rel, not existed, new_sha, diff)


def rename_note(repo, old_path: str, new_path: str, *, body: str | None = None,
                set_fields: dict | None = None, summary: str | None = None,
                idx=None, log=None, allowlist: list[str] | None = None,
                tombstone_fn: Callable[[str], None] | None = None,
                dry_run: bool = False) -> CommitResult:
    """U10 — rename/move as one atomic surface: git mv + index re-key, with no
    re-materialization of the old slug. Optional content edit in the same move goes
    through the diff-or-die gate first (abort = no git op).

    ``tombstone_fn`` (U13) is an optional sink invoked with the **neutral
    repo-relative old path** just before the removing git op, so a deployment that
    coexists with an external DB→disk restore can record the removed slug and prevent
    its resurrection. It defaults to ``None`` (no-op): the engine stays repo-agnostic
    — it owns no external path or format, so it takes on no dependency on any
    particular companion system."""
    repo = Path(repo)
    new_rel = serialize.check(repo, new_path, allowlist=allowlist)   # guard both ends
    old_rel = serialize.check(repo, old_path, allowlist=allowlist)
    if dry_run:
        old_fp = repo / old_rel
        if not old_fp.exists():
            raise FileNotFoundError(old_rel)
        original = old_fp.read_text(encoding="utf-8")
        new_text = (fg.gated_edit(original, body=body, set_fields=set_fields)
                    if (body is not None or set_fields) else original)   # gate may abort
        diff = f"rename: {old_rel} -> {new_rel}\n" + (
            _preview_diff(new_rel, original, new_text) if new_text != original else "")
        return CommitResult(new_rel, created=False, new_sha=None, diff=diff, dry_run=True)
    lock = serialize.index_write_lock(repo).acquire()               # single-writer (KTD9/R13)
    try:
        return _rename_locked(repo, old_rel, new_rel, body, set_fields, summary,
                              idx, log, tombstone_fn)
    finally:
        lock.release()


def _rename_locked(repo, old_rel, new_rel, body, set_fields, summary, idx, log,
                   tombstone_fn) -> CommitResult:
    old_fp = repo / old_rel
    if not old_fp.exists():
        raise FileNotFoundError(old_rel)

    original = old_fp.read_text(encoding="utf-8")
    new_text = original
    if body is not None or set_fields:
        new_text = fg.gated_edit(original, body=body, set_fields=set_fields)  # may abort first

    # Tombstone-first (U13): record the removed slug BEFORE the git op — after the gate
    # (so a gate-abort leaves no orphan tombstone), so a crash mid-op cannot leave an
    # un-tombstoned orphan. The engine passes the neutral old rel-path; the injected
    # sink owns any external path/format. No sink → no-op (portable, no coupling).
    if tombstone_fn is not None:
        tombstone_fn(old_rel)

    old_sha = _git(repo, "rev-parse", "HEAD").stdout.strip() or None
    _git(repo, "mv", old_rel, new_rel)
    new_fp = repo / new_rel
    if new_text != original:
        new_fp.write_text(new_text, encoding="utf-8")
    _git(repo, "add", "--", new_rel)
    # Path-scoped commit (coexistence): only the moved pair, never a fleet committer's
    # other staged changes on the shared checkout.
    _git(repo, "commit", "-q", "-m", summary or f"rename: {old_rel} -> {new_rel}",
         "--", old_rel, new_rel)
    new_sha = _git(repo, "rev-parse", "HEAD").stdout.strip() or None

    if idx is not None:
        idx.rekey_path(old_rel, new_rel)                 # follow the moved blob
        if new_text != original:
            idx.upsert_lexical(new_rel, ingest.chunks_for_text(new_rel, new_text))
    if log is not None:
        log.append(verb="rename", path=new_rel, old_sha=old_sha, new_sha=new_sha,
                   summary=summary or f"{old_rel} -> {new_rel}")
    diff = _git(repo, "show", "--format=", "--patch", new_sha).stdout
    return CommitResult(new_rel, False, new_sha, diff)
