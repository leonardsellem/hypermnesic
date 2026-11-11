"""LS-4075 — the optional spend envelope on the embedding provider seam.

The guard lives at the *external SDK seam*, so these tests patch ``openai.OpenAI``
(a physical request is a counted call) and use REAL reservation files, REAL
``flock``s and a REAL multi-process wave. No network, no key, no paid call.

The product contract: unset env → unchanged behavior; set env → one durable,
never-refunded reservation per physical request, and every unusable state is a
classified refusal that never reaches the provider.
"""

from __future__ import annotations

import json
import multiprocessing
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from hypermnesic import _spend_envelope as env_mod
from hypermnesic import cli, config, serialize
from hypermnesic import converge as converge_mod
from hypermnesic import embed as embed_mod
from hypermnesic import index as index_mod

KEY = "sk-unit-test-key"


# --- the external SDK seam ------------------------------------------------------

@pytest.fixture
def sdk(monkeypatch):
    """Patch the OpenAI SDK: every physical request is one counted call."""
    state = SimpleNamespace(calls=[], init_kwargs=[], fail=None)

    class _Client:
        def __init__(self, **kwargs):
            state.init_kwargs.append(kwargs)
            self.embeddings = self

        def create(self, *, model, input, dimensions):
            state.calls.append({"model": model, "inputs": list(input), "dimensions": dimensions})
            if state.fail is not None:
                raise state.fail
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * dimensions)
                                         for _ in input])

    monkeypatch.setattr("openai.OpenAI", _Client)
    return state


def _embedder(**kwargs):
    return embed_mod.OpenAIEmbedder(api_key=KEY, cooldown_seconds=0, **kwargs)


def _ts(delta_seconds: float) -> str:
    moment = datetime.now(UTC) + timedelta(seconds=delta_seconds)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Envelope:
    """A real on-disk envelope state in a private tmp dir."""

    def __init__(self, tmp_path: Path, monkeypatch, *, enable: bool = True):
        self.dir = tmp_path / "envelope"
        self.dir.mkdir(exist_ok=True)
        self.path = self.dir / "state.json"
        if enable:
            monkeypatch.setenv(env_mod.ENV_VAR, str(self.path))

    def write(self, *, limit: int = 50_000_000, model: str = config.EMBED_MODEL,
              expires_in: float = 3600, reservations=(), mode: int = 0o600,
              raw: str | None = None, **overrides) -> None:
        if raw is not None:
            self.path.write_text(raw, encoding="utf-8")
        else:
            state = {
                "schema": env_mod.SCHEMA,
                "envelope_id": "ls4075-test-envelope",
                "expires_at": _ts(expires_in),
                "model": model,
                "limit_micro_usd": limit,
                "reservations": [
                    {"request_id": f"seed-{i}", "timestamp": _ts(0), "utf8_bytes": 0,
                     "reserved_micro_usd": reserved}
                    for i, reserved in enumerate(reservations)
                ],
            }
            state.update(overrides)
            self.path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        self.path.chmod(mode)

    def read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def rows(self) -> list[dict]:
        return self.read()["reservations"]

    def total(self) -> int:
        return sum(row["reserved_micro_usd"] for row in self.rows())


@pytest.fixture
def envelope(tmp_path, monkeypatch):
    return Envelope(tmp_path, monkeypatch)


def _refusal(exc_info) -> str:
    return exc_info.value.reason


def _build_stale_index(repo, fake_embedder) -> None:
    """Build a real index, then drop its chunk vectors so a drain has work to do."""
    idx = index_mod.build_index(repo, fake_embedder)
    try:
        idx.conn.execute("DELETE FROM vec_chunks")
        idx.conn.commit()
        assert idx.stale_chunk_ids()
    finally:
        idx.close()


# --- the bound ----------------------------------------------------------------

def test_reserve_bound_is_the_published_rate_on_bytes():
    # 1 MiB of input: tokens <= bytes at 0.13 USD/1M tokens => 0.13 USD = 130_000 micro-USD.
    assert env_mod._reserve_micro_usd(1_000_000, 0) == 130_000
    assert env_mod._reserve_micro_usd(100, 0) == 13
    assert env_mod._reserve_micro_usd(1, 0) == 1          # 0.13 micro-USD rounds up to 1
    assert env_mod._reserve_micro_usd(0, 1) == 1
    assert env_mod._reserve_micro_usd(0, 0) == 1          # never a zero-cost request


