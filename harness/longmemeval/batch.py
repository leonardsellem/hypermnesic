"""OpenAI Batch API transport for the QA headline — 50% cheaper than the sync API.

Model-agnostic. The caller builds a list of chat.completions request dicts (each
with a unique ``custom_id``); this uploads them as one batch, polls to completion,
and returns ``{custom_id: {"content": str|None, "error": str|None}}``. The
QA-specific request *assembly* and result *parsing* live in ``qa.py`` (reusing
``Reader``/``Judge``'s ``request_body`` + ``*_from_content``), so the con/json/
per-type prompt logic has one source shared with the sync path.

The offline 500-Q run is a textbook batch candidate (no interactivity, 24h window
acceptable). ``submit_and_collect`` is transport-only and fully injectable
(``client``, ``sleep``, ``monotonic``) so it is exercised offline with a fake
client; the live submission is validated by the cheap gpt-4.1-mini pre-flight.
"""

from __future__ import annotations

import io
import json
import time
from collections.abc import Callable

_TERMINAL = {"completed", "failed", "expired", "cancelled", "cancelling"}


class BatchError(RuntimeError):
    """Raised when a batch ends in a non-``completed`` terminal state or times out."""


def to_jsonl(requests: list[dict]) -> bytes:
    return ("\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n").encode("utf-8")


def _read_file(client, file_id: str) -> str:
    content = client.files.content(file_id)
    data = content.read() if hasattr(content, "read") else content
    return data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)


def _parse_row(row: dict) -> dict:
    err = row.get("error")
    resp = row.get("response") or {}
    if err or resp.get("status_code") != 200:
        return {"content": None, "error": str(err or f"status {resp.get('status_code')}")}
    try:
        return {"content": resp["body"]["choices"][0]["message"]["content"], "error": None}
    except (KeyError, IndexError, TypeError) as exc:  # malformed completion body
        return {"content": None, "error": f"malformed response: {exc!r}"}


def submit_and_collect(client, requests: list[dict], *,
                       endpoint: str = "/v1/chat/completions",
                       completion_window: str = "24h",
                       poll_interval: float = 15.0,
                       timeout: float = 24 * 3600,
                       sleep: Callable[[float], None] = time.sleep,
                       monotonic: Callable[[], float] = time.monotonic,
                       log: Callable[[str], None] = lambda _m: None) -> dict[str, dict]:
    """Upload ``requests`` as one batch, poll to completion, and return per-custom_id
    results. Raises ``BatchError`` on a non-completed terminal state or timeout."""
    if not requests:
        return {}
    upload = client.files.create(file=io.BytesIO(to_jsonl(requests)), purpose="batch")
    batch = client.batches.create(input_file_id=upload.id, endpoint=endpoint,
                                  completion_window=completion_window)
    log(f"batch {batch.id}: submitted {len(requests)} requests")
    deadline = monotonic() + timeout
    while batch.status not in _TERMINAL:
        if monotonic() > deadline:
            raise BatchError(f"batch {batch.id} timed out in status {batch.status!r}")
        sleep(poll_interval)
        batch = client.batches.retrieve(batch.id)
        log(f"batch {batch.id}: {batch.status}")
    if batch.status != "completed":
        raise BatchError(f"batch {batch.id} ended in status {batch.status!r}")

    out: dict[str, dict] = {}
    output_file_id = getattr(batch, "output_file_id", None)
    if output_file_id:
        for line in _read_file(client, output_file_id).splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["custom_id"]] = _parse_row(row)
    error_file_id = getattr(batch, "error_file_id", None)
    if error_file_id:  # requests that errored before producing a completion
        for line in _read_file(client, error_file_id).splitlines():
            if line.strip():
                row = json.loads(line)
                out.setdefault(row["custom_id"],
                               {"content": None, "error": str(row.get("error") or "batch error")})
    return out
