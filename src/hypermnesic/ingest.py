"""Walk a markdown corpus and chunk it for indexing.

Reads files defensively (non-UTF-8 bytes are replaced, never crash), strips
YAML frontmatter from the indexed body, and groups paragraphs into bounded
chunks while tracking the nearest preceding heading. Deterministic order
(sorted paths) so rebuilds are reproducible.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")

_SKIP_DIRS = {".git", ".hypermnesic", "node_modules", "__pycache__", ".obsidian", ".worktrees"}
# `.worktrees` holds git checkouts of the same vault: every file is a stale copy
# of a tracked note, so indexing them doubles the corpus and outranks the
# canonical page with an older revision.
# Chunk target (chars). A hard cap well under the embedding model's 8192-token
# input limit: ~4000 chars ≈ ~1000 tokens worst case, so no chunk can overflow
# the API (the input[118] 8192-token failure on the first full index).
MAX_CHARS = 4000


def _split_oversized(block: str) -> list[str]:
    """Split a single block longer than MAX_CHARS into <=MAX_CHARS pieces.

    Prefers line boundaries; falls back to a hard character slice for a block
    with no usable whitespace (a giant table row, a base64 blob).
    """
    if len(block) <= MAX_CHARS:
        return [block]
    pieces: list[str] = []
    buf: list[str] = []
    size = 0
    for line in block.splitlines():
        while len(line) > MAX_CHARS:  # a single monstrous line
            if buf:
                pieces.append("\n".join(buf))
                buf, size = [], 0
            pieces.append(line[:MAX_CHARS])
            line = line[MAX_CHARS:]
        if size + len(line) + 1 > MAX_CHARS and buf:
            pieces.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        pieces.append("\n".join(buf))
    return [p for p in pieces if p.strip()]


@dataclass(frozen=True)
class Chunk:
    path: str          # repo-relative posix path
    ord: int           # 0-based chunk index within the file
    heading: str       # nearest preceding heading ("" if none)
    text: str


def strip_frontmatter(raw: str) -> str:
    return _FRONTMATTER_RE.sub("", raw, count=1)


class AdmissionError(RuntimeError):
    """The eligible-path set could not be computed.

    Retryable: callers must not prune index rows or advance a checkpoint from a
    failed or unstable enumeration (R2 — a failed read is not proof of absence).
    """


def is_markdown(path: str) -> bool:
    """Syntactic Markdown predicate: ``.md``, path-safe, outside a hard skip."""
    return (path.endswith(".md") and _safe_rel(path)
            and not any(part in _SKIP_DIRS for part in path.split("/")[:-1]))


def _safe_rel(path: str) -> bool:
    if not path or path.startswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def _run(args: list[str], *, input: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, input=input, capture_output=True)
    except OSError as exc:                     # git missing/unrunnable
        raise AdmissionError(f"cannot run {args[0]}: {exc}") from exc


def _git_bytes(repo: Path, *args: str, input: bytes | None = None) -> subprocess.CompletedProcess:
    # core.quotepath=false: emit non-ASCII paths raw so they survive decoding.
    return _run(["git", "-C", str(repo), "-c", "core.quotepath=false", *args], input=input)


def _git_root(repo: Path) -> Path | None:
    """``repo``'s own toplevel, or None when it is not a Git work tree root."""
    try:
        out = _run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"])
    except AdmissionError:
        return None
    if out.returncode != 0:
        return None
    try:
        root = Path(os.fsdecode(out.stdout.strip())).resolve()
        return root if root == Path(repo).resolve() else None
    except OSError:
        return None


def _stage_records(out: bytes) -> Iterator[tuple[bytes, bytes, str]]:
    """Parse ``ls-files --stage -z`` into (mode, stage, path)."""
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, sep, raw = rec.partition(b"\t")
        fields = meta.split(b" ")
        if sep and len(fields) == 3:
            yield fields[0], fields[2], os.fsdecode(raw)


def _tracked_regular(repo: Path) -> set[str]:
    """Stage-0 regular tracked entries (symlinks and gitlinks are not files)."""
    proc = _git_bytes(repo, "ls-files", "--stage", "-z")
    if proc.returncode != 0:
        raise AdmissionError(f"git ls-files failed: {proc.stderr.decode(errors='replace')}")
    return {path for mode, stage, path in _stage_records(proc.stdout)
            if mode in (b"100644", b"100755") and stage == b"0"}


