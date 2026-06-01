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

from pathlib import Path, PurePosixPath

# Agent-instruction files (privilege escalation if writable) — matched anywhere.
_INSTRUCTION_FILES = {"claude.md", "agents.md", "gemini.md", ".cursorrules",
                      "copilot-instructions.md"}
# Directory components that are off-limits anywhere in the path.
_PROTECTED_DIRS = {".git", ".github", ".obsidian", ".claude", ".codex", "views",
                   "scripts", "bin", "hooks", ".hypermnesic"}
_NEVER_FILES = {".gitignore", ".gitattributes", ".gitmodules"}


class WriteGuardError(Exception):
    """Raised when a write targets a protected path, escapes the repo, or is
    outside the per-repo allowlist."""


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


def check(repo, rel_path: str, *, allowlist: list[str] | None = None) -> str:
    """Validate a write to ``rel_path`` within ``repo``. Return the normalized
    repo-relative posix path, or raise WriteGuardError."""
    repo_root = Path(repo).resolve()
    if PurePosixPath(rel_path).is_absolute() or Path(rel_path).is_absolute():
        raise WriteGuardError(f"absolute path not allowed: {rel_path}")
    resolved = (repo_root / rel_path).resolve()
    try:
        rel = resolved.relative_to(repo_root)
    except ValueError:
        raise WriteGuardError(f"path escapes repo root: {rel_path}") from None
    rel_posix = rel.as_posix()
    reason = protected_reason(rel_posix)
    if reason:
        raise WriteGuardError(f"refused protected path {rel_posix!r}: {reason}")
    if allowlist is not None:
        if not any(rel_posix == a or rel_posix.startswith(a.rstrip("/") + "/")
                   for a in allowlist):
            raise WriteGuardError(f"path {rel_posix!r} not in writable allowlist")
    return rel_posix
