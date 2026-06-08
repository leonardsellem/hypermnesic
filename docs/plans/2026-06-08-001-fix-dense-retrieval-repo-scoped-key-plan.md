# Dense Retrieval Repo-Scoped Key Lookup Implementation Plan

> **For implementers:** implement this plan task-by-task. Do not implement directly from the brainstorm; this plan is the scope of record for dense retrieval reliability.

**Goal:** Make dense/vector retrieval use the vault/repo-scoped `.env` from every repo-addressed CLI and MCP path, while keeping secret-free diagnostics and graceful lexical fallback.

**Architecture:** Add a single repo-aware credential resolver in `config.py`, thread repo context through `OpenAIEmbedder` and OpenAI expansion, and update doctor/MCP/CLI callers to construct embedders with the same repo they already use for index convergence. Keep read paths available when dense is down; improve `doctor` details so missing index, missing key, invalid key, and stale vectors are distinguishable.

**Tech Stack:** Python 3.11+, argparse CLI, FastMCP server backend, OpenAI SDK, SQLite/FTS5/sqlite-vec, `uv`, pytest with git-backed fixture repos.

---

## Source Requirements

- Requirements document: `docs/brainstorms/2026-06-08-dense-retrieval-reliability-requirements.md`
- Investigation symptom: `hypermnesic doctor /path/to/vault --json` reports `dense_retrieval=fail` when launched outside the vault even though `/path/to/vault/.env` contains a valid `OPENAI_API_KEY`.
- Branch for implementation: create a branch off `origin/main`, for example:
  `fix/dense-retrieval-repo-scoped-key-lookup`.

## Zero-Core Boundary

This is a **Hypermnesic-only** plan. It must preserve the user's zero-core constraint:

- Do **not** edit the Hermes Agent codebase, Hermes core runtime, Hermes gateway, Hermes WebUI, or
  any files under `~/.hermes/`.
- Do **not** add or require a Hermes Agent wrapper, plugin, skill, model/provider config change, or
  profile-memory change as part of the implementation.
- Do **not** make Hypermnesic depend on Hermes Agent behavior for dense retrieval. The fix belongs
  entirely inside this repository's package, tests, and docs.
- If a future operator wants an external shell wrapper or secret-manager integration, document it as
  optional operational guidance only; it is not part of this core fix.

## Current State / Evidence

Observed source paths:

- `src/hypermnesic/config.py`
  - `_DOTENV_PATHS = [Path.cwd() / ".env"]` is evaluated at import time.
  - `get_api_key()` checks only process `OPENAI_API_KEY` and `_DOTENV_PATHS`.
  - No current API accepts a `repo` or reports a non-secret source category.
- `src/hypermnesic/embed.py`
  - `OpenAIEmbedder` stores an optional explicit `api_key`, but otherwise calls `config.get_api_key()` with no repo context.
  - `smoke_embed_or_die()` also calls `config.get_api_key()` with no repo context.
- `src/hypermnesic/expand.py`
  - `OpenAIExpander` uses `config.get_api_key()` with no repo context.
- `src/hypermnesic/doctor.py`
  - `run_doctor(repo, ...)` receives the repo path but `_has_api_key()` ignores it.
  - `dense_retrieval` is a coarse pass/fail check with no source category, live-check state, or vector coverage detail.
- `src/hypermnesic/mcp_server.py`
  - `_Backend` already derives `repo` from `<repo>/.hypermnesic/index.db` when `repo` is omitted.
  - `_Backend.embedder` constructs `embed.OpenAIEmbedder()` without passing the derived repo.
  - `build_cloud_server(...)` passes `repo` through to `build_server(...)`, so cloud can inherit the same backend fix.
- `src/hypermnesic/cli.py`
  - Dense-required commands (`index`, `embed`, `reindex`, `init`) call `smoke_embed_or_die()` and `OpenAIEmbedder()` without repo context.
  - Dense-optional read/converge commands (`think`, `retrieve`, `local-proof --dense`, `resolve`, `list-folders`, `converge`, `memory`) construct `OpenAIEmbedder()` without repo context.
  - `serve`/`serve-cloud` rely on `mcp_server` construction.
- Existing tests:
  - `tests/test_doctor.py` covers doctor output shape, non-mutation, and secret-free output, but not repo `.env` lookup from a different cwd.
  - `tests/test_index.py::test_smoke_embed_fails_loud_on_missing_key` covers missing key via patched `_DOTENV_PATHS`.
  - `tests/test_install.py` already checks systemd units reference `EnvironmentFile` and do not inline secrets.
  - There is no `tests/test_config.py` yet.

Root cause: dense credential lookup is cwd-scoped while the product and CLI are repo-scoped.

## Requirements / Acceptance Criteria

### Functional

1. Process env `OPENAI_API_KEY` remains the highest-priority key source.
2. Repo-aware flows must check `<repo>/.env` after process env and then stop. They must not fall through to cwd `.env` when an explicit repo context exists.
3. Historical cwd `.env` fallback may remain only for flows with no repo context (`repo is None`). It must not be used for repo-addressed commands or servers.
4. `doctor.run_doctor(repo, ...)` must report dense configured when `<repo>/.env` exists even if the process cwd is elsewhere.
5. `OpenAIEmbedder(repo=repo)` and `smoke_embed_or_die(repo=repo)` must use the same repo-aware key lookup.
6. MCP `_Backend` must pass its derived repo to `OpenAIEmbedder`, including the no-`--repo` case where repo is derived from `--index-db`.
7. CLI commands that already know `args.repo` must pass that path into the embedder/smoke-check.
8. Read paths must continue graceful lexical fallback when dense is missing or fails.

