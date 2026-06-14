---
title: "Launch-week response SLO"
status: active
audience: operator
linear: LS-1688
last_checked: 2026-06-14
---

# Launch-week response SLO

This is the PR-19 / LS-1688 operational checklist for the first two public weeks.
It defines what counts as a first-contact item, how to check the queue, and what
evidence to record before LS-1688 can move to Done.

## SLO

For the first two public weeks, every new external issue, pull request, and
discussion gets an operator response within 24 hours.

The first external pull request should be either:

- merged after pairing on required gates, or
- explicitly triaged with the next action and owner.

## What counts

Count items when the author is not the maintainer/operator account and the item is
not an automation-only event:

- GitHub issues in `leonardsellem/hypermnesic`
- GitHub pull requests in `leonardsellem/hypermnesic`
- GitHub Discussions in `leonardsellem/hypermnesic` after Discussions are enabled
- Security reports are handled through `SECURITY.md`, not public Discussions, but
  their first acknowledgement still belongs in the private-response SLO

Do not count maintainer-seeded `good first issue` / `help wanted` issues as
first-contact items.

## Check cadence

- Check twice daily during the first public week.
- Check daily during the second public week.
- Record each check as a Linear LS-1688 comment with:
  - timestamp,
  - issue/PR/discussion URLs reviewed,
  - oldest unresponded external item age,
  - first external PR state,
  - action taken or reason no action was required.

## Commands

```sh
gh issue list --repo leonardsellem/hypermnesic --state open --limit 100 \
  --json number,title,author,createdAt,updatedAt,comments,url,labels

gh pr list --repo leonardsellem/hypermnesic --state open --limit 100 \
  --json number,title,author,createdAt,updatedAt,comments,url,labels,isDraft

gh api graphql -f owner=leonardsellem -f repo=hypermnesic -f query='
query($owner:String!, $repo:String!) {
  repository(owner:$owner, name:$repo) {
    hasDiscussionsEnabled
    discussions(first:50, orderBy:{field:CREATED_AT, direction:DESC}) {
      totalCount
      nodes {
        number
        title
        createdAt
        updatedAt
        url
        author { login }
        comments { totalCount }
      }
    }
  }
}'
```

## Baseline on 2026-06-14

- Open issues: 10 maintainer-seeded contribution-funnel issues, all authored by
  `leonardsellem`:
  - #55 Relocate process-history docs into the docs taxonomy
  - #56 Add a docs-drift guard for the CLI reference
  - #57 Add a docs-drift guard for the MCP tools reference
  - #58 Document the legacy `/cloud` retirement path
  - #59 Add a LongMemEval cost-estimate dry run
  - #60 Add a no-spend LongMemEval smoke walkthrough
  - #61 Add one additional remote-client smoke template
  - #62 Add richer `doctor --json` examples to the CLI reference
  - #63 Document shell completion setup for the CLI
  - #64 Add a quick memory-routing decision table to plugin docs
- Open PRs: none.
- Discussions: disabled (`hasDiscussionsEnabled: false`), total discussions `0`.
- External first-contact items older than 24 hours: `0`.
- First external PR: none yet.

## Completion evidence

LS-1688 can move to Done only after the launch-window check log proves:

- no external first-contact item exceeded 24 hours without a response, and
- the first external PR was merged or explicitly triaged.
