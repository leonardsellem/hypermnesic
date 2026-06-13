"""U2 — folder-taxonomy derivation: turn the index's path set into bounded, sorted
folder entries so an agent can discover the vault's writable structure before placing
a note. [R3/R4/R5/R7/R8]

Pure and server-free: ``derive_folders`` takes a set of repo-relative markdown paths
(``index.Index.all_paths()``) and returns the child folders under a sanitized ``root``
to a clamped ``depth``, each carrying its repo-relative path, ``writable`` flag,
protected reason, and a *recursive* note count, with a deterministic sort applied
**before** a node cap (so truncation drops a deterministic tail).

Writability is single-sourced from the write guard: a folder's flag is exactly
``serialize.writable_reason(prefix + "__probe__.md", allowlist=effective_surface) is
None`` — probing a file *under* the prefix so the classification matches what
``commit_note`` accepts for a write into that folder (``protected_reason`` deliberately
excludes the leaf, so a bare prefix would mis-read ``projects/scripts/`` as writable).
"""

from __future__ import annotations

import re
from ipaddress import ip_address, ip_network
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from hypermnesic import config, serialize

# A synthetic file probed under each folder prefix. A note (``.md``) is what an agent
# would write, so the flag answers "can a note land directly here". Never collides with
# a real path; classified by serialize.writable_reason like any other write target.
_PROBE = "__probe__.md"
_INSTRUCTION_CANDIDATES = ("AGENTS.md", "CLAUDE.md")
_URL_RE = re.compile(r"https?://[^\s<>()\"'`]+")
_LOCAL_ABSPATH_RE = re.compile(
    r"(?<![\w.-])/"
    r"(?:Users|home|root|var|etc|opt|srv|mnt|Volumes|tmp|run|private)"
    r"(?:/[^\s<>()\"'`]+)+"
)
_TRAILING_PUNCT = ".,;:!?"
_TAILNET_CGNAT = ip_network("100.64.0.0/10")


def normalize_root(root: str | None) -> str:
    """Normalize a caller-supplied ``root`` to a repo-relative trailing-slash prefix
    (``""`` = vault root). Reject absolute paths and ``..`` traversal — the predicate
    is only ever evaluated on index-derived or sanitized prefixes (V6)."""
    raw = (root or "").strip()
    if not raw or raw == ".":
        return ""
    p = PurePosixPath(raw)
    if p.is_absolute():
        raise ValueError(f"root must be repo-relative, not absolute: {root!r}")
    parts = [seg for seg in p.parts if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise ValueError(f"root must not contain '..' traversal: {root!r}")
    return "/".join(parts) + "/" if parts else ""


def _sanitize_instruction_content(content: str) -> str:
    """Keep repo guidance useful while removing host-local coordinates.

    Instruction files can legitimately mention local deployment paths or private
    MCP endpoints. `list_folders` is a remote read surface, so those coordinates
    must not be echoed to ChatGPT/Claude clients as raw metadata.
    """
    def split_token(match: re.Match[str]) -> tuple[str, str]:
        suffix = ""
        token = match.group(0)
        while token and token[-1] in _TRAILING_PUNCT:
            suffix = token[-1] + suffix
            token = token[:-1]
        return token, suffix

    def is_private_host(host: str) -> bool:
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".ts.net"):
            return True
        try:
            addr = ip_address(host.strip("[]"))
        except ValueError:
            return False
        return addr.is_private or addr.is_loopback or addr in _TAILNET_CGNAT

    def redact_url(match: re.Match[str]) -> str:
        token, suffix = split_token(match)
        parts = urlsplit(token)
        if parts.path.rstrip("/") == "/mcp" or is_private_host(parts.hostname or ""):
            return f"<endpoint-url>{suffix}"
        return f"{token}{suffix}"

    def redact_path(match: re.Match[str]) -> str:
        _, suffix = split_token(match)
        return f"<local-path>{suffix}"

    content = _URL_RE.sub(redact_url, content)
    return _LOCAL_ABSPATH_RE.sub(redact_path, content)


def agent_instruction_for_root(repo: Path, root: str | None) -> dict | None:
    """Return the direct instruction file for ``root`` if present.

    Precedence is root-local ``AGENTS.md`` first, then root-local ``CLAUDE.md``.
    Descendant instruction files are deliberately ignored: callers should narrow
    ``root`` when they want guidance for a child folder.
    """
    root_prefix = normalize_root(root)
    base = Path(repo) / root_prefix
    for name in _INSTRUCTION_CANDIDATES:
        candidate = base / name
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8")
            return {"source": name, "content": _sanitize_instruction_content(content)}
    return None


def derive_folders(paths, *, root: str = "", depth: int = 1,
                   effective_surface: list[str] | None = None,
                   max_nodes: int = config.LIST_FOLDERS_MAX_NODES,
                   max_depth: int = config.LIST_FOLDERS_MAX_DEPTH) -> dict:
    """Derive bounded, sorted folder entries under ``root`` to ``depth`` levels.

    ``paths``: repo-relative markdown paths (already content-only — the index excludes
    ``.git``/``.obsidian``/``node_modules``/``__pycache__``/non-``.md``, so R5's
    structural limit is inherited). ``effective_surface``: the install's effective write
    configuration (``None`` = blocklist). Returns ``{root, depth, folders, truncated,
    omitted}`` where each folder is ``{path, writable, protected_reason, note_count}``.
    Raises ``ValueError`` on an absolute / traversal ``root``.
    """
    root_prefix = normalize_root(root)
    depth = max(1, min(int(depth), max_depth))
    under = [p for p in paths if p.startswith(root_prefix)]

    # Folder prefixes at every level from 1..depth that contain at least one note.
    folder_prefixes: set[str] = set()
    for p in under:
        segments = p[len(root_prefix):].split("/")[:-1]        # dir components, drop the filename
        for level in range(1, min(depth, len(segments)) + 1):
            folder_prefixes.add(root_prefix + "/".join(segments[:level]) + "/")

    entries = []
    for prefix in folder_prefixes:
        reason = serialize.writable_reason(prefix + _PROBE, allowlist=effective_surface)
        note_count = sum(1 for p in under if p.startswith(prefix))   # recursive (at/under prefix)
        entries.append({"path": prefix, "writable": reason is None,
                        "protected_reason": reason, "note_count": note_count})

    entries.sort(key=lambda e: e["path"])                      # deterministic order BEFORE the cap
    total = len(entries)
    truncated = total > max_nodes
    if truncated:
        entries = entries[:max_nodes]                          # drop a deterministic tail
    return {"root": root_prefix, "depth": depth, "folders": entries,
            "truncated": truncated, "omitted": total - len(entries)}
