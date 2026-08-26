---
type: Reference
title: Review and Navigation Surfaces
description: The generated, review-gated organizing layer — the proposal queue, the GENERATED demarcation, salience digests, serendipity connections, MOC/dashboard navigation, and the daily loop.
verified:
  - by: openwiki/0.4.0
    at: 2026-08-26T12:15:12.148Z
sources:
  - id: openwiki-source-1f366c0f066b53e2ffd37c97
    resource: repo://docs/guides/daily-workflows.md
  - id: openwiki-source-b71cfd92d11a88500eb68d63
    resource: repo://src/hypermnesic/audit_log.py
  - id: openwiki-source-51d97e561438845ebfc72a76
    resource: repo://src/hypermnesic/capture.py
  - id: openwiki-source-5f17d71d8e2d83b9ea0bc2ae
    resource: repo://src/hypermnesic/config.py
  - id: openwiki-source-5c8ff08d6850b78d1e5ac3b9
    resource: repo://src/hypermnesic/connect.py
  - id: openwiki-source-dc8a4871d5ced7a62fac4926
    resource: repo://src/hypermnesic/daily_review.py
  - id: openwiki-source-3a05a10f6a1dad4ec686dc45
    resource: repo://src/hypermnesic/generated.py
  - id: openwiki-source-d0c2638cdea3e85ab949dd06
    resource: repo://src/hypermnesic/index.py
  - id: openwiki-source-bf30bdf8a5e94f3f19416f00
    resource: repo://src/hypermnesic/memory_control.py
  - id: openwiki-source-83a93469d21e15084cc1477a
    resource: repo://src/hypermnesic/nav_surface.py
  - id: openwiki-source-802c4acce1763f2c8920a3cf
    resource: repo://src/hypermnesic/propose.py
  - id: openwiki-source-a00130abfc308c0df4234136
    resource: repo://src/hypermnesic/salience.py
  - id: openwiki-source-09482d0b1f2326b722bdba05
    resource: repo://src/hypermnesic/serialize.py
  - id: openwiki-source-02a7cae120d1e95c54556e73
    resource: repo://tests/test_daily_review.py
  - id: openwiki-source-0787b96150e9d987c4a715f9
    resource: repo://tests/test_nav_surface.py
  - id: openwiki-source-e3322aedaee646fa1bae8ef6
    resource: repo://tests/test_propose.py
  - id: openwiki-source-d7570bb5695ee4ffd06cfe28
    resource: repo://tests/test_salience.py
generated: {by: "claude-code", at: "2026-08-26T12:15:12.148Z"}
---

# Review and Navigation Surfaces

These surfaces keep a vault organized and resurfaced without ever taking the decision away
from the owner. One rule governs all of them:

> **A generated artifact is a proposal. It is never auto-applied, and it never rewrites a
> source note.**

That is enforced structurally — every one of these modules emits through the proposal queue
rather than through a direct write — not by convention.

## The proposal queue

The queue is the single front door for organizing writes. A set of path-scoped changes becomes
a narrow, gate-checked commit on a dedicated proposal branch, surfaced as a pull request the
owner approves. **The agent never merges.**

It deliberately **reuses the kernel's safety surface** rather than inventing a parallel write
path: the same protected-path guard, the same diff-or-die frontmatter gate, an isolated commit
posture, and the same append-only audit log. See
[Git-First Write Path](git-first-write-path.md) and
[Write Guard and Security Model](write-guard-and-security-model.md).

Several properties matter:

- **The declared scope is required, not optional.** Every proposal must pass its target
  allowlist explicitly to the guard, so a change cannot reach outside the scope its caller
  declared. The guard runs on every path **before any branch exists**.
- **Multi-file atomicity.** Every file is gated **in memory first**. Any abort raises before a
  branch is created, so an aborted proposal never leaves a partial or orphan branch behind.
- **A no-op is a no-op.** If every proposed file already matches its content at `HEAD`, the
  result is a no-op with no branch and no pull request.
- **Two tiers.** A proposal in which *every* change is a new file in a free-append zone takes
  the fast path and commits straight to `HEAD` — this is what makes frictionless capture
  possible. A curated path can never reach the fast path, and the fast path never overwrites.
- **Slugs are sanitized.** A caller-supplied title is reduced to a bounded, restricted
  character set with traversal sequences removed and no leading dash or slash, so a title
  cannot inject a git option or a ref traversal into the branch or PR commands.