### Diagnostics

1. `doctor` must stay non-mutating and secret-free.
2. `dense_retrieval` detail should include non-secret fields such as:
   - `key_configured: bool`
   - `key_source: "process_env" | "repo_dotenv" | "cwd_dotenv" | "missing"`
   - `dense_state: "not_configured" | "configured_unverified" | "configured_valid" | "configured_invalid" | "index_missing_or_unbuilt" | "vectors_stale_or_absent"`
   - `live_check: "skipped" | "pass" | "fail"`
   - optional `vector_coverage` when an index exists
3. Human doctor output must remain readable and not print secret values, `.env` values, or absolute operator paths.
4. Add an explicit `--check-dense-live` flag to `doctor`/`status` for live smoke embedding. Default doctor remains offline-friendly and reports `configured_unverified` when a key is found but the live check is skipped.

### Vector coverage

When an index exists, doctor should add coverage detail under `dense_retrieval.detail.vector_coverage`:

- `chunks_total`
- `chunk_vectors`
- `chunks_missing_vectors`
- `docs_total`
- `doc_vectors`
- `docs_missing_vectors`

Do not expose note bodies, key values, or absolute paths in this diagnostic.

### Documentation

Because this changes configuration and CLI diagnostics, update in the same implementation PR:

- `docs/reference/configuration.md`
- `docs/reference/cli.md`
- `README.md` if quick-start/dense wording needs correction
- `CHANGELOG.md` under `[Unreleased]`

## Proposed Approach

Ship a narrow repo-aware resolver rather than per-call workarounds.

1. Introduce a small structured status object in `config.py`:

   ```python
   @dataclass(frozen=True)
   class ApiKeyStatus:
       configured: bool
       source: str  # process_env | repo_dotenv | cwd_dotenv | missing
       checked: tuple[str, ...]
       error: str | None = None
   ```

   The object must never contain the key value or an absolute file path.

2. Add helper functions:

   ```python
   def api_key_status(repo: Path | str | None = None) -> ApiKeyStatus: ...
   def get_api_key(repo: Path | str | None = None) -> str: ...
   ```

   Resolution order:

   1. `os.environ["OPENAI_API_KEY"]` → `process_env`
   2. If `repo is not None`: `<repo>/.env` → `repo_dotenv`; otherwise `missing`.
   3. If `repo is None` only: `_DOTENV_PATHS` fallback → `cwd_dotenv`.
   4. missing → `missing`.

   Preserve existing quoted-value parsing for `.env` lines.

3. Thread `repo` through OpenAI helpers:

   - `embed.OpenAIEmbedder(api_key=None, repo=None, ...)`
   - `embed.smoke_embed_or_die(embedder=None, repo=None)`
   - `expand.OpenAIExpander(api_key=None, repo=None, ...)`

4. Update CLI constructors to pass `Path(args.repo)` where available. For server paths, update `_Backend.embedder` to pass `self.repo`.

5. Update doctor to call `config.api_key_status(repo)` and optionally run `embed.smoke_embed_or_die(repo=repo)` when `check_dense_live=True`.

6. Add vector coverage helper in `doctor.py` or `index.py`. Prefer `doctor.py` for diagnostics-only SQL unless the same coverage is reused elsewhere.
7. Add explicit dense next-action mapping in `doctor.py`. The structured `dense_state` is not enough:
   the diagnostic must map each failure class to an actionable, secret-free remediation:
   - missing key → export `OPENAI_API_KEY` or create gitignored `<repo>/.env`;
   - unreadable repo `.env` → repair file permissions or set process env;
   - invalid live check → repair/rotate key or network and rerun `--check-dense-live`;
   - missing index → run `hypermnesic local-proof /path/to/vault` or `hypermnesic init /path/to/vault`;
   - stale/absent vectors → run `hypermnesic converge /path/to/vault --now --json` or manual reindex if the coverage signal says convergence is insufficient.
8. For `--index-db` server paths, validate or clearly document repo derivation from
   `<repo>/.hypermnesic/index.db`. If the path does not match that shape and `--repo` was omitted,
   fail or diagnose actionably with: “pass `--repo /path/to/vault`”. Do not silently use an unsafe
   parent-parent guess for credential lookup in ambiguous cases.

## Implementation Phases

### Phase 0: Branch and baseline

**Objective:** Start from a clean branch and capture baseline behavior.

**Files:** none.

**Steps:**

1. Create branch:

   ```bash
   cd /path/to/hypermnesic
   git fetch origin main
   git checkout -b fix/dense-retrieval-repo-scoped-key-lookup origin/main
   ```

2. Run focused baseline tests:

   ```bash
   uv run pytest tests/test_doctor.py tests/test_index.py tests/test_install.py -q -o 'addopts='
   ```

   Expected: PASS on a clean baseline. If not, stop and record the failure before editing.

3. Reproduce the current bug manually if the repo `.env` is available:

   ```bash
   cd /tmp
   env -u OPENAI_API_KEY uv --project /path/to/hypermnesic run hypermnesic doctor /path/to/vault --json
   ```

   Current expected before fix: `dense_retrieval` fails when process env lacks `OPENAI_API_KEY`.

