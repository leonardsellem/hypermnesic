# Memory control

Hypermnesic memory is controlled through the same objects that make it trustworthy:
markdown files, git commits, the disposable index, and the append-only audit log. The
`hypermnesic memory` command group gives owners product-level verbs for those objects so
you do not have to reverse-engineer state from raw git commands.

Use this guide after local proof and setup diagnosis are healthy:

```sh
hypermnesic local-proof /path/to/vault
hypermnesic doctor /path/to/vault --public-url https://<your-host>.ts.net/mcp
```

## Inspect what is remembered

List remembered files:

```sh
hypermnesic memory list /path/to/vault
hypermnesic memory list /path/to/vault --folder projects/
hypermnesic memory list /path/to/vault --source-type captured
hypermnesic memory list /path/to/vault --protected
```

Inspect one memory:

```sh
hypermnesic memory inspect /path/to/vault projects/acme/decision.md
```

The output is file-and-commit based: repo-relative path, title, bounded snippet, last
commit, source type, audit actor when available, and whether the path is currently
writable under the same guard used by `commit_note`.

Source types are evidence-based:

- `authored`: ordinary markdown source content.
- `captured`: raw source material under `sources/`.
- `generated`: a Hypermnesic generated surface with `generated_by: hypermnesic`.

Unknown or missing evidence is shown as `unknown`; the control surface does not invent
provenance.

## Answer what an agent may write

Before granting or debugging writes, ask the control surface what the effective write
surface allows:

```sh
hypermnesic memory write-scope /path/to/vault
hypermnesic memory write-scope /path/to/vault --allowlist projects/
```

This uses the same folder derivation and protected-path guard as `list-folders` and
`commit_note`. An explicit `--allowlist` narrows the surface; it never weakens protected
classes such as `.git/`, `.github/`, agent-instruction files, `scripts/`, `hooks/`,
`skills/`, build files, CI files, and credential files.

## Export memory

Export preserves markdown layout and writes a provenance manifest:

```sh
hypermnesic memory export /path/to/vault --folder projects/acme/ --dest ./hypermnesic-export
hypermnesic memory export /path/to/vault --path notes/specific.md --dest ./hypermnesic-export
```

The export is not an opaque database dump. It copies selected markdown files and creates
`hypermnesic-export-manifest.json` with source path, last commit, actor when known, and
source type. Disposable index state such as `.hypermnesic/index.db` is not exported.

## Preview and apply forget/delete

Always preview first:

```sh
hypermnesic memory forget /path/to/vault projects/acme/bad-memory.md
```

Preview shows the target path, guard result, intended git effect, and verification plan.
Apply only after the preview is correct:

```sh
hypermnesic memory forget /path/to/vault projects/acme/bad-memory.md --apply
```

Forget/delete means:

- the current source file is removed from the git tree by a new commit;
- the disposable index removes that path or tells you to reindex when needed;
- recall should no longer return the removed current source path.

It does **not** mean:

- rewriting git history;
- deleting old chat contexts outside the vault;
- proving the memory never existed.

Protected paths and dirty working trees are refused before mutation. Refusals leave no
partial file, index, or audit side effect.

## Revert a recent memory write

For a recent single-file markdown write, preview the revert:

```sh
hypermnesic memory revert /path/to/vault <commit-sha>
```

Then apply it as a new commit:

```sh
hypermnesic memory revert /path/to/vault <commit-sha> --apply
```

Complex cases are refused rather than guessed. Multi-file commits, missing commit
metadata, conflicts, and dirty trees require manual owner review.

## Audit writes and refusals

View recent write, forget, revert, reconcile, and refusal entries:

```sh
hypermnesic memory audit /path/to/vault
hypermnesic memory audit /path/to/vault --limit 20 --json
```

Audit output is summary-only. It includes actor, verb, path, shas, summary, and refusal
category where available; it does not display raw note bodies, tokens, or credential
material.

## JSON mode

Every memory-control command supports `--json` for agents and CI checks:

```sh
hypermnesic memory inspect /path/to/vault projects/acme/decision.md --json
hypermnesic memory write-scope /path/to/vault --json
```

Use JSON when a client needs to prove:

- which file was inspected or removed;
- which commit produced the current state;
- which guard refused a path;
- whether recall/index verification succeeded after a control action.