# --- absent env: the product is unchanged -------------------------------------

def test_absent_envelope_keeps_generic_behavior(sdk, tmp_path, monkeypatch):
    monkeypatch.delenv(env_mod.ENV_VAR, raising=False)
    emb = _embedder()
    assert len(emb.embed(["hello"])) == 1
    assert len(emb.embed(["hello again"])) == 1
    assert len(sdk.calls) == 2
    assert "max_retries" not in sdk.init_kwargs[0]        # SDK default retries untouched
    assert list(tmp_path.iterdir()) == []


# --- admitted then refused, with an unchanged SDK counter ----------------------

def test_admitted_call_then_refusal_without_a_second_sdk_call(sdk, envelope):
    texts = ["x" * 100]
    per_request = env_mod._reserve_micro_usd(100, 1)
    envelope.write(limit=per_request)

    assert len(_embedder().embed(texts)) == 1
    assert len(sdk.calls) == 1
    assert envelope.rows()[0]["reserved_micro_usd"] == per_request
    assert envelope.rows()[0]["utf8_bytes"] == 100

    with pytest.raises(embed_mod.EmbeddingError) as refused:
        _embedder().embed(texts)
    assert _refusal(refused) == "spend_envelope_exhausted"
    assert len(sdk.calls) == 1                            # the refusal cost nothing
    assert envelope.total() == per_request                # no refund, no second row


# --- every unusable state refuses before the provider -------------------------

@pytest.mark.parametrize("case", [
    "missing", "invalid_path", "empty_env", "whitespace_env", "corrupt", "wrong_schema",
    "wrong_keys", "bad_envelope_id", "bad_limit_type", "bad_limit_range", "bad_row",
    "bad_row_bytes", "undercut_reserve", "duplicate_row", "non_finite", "over_committed",
    "expired", "unapproved_state_model", "symlink", "world_writable",
])
def test_unusable_states_refuse_before_any_sdk_call(sdk, envelope, monkeypatch, case):
    good_row = {"request_id": "row-1", "timestamp": _ts(0), "utf8_bytes": 10,
                "reserved_micro_usd": 2}
    if case == "missing":
        pass                                              # never written
    elif case == "invalid_path":
        monkeypatch.setenv(env_mod.ENV_VAR, "relative/state.json")
    elif case == "empty_env":
        envelope.write()
        monkeypatch.setenv(env_mod.ENV_VAR, "")
    elif case == "whitespace_env":
        envelope.write()
        monkeypatch.setenv(env_mod.ENV_VAR, "   ")
    elif case == "corrupt":
        envelope.write(raw="not json at all")
    elif case == "wrong_schema":
        envelope.write(schema="hypermnesic-spend-envelope/v2")
    elif case == "wrong_keys":
        envelope.write(extra="nope")
    elif case == "bad_envelope_id":
        envelope.write(envelope_id="has spaces and is not opaque")
    elif case == "bad_limit_type":
        envelope.write(limit=True)
    elif case == "bad_limit_range":
        envelope.write(limit=0)
    elif case == "bad_row":
        envelope.write(reservations=())
        state = envelope.read()
        state["reservations"] = [{"request_id": "row-1", "timestamp": _ts(0),
                                  "utf8_bytes": 10}]
        envelope.write(raw=json.dumps(state))
    elif case == "bad_row_bytes":
        envelope.write(reservations=())
        state = envelope.read()
        state["reservations"] = [{**good_row, "utf8_bytes": -1}]
        envelope.write(raw=json.dumps(state))
    elif case == "undercut_reserve":
        envelope.write(reservations=())
        state = envelope.read()
        state["reservations"] = [{**good_row, "utf8_bytes": 10_000,
                                  "reserved_micro_usd": 1}]
        envelope.write(raw=json.dumps(state))
    elif case == "duplicate_row":
        envelope.write(reservations=())
        state = envelope.read()
        state["reservations"] = [good_row, dict(good_row)]
        envelope.write(raw=json.dumps(state))
    elif case == "non_finite":
        envelope.write(reservations=())
        state = envelope.read()
        state["limit_micro_usd"] = float("nan")
        envelope.write(raw=json.dumps(state))             # emits the NaN literal
    elif case == "over_committed":
        envelope.write(limit=10, reservations=(4, 4, 4))
    elif case == "expired":
        envelope.write(expires_in=-1)
    elif case == "unapproved_state_model":
        envelope.write(model="text-embedding-ada-002")
    elif case == "symlink":
        envelope.write()
        target = envelope.dir / "real.json"
        target.write_text(envelope.path.read_text(encoding="utf-8"), encoding="utf-8")
        envelope.path.unlink()
        envelope.path.symlink_to(target)
    elif case == "world_writable":
        envelope.write(mode=0o666)

    with pytest.raises(embed_mod.EmbeddingError) as refused:
        _embedder().embed(["hello"])
    reason = _refusal(refused)
    assert reason.startswith("spend_envelope_"), reason
    assert reason != "rate_limited"                       # never misreported as HTTP 429
    assert sdk.calls == []
    assert sdk.init_kwargs == []                          # refused before the client existed
    assert refused.value.provider_code is None


