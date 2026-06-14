---
title: "Directory submission prep"
status: prepared
audience: operator
linear: LS-1683
last_checked: 2026-06-14
---

# Directory submission prep

This is the PR-14 / LS-1683 prep artifact. It records the target directories,
copy-ready draft entries, verification evidence, and the exact pause points before
any externally visible submission.

Do not submit from this document without operator approval.

## Current evidence

- Main repo: `https://github.com/leonardsellem/hypermnesic` is public.
- Main repo description/topics are set; GitHub community profile reports `100%`.
- README demo link to use in submissions:
  `https://github.com/leonardsellem/hypermnesic#quick-start`.
- Companion repo: `https://github.com/leonardsellem/hypermnesic-companion` is public.
- Companion release `0.3.0` is published with individual `main.js`, `manifest.json`,
  and `styles.css` assets.
- Companion root `manifest.json`:

```json
{
  "id": "hypermnesic-companion",
  "name": "Hypermnesic Companion",
  "version": "0.3.0",
  "minAppVersion": "1.5.0",
  "description": "Surface read-only, pause-triggered related notes and an interrogable reinvention nudge from your tailnet hypermnesic index as you write. Never writes the vault.",
  "author": "Leonard Sellem",
  "authorUrl": "https://github.com/leonardsellem",
  "isDesktopOnly": true
}
```

- Companion `versions.json` contains `"0.3.0": "1.5.0"`.
- Official MCP Registry search for `hypermnesic` currently returns no entries.
- Official `mcp-publisher validate` passes for the staged registry draft after the
  description was shortened to the current <=100 character schema limit.
- Official MCP Registry publication is blocked in this environment until an operator
  completes `mcp-publisher login github`.
- `punkpeye/awesome-mcp-servers` PR opened:
  `https://github.com/punkpeye/awesome-mcp-servers/pull/8056`.
- Obsidian community-plugin submission branch is prepared:
  `https://github.com/leonardsellem/obsidian-releases/tree/add-hypermnesic-companion`.
  Creating the upstream PR from this environment failed because the current GitHub token
  lacks `CreatePullRequest` permission for `obsidianmd/obsidian-releases`.

## Target 1: official MCP Registry

Source checked:

- `https://modelcontextprotocol.io/registry/about`
- `https://modelcontextprotocol.io/registry/quickstart`
- `https://modelcontextprotocol.io/registry/remote-servers`
- `https://modelcontextprotocol.io/registry/package-types`

Important constraints:

- The official registry stores MCP server metadata, not package artifacts.
- Publishing uses the official `mcp-publisher` CLI.
- GitHub-authenticated names must be under the matching namespace, for example
  `io.github.leonardsellem/hypermnesic`.
- Package-backed registry entries require a public package registry artifact. PyPI
  publication is tracked separately by LS-1684, so this prep does not assume PyPI.
- Remote-server entries are supported with `remotes`; remote URLs must be publicly
  accessible. URL template variables are supported for multi-tenant/self-hosted
  deployments.

Draft `server.json` for a self-hosted remote-template listing is stored at
`docs/launch/mcp-registry-server.draft.json`:

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.leonardsellem/hypermnesic",
  "title": "Hypermnesic",
  "description": "Git-first Markdown memory for AI agents with reviewable commits and a disposable search index.",
  "repository": {
    "url": "https://github.com/leonardsellem/hypermnesic",
    "source": "github"
  },
  "version": "0.1.0",
  "remotes": [
    {
      "type": "streamable-http",
      "url": "https://{host}/mcp",
      "variables": {
        "host": {
          "description": "Public HTTPS host for your Hypermnesic deployment, without the /mcp path.",
          "isRequired": true
        }
      }
    }
  ]
}
```

The official MCP Registry currently enforces `description` length <= 100
characters; keep the draft below that limit.

Approval-gated commands:

```sh
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher
cp docs/launch/mcp-registry-server.draft.json server.json
./mcp-publisher validate
./mcp-publisher login github
./mcp-publisher publish
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.leonardsellem/hypermnesic"
```

Pause before copying to root, `login`, or `publish`. Root-level `server.json`,
authentication, and publication are externally visible release-positioning work.

If LS-1684 goes ahead, add a package-backed PyPI entry after the package is live and
the README contains the required `mcp-name` verification string.

## Target 2: awesome-mcp-servers

Source checked:

- `https://github.com/punkpeye/awesome-mcp-servers`
- `https://github.com/punkpeye/awesome-mcp-servers/blob/main/CONTRIBUTING.md`

