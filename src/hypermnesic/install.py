"""Deployment provisioning: the opt-in post-merge convergence hook (U33).

The hook pre-warms the index after a pull (FR-R36..R38). It is **opt-in**,
**idempotent** (re-running installs exactly one managed block), and
**non-destructive**: a clearly-delimited managed block is appended to — or updated
inside — an existing hook, never overwriting the operator's own hook content. The
uninstall path removes *only* the managed block. Lazy read-time convergence
(U27/U28) remains the correctness guarantee; the hook only warms the cache, and
it ends with ``|| true`` so a convergence hiccup never fails a ``git pull``.

(U34 extends this module with role-aware service/config provisioning.)
"""

from __future__ import annotations

import json
import shlex
import shutil
import stat
import sys
from pathlib import Path

from hypermnesic import config
from hypermnesic import index as index_mod

DEFAULT_PORT = 8848
DEFAULT_PATH = "/mcp"
ROLES = ("single", "master", "client")
_LOCALHOST = "127.0.0.1"
_WILDCARD = ("0.0.0.0", "::", "")


class InstallError(RuntimeError):
    """A role install cannot proceed — raised before any artifact is written so a
    failed install never leaves a half-provisioned host."""


_MANAGED_BEGIN = "# >>> hypermnesic managed block (do not edit inside markers) >>>"
_MANAGED_END = "# <<< hypermnesic managed block <<<"
# Hooks that warm the index. post-merge fires after `git pull` fast-forwards/merges;
# the set is extensible (post-rewrite/post-checkout) without changing the contract.
HOOK_NAMES = ("post-merge",)


def _hypermnesic_exe() -> str:
    """Absolute path to the installed console script when resolvable (so the unit and
    hook are robust regardless of the runtime PATH); falls back to the bare name.

    ``systemctl --user`` runs the unit without the project venv on ``$PATH``, so
    ``shutil.which`` misses and a bare ``hypermnesic`` ExecStart would fail to start
    (U2). When PATH resolution misses, fall back to the console script installed
    next to the running interpreter (``<venv>/bin/hypermnesic``) before the bare
    name — that is the absolute path the service actually needs."""
    found = shutil.which("hypermnesic")
    if found:
        return found
    venv_exe = Path(sys.executable).parent / "hypermnesic"
    if venv_exe.exists():
        return str(venv_exe)
    return "hypermnesic"


def _managed_block(repo: Path) -> str:
    exe = _hypermnesic_exe()
    # shlex.quote both fields so a repo path (or resolved exe path) containing shell
    # metacharacters cannot break out of the hook command and run on every `git pull`.
    cmd = f"{shlex.quote(exe)} converge {shlex.quote(str(repo))} >/dev/null 2>&1 || true"
    return "\n".join([
        _MANAGED_BEGIN,
        "# hypermnesic U33: pre-warm the index after a pull. Lazy read-time convergence",
        "# is the correctness guarantee (FR-R38); this only warms the cache.",
        cmd,
        _MANAGED_END,
        "",
    ])


def _strip_managed(text: str) -> str:
    """Return ``text`` with the managed block (BEGIN..END inclusive) removed, leaving
    every other line — including any operator content before or after — intact."""
    out: list[str] = []
    buf: list[str] = []
    skip = False
    for ln in text.splitlines():
        if ln.strip() == _MANAGED_BEGIN:
            skip = True
            buf = []
            continue
        if skip:
            if ln.strip() == _MANAGED_END:
                skip = False
                buf = []
            else:
                buf.append(ln)
            continue
        out.append(ln)
    if skip:                # BEGIN with no closing END (truncated/corrupt block) → keep content
        out.extend(buf)
    return "\n".join(out)


def install_hooks(repo) -> dict:
    """Install/refresh the managed post-merge hook in ``repo/.git/hooks``. Idempotent
    and non-destructive. Returns the installed hook names + hooks dir."""
    repo = Path(repo).resolve()
    if not (repo / ".git").exists():
        raise FileNotFoundError(f"not a git repo (no .git): {repo}")
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for name in HOOK_NAMES:
        hook = hooks_dir / name
        block = _managed_block(repo)
        if hook.exists():
            base = _strip_managed(hook.read_text(encoding="utf-8")).rstrip("\n")
            new = (base + "\n\n" + block) if base.strip() else "#!/bin/sh\n\n" + block
        else:
            new = "#!/bin/sh\n\n" + block
        hook.write_text(new, encoding="utf-8")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(name)
    return {"installed": installed, "hooks_dir": str(hooks_dir)}


