"""Deployment provisioning: the opt-in post-merge convergence hook (U33).

The hook pre-warms the index after a pull (FR-R36..R38). It is **opt-in**,
**idempotent** (re-running installs exactly one managed block), and
**non-destructive**: a clearly-delimited managed block is appended to — or updated
inside — an existing hook, never overwriting the operator's own hook content. The
uninstall path removes *only* the managed block. Lazy read-time convergence
(U27/U28) remains the correctness guarantee; the hook only warms the cache, and
it ends with ``|| true`` so a convergence hiccup never fails a ``git pull``.

(U34 extends this module with role-aware service/config provisioning.)
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

_MANAGED_BEGIN = "# >>> hypermnesic managed block (do not edit inside markers) >>>"
_MANAGED_END = "# <<< hypermnesic managed block <<<"
# Hooks that warm the index. post-merge fires after `git pull` fast-forwards/merges;
# the set is extensible (post-rewrite/post-checkout) without changing the contract.
HOOK_NAMES = ("post-merge",)


def _hypermnesic_exe() -> str:
    """Absolute path to the installed console script when resolvable (so the hook is
    robust regardless of the runtime PATH); falls back to the bare name otherwise."""
    return shutil.which("hypermnesic") or "hypermnesic"


def _managed_block(repo: Path) -> str:
    exe = _hypermnesic_exe()
    return "\n".join([
        _MANAGED_BEGIN,
        "# hypermnesic U33: pre-warm the index after a pull. Lazy read-time convergence",
        "# is the correctness guarantee (FR-R38); this only warms the cache.",
        f'"{exe}" converge "{repo}" >/dev/null 2>&1 || true',
        _MANAGED_END,
        "",
    ])


def _strip_managed(text: str) -> str:
    """Return ``text`` with the managed block (BEGIN..END inclusive) removed, leaving
    every other line — including any operator content before or after — intact."""
    out: list[str] = []
    skip = False
    for ln in text.splitlines():
        if ln.strip() == _MANAGED_BEGIN:
            skip = True
            continue
        if skip:
            if ln.strip() == _MANAGED_END:
                skip = False
            continue
        out.append(ln)
    return "\n".join(out)


def install_hooks(repo) -> dict:
    """Install/refresh the managed post-merge hook in ``repo/.git/hooks``. Idempotent
    and non-destructive. Returns the installed hook names + hooks dir."""
    repo = Path(repo).resolve()
    if not (repo / ".git").exists():
        raise FileNotFoundError(f"not a git repo (no .git): {repo}")
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for name in HOOK_NAMES:
        hook = hooks_dir / name
        block = _managed_block(repo)
        if hook.exists():
            base = _strip_managed(hook.read_text(encoding="utf-8")).rstrip("\n")
            new = (base + "\n\n" + block) if base.strip() else "#!/bin/sh\n\n" + block
        else:
            new = "#!/bin/sh\n\n" + block
        hook.write_text(new, encoding="utf-8")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(name)
    return {"installed": installed, "hooks_dir": str(hooks_dir)}


def uninstall_hooks(repo) -> dict:
    """Remove only the managed block from each managed hook (operator content kept).
    A hook left as a bare shebang is removed entirely."""
    repo = Path(repo).resolve()
    hooks_dir = repo / ".git" / "hooks"
    removed: list[str] = []
    for name in HOOK_NAMES:
        hook = hooks_dir / name
        if not hook.exists() or _MANAGED_BEGIN not in hook.read_text(encoding="utf-8"):
            continue
        stripped = _strip_managed(hook.read_text(encoding="utf-8")).rstrip("\n")
        if stripped.strip() in ("", "#!/bin/sh"):
            hook.unlink()                       # nothing left but a bare shebang → remove
        else:
            hook.write_text(stripped + "\n", encoding="utf-8")
        removed.append(name)
    return {"removed": removed}
