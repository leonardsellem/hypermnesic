"""U1 — dataset acquisition + reproducibility manifest.

Pins everything a third party needs to reproduce the headline number from the
committed harness alone (R14/R16, flow F3): the dataset URL + content hash +
release tag, the production embedding model/dim, both reader snapshots and the
canonical judge snapshot, the frozen retrieval params (k + fusion weights +
lanes), the prompt-template version, and a run seed. The manifest is committed;
the multi-GB dataset JSON is referenced by hash and downloaded, never committed
(R15). The OpenAI key is never read here and never enters the serialized output
(credential discipline — see ``hypermnesic.config.get_api_key``).

Downloading uses stdlib ``urllib`` + ``hashlib`` (no new dependency): stream to a
temp file, hash it, and only move it into place once the SHA-256 matches the
pinned constant — a mismatch fails loud and leaves no corpus behind (the frozen-
fixture discipline of ``harness/capture_gbrain_baseline.py``).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from hypermnesic import config

# --- pinned dataset identity ------------------------------------------------
# HF cleaned release (2025-09), MIT licensed, 500 instances. The `_s` variant is
# the v1 headline (~115k tokens / ~40 sessions per instance).
DATASET_RELEASE = "longmemeval-cleaned-2025-09"
DATASET_VARIANT = "_s"
DATASET_URL = (
    "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/"
    "resolve/main/longmemeval_s_cleaned.json"
)
# Pinned at dataset-acquisition (the U1 verification step), 2026-06-02, from the
# HF cleaned-2025-09 release: 500 instances, 277,383,467 bytes. A re-download is
# now verified strictly against this hash; a divergent download fails loud and
# installs no corpus (R14/R16). Re-pin only if the upstream release is bumped,
# recording the change in harness/BENCHMARKS.md.
DATASET_SHA256 = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"

# --- pinned models ----------------------------------------------------------
READER_LEAD = "gpt-4.1-2025-04-14"        # 1M context → `_s` fits untruncated
READER_ANCHOR = "gpt-4o-2024-08-06"       # apples-to-apples GPT-4o-judge anchor
READER_DEV = "gpt-4.1-mini"               # cheap dev/CI reader (non-headline)
JUDGE_MODEL = "gpt-4o-2024-08-06"         # the canonical LongMemEval judge (R11)

PROMPT_TEMPLATE_VERSION = "longmemeval-v1-2024-10"  # the 5 per-type autoeval prompts
RUN_SEED = 20260602

# --- frozen retrieval params (R19: frozen before the headline; no tune-to-pass) -
# Held equal to the production read-path defaults (`retrieve.search`). Any change
# is recorded here and disclosed in the verdict doc.
RETRIEVAL_K = 10
RETRIEVAL_CANDIDATE_K = 50
RETRIEVAL_WEIGHTS = (1.0, 1.0, 1.0)       # (lexical, dense, doc) RRF weights
RETRIEVAL_USE_DOC_LANE = True
RETRIEVAL_COLLAPSE_DUPLICATES = True

# --- Phase-1 embedding cost assumptions (recorded, not assumed) -------------
# text-embedding-3-large list price as of the 2025-09 release; a documented
# assumption (the engine config does not carry pricing). Token volume: 500
# instances at ~115k tokens each, embedded across BOTH the per-session and the
# per-turn corpus (n_corpora=2). The content-hash cache (U3) collapses the shared
# text so re-runs and the F3 critic re-run stay well under this ceiling.
EMBED_PRICE_PER_MILLION_TOKENS_USD = 0.13
COST_N_INSTANCES = 500
COST_TOKENS_PER_INSTANCE = 115_000
COST_N_CORPORA = 2


class DatasetIntegrityError(RuntimeError):
    """Raised when a downloaded dataset does not match the pinned SHA-256."""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    verified: bool  # True only when checked against a pinned (non-empty) hash


@dataclass
class Manifest:
    dataset_url: str
    dataset_sha256: str
    dataset_release: str
    dataset_variant: str
    embed_model: str
    embed_dim: int
    reader_models: list[str]
    judge_model: str
    retrieval: dict
    prompt_template_version: str
    seed: int
    phase1_embedding_cost_ceiling_usd: float
    cost_assumptions: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, blob: str) -> Manifest:
        return cls(**json.loads(blob))


def _cost_ceiling_usd() -> tuple[float, dict]:
    """Phase-1 embedding-cost ceiling + the assumptions it is derived from."""
    total_tokens = COST_N_INSTANCES * COST_TOKENS_PER_INSTANCE * COST_N_CORPORA
    ceiling = round(total_tokens / 1_000_000 * EMBED_PRICE_PER_MILLION_TOKENS_USD, 2)
    assumptions = {
        "n_instances": COST_N_INSTANCES,
        "tokens_per_instance": COST_TOKENS_PER_INSTANCE,
        "n_corpora": COST_N_CORPORA,
        "total_tokens": total_tokens,
        "price_per_million_tokens_usd": EMBED_PRICE_PER_MILLION_TOKENS_USD,
        "note": "ceiling; the U3 content-hash cache makes re-runs and the F3 "
                "critic re-run far cheaper by reusing shared session/turn text.",
    }
    return ceiling, assumptions


def default_manifest() -> Manifest:
    """The canonical pinned manifest for the `_s` v1 headline.

    Reads the embedding model/dim from ``hypermnesic.config`` (R12) so the
    manifest can never drift from the production embed config. Reads no
    credential.
    """
    ceiling, assumptions = _cost_ceiling_usd()
    return Manifest(
        dataset_url=DATASET_URL,
        dataset_sha256=DATASET_SHA256,
        dataset_release=DATASET_RELEASE,
        dataset_variant=DATASET_VARIANT,
        embed_model=config.EMBED_MODEL,
        embed_dim=config.EMBED_DIM,
        reader_models=[READER_LEAD, READER_ANCHOR, READER_DEV],
        judge_model=JUDGE_MODEL,
        retrieval={
            "k": RETRIEVAL_K,
            "candidate_k": RETRIEVAL_CANDIDATE_K,
            "weights": list(RETRIEVAL_WEIGHTS),
            "use_doc_lane": RETRIEVAL_USE_DOC_LANE,
            "collapse_duplicates": RETRIEVAL_COLLAPSE_DUPLICATES,
        },
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        seed=RUN_SEED,
        phase1_embedding_cost_ceiling_usd=ceiling,
        cost_assumptions=assumptions,
    )


DOWNLOAD_TIMEOUT = 120  # seconds; fail a stalled CDN connection rather than hang forever


def _urlopen(url: str):
    # noqa: S310 — pinned HF https URL, hash-verified after download
    return urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT)  # noqa: S310


def download_dataset(dest: Path, *, url: str = DATASET_URL, expected_sha256: str,
                     opener: Callable[[str], object] = _urlopen,
                     chunk: int = 1 << 20) -> DownloadResult:
    """Stream ``url`` to ``dest``, verifying SHA-256 against ``expected_sha256``.

    Streams to a sibling temp file while hashing, then atomically moves it into
    place only after the digest is confirmed. On a mismatch it raises
    ``DatasetIntegrityError`` and leaves **no** file at ``dest`` (the temp is
    removed). When ``expected_sha256`` is empty the download runs in capture mode
    — it still writes the file and reports the computed hash, but marks the
    result ``verified=False`` (a headline run must pass a pinned hash).
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), prefix=".dl-", suffix=".part")
    tmp = Path(tmp_name)
    try:
        with opener(url) as resp, open(fd, "wb") as out:  # both closed on every exit
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                h.update(block)
                out.write(block)
        digest = h.hexdigest()
        if expected_sha256 and digest != expected_sha256:
            raise DatasetIntegrityError(
                f"dataset SHA-256 mismatch: got {digest}, expected {expected_sha256} "
                f"(url={url}). Refusing to install a corpus from a divergent download."
            )
        tmp.replace(dest)
        return DownloadResult(path=dest, sha256=digest, verified=bool(expected_sha256))
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Emit the canonical manifest (the committed reproducibility snapshot).

    ``--out PATH`` writes it (default: ``harness/longmemeval/manifest.json``);
    otherwise it prints to stdout. Regenerate + commit after pinning
    ``DATASET_SHA256`` so the F3 critic re-run reads a complete manifest.
    """
    import argparse

    ap = argparse.ArgumentParser(description="emit the LongMemEval reproducibility manifest")
    ap.add_argument("--out", default=None, help="write the manifest JSON here")
    args = ap.parse_args(argv)
    blob = default_manifest().to_json()
    if args.out:
        Path(args.out).write_text(blob + "\n", encoding="utf-8")
        print(f"wrote manifest → {args.out}")
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
