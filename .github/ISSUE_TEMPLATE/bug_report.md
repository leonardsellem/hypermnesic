---
name: Bug report
about: Report something that isn't working as documented
title: "[bug] "
labels: bug
assignees: ""
---

## What happened

A clear description of the bug and what you expected instead.

## Steps to reproduce

1. …
2. …

## Deployment shape

Help us reproduce — hypermnesic's behavior depends on how it's deployed:

- **hypermnesic version:** (`hypermnesic --version`)
- **How you're running it:** self-hosted endpoint / local CLI only / plugin client
- **Engine host OS:** (e.g. Ubuntu 24.04, macOS 14)
- **Client:** (Claude / ChatGPT connector, Claude Code plugin, Codex, Obsidian companion, CLI)
- **Vault size:** approximate number of markdown files
- **Serving lane:** unified public OAuth `/mcp` (Funnel) / tailnet read companion (`:8848`) / local CLI
- **Tailscale / Funnel state:** (e.g. `tailscale status` healthy? Funnel configured?)
- **Embeddings:** `OPENAI_API_KEY` set, or running lexical-only / degraded?

## Logs / output

Paste relevant output. **Redact any tokens, hostnames, or IPs** — never paste secrets.

## Additional context

Anything else that might help.
