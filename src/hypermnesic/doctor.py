"""Non-mutating setup diagnostics for owners and agents."""

from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hypermnesic import client_guidance, config
from hypermnesic import index as index_mod


@dataclass(frozen=True)
class NextAction:
    code: str
    summary: str
    command: str | None = None
    doc: str | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "summary": self.summary,
            "command": self.command,
            "doc": self.doc,
        }


@dataclass(frozen=True)
class DiagnosticCheck:
    id: str
    category: str
    status: str
    severity: str
    summary: str
    next_action: NextAction
    detail: dict | None = None

    def as_dict(self) -> dict:
        out = {
            "id": self.id,
            "category": self.category,
            "status": self.status,
            "severity": self.severity,
            "summary": self.summary,
            "next_action": self.next_action.as_dict(),
        }
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass(frozen=True)
class DoctorResult:
    checks: list[DiagnosticCheck]
    public_url: str | None
    resource: str | None

    @property
    def status(self) -> str:
        return "needs_attention" if any(c.status == "fail" for c in self.checks) else "ready"

    @property
    def what_this_means(self) -> str:
        if self.status == "ready":
            return (
                "Local memory is healthy enough to use, and any configured remote endpoint "
                "checks did not find a blocking failure."
            )
        failing = [c for c in self.checks if c.status == "fail"]
        first = failing[0]
        return f"Hypermnesic needs attention: {first.summary}"

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "what_this_means": self.what_this_means,
            "public_url": self.public_url,
            "resource": self.resource,
            "checks": [c.as_dict() for c in self.checks],
            "next_actions": client_guidance.client_next_action_map(self.public_url),
        }


def run_doctor(repo, *, public_url: str | None = None, resource: str | None = None,
               env_file=None, ops=None, check_dense_live: bool = False) -> DoctorResult:
    """Return setup diagnostics without writing files, services, secrets, or git commits."""
    from hypermnesic import install

    repo = Path(repo)
    resource = resource or public_url
    ops = ops or install.SetupOps()
    checks: list[DiagnosticCheck] = []

    git_ok = _is_git_repo(repo)
    checks.append(_check(
        "local_git_repo", "local", "pass" if git_ok else "fail",
        "Vault is a git repo." if git_ok else "Vault is not a git repo.",
        "none" if git_ok else "initialize_git",
        "No action needed." if git_ok else "Initialize the vault with git before setup.",
        "git init" if not git_ok else None,
        "docs/guides/getting-started.md",
    ))

    idx_path = repo / index_mod.STATE_DIRNAME / "index.db"
    index_exists = idx_path.exists()
    fresh = _index_fresh(repo, idx_path) if index_exists and git_ok else None
    if index_exists and fresh is not False:
        idx_status, idx_summary = "pass", "Disposable index exists and is current enough."
    elif index_exists:
        idx_status, idx_summary = "warn", "Disposable index exists but may lag HEAD."
    else:
        idx_status, idx_summary = "fail", "Disposable index is missing."
    checks.append(_check(
        "local_index", "local", idx_status, idx_summary,
        "none" if idx_status == "pass" else "initialize_index",
        "No action needed." if idx_status == "pass" else "Run local-proof or init to build it.",
        "hypermnesic local-proof /path/to/vault" if idx_status != "pass" else None,
        "docs/guides/getting-started.md",
        {"state_path": f"{index_mod.STATE_DIRNAME}/index.db", "fresh": fresh},
    ))

    checks.append(_dense_retrieval_check(repo, idx_path, check_live=check_dense_live))

    checks.append(_env_file_check(env_file))

    if public_url:
        tailscale_ok = bool(ops.tailscale_ready())
        checks.append(_check(
            "tailscale", "remote", "pass" if tailscale_ok else "fail",
            "Tailscale is installed and authenticated." if tailscale_ok else
            "Tailscale is missing or not authenticated.",
            "none" if tailscale_ok else "authenticate_tailscale",
            "No action needed." if tailscale_ok else
            "Install Tailscale and authenticate this node before setup.",
            "tailscale up" if not tailscale_ok else None,
            "docs/guides/getting-started.md",
        ))
    else:
        checks.append(_skipped(
            "tailscale", "remote", "No public URL supplied; remote reach checks skipped.",
            "provide_public_url"))

    checks.append(_service_unit_check(repo, bool(public_url)))
    if public_url:
        discovery = ops.verify_discovery(public_url, resource or public_url)
        checks.extend(_discovery_checks(discovery))
    else:
        checks.append(_skipped(
            "remote_url", "remote", "No public URL supplied; remote endpoint checks skipped.",
            "provide_public_url"))
        checks.append(_skipped(
            "oauth_discovery", "oauth", "No public URL supplied; OAuth discovery skipped.",
            "provide_public_url"))
        checks.append(_skipped(
            "auth_challenge", "auth", "No public URL supplied; auth challenge skipped.",
            "provide_public_url"))
        checks.append(_skipped(
            "write_availability", "write", "No public URL supplied; write availability skipped.",
            "provide_public_url"))

    return DoctorResult(checks=checks, public_url=public_url, resource=resource)


