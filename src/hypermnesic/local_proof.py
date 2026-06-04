"""Local-first product proof.

This is a small orchestration layer over existing primitives: git validation,
lexical/dense index projection, retrieve, and ``commit_note`` dry-run preview.
It deliberately does not provision endpoints, clients, or services.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hypermnesic import commit_note, index, retrieve, serialize
from hypermnesic import embed as embed_mod
from hypermnesic import frontmatter_gate as fg

DEMO_QUERY = "what should Hypermnesic remember about the demo vault"
DEMO_NOTE_PATH = "memory/local-proof-memory.md"
DEFAULT_PREVIEW_PATH = "memory/local-proof-preview.md"
DEMO_NOTE_BODY = (
    "# Local proof memory\n\n"
    f"Question answered: {DEMO_QUERY}\n\n"
    "Hypermnesic remembers that markdown files are the source of truth, git keeps "
    "provenance, and the disposable index makes those files searchable.\n"
)
PREVIEW_BODY = (
    "# Local proof preview\n\n"
    "This local proof preview shows the exact git diff that would be written. "
    "The default proof is dry-run only, so no file or commit is created.\n"
)

_APPROVAL_TOKEN_NAME = "HYPERMNESIC_CLOUD_APPROVAL" + "_TOKEN"
_OPERATOR_HOME_PREFIX = "/home/" + "ubuntu/"
_REDACTIONS = (
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+"), "[redacted-token]"),
    (re.compile(r"sk-[A-Za-z0-9]{10,}"), "[redacted-token]"),
    (re.compile(re.escape(_APPROVAL_TOKEN_NAME) + r"=[^\s]+"), "[redacted-token]"),
    (re.compile(re.escape(_OPERATOR_HOME_PREFIX) + r"[^\s,.)\"']+"), "[redacted-path]"),
)


@dataclass
class LocalProofError(Exception):
    code: str
    message: str
    next_action: str

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict:
        return {
            "status": "needs_action",
            "completed_milestones": [],
            "degraded_capabilities": {
                "degraded_lexical_only": True,
                "message": "Local proof did not complete, so dense status was not evaluated.",
            },
            "source_path": None,
            "next_action": self.next_action,
            "error": {"code": self.code, "message": self.message},
        }


@dataclass
class LocalProofResult:
    mode: str
    source_path: str
    retrieval: dict
    write_preview: dict
    degraded_capabilities: dict
    index_info: dict
    completed_milestones: list[str]
    next_action: str

    def as_dict(self) -> dict:
        return {
            "status": "local_memory_works",
            "mode": self.mode,
            "completed_milestones": self.completed_milestones,
            "degraded_capabilities": self.degraded_capabilities,
            "source_path": self.source_path,
            "retrieval": self.retrieval,
            "write_preview": self.write_preview,
            "index": self.index_info,
            "files_are_source_of_truth": True,
            "next_action": self.next_action,
            "error": None,
        }


def run_local_proof(*, repo: Path | str | None = None, demo_dir: Path | str | None = None,
                    query: str | None = None, seed_sample: bool = False,
                    preview_path: str = DEFAULT_PREVIEW_PATH,
                    embedder=None) -> LocalProofResult:
    """Run the local proof and return a stable agent-facing result contract.

    Existing-vault mode is read-only by default: it indexes/retrieves and performs
    a ``commit_note`` dry-run preview, but it does not create sample content unless
    ``seed_sample`` is explicit. Demo mode creates a dedicated tiny git vault.
    """
    if repo is not None and demo_dir is not None:
        raise LocalProofError(
            "ambiguous_target",
            "choose either an existing git repo or --demo-dir, not both",
            "Run local-proof with a repo path, or omit it and pass --demo-dir.",
        )
    if repo is None and demo_dir is None:
        raise LocalProofError(
            "missing_target",
            "local proof needs an existing git repo or a demo directory",
            "Pass a markdown git repo path, or run with --demo-dir for a tiny demo vault.",
        )

    mode = "demo" if demo_dir is not None else "existing"
    vault = _prepare_demo(Path(demo_dir)) if demo_dir is not None else Path(repo)
    _require_git_repo(vault)
    if seed_sample and mode == "existing":
        _ensure_sample_note(vault)

    q = query or _default_query_for(vault, mode)
    idx, catchup = _open_projected_index(vault, embedder)
    try:
        res = retrieve.search(idx, q, embedder=embedder, k=3,
                              recency_fn=retrieve.git_commit_recency(vault))
        if not res.hits:
            raise LocalProofError(
                "no_retrieval_hit",
                "local proof could not retrieve a source note for that question",
                "Add a markdown note containing the answer, rerun with --query, or use "
                "--demo-dir to see the deterministic sample path.",
            )
        hit = res.hits[0]
    finally:
        idx.close()

    preview = _preview_write(vault, preview_path)
    degraded = res.degraded or catchup.get("status") == "no-git" or embedder is None
    source_path = hit.path
    return LocalProofResult(
        mode=mode,
        source_path=source_path,
        retrieval={
            "question": q,
            "hit": {
                "path": source_path,
                "heading": _sanitize_text(hit.heading or ""),
                "snippet": _sanitize_text(hit.text[:280]),
                "channels": sorted(hit.channels),
                "score": round(hit.score, 6),
            },
        },
        write_preview=preview,
        degraded_capabilities={
            "degraded_lexical_only": bool(degraded),
            "message": _degradation_message(bool(degraded)),
        },
        index_info={
            "state_path": f"{index.STATE_DIRNAME}/index.db",
            "disposable_projection": True,
            "catchup_status": catchup.get("status"),
        },
        completed_milestones=[
            "git_vault_confirmed",
            "markdown_memory_found",
            "index_projected",
            "natural_question_retrieved",
            "source_path_shown",
            "dry_run_write_previewed",
        ],
        next_action=(
            "Local memory works. Next, connect remote clients after running setup "
            "diagnostics from the next sprint."
        ),
    )


def _run_git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, check=check)


def _require_git_repo(repo: Path) -> None:
    cp = _run_git(repo, "rev-parse", "--is-inside-work-tree")
    if cp.returncode != 0 or cp.stdout.strip() != "true":
        raise LocalProofError(
            "not_git_repo",
            "local proof needs a git repo of markdown files",
            "Initialize your vault with git first, or use --demo-dir for a generated proof vault.",
        )


def _prepare_demo(demo_dir: Path) -> Path:
    demo_dir = Path(demo_dir)
    if demo_dir.exists() and not (demo_dir / ".git").exists() and any(demo_dir.iterdir()):
        raise LocalProofError(
            "demo_dir_not_empty",
            "demo directory exists and is not an empty directory or git repo",
            "Choose an empty directory for --demo-dir so the proof cannot overwrite your data.",
        )
    demo_dir.mkdir(parents=True, exist_ok=True)
    if not (demo_dir / ".git").exists():
        _run_git(demo_dir, "init", "-q", "-b", "main", check=True)
        _run_git(demo_dir, "config", "user.email", "local-proof@example.invalid", check=True)
        _run_git(demo_dir, "config", "user.name", "hypermnesic local proof", check=True)
    _ensure_sample_note(demo_dir)
    return demo_dir


def _ensure_sample_note(repo: Path) -> None:
    target = repo / DEMO_NOTE_PATH
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEMO_NOTE_BODY, encoding="utf-8")
    _run_git(repo, "add", "--", DEMO_NOTE_PATH, check=True)
    _run_git(repo, "commit", "-q", "-m", "local proof memory", "--", DEMO_NOTE_PATH,
             check=True)


def _default_query_for(repo: Path, mode: str) -> str:
    if mode == "demo":
        return DEMO_QUERY
    for rel in _committed_markdown_paths(repo):
        try:
            text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        question = _question_from_text(text)
        if question:
            return question
    return DEMO_QUERY


def _committed_markdown_paths(repo: Path) -> list[str]:
    cp = _run_git(repo, "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", "HEAD")
    if cp.returncode != 0:
        return []
    return sorted(
        line for line in cp.stdout.splitlines()
        if line.endswith(".md") and not line.startswith(f"{index.STATE_DIRNAME}/")
    )


def _question_from_text(text: str) -> str | None:
    fallback: str | None = None
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if not line:
            continue
        if line.lower().startswith("question answered:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return value
        if fallback is None and len(line.split()) >= 3:
            fallback = line[:160]
    return fallback


def _open_projected_index(repo: Path, embedder=None):
    state = index.state_dir_for(repo)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    index.ensure_ignored(repo)
    idx = index.Index(state / "index.db")
    os.chmod(state / "index.db", 0o600)
    idx.create_schema()
    try:
        catchup = index.catch_up(idx, repo, embedder=embedder)
    except embed_mod.EmbeddingError:
        catchup = index.catch_up(idx, repo, embedder=None)
    return idx, catchup


def _preview_write(repo: Path, preview_path: str) -> dict:
    try:
        result = commit_note.commit_note(
            repo,
            preview_path,
            body=PREVIEW_BODY,
            summary="local proof preview",
            dry_run=True,
        )
    except (serialize.WriteGuardError, fg.FrontmatterDriftError, ValueError) as exc:
        raise LocalProofError(
            "write_preview_refused",
            f"dry-run write preview was refused: {exc}",
            "Choose a normal markdown destination such as memory/local-proof-preview.md.",
        ) from exc
    return {
        "dry_run": True,
        "destination": result.path,
        "created": result.created,
        "noop": result.noop,
        "guard": "passed",
        "commit_created": False,
        "diff": result.diff,
    }


def _degradation_message(degraded: bool) -> str:
    if degraded:
        return (
            "Local memory still works from exact text in your markdown files; "
            "embeddings improve ranking and fuzzy recall when configured."
        )
    return (
        "Dense retrieval is available; markdown source paths remain visible so the "
        "answer stays grounded in files."
    )


def _sanitize_text(text: str) -> str:
    out = text
    for pattern, replacement in _REDACTIONS:
        out = pattern.sub(replacement, out)
    return out