### Phase 1: Add credential-resolution unit tests

**Objective:** Lock in repo-scoped lookup, precedence, secret-free metadata, and backwards-compatible missing-key behavior before changing production code.

**Files:**

- Create: `tests/test_config.py`
- Modify only if needed: `tests/test_index.py`

**Tests to add in `tests/test_config.py`:**

```python
from __future__ import annotations

from hypermnesic import config

_KEY_NAME = "OPENAI_" + "API_KEY"


def _dotenv_line(value: str) -> str:
    return f"{_KEY_NAME}={value}\n"


def test_api_key_status_finds_repo_dotenv_from_different_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    repo_key = "repo-test-key"
    repo = tmp_path / "vault"
    repo.mkdir()
    (repo / ".env").write_text(_dotenv_line(f"'{repo_key}'"), encoding="utf-8")
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(config, "_DOTENV_PATHS", [cwd / ".env"])

    status = config.api_key_status(repo)

    assert status.configured is True
    assert status.source == "repo_dotenv"
    assert config.get_api_key(repo) == repo_key
    assert repo_key not in repr(status)


def test_process_env_precedes_repo_dotenv(monkeypatch, tmp_path):
    repo_key = "repo-test-key"
    env_key = "env-test-key"
    repo = tmp_path / "vault"
    repo.mkdir()
    (repo / ".env").write_text(_dotenv_line(repo_key), encoding="utf-8")
    monkeypatch.setenv(_KEY_NAME, env_key)

    status = config.api_key_status(repo)

    assert status.configured is True
    assert status.source == "process_env"
    assert config.get_api_key(repo) == env_key
    assert repo_key not in repr(status)
    assert env_key not in repr(status)


def test_repo_context_does_not_fall_back_to_cwd_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    cwd_key = "cwd-test-key"
    repo = tmp_path / "vault"
    repo.mkdir()
    cwd_env = tmp_path / "cwd.env"
    cwd_env.write_text(_dotenv_line(cwd_key), encoding="utf-8")
    monkeypatch.setattr(config, "_DOTENV_PATHS", [cwd_env])

    status = config.api_key_status(repo)

    assert status.configured is False
    assert status.source == "missing"


def test_cwd_dotenv_fallback_when_no_repo_context(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    cwd_key = "cwd-test-key"
    cwd_env = tmp_path / "cwd.env"
    cwd_env.write_text(_dotenv_line(cwd_key), encoding="utf-8")
    monkeypatch.setattr(config, "_DOTENV_PATHS", [cwd_env])

    status = config.api_key_status(repo=None)

    assert status.configured is True
    assert status.source == "cwd_dotenv"
    assert config.get_api_key(repo=None) == cwd_key


def test_missing_key_reports_missing_without_paths_or_secret(monkeypatch, tmp_path):
    monkeypatch.delenv(_KEY_NAME, raising=False)
    repo = tmp_path / "vault"
    repo.mkdir()
    monkeypatch.setattr(config, "_DOTENV_PATHS", [tmp_path / "absent.env"])

    status = config.api_key_status(repo)

    assert status.configured is False
    assert status.source == "missing"
    assert str(tmp_path) not in repr(status)
```

**Run to verify failure before implementation:**

```bash
uv run pytest tests/test_config.py -q -o 'addopts='
```

Expected before code changes: FAIL because `api_key_status` does not exist.

### Phase 2: Implement repo-aware key status in `config.py`

**Objective:** Add the single source of truth for repo-aware secret lookup.

**Files:**

- Modify: `src/hypermnesic/config.py`
- Test: `tests/test_config.py`

**Implementation details:**

1. Import `dataclass` and keep `Path`.
2. Add `ApiKeyStatus` with only non-secret fields.
3. Extract dotenv parsing into a helper that can read a specific path **without collapsing unreadable and absent files**:

   ```python
   @dataclass(frozen=True)
   class DotenvRead:
       key: str | None = None
       unreadable: bool = False

   def _read_dotenv_key_from(path: Path) -> DotenvRead:
       try:
           text = Path(path).read_text(encoding="utf-8")
       except FileNotFoundError:
           return DotenvRead()
       except OSError:
           return DotenvRead(unreadable=True)
       for line in text.splitlines():
           line = line.strip()
           if line.startswith("OPENAI_API_KEY="):
               return DotenvRead(line.split("=", 1)[1].strip().strip('"').strip("'"))
       return DotenvRead()
   ```

4. Preserve `_DOTENV_PATHS` for tests and fallback compatibility, but do not make it the repo-aware primary source.
5. Implement `api_key_status(repo=None)` and `get_api_key(repo=None)` with the precedence above. Define `ApiKeyStatus.checked` as source categories only, for example `("process_env", "repo_dotenv")`; never store absolute paths in it.
6. Preserve unreadable-file observability: an unreadable repo `.env` should produce a non-secret `ApiKeyStatus.error` category such as `repo_dotenv_unreadable` and a missing/failed dense diagnostic with an actionable next step. Add a test for this branch.
7. Keep `ConfigError` wording useful, e.g. mention checked environment, repo `.env` when a repo was supplied, and cwd fallback only when no repo was supplied, but never include values or absolute paths.