def test_unapproved_embedder_model_refuses(sdk, envelope, monkeypatch):
    envelope.write()
    emb = embed_mod.OpenAIEmbedder(api_key=KEY, model="text-embedding-3-small",
                                   cooldown_seconds=0)
    with pytest.raises(embed_mod.EmbeddingError) as refused:
        emb.embed(["hello"])
    assert _refusal(refused) == "spend_envelope_model"
    assert sdk.calls == []


def test_missing_state_is_never_auto_created(sdk, envelope):
    with pytest.raises(embed_mod.EmbeddingError) as refused:
        _embedder().embed(["hello"])
    assert _refusal(refused) == "spend_envelope_unavailable"
    assert sdk.calls == []
    assert not envelope.path.exists()
    assert not list(envelope.dir.glob("*.json"))


def test_held_lock_refuses_with_no_sdk_call(sdk, envelope):
    envelope.write()
    with serialize.FileLock(Path(f"{envelope.path}.lock")):
        with pytest.raises(embed_mod.EmbeddingError) as refused:
            _embedder().embed(["hello"])
    assert _refusal(refused) == "spend_envelope_locked"
    assert sdk.calls == []
    assert envelope.rows() == []


def test_unwritable_state_refuses_and_forbids_io(sdk, envelope):
    envelope.write()
    Path(f"{envelope.path}.lock").touch()                 # the lock exists; the write cannot
    envelope.dir.chmod(stat.S_IRUSR | stat.S_IXUSR)       # no write on the directory
    try:
        with pytest.raises(embed_mod.EmbeddingError) as refused:
            _embedder().embed(["hello"])
    finally:
        envelope.dir.chmod(stat.S_IRWXU)
    assert _refusal(refused) == "spend_envelope_write_failed"
    assert sdk.calls == []
    assert envelope.rows() == []


# --- the reservation is pessimistic and durable --------------------------------

def test_provider_failure_retains_the_full_reserve(sdk, envelope):
    texts = ["y" * 200]
    envelope.write(limit=env_mod._reserve_micro_usd(200, 1))
    sdk.fail = RuntimeError("provider down")
    with pytest.raises(embed_mod.EmbeddingError) as failed:
        _embedder().embed(texts)
    assert _refusal(failed) == "embedding_error"
    assert len(sdk.calls) == 1
    assert envelope.total() == envelope.read()["limit_micro_usd"]   # nothing refunded

    sdk.fail = None
    with pytest.raises(embed_mod.EmbeddingError) as refused:
        _embedder().embed(texts)
    assert _refusal(refused) == "spend_envelope_exhausted"
    assert len(sdk.calls) == 1


def test_adaptive_retry_reserves_its_own_request(sdk, envelope):
    class RateLimitError(Exception):
        status_code = 429

    texts = ["z" * 200]
    per_request = env_mod._reserve_micro_usd(200, 1)
    envelope.write(limit=per_request * 2)
    sdk.fail = RateLimitError("429")
    with pytest.raises(embed_mod.EmbeddingError) as failed:
        _embedder().embed(texts)
    assert _refusal(failed) == "rate_limited"
    sdk.fail = None
    assert _embedder().embed(texts)
    rows = envelope.rows()
    assert len(rows) == 2                                 # each physical attempt paid its way
    assert envelope.total() == per_request * 2
    assert rows[0]["request_id"] != rows[1]["request_id"]