def setup_milestones(public_url: str, resource: str, discovery: dict) -> list[dict]:
    """Milestone vocabulary shared by setup and doctor."""
    checks = [
        _check("service_unit", "remote", "pass", "Cloud service unit was rendered and started.",
               "none", "No action needed."),
        _check("funnel", "remote", "pass", "Funnel routes were applied for MCP and discovery.",
               "none", "No action needed."),
    ]
    checks.extend(_discovery_checks(discovery))
    checks.append(_check(
        "write_availability", "write", "pass" if discovery.get("ok") else "fail",
        "Write tool is available through OAuth-scoped remote serving." if discovery.get("ok") else
        "Write availability could not be proven because discovery failed.",
        "none" if discovery.get("ok") else "repair_funnel",
        "No action needed." if discovery.get("ok") else "Repair service/funnel discovery.",
        "hypermnesic doctor /path/to/vault --public-url " + public_url,
        "docs/guides/getting-started.md",
        {"resource": resource},
    ))
    return [c.as_dict() for c in checks]


def _check(check_id: str, category: str, status: str, summary: str, code: str,
           action_summary: str, command: str | None = None, doc: str | None = None,
           detail: dict | None = None) -> DiagnosticCheck:
    severity = {"pass": "info", "skipped": "info", "warn": "warning", "fail": "error"}[status]
    return DiagnosticCheck(
        id=check_id,
        category=category,
        status=status,
        severity=severity,
        summary=summary,
        next_action=NextAction(code=code, summary=action_summary, command=command, doc=doc),
        detail=detail,
    )


def _skipped(check_id: str, category: str, summary: str, code: str) -> DiagnosticCheck:
    return _check(check_id, category, "skipped", summary, code,
                  "Provide a public URL to run this remote check.",
                  doc="docs/guides/getting-started.md")


def _is_git_repo(repo: Path) -> bool:
    cp = subprocess.run(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
                        capture_output=True, text=True)
    return cp.returncode == 0 and cp.stdout.strip() == "true"


def _git_head(repo: Path) -> str | None:
    cp = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                        capture_output=True, text=True)
    return cp.stdout.strip() if cp.returncode == 0 and cp.stdout.strip() else None


def _index_fresh(repo: Path, idx_path: Path) -> bool | None:
    try:
        idx = index_mod.Index(idx_path)
        try:
            checkpoint = idx.get_checkpoint()
        finally:
            idx.close()
    except Exception:
        return False
    head = _git_head(repo)
    return checkpoint == head if head else None


