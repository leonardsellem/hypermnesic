"""Owner-facing memory control over files, git, index, and audit log.

The source of truth remains the markdown/git tree. This module provides product
verbs over that truth; it does not introduce a second memory store.
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from hypermnesic import audit_log, folders, generated, ingest, serialize


def _git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=check)


def _head(repo: Path) -> str | None:
    return _git(repo, "rev-parse", "HEAD").stdout.strip() or None


def _last_commit(repo: Path, rel: str) -> str | None:
    return _git(repo, "log", "-1", "--format=%H", "--", rel).stdout.strip() or None


def _commit_subject(repo: Path, sha: str | None) -> str:
    if not sha:
        return ""
    return _git(repo, "log", "-1", "--format=%s", sha).stdout.strip()


def _sanitize_rel(rel: str) -> str:
    p = PurePosixPath(rel)
    if p.is_absolute() or any(part == ".." for part in p.parts):
        raise ValueError(f"path must be repo-relative and inside the vault: {rel!r}")
    return p.as_posix()


def _latest_audit_for(log: audit_log.AuditLog | None, rel: str) -> dict | None:
    if log is None:
        return None
    for entry in reversed(log.entries()):
        if entry.get("path") == rel:
            return entry
    return None


def _source_type(repo: Path, rel: str) -> str:
    fp = repo / rel
    text = fp.read_text(encoding="utf-8", errors="replace") if fp.exists() else ""
    if generated.is_generated(text):
        return "generated"
    if rel.startswith("sources/"):
        return "captured"
    return "authored"


def _title(repo: Path, rel: str) -> str:
    fp = repo / rel
    raw = fp.read_text(encoding="utf-8", errors="replace") if fp.exists() else ""
    return ingest.note_title(raw, rel)


def _snippet(idx, rel: str) -> str:
    for chunk in idx.all_chunks():
        if chunk["path"] == rel:
            return chunk["text"][:220]
    return ""


def _item(repo: Path, idx, rel: str, *, log: audit_log.AuditLog | None = None,
          allowlist: list[str] | None = None) -> dict:
    reason = serialize.writable_reason(rel, allowlist=allowlist)
    last = _last_commit(repo, rel)
    audit = _latest_audit_for(log, rel)
    return {
        "path": rel,
        "title": _title(repo, rel),
        "heading": _title(repo, rel),
        "snippet": _snippet(idx, rel),
        "last_commit": last,
        "last_commit_subject": _commit_subject(repo, last),
        "actor": audit.get("actor") if audit else "unknown",
        "audit_verb": audit.get("verb") if audit else None,
        "source_type": _source_type(repo, rel),
        "writable": reason is None,
        "protected_reason": reason,
        "provenance": {
            "source": "git-file",
            "path": rel,
            "last_commit": last,
        },
    }


def list_memories(repo, idx, *, log: audit_log.AuditLog | None = None,
                  folder: str | None = None, writable: bool | None = None,
                  source_type: str | None = None, allowlist: list[str] | None = None,
                  recent: bool = False) -> dict:
    repo = Path(repo)
    folder = folders.normalize_root(folder) if folder else ""
    items = []
    for rel in sorted(idx.all_paths()):
        if folder and not rel.startswith(folder):
            continue
        item = _item(repo, idx, rel, log=log, allowlist=allowlist)
        if writable is not None and item["writable"] is not writable:
            continue
        if source_type is not None and item["source_type"] != source_type:
            continue
        items.append(item)
    if recent:
        items.sort(key=lambda item: item["last_commit"] or "", reverse=True)
    return {
        "status": "ok",
        "items": items,
        "count": len(items),
        "filters": {
            "folder": folder,
            "writable": writable,
            "source_type": source_type,
            "recent": recent,
        },
        "degraded_lexical_only": bool(idx.stale_chunk_ids()),
        "manual_reindex_recommended": idx.get_checkpoint() not in (None, _head(repo)),
    }


def inspect_memory(repo, idx, rel_path: str, *, log: audit_log.AuditLog | None = None,
                   allowlist: list[str] | None = None) -> dict:
    repo = Path(repo)
    rel = _sanitize_rel(rel_path)
    if rel not in idx.all_paths():
        return {"status": "not_found", "path": rel, "error": "memory_not_found"}
    item = _item(repo, idx, rel, log=log, allowlist=allowlist)
    return {"status": "ok", **item}


def write_scope(repo, idx, *, allowlist: list[str] | None = None, root: str = "",
                depth: int = 1) -> dict:
    listing = folders.derive_folders(idx.all_paths(), root=root, depth=depth,
                                     effective_surface=allowlist)
    mode = "allowlist" if allowlist is not None else "blocklist"
    return {
        **listing,
        "summary": {
            "mode": mode,
            "allowlist": allowlist or [],
            "answer": (
                "Agent writes are limited to the allowlist plus protected-path guards."
                if allowlist is not None
                else "Agent writes may target unprotected paths; protected classes stay refused."
            ),
        },
    }


def _selected_items(repo: Path, idx, *, log=None, folder: str | None = None,
                    paths: list[str] | None = None, allowlist=None) -> list[dict]:
    if paths:
        out = []
        for rel in paths:
            inspected = inspect_memory(repo, idx, rel, log=log, allowlist=allowlist)
            if inspected["status"] == "ok":
                out.append(inspected)
        return out
    return list_memories(repo, idx, log=log, folder=folder, allowlist=allowlist)["items"]


def export_memories(repo, idx, dest, *, log: audit_log.AuditLog | None = None,
                    folder: str | None = None, paths: list[str] | None = None,
                    allowlist: list[str] | None = None, exported_at: str | None = None) -> dict:
    repo = Path(repo)
    dest = Path(dest)
    items = _selected_items(repo, idx, log=log, folder=folder, paths=paths, allowlist=allowlist)
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for item in items:
        rel = item["path"]
        src = repo / rel
        if not src.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append({
            "path": rel,
            "last_commit": item["last_commit"],
            "actor": item["actor"],
            "source_type": item["source_type"],
        })
    manifest = {
        "version": 1,
        "exported_at": exported_at or _dt.datetime.now(_dt.UTC).isoformat(),
        "filter": {
            "folder": folders.normalize_root(folder) if folder else "",
            "paths": paths or [],
        },
        "items": copied,
    }
    (dest / "hypermnesic-export-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "exported" if copied else "empty", "dest": str(dest),
            "count": len(copied), "manifest": "hypermnesic-export-manifest.json",
            "items": copied}


def preview_forget(repo, idx, rel_path: str, *, allowlist: list[str] | None = None) -> dict:
    repo = Path(repo)
    rel = serialize.check(repo, rel_path, allowlist=allowlist)
    if not (repo / rel).is_file():
        raise FileNotFoundError(rel)
    return {
        "stage": "preview",
        "target": inspect_memory(repo, idx, rel, allowlist=allowlist),
        "will_create_commit": True,
        "diff_intent": f"delete {rel} from the current git tree",
        "guard": {"writable": True, "protected_reason": None},
        "verification_plan": [
            "source file absent from the current tree",
            "index rows removed or convergence reports manual reindex",
            "recall no longer returns the removed current source path",
        ],
        "limits": [
            "This removes current source content; git history and old chat contexts may still "
            "contain prior mentions.",
            "Generated/index state is disposable and distinct from source deletion.",
        ],
    }


def apply_forget(repo, idx, rel_path: str, *, log: audit_log.AuditLog | None = None,
                 allowlist: list[str] | None = None, summary: str | None = None) -> dict:
    repo = Path(repo)
    rel = serialize.check(repo, rel_path, allowlist=allowlist)
    serialize.preflight(repo, require_clean=True)
    if not (repo / rel).is_file():
        raise FileNotFoundError(rel)
    lock = serialize.index_write_lock(repo).acquire()
    try:
        old_sha = _head(repo)
        _git(repo, "rm", "-q", "--", rel, check=True)
        _git(repo, "commit", "-q", "-m", summary or f"forget: {rel}", "--", rel, check=True)
        new_sha = _head(repo)
        idx.remove_path(rel)
        idx.set_checkpoint(new_sha)
        if log is not None:
            log.append("forget", rel, old_sha, new_sha, summary or f"forget: {rel}")
        return {
            "stage": "applied",
            "path": rel,
            "commit": new_sha,
            "verification": {
                "source_exists": (repo / rel).exists(),
                "index_contains_path": rel in idx.all_paths(),
                "manual_reindex_recommended": False,
            },
            "limits": preview_forget_limits(),
        }
    finally:
        lock.release()


def preview_forget_limits() -> list[str]:
    return [
        "Current source content is removed; git history may still contain previous content.",
        "Generated/index state is disposable and can be rebuilt from current files.",
        "Old chat contexts outside the vault are not erased by this git commit.",
    ]


def _changed_md_paths(repo: Path, sha: str) -> list[str]:
    out = _git(repo, "show", "--format=", "--name-only", sha, check=True).stdout
    return sorted(path for path in out.splitlines() if path.endswith(".md"))


def preview_revert(repo, sha: str) -> dict:
    repo = Path(repo)
    if _git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        return {"stage": "preview", "commit": sha, "supported": False,
                "reason": "commit_not_found", "paths": []}
    paths = _changed_md_paths(repo, sha)
    supported = len(paths) == 1
    return {"stage": "preview", "commit": sha, "supported": supported, "paths": paths,
            "reason": None if supported else "only single-file markdown commits are supported"}


def apply_revert(repo, idx, sha: str, *, log: audit_log.AuditLog | None = None) -> dict:
    repo = Path(repo)
    preview = preview_revert(repo, sha)
    if not preview["supported"]:
        raise ValueError(preview["reason"])
    serialize.preflight(repo, require_clean=True)
    paths = preview["paths"]
    old_sha = _head(repo)
    cp = _git(repo, "revert", "--no-edit", sha)
    if cp.returncode != 0:
        _git(repo, "revert", "--abort")
        raise RuntimeError(cp.stderr.strip() or "git revert failed")
    new_sha = _head(repo)
    for rel in paths:
        fp = repo / rel
        if fp.exists():
            idx.upsert_lexical(rel, ingest.chunks_for_text(rel, fp.read_text(encoding="utf-8")))
        else:
            idx.remove_path(rel)
    idx.set_checkpoint(new_sha)
    if log is not None:
        log.append("revert", paths[0], old_sha, new_sha, f"revert: {sha}")
    return {"stage": "applied", "commit": new_sha, "reverted": sha,
            "paths": paths,
            "verification": {"paths_present": {rel: (repo / rel).exists() for rel in paths}}}


def audit_view(log: audit_log.AuditLog, *, limit: int | None = None) -> dict:
    entries = log.entries()
    if limit is not None:
        entries = entries[-limit:]
    safe = []
    for entry in entries:
        safe.append({
            "ts": entry.get("ts"),
            "actor": entry.get("actor"),
            "verb": entry.get("verb"),
            "attempted_verb": entry.get("attempted_verb"),
            "path": entry.get("path"),
            "old_sha": entry.get("old_sha"),
            "new_sha": entry.get("new_sha"),
            "summary": audit_log._safe_summary(entry.get("summary", "")),
            "category": entry.get("category"),
        })
    return {"status": "ok", "entries": safe, "count": len(safe)}
