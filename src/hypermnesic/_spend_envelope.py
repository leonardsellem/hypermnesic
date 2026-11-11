"""Optional, fail-closed spend envelope on the one embedding provider seam.

Set ``HYPERMNESIC_SPEND_ENVELOPE`` to an **existing absolute** JSON state file to
put a hard, non-renewing ceiling on every physical embeddings request. Unset, the
engine behaves exactly as before: no lock, no file, SDK retries unchanged.

While it is set, :meth:`embed.OpenAIEmbedder.embed` reserves the pessimistic cost
bound of the request **before any SDK I/O**, under one adjacent persistent
``flock`` that spans read → validate → append → atomic write. A reservation is
never refunded: success, provider failure, crash and unknown outcome all keep it,
so the file bounds exposure (a reserve, never an invoice) and a crash can waste
allowance but can never overspend it. The file holds counters only — request ids,
timestamps, UTF-8 byte counts, micro-USD — never input text and never a
credential. Nothing here auto-creates, resets or repairs the state: every
unusable state is a refusal, and a refusal never reaches the network.

Bound, at the published rate of 0.13 USD per 1M tokens for
``text-embedding-3-large``: the model's encoding is ``cl100k_base``, where every
token covers at least one UTF-8 byte (so ``tokens <= bytes``), with one extra
token allowed per input for a provider-side special token. Hence
``ceil((bytes + inputs) * 13 / 100)`` micro-USD per physical request.
"""

from __future__ import annotations

import json
import os
import re
import stat
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from hypermnesic import config, serialize

ENV_VAR = "HYPERMNESIC_SPEND_ENVELOPE"
SCHEMA = "hypermnesic-spend-envelope/v1"

# Published text-embedding-3-large price: 0.13 USD / 1M tokens = 13 micro-USD/100 tokens.
_MICRO_USD_PER_100_TOKENS = 13
_MAX_STATE_BYTES = 64 * 1024 * 1024
_MAX_UTF8_BYTES = 1 << 40
# shortcut: the whole reserve list is read and appended per request (O(rows));
# a fresh envelope is the compaction path, never a reset of this one.
_MAX_RESERVATIONS = 500_000

_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_STATE_KEYS = frozenset(
    {"schema", "envelope_id", "expires_at", "model", "limit_micro_usd", "reservations"})
_ROW_KEYS = frozenset({"request_id", "timestamp", "utf8_bytes", "reserved_micro_usd"})


class SpendEnvelopeRefused(RuntimeError):
    """Admission is impossible; raised before any SDK I/O.

    ``reason`` is one of the ``spend_envelope_*`` classes and is safe to report
    (it never carries input text, a path fragment beyond the class, or a secret).
    """

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason


def path() -> Path | None:
    """The configured state path, or ``None`` when the guard is not enabled."""
    raw = os.environ.get(ENV_VAR)
    if raw is None or not raw.strip():
        return None
    return Path(raw.strip())


def enabled() -> bool:
    return path() is not None


def reserve(model: str, texts: list[str]) -> None:
    """Durably reserve one physical request, or refuse before any provider call.

    No-op when the guard is not enabled. The lock, the read, the cumulative-total
    check, the append and the fsynced atomic write all happen under one lock, so
    independent processes cannot oversubscribe the same ceiling.
    """
    state_path = path()
    if state_path is None:
        return
    if not state_path.is_absolute():
        raise SpendEnvelopeRefused(
            "spend_envelope_invalid_path", f"{ENV_VAR} must be an absolute path")
    if not state_path.parent.is_dir():
        raise SpendEnvelopeRefused(
            "spend_envelope_unavailable", "envelope directory is missing")
    utf8_bytes = sum(len(text.encode("utf-8")) for text in texts)
    reserved_micro_usd = _reserve_micro_usd(utf8_bytes, len(texts))

    lock = serialize.FileLock(Path(f"{state_path}.lock"))
    try:
        lock.acquire()                       # non-blocking: a held lock refuses, never queues
    except serialize.LockBusyError as exc:
        raise SpendEnvelopeRefused(
            "spend_envelope_locked", "envelope state is locked by another process") from exc
    except OSError as exc:
        raise SpendEnvelopeRefused(
            "spend_envelope_unavailable", "could not open the envelope lock") from exc
    try:
        state = _read_state(state_path)
        if state["model"] != model:
            raise SpendEnvelopeRefused(
                "spend_envelope_model",
                f"envelope is bound to {state['model']!r}, not {model!r}")
        reserved_total = sum(row["reserved_micro_usd"] for row in state["reservations"])
        if reserved_total + reserved_micro_usd > state["limit_micro_usd"]:
            raise SpendEnvelopeRefused(
                "spend_envelope_exhausted",
                f"reserved {reserved_total} + {reserved_micro_usd} "
                f"> limit {state['limit_micro_usd']} micro-USD")
        state["reservations"].append({
            "request_id": _request_id(),
            "timestamp": _now_text(),
            "utf8_bytes": utf8_bytes,
            "reserved_micro_usd": reserved_micro_usd,
        })
        _write_state(state_path, state)      # a failed persistence forbids the call
    finally:
        lock.release()