**Run:**

```bash
uv run pytest tests/test_config.py tests/test_index.py::test_smoke_embed_fails_loud_on_missing_key -q -o 'addopts='
```

Expected after implementation: PASS.

### Phase 3: Thread repo through embedder and expander

**Objective:** Make all OpenAI helper classes capable of using repo-scoped lookup.

**Files:**

- Modify: `src/hypermnesic/embed.py`
- Modify: `src/hypermnesic/expand.py`
- Modify: `tests/test_index.py` or create focused tests in `tests/test_config.py`

**Changes:**

1. Update `OpenAIEmbedder.__init__`:

   ```python
   def __init__(self, api_key: str | None = None,
                model: str = config.EMBED_MODEL, dim: int = config.EMBED_DIM,
                repo=None):
       self.model = model
       self.dim = dim
       self.repo = repo
       self._api_key = api_key
       self._client = None
   ```

2. Update `_get_client()` to call `config.get_api_key(repo=self.repo)`.
3. Update `smoke_embed_or_die(embedder=None, repo=None)` to call `config.get_api_key(repo=repo)` and construct `OpenAIEmbedder(api_key=key, repo=repo)`.
4. Update `OpenAIExpander.__init__(..., repo=None)` and `_get_client()` similarly.
5. Add behavior-level tests using monkeypatches to avoid the real OpenAI SDK:

   ```python
   def test_openai_embedder_uses_repo_context(monkeypatch, tmp_path):
       from hypermnesic import config
       from hypermnesic.embed import OpenAIEmbedder

       repo = tmp_path / "vault"
       repo.mkdir()
       seen = {}

       def fake_get_api_key(*, repo=None):
           seen["repo"] = repo
           return "env-test-key"

       class FakeEmbeddings:
           def create(self, **_kwargs):
               return type("Resp", (), {"data": [type("Item", (), {"embedding": [0.0] * config.EMBED_DIM})()]})()

       class FakeClient:
           def __init__(self, *, api_key):
               self.embeddings = FakeEmbeddings()

       monkeypatch.setattr(config, "get_api_key", fake_get_api_key)
       monkeypatch.setattr("openai.OpenAI", FakeClient)

       OpenAIEmbedder(repo=repo).embed(["probe"])

       assert seen["repo"] == repo
   ```

   Add analogous tests for `smoke_embed_or_die(repo=...)` and `OpenAIExpander(repo=...)` so the real credential lookup call path is covered, not just constructor attribute storage.

   Do not hit the network in unit tests.

**Run:**

```bash
uv run pytest tests/test_config.py tests/test_index.py -q -o 'addopts='
```

Expected: PASS.

### Phase 4: Update doctor diagnostics and live-check flag

**Objective:** Make `doctor` report repo-scoped key status, optional live smoke status, and vector coverage.

**Files:**

- Modify: `src/hypermnesic/doctor.py`
- Modify: `src/hypermnesic/cli.py`
- Modify: `tests/test_doctor.py`

**API changes:**

1. Extend `doctor.run_doctor(...)` signature:

   ```python
   def run_doctor(repo, *, public_url=None, resource=None, env_file=None, ops=None,
                  check_dense_live: bool = False) -> DoctorResult:
   ```

2. Replace `_has_api_key()` with a helper that accepts repo and live-check flag, for example:

   ```python
   def _dense_retrieval_check(repo: Path, idx_path: Path, *, check_live: bool) -> DiagnosticCheck:
       status = config.api_key_status(repo)
       dense_state = "not_configured"
       live_check = "skipped"
       if status.configured:
           dense_state = "configured_unverified"
           if check_live:
               try:
                   from hypermnesic import embed
                   embed.smoke_embed_or_die(repo=repo)
                   dense_state = "configured_valid"
                   live_check = "pass"
               except embed.EmbeddingError:
                   dense_state = "configured_invalid"
                   live_check = "fail"
       detail = {
           "key_configured": status.configured,
           "key_source": status.source,
           "dense_state": dense_state,
           "live_check": live_check,
       }
       coverage = _vector_coverage(repo, idx_path)
       if coverage is not None:
           detail["vector_coverage"] = coverage
           if status.configured and dense_state != "configured_invalid" and (
               coverage["chunks_missing_vectors"] or coverage["docs_missing_vectors"]
           ):
               dense_state = "vectors_stale_or_absent"
               detail["dense_state"] = dense_state
       elif status.configured and dense_state != "configured_invalid":
           dense_state = "index_missing_or_unbuilt"
           detail["dense_state"] = dense_state
       ...
   ```

3. Keep the top-level `dense_retrieval` status compatible but do not let it imply full dense usability:
   - `pass` may mean “dense credentials are configured” when a key is found and live check is skipped or passes.
   - `fail` when missing or live check fails.
   - If index is missing or vectors are stale/absent while the key is configured, either use `warn` if compatible with the existing status model, or keep top-level `pass` but make the human summary and `dense_state` explicitly say dense retrieval is not fully usable yet. Do not present missing index/stale vectors as healthy dense retrieval.
