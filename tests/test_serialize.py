"""U12 guard — protected-path denylist + within-repo + allowlist."""

from __future__ import annotations

import pytest

from hypermnesic import serialize


@pytest.mark.parametrize("bad", [
    ".git/config",
    "CLAUDE.md",
    "AGENTS.md",
    "projects/x/AGENTS.md",                 # nested instruction file
    ".github/workflows/ci.yml",             # foreign repo's CI
    ".obsidian/workspace.json",
    "scripts/evil.py",
    "bin/run",
    ".gitignore",
    "views/projects.yml",
    ".hypermnesic/index.db",
])
def test_protected_paths_refused(make_corpus, bad):
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    with pytest.raises(serialize.WriteGuardError):
        serialize.check(repo, bad)


@pytest.mark.parametrize("ok", [
    "notes/new-note.md",
    "concepts/idea.md",
    "projects/x/notes/thing.md",
])
def test_writable_paths_allowed(make_corpus, ok):
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    assert serialize.check(repo, ok) == ok


def test_traversal_and_absolute_refused(make_corpus):
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    with pytest.raises(serialize.WriteGuardError):
        serialize.check(repo, "../../etc/passwd")
    with pytest.raises(serialize.WriteGuardError):
        serialize.check(repo, "/etc/passwd")


def test_allowlist_enforced(make_corpus):
    repo = make_corpus({"a.md": "# A\n\nb\n"})
    assert serialize.check(repo, "notes/a.md", allowlist=["notes/"]) == "notes/a.md"
    with pytest.raises(serialize.WriteGuardError):
        serialize.check(repo, "concepts/a.md", allowlist=["notes/"])


def test_rule_generalizes_to_unseen_repo(make_corpus):
    # the denylist is a RULE, not a fixed gbrain list — holds for any repo
    repo = make_corpus({"README.md": "# r\n\nx\n"})
    for bad in ("CLAUDE.md", ".github/workflows/x.yml", "deep/nested/AGENTS.md"):
        with pytest.raises(serialize.WriteGuardError):
            serialize.check(repo, bad)
