"""Non-mutating setup diagnostics for owners and agents."""

from __future__ import annotations

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
               env_file=None, ops=None) -> DoctorResult:
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

    dense_ok = _has_api_key()
    checks.append(_check(
        "dense_retrieval", "local", "pass" if dense_ok else "fail",
        "Dense retrieval key is configured." if dense_ok else
        "Dense retrieval is not configured; lexical recall still works.",
        "none" if dense_ok else "configure_key",
        "No action needed." if dense_ok else "Set OPENAI_API_KEY when you want dense ranking.",
        None,
        "docs/reference/configuration.md",
    ))

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


def _has_api_key() -> bool:
    try:
        config.get_api_key()
        return True
    except config.ConfigError:
        return False


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