4. Add `--check-dense-live` to both `doctor` and `status` parser definitions and pass it through to `run_doctor`.
5. Add `_vector_coverage(repo, idx_path)` using schema-aware SQL counts. Return `None` if index is missing or unreadable. Coverage semantics must be:
   - `chunks_total = COUNT(*) FROM chunks`
   - `chunk_vectors = COUNT(*) FROM vec_chunks JOIN chunks USING(chunk_id)` so orphan vectors do not over-report coverage
   - `chunks_missing_vectors = len(idx.stale_chunk_ids())`
   - `docs_total = COUNT(DISTINCT path) FROM chunks` (not `COUNT(*) FROM docs`, because paths with no doc row are exactly missing doc vectors)
   - `doc_vectors = COUNT(*) FROM vec_docs JOIN docs USING(doc_id)` so orphan doc vectors do not over-report coverage
   - `docs_missing_vectors = len(idx.paths_missing_doc_vector())`
   - `manual_reindex_recommended` or an equivalent `catchup_mode`/`can_incrementally_catch_up` signal satisfying R6.
   Add at least one stale/missing vector test that asserts both counts and the catchup/reindex signal.

**Tests to add/update in `tests/test_doctor.py`:**

1. Repo `.env` from non-repo cwd:

   ```python
   _KEY_NAME = "OPENAI_" + "API_KEY"

   def _dotenv_line(value: str) -> str:
       return f"{_KEY_NAME}={value}\n"

   def test_doctor_finds_repo_dotenv_from_different_cwd(
           make_corpus, fake_embedder, monkeypatch, tmp_path):
       monkeypatch.delenv(_KEY_NAME, raising=False)
       monkeypatch.setattr(config, "_DOTENV_PATHS", [tmp_path / "absent.env"])
       repo_key = "repo-test-key"
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
       (repo / ".env").write_text(_dotenv_line(repo_key), encoding="utf-8")
       _build_index(repo, fake_embedder)
       elsewhere = tmp_path / "elsewhere"
       elsewhere.mkdir()
       monkeypatch.chdir(elsewhere)

       out = doctor.run_doctor(repo, ops=_DoctorOps()).as_dict()
       checks = {c["id"]: c for c in out["checks"]}
       dense = checks["dense_retrieval"]

       assert dense["status"] == "pass"
       assert dense["detail"]["key_configured"] is True
       assert dense["detail"]["key_source"] == "repo_dotenv"
       assert dense["detail"]["dense_state"] == "configured_unverified"
       assert dense["detail"]["live_check"] == "skipped"
       assert repo_key not in json.dumps(out)
   ```

2. Process env precedence:

   ```python
   def test_doctor_reports_process_env_precedence(make_corpus, fake_embedder, monkeypatch):
       repo_key = "repo-test-key"
       env_key = "env-test-key"
       monkeypatch.setenv(_KEY_NAME, env_key)
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
       (repo / ".env").write_text(_dotenv_line(repo_key), encoding="utf-8")
       _build_index(repo, fake_embedder)

       out = doctor.run_doctor(repo, ops=_DoctorOps()).as_dict()
       dense = {c["id"]: c for c in out["checks"]}["dense_retrieval"]

       assert dense["detail"]["key_source"] == "process_env"
       assert env_key not in json.dumps(out)
       assert repo_key not in json.dumps(out)
   ```

3. Vector coverage when index exists:

   ```python
   def test_doctor_dense_detail_reports_vector_coverage(make_corpus, fake_embedder, monkeypatch):
       monkeypatch.setenv(_KEY_NAME, "env-test-key")
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
       _build_index(repo, fake_embedder)

       out = doctor.run_doctor(repo, ops=_DoctorOps()).as_dict()
       coverage = {c["id"]: c for c in out["checks"]}["dense_retrieval"]["detail"]["vector_coverage"]

       assert coverage["chunks_total"] >= 1
       assert coverage["chunk_vectors"] >= 1
       assert coverage["chunks_missing_vectors"] == 0
       assert coverage["docs_total"] >= 1
       assert coverage["doc_vectors"] >= 1
       assert coverage["docs_missing_vectors"] == 0
   ```

4. CLI flag passes through:

   ```python
   def test_doctor_cli_accepts_check_dense_live(make_corpus, fake_embedder, monkeypatch, capsys):
       from hypermnesic import cli, embed
       monkeypatch.setenv(_KEY_NAME, "env-test-key")
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
       _build_index(repo, fake_embedder)
       monkeypatch.setattr(embed, "smoke_embed_or_die", lambda repo=None, embedder=None: None)

       rc = cli.main(["doctor", str(repo), "--check-dense-live", "--json"])
       out = json.loads(capsys.readouterr().out)
       dense = {c["id"]: c for c in out["checks"]}["dense_retrieval"]

       assert rc == 0
       assert dense["detail"]["live_check"] == "pass"
   ```

