import json

from hypermnesic import client_control


def _grant(grant_id="grant-1", scopes=("read",), status="active"):
    return {
        "grant_id": grant_id,
        "client_id": "cid-1",
        "client_name": "ChatGPT",
        "redirect_uri": "https://chatgpt.com/connector_platform_oauth_redirect",
        "redirect_origin": "https://chatgpt.com",
        "scopes": list(scopes),
        "write_enabled": "write" in scopes,
        "issued_at": 1_000_000,
        "updated_at": 1_000_000,
        "access_expires_at": 1_003_600,
        "refresh_expires_at": 1_086_400,
        "status": status,
        "active": status == "active",
        "revoked_at": None,
    }


def test_client_control_lists_secret_free_grants(tmp_path):
    store = tmp_path / "client-grants.json"
    client_control.upsert_grant(store, _grant(scopes=("read", "write")))
    out = client_control.list_grants(store)
    assert out["status"] == "ok"
    assert out["count"] == 1
    grant = out["grants"][0]
    assert grant["client_name"] == "ChatGPT"
    assert grant["write_enabled"] is True
    blob = json.dumps(out)
    assert "access_token" not in blob
    assert "refresh_token" not in blob
    assert "approval" not in blob


def test_client_control_revoke_updates_metadata_idempotently(tmp_path):
    store = tmp_path / "client-grants.json"
    client_control.upsert_grant(store, _grant(scopes=("read", "write")))
    preview = client_control.revoke_grant(store, "grant-1", apply=False)
    assert preview["stage"] == "preview" and preview["would_revoke"] is True
    applied = client_control.revoke_grant(store, "grant-1", apply=True, now=lambda: 1_000_100)
    assert applied["status"] == "revoked"
    again = client_control.revoke_grant(store, "grant-1", apply=True, now=lambda: 1_000_101)
    assert again["status"] == "already_revoked"
    grant = client_control.list_grants(store)["grants"][0]
    assert grant["status"] == "revoked" and grant["active"] is False


def test_client_control_unknown_grant_is_clear(tmp_path):
    store = tmp_path / "client-grants.json"
    client_control.upsert_grant(store, _grant())
    out = client_control.revoke_grant(store, "missing", apply=True)
    assert out["status"] == "not_found"
    assert out["grant_id"] == "missing"