def test_restart_joins_the_original_state(sdk, envelope):
    per_request = env_mod._reserve_micro_usd(100, 1)
    envelope.write(limit=per_request * 2)
    assert _embedder().embed(["a" * 100])
    assert _embedder().embed(["b" * 100])                 # a fresh embedder joins the same file
    assert len(envelope.rows()) == 2
    assert envelope.total() == per_request * 2
    with pytest.raises(embed_mod.EmbeddingError) as refused:
        _embedder().embed(["c" * 100])
    assert _refusal(refused) == "spend_envelope_exhausted"
    assert len(sdk.calls) == 2


def test_long_lived_process_recovers_when_the_state_is_replenished(sdk, envelope):
    emb = _embedder()                                     # one embedder, like a server
    envelope.write(limit=1)
    with pytest.raises(embed_mod.EmbeddingError) as refused:
        emb.embed(["a" * 100])
    assert _refusal(refused) == "spend_envelope_exhausted"
    assert sdk.calls == []

    envelope.write(limit=1_000)                           # operator re-seeds the same path
    assert len(emb.embed(["a" * 100])) == 1               # no restart, no cached state
    assert len(sdk.calls) == 1


def test_state_holds_counters_only(sdk, envelope):
    envelope.write()
    _embedder().embed(["SECRET-CONTENT-marker"])
    raw = envelope.path.read_text(encoding="utf-8")
    assert "SECRET-CONTENT" not in raw
    assert KEY not in raw
    state = json.loads(raw)
    assert set(state) == {"schema", "envelope_id", "expires_at", "model",
                          "limit_micro_usd", "reservations"}
    row = state["reservations"][0]
    assert set(row) == {"request_id", "timestamp", "utf8_bytes", "reserved_micro_usd"}
    assert row["utf8_bytes"] == len(b"SECRET-CONTENT-marker")
    assert row["timestamp"].endswith("Z")
    assert "total" not in state and "spent_micro_usd" not in state


def test_guarded_client_disables_sdk_retries(sdk, envelope):
    envelope.write()
    _embedder().embed(["hello"])
    assert sdk.init_kwargs[0]["max_retries"] == 0


def test_client_built_before_arming_is_rebuilt_guarded(sdk, envelope, monkeypatch):
    monkeypatch.delenv(env_mod.ENV_VAR, raising=False)
    emb = _embedder()
    emb._get_client()                                    # built while the guard is off
    assert "max_retries" not in sdk.init_kwargs[0]

    envelope.write()                                     # armed after construction
    monkeypatch.setenv(env_mod.ENV_VAR, str(envelope.path))
    _ = emb.embed(["hello"])
    assert sdk.init_kwargs[-1]["max_retries"] == 0       # rebuilt from one decision point
    assert len(envelope.rows()) == 1


def test_structural_row_cap_refuses_as_full(sdk, envelope, monkeypatch):
    monkeypatch.setattr(env_mod, "_MAX_RESERVATIONS", 1)
    envelope.write(limit=1000, reservations=(1, 1))
    with pytest.raises(embed_mod.EmbeddingError) as refused:
        _embedder().embed(["hello"])
    assert _refusal(refused) == "spend_envelope_full"
    assert sdk.calls == []


# --- independent processes cannot oversubscribe -------------------------------

def _reserve_in_child(args) -> str:
    model, texts = args
    try:
        env_mod.reserve(model, texts)
        return "reserved"
    except env_mod.SpendEnvelopeRefused as exc:
        return exc.reason