5. Required state-distinction regressions:

   ```python
   def test_doctor_distinguishes_missing_index_from_missing_key(make_corpus, monkeypatch):
       monkeypatch.setenv(_KEY_NAME, "env-test-key")
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})

       dense = {c["id"]: c for c in doctor.run_doctor(repo, ops=_DoctorOps()).as_dict()["checks"]}[
           "dense_retrieval"
       ]

       assert dense["detail"]["key_configured"] is True
       assert dense["detail"]["dense_state"] == "index_missing_or_unbuilt"
       assert "local-proof" in (dense["next_action"]["command"] or dense["next_action"]["summary"])

   def test_doctor_reports_missing_key_even_when_index_exists(make_corpus, fake_embedder, monkeypatch, tmp_path):
       monkeypatch.delenv(_KEY_NAME, raising=False)
       monkeypatch.setattr(config, "_DOTENV_PATHS", [tmp_path / "absent.env"])
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
       _build_index(repo, fake_embedder)

       dense = {c["id"]: c for c in doctor.run_doctor(repo, ops=_DoctorOps()).as_dict()["checks"]}[
           "dense_retrieval"
       ]

       assert dense["status"] == "fail"
       assert dense["detail"]["dense_state"] == "not_configured"
       assert dense["next_action"]["code"] == "configure_key"

   def test_doctor_reports_vectors_stale_or_absent(make_corpus, fake_embedder, monkeypatch):
       monkeypatch.setenv(_KEY_NAME, "env-test-key")
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
       idx = index.build_index(repo, fake_embedder)
       idx.conn.execute("DELETE FROM vec_chunks")
       idx.conn.execute("DELETE FROM vec_docs")
       idx.conn.commit()
       idx.close()

       dense = {c["id"]: c for c in doctor.run_doctor(repo, ops=_DoctorOps()).as_dict()["checks"]}[
           "dense_retrieval"
       ]

       assert dense["detail"]["dense_state"] == "vectors_stale_or_absent"
       assert dense["detail"]["vector_coverage"]["chunks_missing_vectors"] >= 1
       assert dense["detail"]["vector_coverage"]["docs_missing_vectors"] >= 1
       assert "converge" in (dense["next_action"]["command"] or dense["next_action"]["summary"])

   def test_doctor_reports_live_dense_failure(make_corpus, fake_embedder, monkeypatch):
       from hypermnesic import embed
       monkeypatch.setenv(_KEY_NAME, "env-test-key")
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
       _build_index(repo, fake_embedder)
       monkeypatch.setattr(
           embed, "smoke_embed_or_die", lambda **_kw: (_ for _ in ()).throw(embed.EmbeddingError("boom"))
       )

       dense = {c["id"]: c for c in doctor.run_doctor(
           repo, ops=_DoctorOps(), check_dense_live=True
       ).as_dict()["checks"]}["dense_retrieval"]

       assert dense["status"] == "fail"
       assert dense["detail"]["dense_state"] == "configured_invalid"
       assert dense["detail"]["live_check"] == "fail"
       assert dense["next_action"]["code"] in {"repair_key", "repair_network", "repair_dense"}
   ```

6. No cwd fallback in doctor for an explicit different repo:

   ```python
   def test_doctor_does_not_use_cwd_dotenv_for_different_repo(make_corpus, fake_embedder, monkeypatch, tmp_path):
       monkeypatch.delenv(_KEY_NAME, raising=False)
       cwd = tmp_path / "cwd-vault"
       cwd.mkdir()
       (cwd / ".env").write_text(_dotenv_line("cwd-test-key"), encoding="utf-8")
       monkeypatch.chdir(cwd)
       repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
       _build_index(repo, fake_embedder)

       dense = {c["id"]: c for c in doctor.run_doctor(repo, ops=_DoctorOps()).as_dict()["checks"]}[
           "dense_retrieval"
       ]

       assert dense["status"] == "fail"
       assert dense["detail"]["key_source"] == "missing"
       assert dense["detail"]["dense_state"] == "not_configured"
   ```

**Run:**

```bash
uv run pytest tests/test_doctor.py tests/test_config.py -q -o 'addopts='
```

Expected: PASS.

### Phase 5: Thread repo into CLI and MCP dense paths

**Objective:** Ensure every repo-addressed entrypoint constructs dense helpers with repo context.

**Files:**

- Modify: `src/hypermnesic/cli.py`
- Modify: `src/hypermnesic/mcp_server.py`
- Modify: `tests/test_auth_cloud.py` or `tests/test_think.py` for backend behavior
- Modify or add tests in `tests/test_cli.py` if needed

**CLI changes:**

Use `repo = Path(args.repo)` near the top of each repo-aware command, then pass it to embed helpers:

- `_cmd_index`: `embed.smoke_embed_or_die(repo=repo)` and `embed.OpenAIEmbedder(repo=repo)`
- `_cmd_embed`: same
- `_cmd_reindex`: same
- `_cmd_init`: same
- `_cmd_think`: `embed.OpenAIEmbedder(repo=repo)`
- `_cmd_retrieve`: `embed.OpenAIEmbedder(repo=repo)`
- `_cmd_local_proof`: `embed.OpenAIEmbedder(repo=Path(args.repo))` in existing-vault dense mode; demo mode can use `demo_dir` after it is prepared only if available, otherwise preserve current behavior and document as follow-up if needed
- `_cmd_resolve`: `embed.OpenAIEmbedder(repo=repo)`
- `_cmd_list_folders`: `embed.OpenAIEmbedder(repo=repo)`
- `_cmd_converge`: `embed.OpenAIEmbedder(repo=repo)`
- `_cmd_memory`: `embed.OpenAIEmbedder(repo=repo)`

**MCP changes:**

In `_Backend.embedder`:

```python
self._embedder = embed.OpenAIEmbedder(repo=self.repo)
```

This covers:

- `serve --index-db <repo>/.hypermnesic/index.db` with no `--repo`
- `serve --repo <repo> ...`
- `serve-cloud`, because `build_cloud_server` delegates to `build_server`

**Tests:**

