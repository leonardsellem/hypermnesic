"""Secret-free owner control over OAuth client grants.

The live OAuth provider owns bearer/refresh tokens and revocation semantics. This module stores
only reviewable metadata so owners can list and mark grants revoked without handling credentials.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from hypermnesic import index

_VERSION = 1
_SAFE_KEYS = {
    "grant_id",
    "client_id",
    "client_name",
    "redirect_uri",
    "redirect_origin",
    "scopes",
    "write_enabled",
    "issued_at",
    "updated_at",
    "access_expires_at",
    "refresh_expires_at",
    "status",
    "active",
    "revoked_at",
}


def grant_store_path(repo: Path) -> Path:
    return index.state_dir_for(Path(repo)) / "client-grants.json"


def _empty() -> dict:
    return {"version": _VERSION, "grants": []}


def _read(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return _empty()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("grants"), list):
        raise ValueError(f"invalid client grant store: {path}")
    return {"version": data.get("version", _VERSION), "grants": data["grants"]}


def _write(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _safe(grant: dict) -> dict:
    return {k: grant.get(k) for k in _SAFE_KEYS if k in grant}


def upsert_grant(path: Path, grant: dict) -> None:
    safe = _safe(grant)
    grant_id = safe.get("grant_id")
    if not grant_id:
        raise ValueError("grant metadata requires grant_id")
    data = _read(Path(path))
    grants = [g for g in data["grants"] if g.get("grant_id") != grant_id]
    grants.append(safe)
    data["grants"] = sorted(
        grants, key=lambda g: (g.get("issued_at") or 0, g.get("grant_id") or "")
    )
    _write(Path(path), data)


def list_grants(path: Path) -> dict:
    data = _read(Path(path))
    grants = [_safe(g) for g in data["grants"]]
    return {"status": "ok", "count": len(grants), "grants": grants}


def find_grant(path: Path, grant_id: str) -> dict | None:
    for grant in _read(Path(path))["grants"]:
        if grant.get("grant_id") == grant_id:
            return _safe(grant)
    return None


def revoke_grant(path: Path, grant_id: str, *, apply: bool = False, now=None) -> dict:
    data = _read(Path(path))
    grants = data["grants"]
    grant = next((g for g in grants if g.get("grant_id") == grant_id), None)
    if grant is None:
        return {"status": "not_found", "grant_id": grant_id}
    if grant.get("status") == "revoked":
        return {"status": "already_revoked", "grant_id": grant_id, "active": False}
    if not apply:
        return {
            "stage": "preview",
            "grant_id": grant_id,
            "client_id": grant.get("client_id"),
            "client_name": grant.get("client_name"),
            "scopes": list(grant.get("scopes") or []),
            "write_enabled": bool(grant.get("write_enabled")),
            "would_revoke": True,
        }
    ts = int((now or time.time)())
    grant["status"] = "revoked"
    grant["active"] = False
    grant["revoked_at"] = ts
    grant["updated_at"] = ts
    _write(Path(path), data)
    return {
        "status": "revoked",
        "grant_id": grant_id,
        "active": False,
        "client_id": grant.get("client_id"),
        "client_name": grant.get("client_name"),
        "scopes": list(grant.get("scopes") or []),
        "write_enabled": bool(grant.get("write_enabled")),
        "next_effect": (
            "Future access for this grant is refused by a running server sharing this store."
        ),
    }