def _reserve_micro_usd(utf8_bytes: int, inputs: int) -> int:
    """Pessimistic bound: ceil at 13 micro-USD per 100 byte-equivalent tokens."""
    tokens = utf8_bytes + inputs              # +1 token per input for a special token
    return max(1, -(-tokens * _MICRO_USD_PER_100_TOKENS // 100))


def _now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _request_id() -> str:
    return f"{time.time_ns():020d}-{uuid.uuid4().hex[:12]}"


def _parse_timestamp(value) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be an RFC3339 UTC string ending in Z")
    parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("timestamp must be UTC")
    return parsed


def _reject_constant(name: str):
    raise ValueError(f"non-finite JSON constant {name}")


def _read_state(state_path: Path) -> dict:
    """Refuse any state that is missing, unsafe, malformed or expired."""
    try:
        info = os.lstat(state_path)
    except OSError as exc:
        raise SpendEnvelopeRefused(
            "spend_envelope_unavailable", "envelope state is missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise SpendEnvelopeRefused(
            "spend_envelope_unavailable", "envelope state is not a regular file")
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise SpendEnvelopeRefused(
            "spend_envelope_unavailable",
            "envelope state must be owned by this user and not group/other writable")
    if info.st_size > _MAX_STATE_BYTES:
        raise SpendEnvelopeRefused("spend_envelope_invalid", "envelope state is too large")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"),
                           parse_constant=_reject_constant)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SpendEnvelopeRefused(
            "spend_envelope_invalid", "envelope state is not valid JSON") from exc

    if not isinstance(state, dict) or set(state) != _STATE_KEYS:
        raise SpendEnvelopeRefused("spend_envelope_invalid", "envelope state has wrong keys")
    if state["schema"] != SCHEMA:
        raise SpendEnvelopeRefused("spend_envelope_invalid", "envelope schema mismatch")
    if not isinstance(state["envelope_id"], str) or not _ID_RE.match(state["envelope_id"]):
        raise SpendEnvelopeRefused("spend_envelope_invalid", "envelope_id is not an opaque id")
    if not isinstance(state["model"], str):
        raise SpendEnvelopeRefused("spend_envelope_invalid", "model is not a string")
    if state["model"] != config.EMBED_MODEL:
        raise SpendEnvelopeRefused(
            "spend_envelope_model", f"envelope model {state['model']!r} is not approved")
    limit = state["limit_micro_usd"]
    if not _is_int(limit) or limit <= 0:
        raise SpendEnvelopeRefused(
            "spend_envelope_invalid", "limit_micro_usd must be a positive integer")
    try:
        expires_at = _parse_timestamp(state["expires_at"])
    except ValueError as exc:
        raise SpendEnvelopeRefused(
            "spend_envelope_invalid",
            "expires_at is not an absolute RFC3339 UTC timestamp") from exc
    rows = state["reservations"]
    if not isinstance(rows, list) or len(rows) > _MAX_RESERVATIONS:
        raise SpendEnvelopeRefused("spend_envelope_invalid", "reservations is not a bounded list")

    seen: set[str] = set()
    reserved_total = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise SpendEnvelopeRefused("spend_envelope_invalid", "reservation has wrong keys")
        request_id = row["request_id"]
        if not isinstance(request_id, str) or not _ID_RE.match(request_id):
            raise SpendEnvelopeRefused(
                "spend_envelope_invalid", "request_id is not an opaque id")
        if request_id in seen:
            raise SpendEnvelopeRefused("spend_envelope_invalid", "duplicate request_id")
        seen.add(request_id)
        try:
            _parse_timestamp(row["timestamp"])
        except ValueError as exc:
            raise SpendEnvelopeRefused(
                "spend_envelope_invalid", "reservation timestamp is not RFC3339 UTC") from exc
        utf8_bytes = row["utf8_bytes"]
        if not _is_int(utf8_bytes) or not 0 <= utf8_bytes <= _MAX_UTF8_BYTES:
            raise SpendEnvelopeRefused(
                "spend_envelope_invalid", "reservation utf8_bytes is out of range")
        reserved = row["reserved_micro_usd"]
        if (not _is_int(reserved) or reserved < _min_reserve(utf8_bytes)
                or reserved > limit):
            raise SpendEnvelopeRefused(
                "spend_envelope_invalid", "reservation reserved_micro_usd is out of range")
        reserved_total += reserved
    if reserved_total > limit:
        raise SpendEnvelopeRefused(
            "spend_envelope_invalid", "reservations exceed the envelope limit")
    if datetime.now(UTC) >= expires_at:
        raise SpendEnvelopeRefused("spend_envelope_expired", "envelope has expired")
    return state


def _min_reserve(utf8_bytes: int) -> int:
    """A row may never record less than the bytes-only bound for its own request."""
    return max(1, -(-utf8_bytes * _MICRO_USD_PER_100_TOKENS // 100))


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _write_state(state_path: Path, state: dict) -> None:
    """Replace the state atomically: temp file in the same dir, fsync, rename, fsync dir."""
    tmp = state_path.with_name(f".{state_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, state_path)
        dir_fd = os.open(state_path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise SpendEnvelopeRefused(
            "spend_envelope_write_failed", "could not persist the reservation") from exc