def uninstall_hooks(repo) -> dict:
    """Remove only the managed block from each managed hook (operator content kept).
    A hook left as a bare shebang is removed entirely."""
    repo = Path(repo).resolve()
    hooks_dir = repo / ".git" / "hooks"
    removed: list[str] = []
    for name in HOOK_NAMES:
        hook = hooks_dir / name
        if not hook.exists():
            continue
        text = hook.read_text(encoding="utf-8")        # read once (no TOCTOU re-read)
        if _MANAGED_BEGIN not in text:
            continue
        stripped = _strip_managed(text).rstrip("\n")
        if stripped.strip() in ("", "#!/bin/sh"):
            hook.unlink()                       # nothing left but a bare shebang → remove
        else:
            hook.write_text(stripped + "\n", encoding="utf-8")
        removed.append(name)
    return {"removed": removed}


# ---------------------------------------------------------------------------
# U34 — role-aware installer (single | master | client)
# ---------------------------------------------------------------------------

def _auth_execstart_flags(auth_issuer: str | None, auth_resource: str | None,
                          required_scopes: list[str] | None) -> str:
    """The OAuth2 RS flags for the master ExecStart (U2). Rendered only when both the
    issuer and resource URLs are present; shlex-quoted so a URL with shell metacharacters
    cannot break the unit. No secret is rendered — the RS introspection credentials are
    read from the environment at runtime, never inlined (threat-model V9)."""
    if not (auth_issuer and auth_resource):
        return ""
    flags = (f" --auth-issuer-url {shlex.quote(auth_issuer)}"
             f" --auth-resource-url {shlex.quote(auth_resource)}")
    for s in (required_scopes or []):
        if s and s.strip():
            flags += f" --required-scope {shlex.quote(s)}"
    return flags


def render_systemd_unit(repo: Path, bind: str, port: int, path: str, exe: str, *,
                        auth_issuer: str | None = None, auth_resource: str | None = None,
                        required_scopes: list[str] | None = None) -> str:
    """A portable user systemd unit running the write-enabled tailnet serve. The
    OPENAI_API_KEY value is NEVER inlined — it is referenced via EnvironmentFile. When
    auth is provided (U2), the OAuth2 RS flags are rendered on ExecStart so the
    write-enabled master starts auth-on (the write_enabled⇒auth-required invariant); the
    RS client credentials stay in the environment, never the unit."""
    state = index_mod.STATE_DIRNAME
    auth = _auth_execstart_flags(auth_issuer, auth_resource, required_scopes)
    return f"""[Unit]
Description=hypermnesic tailnet MCP server (master)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={repo}
# OPENAI_API_KEY (and the OAuth2 RS introspection creds, if any) are read from the
# gitignored .env / environment below — their VALUES are never inlined here.
EnvironmentFile=-{repo}/.env
ExecStart={exe} serve --index-db {repo}/{state}/index.db --host {bind} \
--port {port} --path {path} --enable-write{auth}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def render_docker(repo: Path, bind: str, port: int, path: str) -> tuple[str, str]:
    """A portable Dockerfile + compose for the always-on master. OPENAI_API_KEY is
    supplied at runtime via env_file (.env) — never baked into the image or compose."""
    state = index_mod.STATE_DIRNAME
    dockerfile = (
        "FROM python:3.11-slim\n"
        "WORKDIR /app\n"
        "COPY . /app\n"
        "RUN pip install --no-cache-dir .\n"
        "# OPENAI_API_KEY is provided at runtime via env_file — never baked into the image.\n"
        'ENTRYPOINT ["hypermnesic"]\n'
    )
    compose = f"""services:
  hypermnesic:
    build: .
    command: serve --index-db /app/{state}/index.db --host {bind} --port {port} \
--path {path} --enable-write
    env_file:
      - .env            # OPENAI_API_KEY — never inlined into this file
    ports:
      - "{bind}:{port}:{port}"
    restart: unless-stopped
