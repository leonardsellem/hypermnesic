# hypermnesic for Hermes Agent

This is the Hermes-specific hypermnesic package. It is separate from the Claude
Code / Codex plugin pack and uses the local **hypermnesic CLI**.

## Setup

1. Install or expose the `hypermnesic` command in the environment that starts
   Hermes.
2. Initialize a local vault or repository:

   ```sh
   hypermnesic init <path-to-your-vault> --json
   ```

3. Configure the vault path for Hermes:

   ```sh
   export HYPERMNESIC_REPO=<path-to-your-vault>
   ```

4. Install and enable this Hermes plugin package. If your Hermes install cannot
   install a plugin from a repository subdirectory, export `plugin/hermes/` as the
   plugin root so `plugin.yaml` is at the package root.

The plugin registers the namespaced skill `hypermnesic:hypermnesic-memory`.

## Optional flat skill

Hermes plugin skills are loaded by namespaced skill view and are not part of the
flat available-skills prompt index. For stronger automatic visibility, copy the
flat skill export into your ordinary Hermes skills directory:

```text
plugin/hermes/flat-skill/hypermnesic-memory/
```

Verify it with ordinary Hermes skill listing after install.

## Optional recall hook

The plugin can register a `pre_llm_call` recall hook. It is opt-in:

```sh
export HYPERMNESIC_HERMES_RECALL=1
```

When enabled and `HYPERMNESIC_REPO` is configured, the hook runs bounded local CLI
recall with `hypermnesic retrieve`. If the prompt is unrelated, the CLI is missing,
configuration is missing, recall fails, no hits are found, or the command times out,
the hook injects nothing and Hermes continues normally.

Disable recall by unsetting `HYPERMNESIC_HERMES_RECALL` or setting it to `0`.

## CLI commands

- `hypermnesic retrieve <repo> <query> --json` reads relevant memory.
- `hypermnesic think <repo> <topic> --json` explores related notes and questions.
- `hypermnesic resolve <repo> <name> --json` resolves entities to existing notes.
- `hypermnesic list-folders <repo> --json` shows folder taxonomy and writable areas.
- `hypermnesic capture <repo> <text> --json` writes raw text and commits it.
- `hypermnesic commit-note <repo> <path> --body <text> --json` is a dry-run preview
  of a guarded note write in the current CLI.

Hermes support does not configure a network memory server and does not use tokens.
Claude Code and Codex users should use the existing Claude/Codex plugin pack.
