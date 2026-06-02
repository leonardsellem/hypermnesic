"""U18 — review-gated proposal/PR queue: the one front door for organizing writes.
[R11/R10/F5/KD7/#12]

Every generated artifact (sidecars, digests, connection nudges, MOCs, capture
triage) is emitted by ``propose()`` as a narrow, path-scoped, gate-checked commit
on a ``hypermnesic/proposals/<slug>`` branch and surfaced as a GitHub PR the owner
approves — **never auto-merged, never a silent write**. This is *structural*
(R11+R10+KD7), not agent politeness.

It reuses the kernel's safety surface — the protected-path guard + allowlist
(``serialize.check``), the diff-or-die frontmatter gate (``frontmatter_gate``),
the worktree-isolated commit posture (``serialize.branch_commit_transaction``,
modelled on ``index.reindex_isolated``), and the append-only audit log — rather
than inventing a parallel write path.

Two tiers (KTD1):
  - **immutable free-append** zones (``sources/``-style, config path-prefix): a
    NEW file is committed straight to HEAD (no proposal friction — U24 capture);
    never an overwrite, never a curated path.
  - **curated**: every other change is gated, branched, and PR'd.

A **global proposal budget** bounds the cold-start PR flood (Risk R-1): the cap is
charged only when a real proposal branch is created.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from hypermnesic import commit_note as cn
from hypermnesic import config, serialize
from hypermnesic import frontmatter_gate as fg

_PROPOSAL_PREFIX = "hypermnesic/proposals/"
_SLUG_MAX = 60


class BudgetExceededError(Exception):
    """Raised when a run would exceed the global proposal budget (R-1)."""


@dataclass
class Change:
    """One path-scoped change in a (possibly multi-file) proposal."""

    path: str
    body: str | None = None
    set_fields: dict | None = None


@dataclass
class ProposalResult:
    slug: str
    branch: str | None
    base_branch: str
    files: list[str]
    commit_sha: str | None
    pr_url: str | None
    pr_skipped: bool
    diff: str
    fast_path: bool = False
    noop: bool = False


# --- slug sanitisation (security) ---------------------------------------------

def safe_slug(title: str) -> str:
    """Derive a safe branch slug from a caller-supplied title.

    Alphanumeric + ``-_/`` only; never starts with ``-`` or ``/``; no ``..``; and
    length-bounded — so a title can't inject a git option or ref traversal into the
    ``git branch`` / ``gh`` calls. Falls back to ``proposal`` for empty input.
    """
    s = title.strip().lower().replace(" ", "-")
    s = s.replace("..", "")                       # kill traversal before charset filter
    s = re.sub(r"[^a-z0-9\-_/]", "", s)           # allowed charset only
    s = re.sub(r"/{2,}", "/", s).strip("-/")      # no empty segments, no leading/trailing -/
    s = s[:_SLUG_MAX].rstrip("-/")
    return s or "proposal"


class ProposalBudget:
    """A persisted per-cycle cap on proposal-branch creation (Risk R-1).

    A "cycle" defaults to a UTC calendar day; ``charge`` rolls the counter over on
    a new cycle. The cap is global across all U18 callers in a run-cycle so a
    cold-start burst can't flood the owner's PR queue (which would decay
    review-gating into de-facto auto-merge — the exact KD7/R10 failure)."""

    def __init__(self, state_path, max_per_cycle: int, cycle_fn=None):
        self.path = Path(state_path)
        self.max = max_per_cycle
        self._cycle_fn = cycle_fn or (lambda: datetime.now(UTC).date().isoformat())

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {"cycle": self._cycle_fn(), "count": 0}

    def remaining(self) -> int:
        st = self._load()
        if st.get("cycle") != self._cycle_fn():
            return self.max
        return max(0, self.max - st.get("count", 0))

    def charge(self, n: int = 1) -> None:
        cyc = self._cycle_fn()
        st = self._load()
        if st.get("cycle") != cyc:
            st = {"cycle": cyc, "count": 0}
        if st["count"] + n > self.max:
            raise BudgetExceededError(
                f"proposal budget exhausted ({st['count']}/{self.max} this cycle)")
        st["count"] += n
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(st), encoding="utf-8")


# --- git helpers --------------------------------------------------------------

def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _head_content(repo, rel: str) -> str:
    """Committed content of ``rel`` at HEAD, or "" if it does not exist there."""
    r = _git(repo, "show", f"HEAD:{rel}")
    return r.stdout if r.returncode == 0 else ""


def _exists_at_head(repo, rel: str) -> bool:
    return _git(repo, "cat-file", "-e", f"HEAD:{rel}").returncode == 0


def _base_branch(repo) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "HEAD"


def _render_new(set_fields: dict, body: str) -> str:
    if not set_fields:
        return body
    buf = StringIO()
    fg._yaml().dump(dict(set_fields), buf)
    return "---\n" + buf.getvalue() + "---\n" + body


def _gate_change(repo, rel: str, change: Change) -> str:
    """Compute the new file text for ``change`` against committed HEAD content,
    enforcing diff-or-die. Raises (no branch created) on unrequested drift."""
    original = _head_content(repo, rel)
    if original == "" and not _exists_at_head(repo, rel):
        return _render_new(change.set_fields or {}, change.body or "")
    return fg.gated_edit(original, body=change.body, set_fields=change.set_fields)


# --- proposal ledger (idempotency + gh resume) --------------------------------

def _ledger_path(repo) -> Path:
    return Path(repo) / ".hypermnesic" / "proposals.json"


def _load_ledger(repo) -> dict:
    try:
        return json.loads(_ledger_path(repo).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _save_ledger(repo, ledger: dict) -> None:
    p = _ledger_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def _pr_body(summary: str, why: str, source: str) -> str:
    return (f"## What\n\n{summary}\n\n"
            f"## Why\n\n{why or '(not stated)'}\n\n"
            f"## Source\n\n{source or '(not stated)'}\n")


def _default_gh_create(*, title: str, body: str, branch: str, base: str) -> str | None:
    """Create a PR via the ``gh`` CLI if it is on PATH, else return None (skipped).

    The body carries what/why/source only — never a credential (the gh token lives
    in the env under the OPENAI_API_KEY-style discipline and is never echoed)."""
    if shutil.which("gh") is None:
        return None
    r = subprocess.run(
        ["gh", "pr", "create", "--head", branch, "--base", base,
         "--title", title, "--body", body],
        capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


# --- the front door -----------------------------------------------------------

def propose(repo, changes, *, slug: str, summary: str, why: str = "", source: str = "",
            allowlist: list[str], idx=None, log=None,
            budget: ProposalBudget | None = None, gh_create=_default_gh_create
            ) -> ProposalResult:
    """Turn a set of path-scoped changes into a review-gated proposal.

    ``allowlist`` is REQUIRED (security): the proposal's declared target scope is
    passed explicitly to the guard so a change can't reach outside it. ``gh_create``
    is the PR-creation hook — pass ``None`` to force the gh-unavailable path (local
    branch + diff, PR skipped, resumable later). The agent NEVER merges.
    """
    repo = Path(repo)
    slug = safe_slug(slug)
    changes = [c if isinstance(c, Change) else Change(**c) for c in changes]

    # Guard + allowlist FIRST, for every path, before any branch exists (R17).
    rels = [serialize.check(repo, c.path, allowlist=allowlist) for c in changes]

    # Routing: a fast-path proposal is one where EVERY change is a new file in an
    # immutable free-append zone. A curated path can never reach the fast path.
    fast = all(config.is_immutable_append_zone(rel) and not _exists_at_head(repo, rel)
               for rel in rels)
    if fast:
        return _free_append(repo, changes, rels, summary, idx, log, allowlist)

    base_branch = _base_branch(repo)
    base_head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Gate every file IN MEMORY first → multi-file atomicity: any abort raises here,
    # before a branch is created, so no partial/orphan branch is ever left behind.
    contents = {rel: _gate_change(repo, rel, c) for rel, c in zip(rels, changes, strict=True)}

    if all(contents[rel] == _head_content(repo, rel) for rel in rels):
        return ProposalResult(slug, None, base_branch, rels, base_head, None,
                              pr_skipped=False, diff="", noop=True)

    branch = _PROPOSAL_PREFIX + slug
    ledger = _load_ledger(repo)
    existing = serialize._local_branches(repo)
    title = summary
    body = _pr_body(summary, why, source)

    if branch in existing:
        return _reconcile_existing(repo, ledger, slug, branch, base_branch, rels,
                                   title, body, gh_create)

    if budget is not None:
        budget.charge(1)                                    # only a real branch is charged

    msg = f"propose: {summary}"
    commit_sha = serialize.branch_commit_transaction(repo, branch, base_head, contents, msg)
    diff = _git(repo, "show", "--format=", "--patch", commit_sha).stdout

    pr_url = gh_create(title=title, body=body, branch=branch, base=base_branch) \
        if gh_create is not None else None
    pr_skipped = pr_url is None

    ledger[slug] = {"branch": branch, "commit": commit_sha, "pr_url": pr_url}
    _save_ledger(repo, ledger)

    if log is not None:
        log.append(verb="propose", path=",".join(rels), old_sha=base_head,
                   new_sha=commit_sha, summary=summary)

    return ProposalResult(slug, branch, base_branch, rels, commit_sha, pr_url,
                          pr_skipped=pr_skipped, diff=diff)


def _reconcile_existing(repo, ledger, slug, branch, base_branch, rels, title, body,
                        gh_create) -> ProposalResult:
    """Branch already exists. Identical content → idempotent no-op; if the PR was
    skipped earlier (orphan branch) and gh is now available, resume PR creation."""
    entry = ledger.get(slug, {"branch": branch, "commit": None, "pr_url": None})
    commit_sha = _git(repo, "rev-parse", branch).stdout.strip()
    if entry.get("pr_url"):                                  # already fully proposed
        return ProposalResult(slug, branch, base_branch, rels, commit_sha,
                              entry["pr_url"], pr_skipped=False, diff="", noop=True)
    pr_url = gh_create(title=title, body=body, branch=branch, base=base_branch) \
        if gh_create is not None else None
    if pr_url is not None:                                   # resumed PR for orphan branch
        entry.update({"branch": branch, "commit": commit_sha, "pr_url": pr_url})
        ledger[slug] = entry
        _save_ledger(repo, ledger)
        return ProposalResult(slug, branch, base_branch, rels, commit_sha, pr_url,
                              pr_skipped=False, diff="", noop=False)
    ledger[slug] = {"branch": branch, "commit": commit_sha, "pr_url": None}
    _save_ledger(repo, ledger)
    return ProposalResult(slug, branch, base_branch, rels, commit_sha, None,
                          pr_skipped=True, diff="", noop=True)


def _free_append(repo, changes, rels, summary, idx, log, allowlist) -> ProposalResult:
    """Immutable-zone fast path: commit new file(s) straight to HEAD (KTD1/U24)."""
    shas, diffs = [], []
    for rel, c in zip(rels, changes, strict=True):
        r = cn.commit_note(repo, rel, body=c.body, set_fields=c.set_fields,
                           summary=summary, idx=idx, log=log, allowlist=allowlist)
        shas.append(r.new_sha)
        diffs.append(r.diff)
    return ProposalResult(safe_slug(summary), None, _base_branch(repo), rels,
                          shas[-1] if shas else None, None, pr_skipped=False,
                          diff="".join(diffs), fast_path=True)