"""
    return dockerfile, compose


def _write_role_config(repo: Path, cfg: dict) -> Path:
    state = repo / index_mod.STATE_DIRNAME
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    p = state / "config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


# The agent identity's bearer token is provided at runtime via this env var — never
# inlined into a (plaintext, chezmoi-tracked) MCP client config (threat-model V9). The
# emitted config only NAMES it; the value lives in the host's environment / secret store.
CLIENT_TOKEN_ENV = "HYPERMNESIC_MCP_TOKEN"


def _client_entry(master_url: str, *, auth_issuer_url: str | None,
                  auth_resource_url: str | None, required_scope: list[str] | None) -> dict:
    """The `mcpServers.hypermnesic` entry. Bare streamable-http when no auth (Phase-1
    parity); OAuth2-aware (U5/R12) when an issuer/resource is given — carrying the
    discovery reference + a *pointer* to the runtime token, never a secret value. The
    exact per-host field names may be refined once U12 settles the AS; the invariant is
    secret-free."""
    entry: dict = {"type": "streamable-http", "url": master_url}
    if auth_issuer_url or auth_resource_url:
        scopes = [s for s in (required_scope or []) if s and s.strip()]
        entry["auth"] = {
            "type": "oauth2",
            "issuer": auth_issuer_url,                       # AS discovery reference (no secret)
            "resource": auth_resource_url or master_url,     # RFC 8707 audience
            "required_scopes": scopes or None,
            "token_env": CLIENT_TOKEN_ENV,                   # pointer to the runtime token
        }
    return entry


def _install_client(master_url: str | None, mcp_config_path: str | None,
                    *, server_name: str = "hypermnesic", auth_issuer_url: str | None = None,
                    auth_resource_url: str | None = None,
                    required_scope: list[str] | None = None) -> dict:
    """Client = config only (no engine, no index). Write/patch an MCP client config
    pointing at the master endpoint; preserve any other servers already present. When
    auth params are given the entry is OAuth2-aware and secret-free (U5)."""
    if not master_url:
        raise InstallError("role 'client' requires --master-url <https://master/mcp>")
    if not mcp_config_path:
        raise InstallError("role 'client' requires --mcp-config <path to MCP client config>")
    path = Path(mcp_config_path)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):           # malformed existing config → reset the map
        servers = data["mcpServers"] = {}
    servers[server_name] = _client_entry(master_url, auth_issuer_url=auth_issuer_url,
                                          auth_resource_url=auth_resource_url,
                                          required_scope=required_scope)   # idempotent upsert
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    authed = "auth" in servers[server_name]
    return {
        "role": "client",
        "artifacts": [str(path)],
        "config": {"master_url": master_url, "oauth2": authed},
        "manual_steps": [
            f"point your MCP client / Obsidian companion at {master_url}"
            + (f" (OAuth2: provide the token via the {CLIENT_TOKEN_ENV} env var — never commit it)"
               if authed else " (tailnet membership is the auth boundary — MVP)"),
        ],
    }


# ---------------------------------------------------------------------------
# U3 — `hypermnesic setup`: one-command bring-up of the unified public endpoint
# ---------------------------------------------------------------------------

CLOUD_SERVICE_NAME = "hypermnesic-cloud"
CLOUD_APPROVAL_ENV = "HYPERMNESIC_CLOUD_APPROVAL_TOKEN"   # the operator consent secret (V9)
DEFAULT_CLIENT_SCOPES_ENV = "HYPERMNESIC_DEFAULT_CLIENT_SCOPES"
DEFAULT_CLOUD_PORT = 8850
_DEFAULT_CLOUD_ENV_FILE = "~/.config/hypermnesic-cloud/cloud.env"


def render_cloud_systemd_unit(repo: Path, *, host: str, port: int, path: str,
                              public_url: str, resource: str, exe: str, env_file: Path,
                              allowlist: list[str] | None = None,
                              token_ttl: int = 3600,
                              default_client_scopes: list[str] | None = None) -> str:
    """A portable user systemd unit running the **unified public** OAuth serve (``serve-cloud``)
    on a loopback bind behind the Tailscale Funnel. The operator consent secret
    (``HYPERMNESIC_CLOUD_APPROVAL_TOKEN``) and OPENAI_API_KEY are referenced via EnvironmentFile —
    their VALUES are never inlined here (V9)."""
    state = index_mod.STATE_DIRNAME
    allow = "".join(f" --allowlist {shlex.quote(a)}" for a in (allowlist or [])
                    if a and a.strip())
    default_scope_args = ""
    if default_client_scopes:
        default_scope_args = " --default-client-scopes" + "".join(
            f" {shlex.quote(scope)}" for scope in default_client_scopes)
    return f"""[Unit]