def _ignored_tracked(repo: Path) -> set[str]:
    """Tracked paths denied by root/nested ``.gitignore`` rules (Git semantics).

    ``--exclude-per-directory`` alone reads only per-directory ``.gitignore``
    files: user/global excludes and ``.git/info/exclude`` stay out of admission.
    """
    proc = _git_bytes(repo, "ls-files", "--cached", "--ignored",
                      "--exclude-per-directory=.gitignore", "-z")
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace")
        raise AdmissionError(f"git ls-files --ignored failed: {detail}")
    return {p for p in (os.fsdecode(rec) for rec in proc.stdout.split(b"\0")) if p}


def _skip_worktree(repo: Path) -> set[str]:
    """Tracked paths with Git's skip-worktree flag (sparse omissions, not deletions)."""
    proc = _git_bytes(repo, "ls-files", "-v", "-z")
    if proc.returncode != 0:
        return set()
    out = set()
    for rec in proc.stdout.split(b"\0"):
        if len(rec) > 2 and rec[1:2] == b" " and rec[:1].upper() == b"S":
            out.add(os.fsdecode(rec[2:]))
    return out


def _read_ignore_file(fp: Path) -> str:
    """Read an applicable ``.gitignore``; a read failure refuses the pass."""
    try:
        return fp.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError as exc:
        raise AdmissionError(f"cannot read {fp}: {exc}") from exc


def _walk_error(exc: OSError) -> None:
    raise AdmissionError(f"cannot scan corpus: {exc}")


def _ignore_files(repo: Path) -> dict[str, str]:
    """Every applicable on-disk ``.gitignore`` of a standalone corpus.

    Walks the corpus (there is no Git tree to ask); worktree admission uses
    :func:`_worktree_ignore_files` so ignored directories are never scanned.
    """
    files: dict[str, str] = {}
    for dirpath, dirnames, _filenames in os.walk(repo, onerror=_walk_error):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        fp = Path(dirpath) / ".gitignore"
        try:
            st = os.lstat(fp)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise AdmissionError(f"cannot stat {fp}: {exc}") from exc
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            continue                          # Git never follows a .gitignore symlink
        files[fp.relative_to(repo).as_posix()] = _read_ignore_file(fp)
    return files


def _worktree_ignore_files(repo: Path) -> dict[str, str]:
    """Applicable ``.gitignore`` files of a Git worktree, listed by Git itself.

    Asking Git avoids reading ignored worktree contents; a file Git would not
    traverse (e.g. ``.gitignore`` inside an ignored directory) is not applicable.
    """
    proc = _git_bytes(repo, "ls-files", "--cached", "--others",
                      "--exclude-per-directory=.gitignore", "-z")
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace")
        raise AdmissionError(f"git ls-files failed: {detail}")
    names = {os.fsdecode(rec) for rec in proc.stdout.split(b"\0")
             if rec and PurePosixPath(os.fsdecode(rec)).name == ".gitignore"}
    files: dict[str, str] = {}
    for rel in sorted(names):
        if not _safe_rel(rel):
            raise AdmissionError(f"unsafe ignore path: {rel!r}")
        fp = repo / rel
        try:
            st = os.lstat(fp)
        except FileNotFoundError:
            continue                          # staged-deleted ignore file
        except OSError as exc:
            raise AdmissionError(f"cannot stat {fp}: {exc}") from exc
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            continue
        files[rel] = _read_ignore_file(fp)
    return files


