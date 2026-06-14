---
title: "PyPI publication decision"
status: decision-needed
audience: operator
linear: LS-1684
last_checked: 2026-06-14
---

# PyPI publication decision

This is the PR-15 / LS-1684 decision memo. It prepares the go/no-go call for
publishing `hypermnesic` to PyPI so users can install the CLI with:

```sh
uv tool install hypermnesic
```

Do not claim the PyPI name, configure a trusted publisher, add an active publishing
workflow, or publish an artifact without operator approval.

## Recommendation

Recommendation: **go**, using PyPI Trusted Publishing from GitHub Actions with a
manual-approval `pypi` environment.

Rationale:

- Name availability: `https://pypi.org/pypi/hypermnesic/json` returned HTTP `404`
  on 2026-06-14, so the name appears unclaimed at this moment.
- Packaging readiness: `uv build` successfully produced
  `dist/hypermnesic-0.1.0.tar.gz` and `dist/hypermnesic-0.1.0-py3-none-any.whl`.
- Install readiness: a clean local `uv tool install` from the built wheel installed
  the `hypermnesic` executable, and `hypermnesic --help` listed the expected CLI
  command surface.
- Public-launch fit: one-command install removes the current clone requirement and
  also gives the official MCP Registry a package-backed option after publication.
- Security fit: official PyPI/PyPA guidance recommends Trusted Publishing so GitHub
  Actions can publish through OIDC without storing a long-lived PyPI API token.

## Current package state

Current `pyproject.toml` already has the core PyPI package metadata:

- `name = "hypermnesic"`
- `version = "0.1.0"`
- `license = "AGPL-3.0-only"`
- `requires-python = ">=3.11"`
- console script: `hypermnesic = "hypermnesic.cli:main"`
- build backend: `hatchling`

The existing CI workflow runs tests, license scan, and public scan but does not publish.

## Required go path

These steps are intentionally not executed by this memo.

1. Operator approves PyPI go/no-go.
2. Operator logs into PyPI and configures a pending Trusted Publisher for:
   - Project name: `hypermnesic`
   - Owner: `leonardsellem`
   - Repository: `hypermnesic`
   - Workflow: the future publish workflow file name
   - Environment: `pypi`
3. Add a GitHub `pypi` environment that requires manual approval.
4. Add a publish workflow that:
   - builds from an explicit release tag,
   - runs a wheel/sdist smoke before upload,
   - has job-level `id-token: write`,
   - publishes only after the `pypi` environment approval,
   - does not use PyPI tokens or repository secrets.
5. For the existing `v0.1.0` release, choose one of:
   - publish `0.1.0` by a workflow dispatch that checks out `refs/tags/v0.1.0`, or
   - cut a new `v0.1.1` release and publish that first.
6. After PyPI publication, update:
   - README quickstart from Git URL install to `uv tool install hypermnesic`,
   - getting-started docs,
   - official MCP Registry draft to include a package-backed PyPI entry,
   - changelog.
7. Verify from a clean environment:

```sh
uv tool install hypermnesic
hypermnesic --version
hypermnesic --help
```

## No-go path

If the operator chooses no-go:

- Record the decision in LS-1684.
- Keep Git URL installation as the public quickstart.
- Leave `docs/launch/directory-submission-prep.md` on the remote-template MCP
  Registry path only.
- Revisit PyPI after the first public adoption signal or after the next release.

## Evidence gathered

```text
PyPI JSON API:
GET https://pypi.org/pypi/hypermnesic/json -> 404
```

```text
uv build:
Successfully built dist/hypermnesic-0.1.0.tar.gz
Successfully built dist/hypermnesic-0.1.0-py3-none-any.whl
```

```text
clean local wheel install:
Installed 1 executable: hypermnesic
hypermnesic --help printed the expected CLI parser and command list.
```

## Sources checked

- PyPI JSON API for name availability:
  `https://pypi.org/pypi/hypermnesic/json`
- uv GitHub Actions publishing guide:
  `https://docs.astral.sh/uv/guides/integration/github/#publishing-to-pypi`
- PyPI Trusted Publishing docs:
  `https://docs.pypi.org/trusted-publishers/using-a-publisher/`
- Python Packaging User Guide:
  `https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/`
