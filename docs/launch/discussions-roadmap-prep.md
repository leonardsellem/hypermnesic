---
title: "GitHub Discussions and roadmap prep"
status: prepared
audience: operator
linear: LS-1686
last_checked: 2026-06-14
---

# GitHub Discussions and roadmap prep

This is the PR-17 / LS-1686 prep artifact. It stores the exact content to post
after GitHub Discussions are enabled, and it names the verification needed before
the issue can move to Done.

Do not enable Discussions, create posts, pin posts, or add public README links from
this document without operator approval.

## Current evidence

- Repository: `https://github.com/leonardsellem/hypermnesic`
- GitHub GraphQL reports `hasDiscussionsEnabled: false`.
- No repository discussions exist yet.
- The public docs truth pin remains `docs/README.md`.
- Remaining public-release gates currently tracked outside this issue:
  - LS-1682 / PR-13: custom GitHub Social preview upload and public unfurl check.
  - LS-1683 / PR-14: external MCP/awesome/Obsidian directory submissions.
  - LS-1684 / PR-15: PyPI go/no-go decision.
  - LS-1688 / PR-19: launch-window response SLO.
  - LS-1689 / PR-20: launch narrative and per-channel posts.
  - LS-1690 / PR-21: launch sequencing and retro.

## Decision recommendation

Use both surfaces:

- **GitHub Discussions** for the public welcome and roadmap threads.
- **Linear/Public release milestone and `docs/launch/`** for execution truth while
  the launch is still actively moving.

After the posts are live, update `README.md` and `docs/README.md` with their actual
URLs. Do not add placeholder links.

## Approval-gated setup checklist

1. Enable GitHub Discussions in repository settings.
2. Create or confirm these discussion categories:
   - `Announcements` for the pinned welcome.
   - `Ideas` or `General` for the pinned roadmap.
   - `Q&A` for support questions.
3. Post the welcome thread below.
4. Post the roadmap thread below.
5. Pin both threads.
6. Update `README.md` and `docs/README.md` with the live discussion URLs.
7. Re-run the full gate set and verify public links.

Pause before step 1 and before pinning. Enabling Discussions and pinning official
threads are externally visible repo-positioning actions.

## Draft welcome discussion

Suggested category: `Announcements`

Suggested title:

```text
Welcome to Hypermnesic
```

Suggested body:

```md
Hypermnesic is git-first memory for AI agents.

The core idea is simple:

- Markdown files are the source of truth.
- The retrieval index is disposable and rebuildable.
- Every write is a reviewable Git commit.
- One OAuth MCP endpoint can serve multiple clients.

Start here:

- README and quick start: https://github.com/leonardsellem/hypermnesic#quick-start
- Architecture: https://github.com/leonardsellem/hypermnesic/blob/main/ARCHITECTURE.md
- MCP tools: https://github.com/leonardsellem/hypermnesic/blob/main/docs/reference/mcp-tools.md
- CLI reference: https://github.com/leonardsellem/hypermnesic/blob/main/docs/reference/cli.md
- Obsidian companion: https://github.com/leonardsellem/hypermnesic-companion
- Benchmarks and caveats: https://github.com/leonardsellem/hypermnesic/blob/main/harness/BENCHMARKS.md

Good places to contribute:

- Setup friction and docs polish.
- MCP client compatibility reports.
- Obsidian companion UX feedback.
- Small issues labeled `good first issue`.
- Reproducible bugs with exact commands, config shape, and client name.

Please do not post secrets, bearer tokens, private vault content, or private hostnames.
If you need to report a vulnerability, use the process in SECURITY.md instead of a
public discussion.
```

## Draft roadmap discussion

Suggested category: `Ideas` or `General`

Suggested title:

```text
Public roadmap after v0.1.0
```

Suggested body:

```md
This is the public roadmap thread for Hypermnesic after v0.1.0.

The current release focus is not adding a large feature surface. It is making the
existing git-first memory loop easier to install, inspect, trust, and use from real
clients.

## Near term

- Finish repository presentation polish, including the custom GitHub Social preview.
- Submit the engine and companion to the relevant MCP, awesome-list, and Obsidian
  directories.
- Decide whether PyPI publication is worth the release-automation cost.
- Keep launch-week response times under 24 hours for new issues, discussions, and PRs.
- Draft and sequence launch posts only from evidence that is already green.

## Contribution funnel

- Keep `good first issue` tasks small and verifiable.
- Merge or explicitly triage the first external PR quickly.
- Prefer fixes that make setup, diagnostics, docs, or client compatibility clearer.

## Product direction

- Preserve the prime invariant: files are truth; the index is a rebuildable projection.
- Keep memory writes reviewable as commits.
- Keep the Obsidian companion read-only.
- Make degraded retrieval states visible rather than silent.
- Treat benchmarks as retrieval-quality evidence, not as a substitute for product
  readiness evidence.

## Not goals right now

- Hosted multi-tenant service.
- Private data in public examples.
- More client-specific adapters when native MCP/OAuth primitives are enough.
- Benchmark spending unless a specific release decision needs fresh numbers.

If you want to help, reply with the workflow you are trying to run, the client you use,
and the exact friction you hit.
```

## README/doc update after live posts

After both discussions are live and pinned, update:

- `README.md`: add a short "Community" bullet near the docs/links area with the live
  welcome and roadmap discussion URLs.
- `docs/README.md`: add the roadmap discussion URL as the public roadmap/community
  truth pin.

Do not add these links before the posts exist.

## Verification after approval-gated setup

- GitHub GraphQL reports `hasDiscussionsEnabled: true`.
- Welcome discussion URL exists and is pinned.
- Roadmap discussion URL exists and is pinned.
- `README.md` links both live URLs.
- `docs/README.md` links the roadmap/community truth URL.
- Full gate set passes after README/docs updates.