Submission shape:

- Fork the repo.
- Edit `README.md`.
- Add one server line in the relevant category, keeping existing format and
  alphabetical order.
- Open a pull request.

Recommended category: `Knowledge & Memory`.

Draft entry:

```md
- [Hypermnesic](https://github.com/leonardsellem/hypermnesic) 🐍 ☁️ 🏠 🍎 🪟 🐧 - Git-first memory for AI agents: Markdown files are truth, the index is disposable, and writes are reviewable commits. Ships a Streamable HTTP MCP endpoint, CLI, and read-only Obsidian companion.
```

Draft PR body note:

```md
The README demo and 5-minute proof are at https://github.com/leonardsellem/hypermnesic#quick-start.
```

Operational note: recent maintainer comments on `punkpeye/awesome-mcp-servers`
submissions ask for a Glama listing and score badge. Treat Glama as a likely
precondition before opening the PR, even though the contributing file still only
requires a README edit.

Approval-gated actions:

1. Submit/claim Hypermnesic in Glama if required.
2. Open the `punkpeye/awesome-mcp-servers` PR.

Current submission state: PR
`https://github.com/punkpeye/awesome-mcp-servers/pull/8056` is open. Glama search did
not yet return a Hypermnesic listing at submission time, so the entry does not include a
Glama score badge yet.

## Target 3: Obsidian community plugin directory

Source checked:

- `https://github.com/obsidianmd/obsidian-releases`
- `https://docs.obsidian.md/Plugins/Releasing/Submit+your+plugin`

Submission shape:

- Obsidian reads `community-plugins.json`.
- The entry fields used for directory search are `id`, `name`, `author`,
  `description`, and `repo`.
- Obsidian pulls `manifest.json` and `README.md` from the plugin repo.
- Release installs download `manifest.json`, `main.js`, and `styles.css` from the
  GitHub release tag matching the manifest version.

Draft `community-plugins.json` entry:

```json
{
  "id": "hypermnesic-companion",
  "name": "Hypermnesic Companion",
  "author": "Leonard Sellem",
  "description": "Surface read-only, pause-triggered related notes and an interrogable reinvention nudge from your tailnet hypermnesic index as you write. Never writes the vault.",
  "repo": "leonardsellem/hypermnesic-companion"
}
```

Draft PR body note:

```md
The engine README demo and 5-minute proof are at https://github.com/leonardsellem/hypermnesic#quick-start. The companion README links back to the engine setup and keeps the plugin read-only by design.
```

Approval-gated action: open the `obsidianmd/obsidian-releases` PR.

Current submission state: branch
`https://github.com/leonardsellem/obsidian-releases/tree/add-hypermnesic-companion`
is pushed and verified. The manual compare URL is
`https://github.com/obsidianmd/obsidian-releases/compare/master...leonardsellem:obsidian-releases:add-hypermnesic-companion?expand=1`.

## Readiness checklist

- [x] Operator approves external official MCP Registry publication.
- [ ] Official MCP Registry entry published and search result recorded.
- [x] Operator approves Glama / awesome-mcp-servers submission path.
- [x] Awesome list PR opened or merged; link recorded.
- [x] Operator approves Obsidian community plugin directory submission.
- [ ] Obsidian submission PR opened; link recorded.

## Verification after submission

- Official MCP Registry: search by `io.github.leonardsellem/hypermnesic` and record
  the JSON result URL/output.
- Awesome list: record PR URL and verify the PR body links the README demo.
- Obsidian: record PR URL and verify the bot accepts `id`, `name`, `description`,
  `repo`, root manifest, `versions.json`, release assets, and PR body demo link.
