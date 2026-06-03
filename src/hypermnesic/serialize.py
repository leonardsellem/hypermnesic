"""U12 (guard portion) — protected-path write guard + within-repo check. [R15/R17]

A **rule-based denylist** refused unconditionally regardless of caller — the rule
(file class), not a fixed list, so it holds when the engine drops into an
arbitrary repo it has never seen: ``.git/``, CI/workflow dirs, agent-instruction
files *anywhere* (CLAUDE.md/AGENTS.md/…, nested too), Obsidian/agent config dirs,
script/hook dirs, and ``.gitignore`` (never a write target). Plus a within-repo
resolution check (no ``..`` traversal, no absolute path, no symlink escape) and
an optional per-repo writable-path allowlist.

(Multi-writer serialization — worktree + path-scoped locks — is the other half of
U12 and is tracked as a follow-up; this module ships the safety guard that must
exist before any write path runs on a real repo.)
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

# Agent-instruction files (privilege escalation if writable) — matched anywhere.
_INSTRUCTION_FILES = {"claude.md", "agents.md", "gemini.md", ".cursorrules",
                      "copilot-instructions.md"}
# Directory components that are off-limits anywhere in the path.
_PROTECTED_DIRS = {".git", ".github", ".obsidian", ".claude", ".codex", "views",
                   "scripts", "bin", "hooks", "skills", ".hypermnesic"}
_NEVER_FILES = {".gitignore", ".gitattributes", ".gitmodules"}


class WriteGuardError(Exception):
    """Raised when a write targets a protected path, escapes the repo, or is
    outside the per-repo allowlist."""


# The single allowlist-miss reason. A sentinel so ``check`` can re-derive its exact
# (path-interpolated) message while the predicate stays path-clean — see writable_reason.
_NOT_IN_ALLOWLIST = "not in writable allowlist"


def protected_reason(rel_path: str) -> str | None:
    """Return why ``rel_path`` is protected, or None if it is a writable class."""
    p = PurePosixPath(rel_path)
    parts = p.parts
    if not parts:
        return "empty path"
    if p.name in _NEVER_FILES:
        return f"never-write file ({p.name})"
    if p.name.lower() in _INSTRUCTION_FILES:
        return f"agent-instruction file ({p.name})"
    for part in parts[:-1]:
        if part in _PROTECTED_DIRS:
            return f"protected dir ({part}/)"
    if parts[0] in _PROTECTED_DIRS:
        return f"protected dir ({parts[0]}/)"
    if "workflows" in parts and ".github" in parts:
        return "CI workflow dir"
    if p.name.startswith("install-git-hooks"):
        return "git-hook installer"
    return None


def writable_reason(rel_path: str, *, allowlist: list[str] | None = None) -> str | None:
    """Why a write to ``rel_path`` would be refused, or None if it is writable.

    The single source of truth for the "is this path writable" decision (U1): the
    protected-path class refusal (allowlist-INDEPENDENT — the real bound) first, then
    the optional allowlist narrowing. ``allowlist=None`` is blocklist mode (protected
    classes are the sole bound). Pure and path-clean: the returned reason never
    interpolates ``rel_path``, so the folder classifier (U2) can surface it verbatim
    and ``check`` (which DOES interpolate) re-derives its message from the sentinel.
    """
    reason = protected_reason(rel_path)
    if reason:
        return reason
    if allowlist is not None and not any(
            rel_path == a or rel_path.startswith(a.rstrip("/") + "/") for a in allowlist):
        return _NOT_IN_ALLOWLIST
    return None


def check(repo, rel_path: str, *, allowlist: list[str] | None = None) -> str:
    """Validate a write to ``rel_path`` within ``repo``. Return the normalized
    repo-relative posix path, or raise WriteGuardError.

    The within-repo resolution + absolute/traversal checks stay HERE (they need repo
    context, V6); the path-class + allowlist decision is delegated to
    :func:`writable_reason` so discovery and the write path share one rule. Messages
    are preserved exactly (protected-path vs allowlist), re-derived from the reason.
    """
    repo_root = Path(repo).resolve()
    if PurePosixPath(rel_path).is_absolute() or Path(rel_path).is_absolute():
        raise WriteGuardError(f"absolute path not allowed: {rel_path}")
    resolved = (repo_root / rel_path).resolve()
    try:
        rel = resolved.relative_to(repo_root)
    except ValueError:
        raise WriteGuardError(f"path escapes repo root: {rel_path}") from None
    rel_posix = rel.as_posix()
    reason = writable_reason(rel_posix, allowlist=allowlist)
    if reason == _NOT_IN_ALLOWLIST:
        raise WriteGuardError(f"path {rel_posix!r} not in writable allowlist")
    if reason:
        raise WriteGuardError(f"refused protected path {rel_posix!r}: {reason}")
    return rel_posix


# --- multi-writer serialization (KTD9: a single indexer holds a write lock) ---

class LockBusyError(Exception):
    """Raised when an exclusive lock is already held (non-blocking acquire)."""


class DirtyTreeError(Exception):
    """Preflight: the working tree has uncommitted changes."""


class HeadDriftError(Exception):
    """Preflight: HEAD moved out from under us (multi-host head-drift)."""


class FileLock:
    """Advisory exclusive ``flock``. Conflicts across descriptors even in-process,
    so concurrent broad reindexers / writers serialize (no SQLite corruption)."""

    def __init__(self, lock_path):
        self.path = Path(lock_path)
        self._fd: int | None = None

    def acquire(self, *, blocking: bool = False) -> FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except OSError as exc:
            os.close(fd)
            raise LockBusyError(f"lock busy: {self.path}") from exc
        self._fd = fd
        return self

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


def _state_dir(repo) -> Path:
    return Path(repo) / ".hypermnesic"


def index_write_lock(repo) -> FileLock:
    """The single-indexer lock (broad writers / reindex hold this)."""
    return FileLock(_state_dir(repo) / "index.lock")


def path_lock(repo, rel_path: str) -> FileLock:
    """A narrow, path-scoped lock — distinct paths proceed concurrently."""
    h = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:16]
    return FileLock(_state_dir(repo) / "locks" / f"{h}.lock")


class BranchExistsError(Exception):
    """Raised when a proposal branch already exists (caller decides idempotency)."""


def branch_commit_transaction(repo, branch: str, base: str,
                              file_contents: dict[str, str], message: str) -> str:
    """Land ``file_contents`` as ONE atomic commit on a fresh ``branch`` cut from
    ``base`` — inside an isolated git worktree, never touching the owner's live
    HEAD (the branch they read in Obsidian). [U18]

    This is the net-new branch+worktree commit machinery the kernel lacked:
    ``commit_note`` commits a single path to HEAD; this stages a *set* of paths on
    a side branch. Mirrors ``index.reindex_isolated``'s worktree posture (build in
    isolation, never block / touch the live tree). Callers gate each file's content
    *before* calling, so a gate abort never reaches here and no branch is created.
    On any failure the branch is rolled back so no partial/orphan branch is left.

    Returns the new commit sha. Raises ``BranchExistsError`` if ``branch`` exists.
    """
    repo = Path(repo)
    if branch in _local_branches(repo):
        raise BranchExistsError(branch)
    rc = subprocess.run(["git", "-C", str(repo), "branch", branch, base],
                        capture_output=True, text=True)
    if rc.returncode != 0:
        raise BranchExistsError(f"could not create branch {branch}: {rc.stderr.strip()}")

    wt = Path(tempfile.mkdtemp(prefix="hypermnesic-propose-"))
    try:
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "--force", str(wt), branch],
                       check=True, capture_output=True, text=True)
        for rel, text in file_contents.items():
            fp = wt / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(text, encoding="utf-8")
            subprocess.run(["git", "-C", str(wt), "add", "--", rel],
                           check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", message],
                       check=True, capture_output=True, text=True)
        return subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        # roll back: drop the worktree and the half-built branch — no orphan ref.
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                       capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo), "branch", "-D", branch],
                       capture_output=True, text=True)
        raise
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                       capture_output=True, text=True)
        shutil.rmtree(wt, ignore_errors=True)


def _local_branches(repo) -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "for-each-ref", "--format=%(refname:short)", "refs/heads"],
        capture_output=True, text=True).stdout
    return set(out.split())


def preflight(repo, *, expected_head: str | None = None, require_clean: bool = False) -> str:
    """Return HEAD; raise on head-drift or (for broad writers) a dirty tree.

    Callers fetch + fast-forward before preflight so head-drift is resolved; this
    detects the unresolved case. The engine's own ``.hypermnesic/`` state dir is
    ignored via ``.git/info/exclude`` so it never shows as a dirty change."""
    repo = Path(repo)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip() or None
    if expected_head is not None and head != expected_head:
        raise HeadDriftError(f"HEAD drifted {expected_head} -> {head}")
    if require_clean:
        porcelain = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                   capture_output=True, text=True).stdout.strip()
        if porcelain:
            raise DirtyTreeError(f"working tree not clean:\n{porcelain}")
    return head