def _dense_retrieval_check(repo: Path, idx_path: Path, *, check_live: bool) -> DiagnosticCheck:
    key_status = config.api_key_status(repo)
    dense_state = "not_configured"
    live_check = "skipped"
    if key_status.configured:
        dense_state = "configured_unverified"
        if check_live:
            from hypermnesic import embed
            try:
                embed.smoke_embed_or_die(repo=repo)
                dense_state = "configured_valid"
                live_check = "pass"
            except embed.EmbeddingError:
                dense_state = "configured_invalid"
                live_check = "fail"

    detail = {
        "key_configured": key_status.configured,
        "key_source": key_status.source,
        "dense_state": dense_state,
        "live_check": live_check,
    }
    if key_status.error:
        detail["key_error"] = key_status.error

    coverage = _vector_coverage(idx_path)
    if coverage is not None:
        detail["vector_coverage"] = coverage
        if key_status.configured and dense_state != "configured_invalid" and (
            coverage["chunks_missing_vectors"] or coverage["docs_missing_vectors"]
        ):
            dense_state = "vectors_stale_or_absent"
            detail["dense_state"] = dense_state
    elif key_status.configured and dense_state != "configured_invalid":
        dense_state = "index_missing_or_unbuilt"
        detail["dense_state"] = dense_state

    if key_status.error == "repo_dotenv_unreadable":
        status = "fail"
        summary = "Dense retrieval key file could not be read; lexical recall still works."
        action_code = "repair_key_file"
        action_summary = "Fix permissions on the repo .env or set OPENAI_API_KEY."
        command = None
    elif not key_status.configured:
        status = "fail"
        summary = "Dense retrieval is not configured; lexical recall still works."
        action_code = "configure_key"
        action_summary = "Set OPENAI_API_KEY or add it to the gitignored repo .env."
        command = None
    elif dense_state == "configured_invalid":
        status = "fail"
        summary = "Dense retrieval live check failed; lexical recall still works."
        action_code = "repair_key"
        action_summary = "Check the OpenAI key/network or rerun without --check-dense-live."
        command = None
    elif dense_state == "index_missing_or_unbuilt":
        status = "warn"
        summary = "Dense retrieval key is configured, but the local index is missing."
        action_code = "initialize_index"
        action_summary = "Build the disposable index before expecting dense retrieval."
        command = "hypermnesic local-proof /path/to/vault"
    elif dense_state == "vectors_stale_or_absent":
        status = "warn"
        summary = "Dense retrieval key is configured, but vectors are stale or absent."
        action_code = "refresh_vectors"
        action_summary = "Run convergence to fill missing dense vectors."
        command = "hypermnesic converge /path/to/vault --now --json"
    else:
        status = "pass"
        summary = "Dense retrieval key is configured."
        action_code = "none"
        action_summary = "No action needed."
        command = None

    return _check(
        "dense_retrieval", "local", status,
        summary, action_code, action_summary,
        command, "docs/reference/configuration.md", detail,
    )


def _vector_coverage(idx_path: Path) -> dict | None:
    if not idx_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{idx_path}?mode=ro", uri=True)
        index_mod._load_vec(conn)
    except sqlite3.Error:
        return None
    try:
        chunks_total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        chunk_vectors = conn.execute(
            "SELECT COUNT(*) FROM vec_chunks v JOIN chunks c ON c.chunk_id = v.chunk_id"
        ).fetchone()[0]
        chunks_missing = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE chunk_id NOT IN "
            "(SELECT chunk_id FROM vec_chunks)"
        ).fetchone()[0]
        docs_total = conn.execute("SELECT COUNT(DISTINCT path) FROM chunks").fetchone()[0]
        doc_vectors = conn.execute(
            "SELECT COUNT(*) FROM vec_docs v JOIN docs d ON d.doc_id = v.doc_id"
        ).fetchone()[0]
        docs_missing = conn.execute(
            "SELECT COUNT(DISTINCT c.path) FROM chunks c "
            "LEFT JOIN docs d ON d.path = c.path "
            "WHERE d.doc_id IS NULL OR d.doc_id NOT IN (SELECT doc_id FROM vec_docs)"
        ).fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return {
        "chunks_total": chunks_total,
        "chunk_vectors": chunk_vectors,
        "chunks_missing_vectors": chunks_missing,
        "docs_total": docs_total,
        "doc_vectors": doc_vectors,
        "docs_missing_vectors": docs_missing,
        "manual_reindex_recommended": bool(chunks_missing or docs_missing),
    }


