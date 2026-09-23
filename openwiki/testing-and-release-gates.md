---
type: Reference
title: Testing and Release Gates
description: How change is validated and shipped — the offline deterministic suite, the gate set CI mirrors exactly, the fresh-install job, the branch topology, and the tag-triggered publish.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-4d1d392666be6dfdd7a91a2e
    resource: repo://.github/workflows/release.yml
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-f317ee207e1653d2033c81a4
    resource: repo://CONTRIBUTING.md
  - id: openwiki-source-196170e31ff8ec60a116165b
    resource: repo://docs/README.md
  - id: openwiki-source-7e2faff78811ec16a74aaa48
    resource: repo://harness/BENCHMARKS.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-a72a6aa6a47eea66ad34a468
    resource: repo://scripts/changelog_section.py
  - id: openwiki-source-d49085b6307a283976e1760a
    resource: repo://scripts/check_version_consistency.py
  - id: openwiki-source-b42150aa768b77959b0fc471
    resource: repo://scripts/license_scan.py
  - id: openwiki-source-12224262a7b33bff0baf3679
    resource: repo://scripts/preflight_public_scan.py
  - id: openwiki-source-6fc73e7c1f9cf3f50dfc9013
    resource: repo://scripts/product_smoke.py
  - id: openwiki-source-3a44815832a872f4778f822b
    resource: repo://SECURITY.md
  - id: openwiki-source-eca76e73bbc2749831def863
    resource: repo://src/hypermnesic/embed.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-04a94f5d7b8de56c2779a7be
    resource: repo://tests/test_changelog_section.py
  - id: openwiki-source-5c0263a3c806687c32295a14
    resource: repo://tests/test_dependency_bounds.py
  - id: openwiki-source-98c095b66db6365e82c220ad
    resource: repo://tests/test_doctor.py
  - id: openwiki-source-2eba846ab3cbfcc6150d04e3
    resource: repo://tests/test_index.py
  - id: openwiki-source-587fb618d5916bb5f0eb237b
    resource: repo://tests/test_license_scan.py
  - id: openwiki-source-84bf43836af5a7c7a11cf9f7
    resource: repo://tests/test_preflight_public_scan.py
  - id: openwiki-source-632c37de667345b12d6a84a9
    resource: repo://tests/test_version_consistency.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Testing and Release Gates

## The gates

CI runs one job whose steps are exactly the commands a contributor runs locally, so passing
locally and passing CI are the same event rather than two hopeful approximations:

```sh
uv sync --extra dev
uv run ruff check .
uv run python scripts/check_version_consistency.py
uv run pytest
uv run python scripts/license_scan.py
uv run python scripts/preflight_public_scan.py
```

A convention runs through all of these: **point at the enforcing gate rather than restating
what it checks.** A prose list of version slots or forbidden licenses is the next thing to
drift; the script is the authority, and it names what diverged when it fails.

## The test suite: offline and deterministic

The suite runs with no network and no API spend, and its determinism is structural rather
than incidental.

Tests inject a **deterministic fake embedder**: identical text always yields an identical
unit vector, different text yields a different one, and it emits exactly the pinned number of
dimensions. Two properties follow. A chunk is reliably its own nearest neighbour, so retrieval
assertions are stable; and rebuilds are bit-reproducible, so an index-reproducibility test is
meaningful rather than flaky. Because the vector width is real, the dimension invariants under
test are real invariants and not a smaller stand-in.

Credential-dependent behaviour is exercised by controlling the environment explicitly — setting
a placeholder key where a configured credential is the subject, deleting it where absence is
the subject — rather than by reaching a live provider. The real provider path is covered
separately by the live smoke embed and live-corpus verification, outside the suite.

A shared corpus fixture builds a small markdown repository, optionally git-initialized with a
deterministic commit, so tests that need real git history get it without a network or an
external checkout.

Tests run in `tests/` with importlib import mode.

Two rules govern contributions: **test-first**, meaning new production behaviour arrives with a
failing test first; and **no "pre-existing" failures**, meaning a red test is either fixed in
your change or filed as a tracked issue, never dismissed or deleted.

## The scanning gates

**Version consistency.** One authority — the project version in the packaging metadata — and
every distributed version string must agree with it: the in-package mirror, each plugin
manifest, and the citation metadata. This gate exists because of a real split where a release
bumped only the Python package and the plugin manifests drifted. It asserts in CI rather than
generating manifests at build time — the lowest-churn choice — and its failure message names
the diverging file and both versions, so the fix needs no investigation.

