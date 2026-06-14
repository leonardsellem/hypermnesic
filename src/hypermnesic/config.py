"""Single source of truth for the embedding model + dimensions, and the
credential read path.

The model and dims are pinned here (KTD2) so the parity result isolates the
*architecture* variable, not the embedding model. ``assert_embedder_agrees``
enforces the dim at startup; a mismatch fails fast rather than mid-run.

Credential discipline: the OpenAI key is read from the environment or a
gitignored repo-root ``.env`` only — never written to the index, audit log, or
any structured output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Held equal to gbrain's pinned config (KTD2).
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 1536

# Optional multi-query expansion (retrieval ranking aid). A small chat model;
# expansion is opt-in and degrades gracefully if the model is unavailable.
EXPANSION_MODEL = "gpt-4o-mini"

# --- read-time convergence tunables (Phase 2.5) --------------------------------
# Starting values; tune against real first-read latency (open question in the
# Phase-2.5 plan). A budget near one embedding batch (index._BATCH = 128) keeps
# a converging read to ~one API round-trip; the debounce coalesces a burst of
# reads; the delta cap signals a manual reindex rather than an unbounded inline
# replay when HEAD has jumped far ahead of the checkpoint (e.g. a big merge).
CONVERGE_EMBED_BUDGET = 128       # per-lane stale chunk/doc surfaces embedded per read
CONVERGE_DEBOUNCE_SECONDS = 5.0   # skip re-convergence within this window
CONVERGE_MAX_DELTA_FILES = 200    # over this many changed md files → signal manual reindex

# Cool down OpenAI embedding calls after a rate-limit/quota 429 so remote clients
# keep serving lexical/graph results without hammering the provider on every read.
EMBED_FAILURE_COOLDOWN_SECONDS = 300.0

# --- list_folders discovery bounds (U2) ----------------------------------------
# Mirror the CONVERGE_MAX_DELTA_FILES "cap + emit a signal" precedent: a large vault
# returns a bounded folder payload (sorted before the cap → a deterministic tail is
# dropped) with a ``truncated`` flag + omitted count; drill deeper by narrowing ``root``.
LIST_FOLDERS_MAX_NODES = 200      # max folder entries returned before truncation
LIST_FOLDERS_MAX_DEPTH = 6        # ceiling on the requested drill-down depth (clamped)

# U18 proposal zone tiers — an explicit path-prefix list, NOT a heuristic.
# Immutable free-append zones accept a NEW file directly (no proposal friction in
# the moment — U24 capture depends on this); they never accept an overwrite.
# Every other writable path is "curated": changes flow through propose→approve.
IMMUTABLE_APPEND_ZONES = ("sources/",)


def is_immutable_append_zone(rel_path: str) -> bool:
    """True if ``rel_path`` lives under a free-append zone (config path-prefix)."""
    return any(rel_path == z.rstrip("/") or rel_path.startswith(z)
               for z in IMMUTABLE_APPEND_ZONES)

# .env candidates, searched in order. Monkeypatched in tests.
_DOTENV_PATHS = [Path.cwd() / ".env"]


class ConfigError(RuntimeError):
    """Raised on a model/dim disagreement or a missing credential."""


@dataclass(frozen=True)
class ApiKeyStatus:
    """Secret-free credential discovery status.

    ``checked`` contains source categories only, never filesystem paths or key values.
    """

    configured: bool
    source: str
    checked: tuple[str, ...]
    error: str | None = None


def _read_dotenv_key_from(path: Path) -> tuple[str | None, str | None]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None
    except OSError:
        return None, "unreadable"
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'"), None
    return None, None


def _read_dotenv_key() -> str | None:
    for path in _DOTENV_PATHS:
        key, _error = _read_dotenv_key_from(Path(path))
        if key:
            return key
    return None


def _api_key_from_sources(repo: Path | str | None = None) -> tuple[str | None, ApiKeyStatus]:
    import os

    checked: list[str] = ["process_env"]
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key, ApiKeyStatus(True, "process_env", tuple(checked))

    if repo is not None:
        checked.append("repo_dotenv")
        repo_key, error = _read_dotenv_key_from(Path(repo) / ".env")
        if repo_key:
            return repo_key, ApiKeyStatus(True, "repo_dotenv", tuple(checked))
        return None, ApiKeyStatus(
            False,
            "missing",
            tuple(checked),
            "repo_dotenv_unreadable" if error else None,
        )

    checked.append("cwd_dotenv")
    key = _read_dotenv_key()
    if key:
        return key, ApiKeyStatus(True, "cwd_dotenv", tuple(checked))
    return None, ApiKeyStatus(False, "missing", tuple(checked))


def api_key_status(repo: Path | str | None = None) -> ApiKeyStatus:
    """Return secret-free OpenAI key discovery metadata."""
    return _api_key_from_sources(repo)[1]


def get_api_key(repo: Path | str | None = None) -> str:
    """Return the OpenAI key from env or approved .env source. Raise ConfigError if absent.

    Never logs or echoes the value.
    """
    key, status = _api_key_from_sources(repo)
    if not key:
        checked = ", ".join(status.checked)
        extra = ""
        if status.error == "repo_dotenv_unreadable":
            extra = " Repo .env could not be read."
        raise ConfigError(
            f"OPENAI_API_KEY is not set (checked {checked}).{extra} "
            "Set it via env var or a gitignored repo-root .env file."
        )
    return key


def assert_embedder_agrees(embedder) -> None:
    """Fail fast if the embedder's output dimension is not the pinned EMBED_DIM."""
    dim = getattr(embedder, "dim", None)
    if dim != EMBED_DIM:
        raise ConfigError(
            f"embedder dim {dim!r} disagrees with pinned EMBED_DIM={EMBED_DIM}"
        )