Description=hypermnesic unified public OAuth MCP (cloud)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={repo}
# HYPERMNESIC_CLOUD_APPROVAL_TOKEN (the consent secret) + OPENAI_API_KEY are read from the
# owner-only env files below — their VALUES are never inlined into this unit.
EnvironmentFile=-{repo}/.env
EnvironmentFile=-{env_file}
ExecStart={exe} serve-cloud --index-db {repo}/{state}/index.db --host {host} \
--port {port} --path {path} --public-url {shlex.quote(public_url)} \
--resource {shlex.quote(resource)} --token-ttl {token_ttl}{default_scope_args}{allow}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def ensure_consent_secret(env_file: Path, *, min_len: int,
                          gen=None) -> tuple[Path, bool]:
    """Reuse a still-valid consent secret or mint a fresh one into an owner-only (chmod-600)
    env file. Returns ``(path, generated)``. Idempotent: a present secret at/above the entropy
    floor is reused untouched; an absent/weak one is (re)generated. The secret lands ONLY in this
    owner-only file — never echoed, never committed (V9; mirrors ``auth-add-client``)."""
    import secrets as _secrets

    env_file = Path(env_file)
    existing = ""
    if env_file.exists():
        for ln in env_file.read_text(encoding="utf-8").splitlines():
            if ln.startswith(CLOUD_APPROVAL_ENV + "="):
                existing = ln.split("=", 1)[1].strip()
                break
    if existing and len(existing) >= min_len:
        return env_file, False                       # still-valid → reuse, don't regenerate
    secret = (gen or (lambda: _secrets.token_urlsafe(32)))()
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(f"{CLOUD_APPROVAL_ENV}={secret}\n", encoding="utf-8")
    env_file.chmod(0o600)
    return env_file, True


def funnel_routes(public_url: str, resource: str, base_target: str) -> list[tuple[str, str]]:
    """The Tailscale funnel mounts the unified endpoint needs, each with its OWN target (proven by
    the U8 live cutover — one shared target does NOT work). ``base_target`` is the loopback origin
    ``http://127.0.0.1:<port>`` of a server serving at root (``--path /``):

    - ``<res_path>`` (e.g. ``/mcp``) → ``base_target`` (root): the funnel strips the mount, so
      ``/mcp``→MCP and ``/mcp/authorize``→the AS endpoint at the server root. (Why the server serves
      at ``/`` not ``/mcp``: otherwise ``/mcp/authorize`` would 404.)
    - the two ROOT discovery well-knowns the chain resolves at, each → the server's matching path:
      RFC 9728 protected-resource at ``…/oauth-protected-resource<res_path>`` and RFC 8414 AS meta
      at the server's bare ``…/oauth-authorization-server``. Missing these is what 404'd the first
      cloud deploy; the path suffixes keep them off honcho's routes."""
    from urllib.parse import urlparse

    base = base_target.rstrip("/")
    res_path = urlparse(resource).path.rstrip("/") or "/mcp"
    iss_path = urlparse(public_url).path.rstrip("/") or "/mcp"
    routes = [
        (res_path, base),                                            # MCP + AS endpoints (root)
        (f"/.well-known/oauth-protected-resource{res_path}",
         f"{base}/.well-known/oauth-protected-resource{res_path}"),  # RFC 9728 (the 401 target)
        (f"/.well-known/oauth-authorization-server{iss_path}",
         f"{base}/.well-known/oauth-authorization-server"),          # RFC 8414 (server-root path)
    ]
    seen: set = set()
    uniq: list[tuple[str, str]] = []
    for m, t in routes:
        if m not in seen:                        # de-dup mounts (issuer==resource path collapses)
            seen.add(m)
            uniq.append((m, t))
    return uniq


