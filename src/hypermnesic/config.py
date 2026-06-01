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

from pathlib import Path

# Held equal to gbrain's pinned config (KTD2).
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 1536

# .env candidates, searched in order. Monkeypatched in tests.
_DOTENV_PATHS = [Path.cwd() / ".env"]


class ConfigError(RuntimeError):
    """Raised on a model/dim disagreement or a missing credential."""


def _read_dotenv_key() -> str | None:
    for path in _DOTENV_PATHS:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def get_api_key() -> str:
    """Return the OpenAI key from env or .env. Raise ConfigError if absent.

    Never logs or echoes the value.
    """
    import os

    key = os.environ.get("OPENAI_API_KEY") or _read_dotenv_key()
    if not key:
        raise ConfigError(
            "OPENAI_API_KEY is not set (checked environment and .env). "
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
