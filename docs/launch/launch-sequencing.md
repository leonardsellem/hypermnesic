---
title: "Launch sequencing"
status: prepared
audience: operator
linear: LS-1690
last_checked: 2026-06-14
---

# Launch sequencing

This is the PR-21 / LS-1690 sequencing plan. It orders the public launch channels,
ties each post to the approved LS-1689 drafts, and names the evidence to record.

Do not post externally without operator approval.

## Preconditions

- PR-10 repository visibility is public.
- PR-12 `v0.1.0` release exists.
- PR-20 launch drafts are staged in `docs/launch/launch-narrative-drafts.md`.
- PR-19 response SLO is active in `docs/launch/launch-week-response-slo.md`.
- Any channel-specific copy edits are approved before posting.

## Sequence

| Order | Channel | Draft source | Timing | Evidence to record |
|---|---|---|---|---|
| 1 | Show HN | `docs/launch/launch-narrative-drafts.md` | Day 0, first public post | HN item URL, first reply timestamp, notable questions |
| 2 | X / Bluesky | same | Day 0 after HN | thread URL(s), first reply timestamp |
| 3 | r/selfhosted | same | Day 1 | Reddit URL, moderation status, first reply timestamp |
| 4 | r/ObsidianMD | same | Day 1 or after companion submission opens | Reddit URL, moderation status, companion questions |
| 5 | r/LocalLLaMA | same | Day 2 | Reddit URL, moderation status, benchmark questions |
| 6 | MCP community Discord | same | Day 2 or after registry submission opens | message link if available, server/channel, first reply timestamp |
| 7 | Directory updates | `docs/launch/directory-submission-prep.md` | As reviews progress | registry/listing/submission URLs |

## Response loop

For each posted channel:

1. Add the post URL to LS-1689 and LS-1690.
2. Run the LS-1688 queue check after posting and again within 24 hours.
3. Answer correction-worthy questions with source links, not speculation.
4. If a draft claim is challenged and evidence is weaker than expected, update the
   launch draft or docs before reusing the claim elsewhere.
5. Keep benchmark answers within the published comparability envelope.

## Stop conditions

Pause the sequence if any of these happen:

- a security report arrives;
- a preflight/public-surface issue is found;
- a benchmark claim is shown to be misleading;
- a setup path fails for a real external user and cannot be answered from docs;
- the response SLO has an unresponded external first-contact item near 24 hours.

## Completion criteria

LS-1690 can move to Done only after:

- all approved channels are posted in the recorded sequence;
- LS-1688 response checks cover the active launch window;
- a retro note is written under `docs/reports/`;
- the full gate set passes for the retro PR.