def _tailscale_funnel_cmd(mount: str, target: str) -> list[str]:
    """The `tailscale funnel --set-path` command for one mount. ALWAYS `funnel`, NEVER `serve`:
    `serve --set-path` silently clears AllowFunnel[:443] and drops the public /cloud + /honcho
    reach (a known live trap). Background + https=443 keep it persistent + public."""
    return ["tailscale", "funnel", "--bg", "--https=443", "--set-path", mount, target]


class SetupOps:
    """The privileged/network side effects of ``setup``, isolated so the orchestration is
    unit-testable without touching Tailscale, systemd, or the network. The real impl shells out
    to ``tailscale funnel`` (never ``serve``) and curls the discovery chain; tests inject a fake."""

    def tailscale_ready(self) -> bool:
        """True iff Tailscale is installed AND this node is logged in (Funnel-capable). setup
        never manages Tailscale's own lifecycle (R14) — it only checks, then fails actionably."""
        import subprocess
        if shutil.which("tailscale") is None:
            return False
        try:
            r = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                               text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return False
        if r.returncode != 0:
            return False
        try:
            return str(json.loads(r.stdout).get("BackendState", "")) == "Running"
        except ValueError:
            return False

    def apply_funnel_route(self, mount: str, target: str) -> None:
        import subprocess
        cmd = _tailscale_funnel_cmd(mount, target)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise InstallError(f"tailscale funnel failed for {mount}: {r.stderr.strip()}")

    def install_and_start_service(self, unit_path, name: str) -> None:
        import subprocess
        dest = Path("~/.config/systemd/user").expanduser()
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(unit_path), str(dest / f"{name}.service"))
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", name], check=False)

    def verify_discovery(self, public_url: str, resource: str) -> dict:
        """Curl the real discovery chain (KTD6): RFC 9728 protected-resource metadata → RFC 8414
        AS metadata → an unauth tools/list (expect 401 + WWW-Authenticate). Verifies real output,
        not an exit code. ``ok`` is False if any step does not resolve to hypermnesic."""
        import urllib.request
        from urllib.parse import urlparse

        from mcp.server.auth.routes import build_resource_metadata_url
        from mcp.shared.auth import AnyHttpUrl

        def _get_json(url: str):
            try:
                with urllib.request.urlopen(url, timeout=8) as resp:
                    return resp.status, json.loads(resp.read().decode())
            except Exception:
                return None, None

        checks: dict = {}
        prm_url = str(build_resource_metadata_url(AnyHttpUrl(resource)))
        st, prm = _get_json(prm_url)
        checks["protected_resource"] = bool(
            st == 200 and prm and str(prm.get("resource", "")).rstrip("/") == resource.rstrip("/"))
        as_servers = (prm or {}).get("authorization_servers") or []
        as_url = (str(as_servers[0]) if as_servers else public_url).rstrip("/")
        st2, asm = _get_json(as_url + "/.well-known/oauth-authorization-server")
        if st2 != 200:
            st2, asm = _get_json(
                f"{urlparse(as_url).scheme}://{urlparse(as_url).netloc}"
                f"/.well-known/oauth-authorization-server{urlparse(as_url).path}")
        checks["as_metadata"] = bool(st2 == 200 and asm and asm.get("token_endpoint"))
        # an unauth POST to the resource must be 401 with a WWW-Authenticate pointing at the PRM
        req = urllib.request.Request(resource, data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=8)
            checks["unauth_401"] = False                 # a 2xx on an unauth write is a failure
        except urllib.error.HTTPError as e:
            checks["unauth_401"] = (e.code == 401)
        except Exception:
            checks["unauth_401"] = False
        return {"ok": all(checks.values()), "checks": checks}


