#!/usr/bin/env python3
"""hero_commit.py (U4) — drive ONE real MCP ``commit_note`` write against a loopback master.

The hero receipt loop needs a **real** git commit, and only the MCP ``commit_note`` tool
produces one — the ``hypermnesic commit-note`` CLI is a dry-run preview. This tiny client
connects to a loopback, write-enabled ``hypermnesic`` master over streamable HTTP and calls
``commit_note`` once.

A ``127.0.0.1`` bind is exempt from the write⇒auth invariant (``mcp_server._LOCALHOST_BINDS``),
so the master runs with **no auth** — there is no OAuth issuer URL or consent screen to
appear on screen in the recording.

Uses the official MCP Python SDK (``mcp>=1.2``, already a dependency — no new package),
so the write goes through the exact same tool surface a real client uses.

    python hero_commit.py --url http://127.0.0.1:8765/mcp \\
        --path memory/decisions/ship-receipts-first.md \\
        --summary "Decide: lead the launch with the git receipt" \\
        --body "We will lead with the receipt loop..."
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def _commit(url: str, path: str, body: str | None, summary: str | None) -> dict:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "commit_note",
                {"path": path, "body": body, "summary": summary},
            )
    # Prefer the structured tool output; fall back to the JSON text block.
    payload = getattr(result, "structuredContent", None)
    if not payload and getattr(result, "content", None):
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                try:
                    payload = json.loads(text)
                    break
                except json.JSONDecodeError:
                    continue
    return payload or {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="one real MCP commit_note write (loopback master)")
    ap.add_argument("--url", default="http://127.0.0.1:8765/mcp",
                    help="loopback master MCP endpoint (default: %(default)s)")
    ap.add_argument("--path", required=True, help="repo-relative note path to write")
    ap.add_argument("--summary", default=None, help="commit summary")
    ap.add_argument("--body", default=None, help="note body (markdown)")
    ap.add_argument("--body-file", default=None, help="read the body from a file")
    args = ap.parse_args(argv)

    body = args.body
    if args.body_file:
        with open(args.body_file, encoding="utf-8") as fh:
            body = fh.read()

    payload = asyncio.run(_commit(args.url, args.path, body, args.summary))

    if payload.get("refused"):
        print(f"✗ commit_note refused: {payload['refused']}")
        return 1
    if not payload.get("committed"):
        print(f"✗ commit_note made no change (noop): {payload}")
        return 1
    sha = (payload.get("new_sha") or "")[:8]
    print(f"✓ commit_note wrote {payload.get('path')}")
    if sha:
        print(f"  commit {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
