"""Client-specific next actions for setup and doctor/status output."""

from __future__ import annotations


def client_next_actions(public_url: str | None) -> list[dict]:
    """Return secret-free guidance for every supported client surface."""
    remote_available = bool(public_url)
    remote_url = public_url if public_url else None
    return [
        {
            "id": "local_cli",
            "label": "Local CLI",
            "mode": "local",
            "available": True,
            "summary": "Use the engine-host CLI directly; no remote MCP setup is needed.",
            "command": "hypermnesic retrieve /path/to/vault \"what do we know about X\"",
            "next_action": "Run local-proof first, then use retrieve/think/resolve locally.",
        },
        {
            "id": "remote_mcp",
            "label": "Generic remote MCP client",
            "mode": "remote",
            "available": remote_available,
            "url": remote_url,
            "summary": (
                "Add the public MCP endpoint URL to the client and complete browser OAuth."
                if remote_available else
                "Remote MCP guidance is unavailable until setup has a public URL."
            ),
            "next_action": (
                f"Use {remote_url} as the MCP server URL."
                if remote_available else
                "Run setup with --public-url before configuring remote clients."
            ),
        },
        {
            "id": "claude_codex_plugin",
            "label": "Claude Code / Codex plugin",
            "mode": "remote",
            "available": remote_available,
            "url": remote_url,
            "summary": (
                "Set HYPERMNESIC_MCP_URL to the endpoint; OAuth discovery handles login."
                if remote_available else
                "Plugin setup needs the public endpoint URL from setup."
            ),
            "next_action": (
                "Install the plugin and set HYPERMNESIC_MCP_URL to the endpoint URL."
                if remote_available else
                "Run setup, then set HYPERMNESIC_MCP_URL."
            ),
        },
        {
            "id": "obsidian_companion",
            "label": "Obsidian companion",
            "mode": "tailnet_read",
            "available": True,
            "summary": "Use the tailnet read route for the read-only Obsidian companion.",
            "next_action": "Point the companion at http://<tailnet-ip>:8848/mcp.",
        },
    ]


def client_next_action_map(public_url: str | None) -> dict:
    return {a["id"]: a for a in client_next_actions(public_url)}