- **A global budget bounds the cold-start flood.** The cap is charged only when a real
  proposal branch is created, so no-ops and re-proposals cost nothing against it.
- **Graceful without a PR host.** With no PR-creation hook available, the branch and diff still
  exist locally and the pull request is simply skipped — the proposal is resumable later rather
  than lost.
- **Re-proposing is reconciliation.** An existing branch for the same slug is reconciled rather
  than duplicated.

## The GENERATED demarcation

A generated file must be **unmistakably** generated — including in a reader view where
frontmatter is collapsed. So every generated artifact carries **both**:

1. `generated_by: hypermnesic` frontmatter, forced in by the renderer so a caller cannot omit
   it; and
2. a rendered, human-visible managed-block marker whose region is explicit, closed by a
   trailing end marker.

The visible marker states plainly that edits inside the region are overwritten. That is the
point: an explicit region means a human edit inside it is never a *surprise* overwrite. The
frontmatter marker is also what lets memory control classify a note as generated rather than
authored, without guessing. See [Memory and Client Control](memory-and-client-control.md).

## Salience and the spaced-review digest

Salience scores every indexed note from signals already in hand:

- **Link degree** from the wikilink graph, normalized by the maximum degree in the vault.
- **Embedding centrality** — mean cosine to every other note, a representativeness proxy.
- **Write recency**, rank-normalized across distinct timestamps so it is monotone and
  scale-free.

Note what recency means here. The audit log is **write-only**; there is no read or access
signal, and adding one would conflict with the read-only-is-structural posture. So "recency"
is recency *of write*, and a note never written through the log scores zero — dormant by
definition.

Scores are deterministic: fixed weights, sorted by score with the path as a stable tiebreak.
Before computing centrality the module ensures full embedding coverage, and the report carries
a `coverage_complete` flag that is false when the embedder was unavailable or failed mid-fill —
so a partial centrality is *labelled* rather than silently reported as final.

The digest surfaces **salient-but-dormant** notes, ranked by structural importance only —
link degree and centrality, deliberately **not** recency, since recency is precisely what makes
them dormant. With nothing dormant, the digest says so instead of padding.

One thing salience never does: **no `salience:` field is ever written into a source note's
frontmatter.** That churn is exactly what the generated-artifact rules forbid. The ranking
lives only in the generated digest.

## Connection and serendipity proposals

The connection surface answers "these two notes grapple with the same idea but aren't linked —
connect them?" A pair is a candidate when its cosine similarity is high **and** no wikilink
edge already joins the two.

It is high-precision by construction, because noisy suggestions destroy trust faster than no
suggestions:

- a **similarity threshold** below which nothing is offered;
- a **near-duplicate exclusion** at the top end — shared templates, raw captures, and
  boilerplate reach near-identical similarity and are not insight;
- a **per-run cap**, with candidates sorted deterministically by similarity then path.

When nothing clears the bar, the surface returns **nothing at all** rather than an empty
proposal — no noise.

This works from vectors and graph edges that already exist; it is deliberately *not* LLM
knowledge-graph extraction. When vectors are derived from the index rather than supplied, a
full unbudgeted embed runs first, so a genuine pair is never missed merely because one note's
chunks had not been embedded yet.

The suggestion is a batched proposal. **The link is never written into a source note.**

## Navigation: MOC and dashboard

The navigation surface is the always-organized human entry point: a Map-of-Content note listing
the vault's notes with a what-changed section drawn from the audit log, plus a dashboard view
configuration that reads note metadata with no plugin code required.

Both are emitted as **one** proposal, and both land in a non-protected dashboards directory —
never in a guard-protected one.

Idempotency rides on a **content-hash slug**: identical content yields an identical slug, so
re-proposing an unchanged surface is a no-op, while changed content yields a new slug and a
fresh proposal that reflects the change. Links to the digest and connection surfaces are
included only when supplied, so navigation generation never blocks on them.

## The daily review

The daily review composes the other surfaces into one review-gated artifact organized around
the loop: **capture → triage → recall → write → review → clean up.**

It gathers the capture backlog with each item's triage stage, the most recent writes from the
audit log, links to whichever generated surfaces exist, a reminder of which recall mode fits
which question — including "resolve before wikilinking, and do not guess on null" — degraded or
offline state, and the cleanup actions with their concrete commands.

**What it does not do**, explicitly: it does not move, delete, or rewrite any source note. It
is a dashboard proposal over existing primitives, and every actual change it points at is a
separate, previewed, owner-driven action. See [CLI Surface](cli-surface.md).