def _check_ignore(ignore_files: dict[str, str], candidates: Iterable[str]) -> set[str]:
    """The subset of ``candidates`` denied by Git's matcher, in a private scratch repo.

    Materialising only the ignore files (never corpus content) keeps a pinned
    commit's projection independent of the dirty worktree or user excludes.
    Exit 1 with no output is "no matches", not a matcher failure.
    """
    cands = sorted(c for c in set(candidates) if _safe_rel(c))
    if not cands:
        return set()
    try:
        with tempfile.TemporaryDirectory(prefix="hypermnesic-ignore-") as td:
            scratch = Path(td)
            init = _run(["git", "init", "-q", str(scratch)])
            if init.returncode != 0:
                raise AdmissionError(f"git init failed: {init.stderr.decode(errors='replace')}")
            for rel, text in ignore_files.items():
                if not _safe_rel(rel):
                    raise AdmissionError(f"unsafe ignore path: {rel!r}")
                fp = scratch / rel
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(text, encoding="utf-8", errors="surrogateescape")
            proc = _run(["git", "-C", str(scratch), "-c", "core.excludesFile=/dev/null",
                         "check-ignore", "--no-index", "--stdin", "-z"],
                        input=b"\0".join(os.fsencode(c) for c in cands) + b"\0")
    except OSError as exc:
        raise AdmissionError(f"ignore matcher failed: {exc}") from exc
    if proc.returncode not in (0, 1):
        raise AdmissionError(
            f"git check-ignore failed: {proc.stderr.decode(errors='replace')}")
    return {os.fsdecode(rec) for rec in proc.stdout.split(b"\0") if rec}


def _pinned_tree(repo: Path, sha: str) -> tuple[set[str], dict[str, str]]:
    """(regular blobs, ``.gitignore`` blobs) at a pinned commit."""
    proc = _git_bytes(repo, "ls-tree", "-r", "-z", sha)
    if proc.returncode != 0:
        raise AdmissionError(f"git ls-tree {sha} failed: {proc.stderr.decode(errors='replace')}")
    regular: set[str] = set()
    blobs: list[tuple[str, str]] = []
    for rec in proc.stdout.split(b"\0"):
        if not rec:
            continue
        meta, sep, raw = rec.partition(b"\t")
        fields = meta.split(b" ")
        if not sep or len(fields) != 3 or fields[1] != b"blob":
            continue
        mode, _typ, oid = fields
        if mode not in (b"100644", b"100755"):
            continue
        path = os.fsdecode(raw)
        regular.add(path)
        if PurePosixPath(path).name == ".gitignore":
            blobs.append((path, oid.decode()))
    if not blobs:
        return regular, {}
    # One batched object read, never one `git show` per ignore file.
    proc = _git_bytes(repo, "cat-file", "--batch",
                      input=b"\n".join(oid.encode() for _, oid in blobs) + b"\n")
    if proc.returncode != 0:
        raise AdmissionError(f"git cat-file failed: {proc.stderr.decode(errors='replace')}")
    data, pos, files = proc.stdout, 0, {}
    try:
        for path, _oid in blobs:
            end = data.index(b"\n", pos)
            header = data[pos:end].split(b" ")
            if len(header) != 3 or header[1] != b"blob":
                raise AdmissionError(f"cannot read {path} at {sha}")
            size = int(header[2])
            files[path] = data[end + 1:end + 1 + size].decode("utf-8", "surrogateescape")
            pos = end + 1 + size + 1
    except (ValueError, IndexError) as exc:
        raise AdmissionError(f"malformed cat-file output at {sha}") from exc
    return regular, files


def admitted_paths_at(repo: Path, sha: str | None) -> set[str]:
    """Eligible Markdown at a pinned commit (replica membership: the Git tree)."""
    if not sha:
        return admitted_paths(repo)
    regular, ignore_files = _pinned_tree(Path(repo), sha)
    md = {p for p in regular if is_markdown(p)}
    return md - _check_ignore(ignore_files, md)


def admitted_paths(repo: Path) -> set[str]:
    """Eligible Markdown for a worktree (Git admission) or a standalone corpus."""
    repo = Path(repo)
    if _git_root(repo) is None:
        return _standalone_admitted(repo)
    _worktree_ignore_files(repo)                # validate every applicable ignore file
    md = {p for p in _tracked_regular(repo) if is_markdown(p)}
    return md - _ignored_tracked(repo)