def setup(repo, *, public_url: str, resource: str | None = None, host: str = _LOCALHOST,
          port: int = DEFAULT_CLOUD_PORT, path: str = "/", env_file=None,
          allowlist: list[str] | None = None, token_ttl: int = 3600,
          default_client_scopes: list[str] | None = None,
          ops=None, secret_factory=None) -> dict:
    """Bring the unified public endpoint fully online in one idempotent command: render +
    install the cloud service, persist the operator consent secret, configure the Tailscale
    funnel (MCP path + discovery well-knowns), verify the real HTTPS discovery chain, and return
    the public URL + login instructions. Re-running converges to the same state (AE4).

    Fail-closed and ordered so a failure leaves no partial state: validate the public origin (R2)
    and Tailscale readiness (R14) BEFORE any side effect; verify discovery (KTD6) AFTER the funnel,
    failing the command if a well-known does not resolve. The consent secret + OPENAI_API_KEY stay
    in owner-only env files, never inlined (V9). Privileged/network steps go through ``ops`` so the
    orchestration is unit-testable; the CLI uses the real ``SetupOps``."""
    from hypermnesic import auth_cloud, client_guidance, doctor
    from hypermnesic.mcp_server import _require_public_https_origin, normalize_default_client_scopes

    resource = resource or public_url
    _require_public_https_origin(public_url, "public_url")     # R2 — fail before any artifact
    _require_public_https_origin(resource, "resource")
    normalized_default_scopes = normalize_default_client_scopes(default_client_scopes)
    repo = Path(repo).resolve()
    if not (repo / ".git").exists():
        raise InstallError(f"setup needs a git repo, but no .git found at {repo}")
    try:
        config.get_api_key(repo=repo)                           # engine credential present?
    except config.ConfigError as exc:
        raise InstallError(f"setup needs OPENAI_API_KEY (env or gitignored .env): {exc}") from exc

    ops = ops or SetupOps()
    if not ops.tailscale_ready():                              # R14 — actionable, no partial state
        raise InstallError(
            "setup requires Tailscale installed and logged in (Funnel-capable). Install it and "
            "run `tailscale up`, then re-run `hypermnesic setup`. setup never manages Tailscale "
            "itself.")

    env_file = Path(env_file).expanduser() if env_file else Path(
        _DEFAULT_CLOUD_ENV_FILE).expanduser()
    _, generated = ensure_consent_secret(
        env_file, min_len=auth_cloud.MIN_APPROVAL_TOKEN_LEN, gen=secret_factory)

    state = repo / index_mod.STATE_DIRNAME
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    exe = _hypermnesic_exe()
    unit_path = state / f"{CLOUD_SERVICE_NAME}.service"
    unit_path.write_text(render_cloud_systemd_unit(
        repo, host=host, port=port, path=path, public_url=public_url, resource=resource,
        exe=exe, env_file=env_file, allowlist=allowlist, token_ttl=token_ttl,
        default_client_scopes=(
            normalized_default_scopes if default_client_scopes is not None else None
        )), encoding="utf-8")
    ops.install_and_start_service(unit_path, CLOUD_SERVICE_NAME)

    base_target = f"http://{host}:{port}"            # server is at root (--path /); pathless base
    routes = funnel_routes(public_url, resource, base_target)
    for mount, tgt in routes:
        ops.apply_funnel_route(mount, tgt)

    discovery = ops.verify_discovery(public_url, resource)
    if not discovery.get("ok"):
        raise InstallError(
            "setup configured the service + funnel but the HTTPS discovery chain did not resolve "
            "to hypermnesic (no exit-code parity — real output checked): "
            f"{discovery.get('checks')}. Check the funnel well-known routes and the running "
            "service, then re-run setup.")

    return {
        "service": CLOUD_SERVICE_NAME, "public_url": public_url, "resource": resource,
        "unit_path": str(unit_path), "env_file": str(env_file),
        "default_client_scopes": normalized_default_scopes,
        "secret_generated": generated, "funnel_routes": routes, "discovery": discovery,
        "converged": not generated,
        "milestones": doctor.setup_milestones(public_url, resource, discovery),
        "what_this_means": (
            "Remote setup is ready: the service, public route, OAuth discovery, and write "
            "challenge checks completed."
        ),
        "client_next_actions": client_guidance.client_next_action_map(public_url),
        "next_steps": [
            f"add {public_url} to your apps (ChatGPT/Claude connector, Claude Code plugin, Codex, "
            "Obsidian) as the hypermnesic MCP URL",
            "on first connect each app opens a browser once to authorize "
            f"({'read+write' if 'write' in normalized_default_scopes else 'read'} by default); "
            "the consent page still requires the operator approval credential",
        ],
    }