Add a backend-level test without network by monkeypatching `embed.OpenAIEmbedder` to capture `repo`. Make the direct `_Backend` test primary because it exercises the derived repo path without depending on FastMCP internals:

```python
def test_mcp_backend_constructs_embedder_with_derived_repo(make_corpus, fake_embedder, monkeypatch):
    from hypermnesic import embed, index, mcp_server

    repo = make_corpus({"a.md": "# A\n\nalpha.\n"})
    index.build_index(repo, fake_embedder).close()
    db = index.state_dir_for(repo) / "index.db"
    seen = {}

    class RecordingEmbedder:
        dim = fake_embedder.dim
        model = fake_embedder.model
        def __init__(self, *, repo=None, **_kw):
            seen["repo"] = repo
        def embed(self, texts):
            return fake_embedder.embed(texts)

    monkeypatch.setattr(embed, "OpenAIEmbedder", RecordingEmbedder)

    backend = mcp_server._Backend(db)

    assert backend.repo == repo
    assert backend.embedder is not None
    assert seen["repo"] == repo
```

Add an ambiguous-index-db regression if validation is added:

```python
def test_mcp_backend_without_repo_rejects_ambiguous_index_db(tmp_path):
    from hypermnesic import mcp_server

    db = tmp_path / "custom-state" / "index.db"
    db.parent.mkdir()

    with pytest.raises(ValueError, match="--repo"):
        mcp_server._Backend(db)
```

If implementation chooses to keep parent-parent derivation for all paths, the plan must instead document that derivation contract and ensure doctor/CLI output tells users to pass `--repo` when their index path is not `<repo>/.hypermnesic/index.db`.

Also add concrete CLI regressions from a different cwd. At minimum, require one dense-required path and one dense-optional read path, using monkeypatches so no network is hit:

- `index`/`embed`: verify `smoke_embed_or_die(repo=repo)` receives the target repo while cwd is elsewhere.
- `retrieve`/`converge`: verify `OpenAIEmbedder(repo=repo)` is constructed while cwd is elsewhere and lexical fallback remains available if embedding fails.

**Run:**

```bash
uv run pytest tests/test_doctor.py tests/test_config.py tests/test_think.py tests/test_auth_cloud.py tests/test_cli.py -q -o 'addopts='
```

Expected: PASS.

### Phase 6: Preserve service/unit behavior

**Objective:** Ensure existing service rendering still references repo `.env` explicitly and does not inline secrets.

**Files:**

- Modify only if test gaps are found: `tests/test_install.py`
- Production changes likely not needed in `src/hypermnesic/install.py`

**Checks:**

1. Ensure `render_systemd_unit(...)` still has:
   - `WorkingDirectory={repo}`
   - `EnvironmentFile=-{repo}/.env`
2. Ensure `render_cloud_systemd_unit(...)` still has:
   - `WorkingDirectory={repo}`
   - `EnvironmentFile=-{repo}/.env`
   - `EnvironmentFile=-{env_file}`
3. Add assertions if current tests only check generic `EnvironmentFile`.

**Run:**

```bash
uv run pytest tests/test_install.py -q -o 'addopts='
```

Expected: PASS.

### Phase 7: Documentation and changelog

**Objective:** Update user-visible docs in the same PR, per AGENTS.md anti-drift rules.

**Files:**

- Modify: `docs/reference/configuration.md`
- Modify: `docs/reference/cli.md`
- Modify: `docs/guides/getting-started.md` if it mentions dense setup, doctor/status repair commands, or repo `.env` behavior
- Modify: `README.md` if wording mentions cwd `.env` or dense setup ambiguously
- Modify: `CHANGELOG.md`

**Doc content requirements:**

1. `docs/reference/configuration.md`
   - State key lookup order: process env, repo `.env`, cwd fallback when no repo context.
   - State `doctor --check-dense-live` behavior if added.
   - Reaffirm secrets are never written to the index/audit log/output.
2. `docs/reference/cli.md`
   - Update `doctor`/`status` options and dense diagnostic fields.
   - Include cwd-independent examples:

     ```sh
     cd /tmp
     hypermnesic doctor /path/to/vault --json
     hypermnesic doctor /path/to/vault --check-dense-live --json
     hypermnesic converge /path/to/vault --now --json
     ```

3. `docs/guides/getting-started.md`
   - Update if it contains dense setup, doctor/status repair commands, or repo `.env` guidance.
   - Ensure examples work from any cwd and use placeholders only.
4. `README.md`
   - If the quick start says the key is read from repo-root `.env`, clarify that this applies to repo-addressed commands regardless of cwd.
5. `CHANGELOG.md`
   - Add `[Unreleased]` entry, likely under `Fixed`:
     `Dense retrieval now discovers repo-scoped .env credentials for repo-addressed CLI/MCP paths instead of depending on process cwd.`

**Run:**

```bash
uv run python scripts/preflight_public_scan.py
```

Expected: PASS; no real host/token/path leaks introduced.

### Phase 8: Manual verification of reproduced bug

**Objective:** Prove the original failure mode is fixed without printing secrets.

**Steps:**

1. From repo cwd, confirm dense configured:

   ```bash
   cd /path/to/hypermnesic
   uv run hypermnesic doctor /path/to/vault --json \
     | python -c 'import json,sys; out=json.load(sys.stdin); print({c["id"]: c["status"] for c in out["checks"]}["dense_retrieval"])'
   ```

   Expected after fix: `pass` if repo `.env` contains a key.