def _standalone_admitted(repo: Path) -> set[str]:
    """Ordinary Markdown discovery + any ``.gitignore`` + hard skips (no tracking)."""
    ignore_files = _ignore_files(repo)
    candidates = []
    for dirpath, dirnames, filenames in os.walk(repo, onerror=_walk_error):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".md"):
                rel = (Path(dirpath) / name).relative_to(repo).as_posix()
                if _safe_rel(rel):
                    candidates.append(rel)
    ignored = _check_ignore(ignore_files, candidates)
    cache: dict[Path, os.stat_result] = {}
    return {p for p in candidates
            if p not in ignored and _disk_state(repo, p, cache) == "file"}


def _disk_state(repo: Path, rel: str, cache: dict[Path, os.stat_result]) -> str:
    """``file`` / ``missing`` / ``nonregular`` / ``symlink`` for a repo-relative path.

    Missing is a classification (the path is absent); any other I/O error is
    retried as :class:`AdmissionError` so it can never be read as a deletion.
    """
    parent = repo
    for part in rel.split("/")[:-1]:
        parent = parent / part
        st = cache.get(parent)
        if st is None:
            try:
                st = os.lstat(parent)
            except (FileNotFoundError, NotADirectoryError):
                return "missing"
            except OSError as exc:
                raise AdmissionError(f"cannot stat {parent}: {exc}") from exc
            cache[parent] = st
        if stat.S_ISLNK(st.st_mode):
            return "symlink"
        if not stat.S_ISDIR(st.st_mode):
            return "missing"
    try:
        st = os.lstat(repo / rel)
    except (FileNotFoundError, NotADirectoryError):
        return "missing"
    except OSError as exc:
        raise AdmissionError(f"cannot stat {rel}: {exc}") from exc
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    return "file" if stat.S_ISREG(st.st_mode) else "nonregular"


def readable_paths(repo: Path, admitted: Iterable[str] | None = None) -> set[str]:
    """The admitted paths that are regular files on disk (never below a symlink)."""
    repo = Path(repo)
    paths = admitted_paths(repo) if admitted is None else set(admitted)
    cache: dict[Path, os.stat_result] = {}
    return {p for p in paths if _disk_state(repo, p, cache) == "file"}


def enumerate_markdown(repo: Path) -> set[str]:
    """One pass's eligible, readable Markdown set — shared by every writer lane."""
    return readable_paths(repo)


def missing_but_protected(repo: Path) -> set[str]:
    """Tracked paths Git marks skip-worktree: absent by design, not deletions."""
    repo = Path(repo)
    if _git_root(repo) is None:
        return set()
    return _skip_worktree(repo) - _ignored_tracked(repo)


def dirty_paths(repo: Path) -> set[str]:
    """Every path with a pending worktree/index change (overlay text is not committed)."""
    repo = Path(repo)
    if _git_root(repo) is None:
        return set()
    proc = _git_bytes(repo, "status", "--porcelain", "--no-renames", "-z")
    if proc.returncode != 0:
        raise AdmissionError(f"git status failed: {proc.stderr.decode(errors='replace')}")
    return {os.fsdecode(rec[3:]) for rec in proc.stdout.split(b"\0")
            if len(rec) > 3 and rec[2:3] == b" "}


def is_admitted(repo: Path, rel: str) -> bool:
    """One path against the worktree admission rule; conservative on failure."""
    try:
        return rel in admitted_paths(Path(repo))
    except AdmissionError:
        return False


def _iter_markdown_files(repo: Path, paths: Iterable[str] | None = None) -> Iterator[Path]:
    repo = Path(repo)
    rels = sorted(readable_paths(repo) if paths is None else paths)
    for rel in rels:
        yield repo / rel


def _chunk_body(body: str) -> Iterator[tuple[str, str]]:
    """Yield (heading, text) chunks from a markdown body."""
    heading = ""
    buf: list[str] = []
    size = 0

    def flush():
        nonlocal buf, size
        text = "\n\n".join(buf).strip()
        buf, size = [], 0
        return text

    for raw_block in re.split(r"\n\s*\n", body):
        raw_block = raw_block.strip()
        if not raw_block:
            continue
        lines = raw_block.splitlines()
        m = _HEADING_RE.match(lines[0])
        if m and len(lines) == 1:
            if buf:
                text = flush()
                if text:
                    yield heading, text
            heading = m.group(1).strip()
            continue
        for block in _split_oversized(raw_block):
            if size + len(block) > MAX_CHARS and buf:
                text = flush()
                if text:
                    yield heading, text
            buf.append(block)
            size += len(block)
    if buf:
        text = flush()
        if text:
            yield heading, text