**License gate.** Scans the *resolved* dependency tree of the active environment and fails on
any strong-copyleft license, verifying the "permissive dependencies" claim instead of asserting
it. Weak copyleft is reported informationally so a human can still eyeball it. Crucially it is
**dependency-scoped**: the project's own distribution is excluded before classification, keyed
on the project name — otherwise the engine's own copyleft license would make the gate reject
the project itself, a false failure. The self-exclusion keys on the name alone, so it never
weakens the check on dependencies.

**Preflight public scan.** Scans git-tracked files for operator-private values — tailnet names,
node addresses, credential material, operator home paths — so none ships in a public surface.
A hit fails with file, line, and pattern, and the matched **value is masked** in the output, so
the gate never re-prints a secret into a console or a CI log. It has three modes: a default
now-gate that defers a named set of inherited process-history documents while **reporting how
many it deferred** rather than dropping them silently; a strict mode that scans everything as
the flip-time gate; and an informational history scan that never fails the gate. Archived
documents are deferred in default mode but scanned under strict, so archiving a document can
never hide a leak.

This is why any host in a doc, fixture, or example must be a placeholder. See
[Configuration and Tunables](configuration-and-tunables.md).

**Product smoke.** A separate deterministic local script runs against a disposable fixture
vault, with path-relative and secret-free output. Product operability is gated separately from
retrieval quality — see [Benchmarks and Evaluation](benchmarks-and-evaluation.md).

## The fresh-install job

A second CI job exists because of a specific outage, and its reasoning generalizes.

Every other job runs inside the lockfile — and the lockfile is **not shipped in the wheel or
sdist**. So no lock-resolved job can see a dependency resolving to a breaking major. That is
exactly how an unbounded dependency range let a new major reach users and crash-loop every
clean install.

The job therefore builds the sdist and wheel, installs the wheel into a clean environment
**resolved from the index with no lockfile** — the way a user's install resolves — reports what
it resolved, and then proves the package actually starts: importing the server module (the
precise line that failed), printing the version, and rendering serve help.

A unit test is the cheap local half of the same protection: it fails the moment a runtime
dependency loses its upper bound, without waiting for that dependency to publish a breaking
major.

## Branches

```text
feature branch ──PR──▶ dev ──PR──▶ main ──tag v*.*.*──▶ PyPI + GitHub release
```

`dev` is the default branch and the baseline for all work; `main` is the **release branch** and
receives `dev` at release time, never a feature branch. Never commit directly to either. Let
the PR tool use the repository default rather than passing an explicit base.

If the two drift apart, reconcile by **merging `main` back into `dev`** — never by
cherry-picking, which leaves the same content under two SHAs to untangle at the next release.

Commits use conventional subjects and require a **DCO sign-off** line. The DCO is a lightweight
provenance attestation; a contributor licence agreement is deliberately not required.

Changes to auth, the MCP server, the write path, or the guard are **security-sensitive**, routed
to the owner through code ownership rules, and should cite the security policy and threat model.
See [Write Guard and Security Model](write-guard-and-security-model.md).

## Releasing: merging publishes nothing

**A merge to `main` publishes nothing.** The release workflow triggers only on a version **tag
push** or a manual dispatch; a branch merge runs CI and stops. Publishing is a deliberate act,
never a side effect of merging.

The release runs in three stages, each gated on the last:

1. **Build** — re-runs the version-consistency gate, then builds the sdist and wheel.
2. **Publish** — uploads to the package index using OIDC trusted publishing. There is **no
   stored API token**: a short-lived identity token is exchanged for an upload token at run
   time. A consequence worth understanding is that a tag pushed from the wrong place cannot be
   quietly undone by rotating a key, which is exactly why tagging is deliberate.
3. **GitHub release** — runs only after publishing succeeded, so nothing is announced that did
   not actually ship, and only for a tag rather than a manual dispatch. Its permissions are
   scoped up to write only for this job; the others stay read-only.

Release notes are **generated from the changelog**, not hand-written, so they cannot drift from
the record — and a missing changelog section exits non-zero, meaning no release. The notes are
assembled with an install line, a link to the published version, and a compare link to the
previous tag when one exists, and the built artifacts are attached to the release with the tag
verified.

## Documentation is part of the change

A change is **not done** until every document it affects is corrected **in the same pull
request**. "Update the docs later" is not permitted, because later does not come and a stale
document actively misleads the next reader.

This is paid-for scar tissue, from the same version split that produced the consistency gate and
from a later effort spent un-staling architectural self-descriptions the code had long since
moved past. Where an automated gate already pins truth, reference the gate instead of copying
its list into prose. Where a process-history document conflicts with the current-truth pins,
the pins win. And drift you find but did not cause is a defect: fix it or file it, exactly like
a failing test.
