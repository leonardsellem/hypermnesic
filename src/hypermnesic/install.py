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


def _install_client(master_url: str | None, mcp_config_path: str | None,
                    *, server_name: str = "hypermnesic") -> dict:
    """Client = config only (no engine, no index). Write/patch an MCP client config
    pointing at the master endpoint; preserve any other servers already present."""
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
    servers[server_name] = {"type": "streamable-http", "url": master_url}   # idempotent upsert
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "role": "client",
        "artifacts": [str(path)],
        "config": {"master_url": master_url},
        "manual_steps": [
            f"point your MCP client / Obsidian companion at {master_url} "
            "(tailnet membership is the auth boundary — MVP)",
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
        return _install_client(master_url, mcp_config_path)

    # --- engine roles: master | single -------------------------------------
    if repo is None:
        raise InstallError(f"role {role!r} requires a repo path")
    # Verify the credential FIRST — fail loud before writing anything (no half-provision).
    try:
        config.get_api_key()                       # presence check only; value is discarded
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

    repo = Path(repo).resolve()
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