def test_concurrent_processes_cannot_exceed_the_ceiling(envelope):
    texts = ["p" * 500]
    per_request = env_mod._reserve_micro_usd(500, 1)
    slots = 5
    envelope.write(limit=per_request * slots)
    with multiprocessing.get_context("fork").Pool(6) as pool:
        results = pool.map(_reserve_in_child, [(config.EMBED_MODEL, texts)] * 24)

    assert set(results) <= {"reserved", "spend_envelope_locked", "spend_envelope_exhausted"}
    admitted = results.count("reserved")
    assert admitted >= 1
    assert admitted <= slots
    assert len(envelope.rows()) == admitted
    assert envelope.total() == admitted * per_request
    assert envelope.total() <= envelope.read()["limit_micro_usd"]
    assert len({row["request_id"] for row in envelope.rows()}) == admitted


# --- the seam is single, so every caller shares it -----------------------------

def test_the_provider_seam_is_one_shared_class():
    root = Path(__file__).resolve().parents[1] / "src" / "hypermnesic"
    embedding_calls = sorted(p.name for p in root.glob("*.py")
                             if "embeddings.create" in p.read_text(encoding="utf-8"))
    assert embedding_calls == ["embed.py"]
    for consumer in ("cli.py", "mcp_server.py"):
        assert "OpenAIEmbedder" in (root / consumer).read_text(encoding="utf-8")
    assert "smoke_embed_or_die" in (root / "doctor.py").read_text(encoding="utf-8")


# --- CLI report / convergence -------------------------------------------------

def test_cli_reports_a_budget_refusal_as_a_named_nonbilling_failure(
        sdk, envelope, make_corpus, fake_embedder, capsys):
    repo = make_corpus({"note.md": "# Note\n\nsome text to embed.\n"})
    _build_stale_index(repo, fake_embedder)
    envelope.write(limit=1)

    rc = cli.main(["embed", str(repo), "--json"])
    report = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert report["status"] == "failed"
    assert report["reason"] == "spend_envelope_exhausted"
    assert report["rate_limit_retries"] == 0
    assert report["provider_code"] is None
    assert report["account_state"] == "unverified"
    assert index_mod.validate_embed_report(report) == []
    assert sdk.calls == []


def test_cli_human_report_never_calls_a_budget_refusal_rate_limited(
        sdk, envelope, make_corpus, fake_embedder, capsys):
    repo = make_corpus({"note.md": "# Note\n\nsome text to embed.\n"})
    _build_stale_index(repo, fake_embedder)
    envelope.write(limit=1)

    rc = cli.main(["embed", str(repo)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "spend_envelope_exhausted" in captured.err
    assert "rate-limited" not in captured.err
    assert sdk.calls == []


def test_zero_work_pass_never_touches_the_envelope(sdk, envelope, make_corpus,
                                                   fake_embedder, capsys):
    repo = make_corpus({"note.md": "# Note\n\nfully embedded already.\n"})
    index_mod.build_index(repo, fake_embedder).close()    # every vector present
    envelope.path.unlink(missing_ok=True)                 # an unusable state on purpose

    rc = cli.main(["embed", str(repo), "--json"])
    report = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert report["status"] == "noop"
    assert sdk.calls == []
    assert not envelope.path.exists()


def test_lock_busy_defers_without_reading_the_envelope(sdk, envelope, make_corpus,
                                                       fake_embedder, capsys):
    repo = make_corpus({"note.md": "# Note\n\nsome text to embed.\n"})
    _build_stale_index(repo, fake_embedder)
    envelope.path.unlink(missing_ok=True)
    state = index_mod.state_dir_for(repo)
    with serialize.dense_maintenance_lock(state):
        rc = cli.main(["embed", str(repo), "--json"])
    report = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert report["status"] == "lock_busy"
    assert sdk.calls == []


def test_convergence_degrades_with_the_envelope_reason(sdk, envelope, make_corpus,
                                                        fake_embedder):
    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    idx = index_mod.build_index(repo, fake_embedder)
    try:
        (repo / "b.md").write_text("# B\n\nbeta.\n", encoding="utf-8")
        import subprocess
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "add b"], check=True,
                       capture_output=True)
        envelope.write(limit=1, reservations=(1,))        # already fully reserved
        result = converge_mod.converge(repo, idx, _embedder(), debounce_seconds=0)
    finally:
        idx.close()
    assert result.status == "converged"
    assert result.degraded is True
    assert result.degraded_reason == "spend_envelope_exhausted"
    assert sdk.calls == []
    assert result.replayed >= 1                            # lexical catch-up still happened