def _env_file_check(env_file) -> DiagnosticCheck:
    if env_file is None:
        return _check(
            "consent_secret_file", "auth", "skipped",
            "Consent secret file was not provided for inspection.",
            "provide_env_file",
            "Pass --env-file when you want doctor to check owner-only file permissions.",
            doc="docs/reference/configuration.md",
        )
    path = Path(env_file)
    if not path.exists():
        return _check(
            "consent_secret_file", "auth", "warn",
            "Consent secret file is not present.",
            "rerun_setup",
            "Run setup to create an owner-only consent secret file.",
            "hypermnesic setup /path/to/vault --public-url https://<your-host>.ts.net/mcp",
            "docs/guides/getting-started.md",
        )
    mode = path.stat().st_mode & 0o777
    return _check(
        "consent_secret_file", "auth", "pass" if mode == 0o600 else "warn",
        "Consent secret file exists with owner-only permissions." if mode == 0o600 else
        "Consent secret file exists but permissions are broader than owner-only.",
        "none" if mode == 0o600 else "repair_secret_permissions",
        "No action needed." if mode == 0o600 else "Restrict the consent secret file to chmod 600.",
        None if mode == 0o600 else "chmod 600 <cloud.env>",
        "docs/reference/configuration.md",
        {"present": True, "owner_only": mode == 0o600},
    )


def _service_unit_check(repo: Path, remote_requested: bool) -> DiagnosticCheck:
    if not remote_requested:
        return _skipped(
            "service_unit", "remote", "No public URL supplied; service status skipped.",
            "provide_public_url")
    state = repo / index_mod.STATE_DIRNAME
    unit = state / "hypermnesic-cloud.service"
    if unit.exists():
        return _check(
            "service_unit", "remote", "pass", "Cloud service unit exists in local state.",
            "none", "No action needed.", detail={"unit": "hypermnesic-cloud.service"})
    return _check(
        "service_unit", "remote", "warn",
        "Cloud service unit was not found in local state.",
        "rerun_setup",
        "Run setup to render and start the cloud service.",
        "hypermnesic setup /path/to/vault --public-url https://<your-host>.ts.net/mcp",
        "docs/guides/getting-started.md",
    )


def _discovery_checks(discovery: dict) -> list[DiagnosticCheck]:
    checks = discovery.get("checks") or {}
    protected = bool(checks.get("protected_resource"))
    metadata = bool(checks.get("as_metadata"))
    unauth = bool(checks.get("unauth_401"))
    return [
        _check(
            "oauth_discovery", "oauth", "pass" if protected and metadata else "fail",
            "OAuth discovery metadata resolves." if protected and metadata else
            "OAuth discovery metadata did not resolve.",
            "none" if protected and metadata else "repair_funnel",
            "No action needed." if protected and metadata else
            "Repair Funnel well-known routes and rerun setup.",
            None if protected and metadata else
            "hypermnesic setup /path/to/vault --public-url https://<your-host>.ts.net/mcp",
            "docs/guides/getting-started.md",
            {"protected_resource": protected, "as_metadata": metadata},
        ),
        _check(
            "auth_challenge", "auth", "pass" if unauth else "fail",
            "Unauthenticated remote requests are challenged." if unauth else
            "Unauthenticated remote request was not challenged as expected.",
            "none" if unauth else "repair_auth",
            "No action needed." if unauth else
            "Check that the public endpoint is the OAuth-protected serve-cloud lane.",
            None if unauth else
            "hypermnesic setup /path/to/vault --public-url https://<your-host>.ts.net/mcp",
            "docs/guides/getting-started.md",
        ),
        _check(
            "write_availability", "write", "pass" if discovery.get("ok") else "fail",
            "Remote write is available only through OAuth-scoped consent." if discovery.get("ok")
            else "Remote write availability could not be verified.",
            "none" if discovery.get("ok") else "request_write_scope",
            "No action needed." if discovery.get("ok") else
            "Reconnect the client and approve write scope after discovery is healthy.",
            None,
            "docs/guides/getting-started.md",
        ),
    ]