2. From a different cwd, confirm same result:

   ```bash
   cd /tmp
   env -u OPENAI_API_KEY uv --project /path/to/hypermnesic run hypermnesic doctor /path/to/vault --json \
     | python -c 'import json,sys; out=json.load(sys.stdin); d={c["id"]: c for c in out["checks"]}["dense_retrieval"]; print(d["status"], d["detail"]["key_source"])'
   ```

   Expected after fix: `pass repo_dotenv`.

3. Optional live check, only when network/API use is acceptable:

   ```bash
   cd /tmp
   env -u OPENAI_API_KEY uv --project /path/to/hypermnesic run hypermnesic doctor /path/to/vault --check-dense-live --json \
     | python -c 'import json,sys; out=json.load(sys.stdin); d={c["id"]: c for c in out["checks"]}["dense_retrieval"]; print(d["detail"]["dense_state"], d["detail"]["live_check"])'
   ```

   Expected with valid key and network: `configured_valid pass`.

4. Confirm no key material appears:

   ```bash
   cd /tmp
   out="$(mktemp)"
   trap 'rm -f "$out"' EXIT
   env -u OPENAI_API_KEY uv --project /path/to/hypermnesic run hypermnesic doctor /path/to/vault --json > "$out"
   python - "$out" <<'PY'
   import sys
   from pathlib import Path
   text = Path(sys.argv[1]).read_text()
   assert 'sk-' not in text
   assert 'OPENAI_' + 'API_KEY=' not in text
   print('secret-free')
   PY
   ```

   Expected: `secret-free`.

### Phase 9: Full gates

**Objective:** Prove the implementation satisfies repo standards before marking done.

**Commands:**

```bash
uv sync --extra dev
uv run ruff check .
uv run python scripts/check_version_consistency.py
uv run pytest
uv run python scripts/license_scan.py
uv run python scripts/preflight_public_scan.py
```

Expected: all PASS. If any gate fails, fix it or file a tracked issue; do not dismiss it as pre-existing.

## Risks / Edge Cases

- **Secret leakage:** `ApiKeyStatus` must never include the key or absolute `.env` paths. Tests must assert this via `repr(status)` and JSON doctor output.
- **Process-env precedence:** A global process key must continue to outrank repo `.env`; diagnostics should reveal only `process_env`, not the value.
- **Two-vault confusion:** Running from one vault while diagnosing another must use the explicit target repo `.env`, not cwd `.env`.
- **Backwards compatibility:** Existing tests monkeypatch `_DOTENV_PATHS`; preserve that fallback so older tests and no-repo helper paths keep working.
- **Import-time cwd capture:** Avoid adding new import-time cwd state. Existing `_DOTENV_PATHS` can remain as fallback, but repo-aware code must build the repo `.env` path at call time.
- **FastMCP test ergonomics:** If invoking FastMCP tools in tests is cumbersome, test `_Backend` directly for repo-derived embedder construction.
- **Local-proof demo mode:** `local-proof --dense --demo-dir` prepares the demo repo inside `run_local_proof`, after CLI embedder construction. Either leave demo dense behavior unchanged for this fix or refactor carefully in a follow-up; do not block the core repo-scoped fix.
- **Network checks:** Live smoke should be opt-in to keep doctor deterministic/offline by default.

## Verification Commands

Focused:

```bash
uv run pytest tests/test_config.py -q -o 'addopts='
uv run pytest tests/test_doctor.py -q -o 'addopts='
uv run pytest tests/test_index.py::test_smoke_embed_fails_loud_on_missing_key -q -o 'addopts='
uv run pytest tests/test_install.py -q -o 'addopts='
uv run pytest tests/test_think.py tests/test_auth_cloud.py tests/test_cli.py -q -o 'addopts='
```

Manual reproduced bug:

```bash
cd /tmp
uv --project /path/to/hypermnesic run hypermnesic doctor /path/to/vault --json
```

Full gate set:

```bash
uv sync --extra dev
uv run ruff check .
uv run python scripts/check_version_consistency.py
uv run pytest
uv run python scripts/license_scan.py
uv run python scripts/preflight_public_scan.py
```

## Rollback / Recovery

- Revert the implementation commit(s) touching `config.py`, `embed.py`, `expand.py`, `doctor.py`, `cli.py`, `mcp_server.py`, tests, and docs.
- Existing lexical fallback behavior should remain available after rollback because no schema or durable data migration is planned.
- If only the live smoke flag causes trouble, remove the flag and keep repo-scoped credential lookup; the live smoke path is additive.
- If vector coverage SQL causes compatibility issues with older index schemas, guard it more narrowly or omit coverage when tables are absent; do not fail doctor because coverage could not be computed.

## Follow-up Compounding Opportunities

- Add a small `hypermnesic dense-status` subcommand only if doctor output proves too broad for automation.
- Consider pre-warming vectors in `setup` or `local-proof --dense` after the repo-scoped key fix is stable.
- Consider migrating existing operator wrappers or docs away from ad-hoc env injection now that repo `.env` lookup is reliable.
- If this workflow recurs, add a repository-local troubleshooting runbook under `docs/` rather than a Hermes Agent skill/profile artifact, preserving the zero-core boundary.