_FM_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)
# A level-1 ATX heading only: a single leading '#' followed by whitespace. '## x'
# does not match (the second '#' breaks the `#\s` requirement), so a section label
# is never mistaken for a note's identity.
_H1_RE = re.compile(r"(?m)^\s{0,3}#\s+(.+)$")
_LEADING_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}[-_ ]?")


def _stem_title(path: str) -> str:
    """De-kebab a path stem into a fallback title: strip a leading ISO date, then
    turn ``-``/``_`` runs into spaces (``2026-06-03-foo-bar`` → ``foo bar``)."""
    stem = _LEADING_ISO_DATE.sub("", Path(path).stem)
    cleaned = re.sub(r"[-_]+", " ", stem).strip()
    return cleaned or Path(path).stem or path   # never blank (e.g. a date-only filename)


def note_title(raw: str, path: str = "") -> str:
    """A note's display identity: frontmatter ``title:`` → first level-1 ``# ``
    heading → de-kebabbed path-stem fallback. Level-specific by design: a note
    that opens with ``## Section`` and has no H1 falls through to the stem rather
    than returning the section label as identity (the U20→U44 dogfood defect)."""
    fm = _FM_TITLE.search(raw[:600])
    if fm:
        title = fm.group(1).strip().strip('"').strip("'")
        if title:
            return title
    m = _H1_RE.search(strip_frontmatter(raw))
    if m and m.group(1).strip():
        return m.group(1).strip()
    return _stem_title(path)


def doc_surface(raw: str, path: str = "") -> str:
    """A doc-level 'what is this about' surface for the doc embedding lane.

    Title (frontmatter `title:` or first H1, falling back to the slug) + all
    section headings + the lead paragraph, bounded to MAX_CHARS. This aligns with
    "about this document" NL queries better than any single mid-body chunk —
    a deterministic proxy for gbrain's compiled-summary representation.
    """
    title = ""
    fm = _FM_TITLE.search(raw[:600])
    if fm:
        title = fm.group(1).strip().strip('"').strip("'")
    body = strip_frontmatter(raw)
    headings = [m.group(1).strip() for m in re.finditer(r"^\s{0,3}#{1,6}\s+(.*)$", body, re.M)]
    if not title:
        title = headings[0] if headings else Path(path).stem.replace("-", " ")
    lead = ""
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if block and not _HEADING_RE.match(block.splitlines()[0]):
            lead = block
            break
    surface = f"{title}\n\n" + "\n".join(headings) + "\n\n" + lead
    return surface.strip()[:MAX_CHARS]


def iter_chunks(repo: Path, paths: Iterable[str] | None = None) -> Iterator[Chunk]:
    repo = Path(repo)
    for fp in _iter_markdown_files(repo, paths):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:                # vanished/unreadable mid-pass: retry, never prune
            raise AdmissionError(f"cannot read {fp}: {exc}") from exc
        body = strip_frontmatter(raw)
        rel = fp.relative_to(repo).as_posix()
        for i, (heading, text) in enumerate(_chunk_body(body)):
            yield Chunk(path=rel, ord=i, heading=heading, text=text)


def chunks_for_text(path: str, raw: str) -> list[Chunk]:
    """Chunk a single document's raw text (frontmatter stripped) — for the
    synchronous lexical extraction in commit_note (U7)."""
    body = strip_frontmatter(raw)
    return [Chunk(path=path, ord=i, heading=h, text=t)
            for i, (h, t) in enumerate(_chunk_body(body))]


def iter_doc_surfaces(repo: Path, paths: Iterable[str] | None = None) -> Iterator[tuple[str, str]]:
    """Yield (repo-relative path, doc surface) for every eligible markdown file."""
    repo = Path(repo)
    for fp in _iter_markdown_files(repo, paths):
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise AdmissionError(f"cannot read {fp}: {exc}") from exc
        rel = fp.relative_to(repo).as_posix()
        surface = doc_surface(raw, rel)
        if surface:
            yield rel, surface