def install(role: str, *, repo=None, bind: str | None = None, port: int = DEFAULT_PORT,
            path: str = DEFAULT_PATH, service: str = "systemd",
            master_url: str | None = None, mcp_config_path: str | None = None,
            auth_issuer_url: str | None = None, auth_resource_url: str | None = None,
            required_scope: list[str] | None = None) -> dict:
    """Provision a host into ``role``.

    Pure, offline, idempotent: it verifies the environment, renders the service
    artifacts, writes the role config, and installs the convergence hook — then
    returns ``manual_steps`` for the host-specific, side-effectful actions (index
    build, ``systemctl enable`` / ``docker compose up``) that are not unit-tested.
    The OPENAI_API_KEY value is never echoed into any artifact.
    """
    if role not in ROLES:
        raise InstallError(f"unknown role {role!r}; choose from {ROLES}")
    if role == "client":
        return _install_client(master_url, mcp_config_path, auth_issuer_url=auth_issuer_url,
                               auth_resource_url=auth_resource_url, required_scope=required_scope)

    # --- engine roles: master | single -------------------------------------
    if repo is None:
        raise InstallError(f"role {role!r} requires a repo path")
    repo = Path(repo).resolve()
    # Verify the credential FIRST — fail loud before writing anything (no half-provision).
    try:
        config.get_api_key(repo=repo)           # presence check only; value is discarded
    except config.ConfigError as exc:
        raise InstallError(
            f"role {role!r} is an engine role and needs OPENAI_API_KEY (env or gitignored "
            f".env) before install: {exc}"
        ) from exc

    bind = _LOCALHOST if role == "single" else bind
    if role == "master" and not bind:
        raise InstallError("role 'master' requires --bind <tailnet-ip>")
    if bind in _WILDCARD:
        raise InstallError(f"refusing bind {bind!r}: never a wildcard (tailnet-only, KTD10)")
    if service not in ("systemd", "docker"):
        raise InstallError(f"unknown --service {service!r}; choose systemd|docker")

    # Verify git BEFORE writing any artifact — install_hooks needs .git, and failing
    # here keeps the "nothing half-provisioned on failure" contract (no orphan unit/config).
    if not (repo / ".git").exists():
        raise InstallError(f"role {role!r} needs a git repo, but no .git found at {repo}")
    state = repo / index_mod.STATE_DIRNAME
    state.mkdir(mode=0o700, parents=True, exist_ok=True)

    artifacts: list[str] = []
    exe = _hypermnesic_exe()
    if service == "systemd":
        up = state / "hypermnesic.service"
        up.write_text(render_systemd_unit(repo, bind, port, path, exe,
                                          auth_issuer=auth_issuer_url,
                                          auth_resource=auth_resource_url,
                                          required_scopes=required_scope), encoding="utf-8")
        artifacts.append(str(up))
    else:  # docker
        dockerfile, compose = render_docker(repo, bind, port, path)
        dp, cp = state / "Dockerfile", state / "compose.yaml"
        dp.write_text(dockerfile, encoding="utf-8")
        cp.write_text(compose, encoding="utf-8")
        artifacts += [str(dp), str(cp)]

    cfg = {"role": role, "bind": bind, "port": port, "path": path,
           "write_enabled": True, "service": service}
    artifacts.append(str(_write_role_config(repo, cfg)))
    hooks = install_hooks(repo)                    # U33 reuse — pre-warm on pull

    manual = [f"hypermnesic init {repo}   # build the index (uses OPENAI_API_KEY; one-time)"]
    if service == "systemd":
        manual += [
            f"cp {state}/hypermnesic.service ~/.config/systemd/user/hypermnesic.service",
            "systemctl --user daemon-reload && systemctl --user enable --now hypermnesic",
        ]
    else:
        manual.append(f"cd {state} && docker compose up -d")

    return {"role": role, "bind": bind, "service": service, "write_enabled": True,
            "artifacts": artifacts, "config": cfg, "hooks": hooks["installed"],
            "manual_steps": manual}
