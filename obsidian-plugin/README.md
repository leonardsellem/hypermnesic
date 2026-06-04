# Hypermnesic Companion — moved

The Obsidian companion plugin now lives in its own repository:

> **https://github.com/leonardsellem/hypermnesic-companion**
>
> _The repository is **private until the companion's first community-directory release**;
> this link becomes public when that ships._

This monorepo no longer carries the plugin source or its read-only proof. The
plugin builds, runs its tests — including the static **read-only invariant** scan
(`test/read-only.test.ts`, ported from the former `tests/test_obsidian_plugin.py`
here) — and ships from that repo under **GPL-3.0**.

The engine in this repo (planned **AGPL-3.0**) and the companion (**GPL-3.0**) communicate
only at arm's length over the read-only MCP wire protocol (`search` / `build_context` /
`think`); neither is a derivative of the other. That holds **because** they are separate
processes with no shared or statically-linked code — and stays true only while the companion
**does not vendor, import, or statically link engine source** (the read-only-over-the-wire
invariant). See the engine README's "License" section for the canonical boundary statement.

In the Hypermnesic daily loop, Obsidian is a **read-only** review and navigation surface for
capture backlog, generated dashboards, daily loop notes, and source paths. Write, cleanup, revoke,
forget/delete, and revert actions stay in the CLI/MCP git-first surfaces; the companion cannot
bypass consent, write scope, protected-path refusals, or server-side write guards.
