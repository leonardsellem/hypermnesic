"""Shared test fixtures: an offline deterministic embedder and corpus builders.

Index *mechanics* (dim, KNN shape, gitignore stability, rebuild reproducibility,
edge cases) must be testable without network or API spend, so tests inject a
``FakeEmbedder``. The real OpenAI path is exercised separately by the live
smoke embed and the live-corpus verification.
"""

from __future__ import annotations

import hashlib
import math
import subprocess
import sys
from pathlib import Path

import pytest

from hypermnesic.config import EMBED_DIM

# harness/ holds CLI tools (parity_harness, portability_probe) that are not part
# of the installed package; put it on the path so tests can import them directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))


class FakeEmbedder:
    """Deterministic unit-vector embedder seeded by text.

    Identical text → identical vector (so a chunk is its own nearest neighbour
    and rebuilds are bit-reproducible); different text → different vector. Emits
    exactly ``EMBED_DIM`` floats so dim invariants are real.
    """

    model = "fake-deterministic"
    dim = EMBED_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        out: list[float] = []
        counter = 0
        while len(out) < EMBED_DIM:
            h = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            for i in range(0, len(h), 4):
                out.append(int.from_bytes(h[i:i + 4], "big") / 2**32 - 0.5)
                if len(out) >= EMBED_DIM:
                    break
            counter += 1
        norm = math.sqrt(sum(x * x for x in out)) or 1.0
        return [x / norm for x in out]


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def make_corpus(tmp_path):
    """Build a small markdown repo (optionally git-initialised) and return its path."""

    def _make(files: dict[str, str], *, git: bool = True,
              gitignore: str | None = None) -> Path:
        repo = tmp_path / "corpus"
        repo.mkdir(exist_ok=True)
        for rel, body in files.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        if gitignore is not None:
            (repo / ".gitignore").write_text(gitignore, encoding="utf-8")
        if git:
            _git(repo, "init", "-q", "-b", "main")
            _git(repo, "config", "user.email", "t@t.t")
            _git(repo, "config", "user.name", "t")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "fixture")
        return repo

    return _make
