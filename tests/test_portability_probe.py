"""U6 — zero-infra portability probe, offline fixtures."""

from __future__ import annotations

import subprocess

import portability_probe as pp

from hypermnesic import index, retrieve

MD = {
    "fr.md": "# Parité\n\nLe rappel français doit égaler gbrain. Voir [[net]].\n",
    "en.md": "# Hetzner\n\nHomelab migration to Hetzner. Links to [[net]].\n",
    "net.md": "# net\n\nNetwork topology. See [[Hetzner]] and [[Parité]].\n",
}


def _commit(repo, msg="x"):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg],
                   check=True, capture_output=True)


def test_markdown_corpus_probe_passes(make_corpus, fake_embedder):
    repo = make_corpus(MD)
    r = pp.probe_repo(repo, fake_embedder, kind="markdown",
                      queries=["Hetzner", "rappel français"])
    assert r["builds"] is True
    assert r["answers"] is True
    assert r["tracked_unchanged"] is True
    assert r["git_clean_after_init"] is True
    assert r["zero_setup"] is True
    assert r["passed"] is True


def test_probe_grade_has_structured_fields(make_corpus, fake_embedder):
    repo = make_corpus(MD)
    r = pp.probe_repo(repo, fake_embedder, kind="markdown", queries=["Hetzner"])
    for field in ("builds", "answers", "zero_setup", "tracked_unchanged", "passed"):
        assert field in r


def test_markdown_corpus_returns_useful_results(make_corpus, fake_embedder):
    # not just a structurally-valid empty answer — the right page comes back
    repo = make_corpus(MD)
    idx = index.build_index(repo, fake_embedder)
    res = retrieve.search(idx, "Hetzner", embedder=fake_embedder, k=3)
    assert any(h.path == "en.md" for h in res.hits)
    from hypermnesic import graph
    g = graph.Graph.from_index(idx)
    assert "net.md" in graph.build_context(g, "en.md", depth=1)
    idx.close()


def test_coding_repo_with_binary_and_no_wikilinks(make_corpus, fake_embedder):
    # a coding repo: a README with no wikilinks + a committed binary file.
    repo = make_corpus({"README.md": "# tool\n\nA CLI tool. No wikilinks here.\n"})
    (repo / "logo.png").write_bytes(bytes(range(256)) * 8)  # binary
    (repo / "main.py").write_text("print('hello')\n", encoding="utf-8")  # non-md, skipped
    _commit(repo, "add binary + code")
    r = pp.probe_repo(repo, fake_embedder, kind="coding", queries=["CLI tool"])
    assert r["builds"] is True            # only README.md indexed; binary/code skipped
    assert r["answers"] is True           # degrades to lexical+dense on no-wikilink md
    assert r["tracked_unchanged"] is True
    assert r["passed"] is True


def test_tracked_files_unchanged_and_state_ignored(make_corpus, fake_embedder):
    repo = make_corpus(MD)
    before = pp._tracked_file_hashes(repo)
    index.build_index(repo, fake_embedder).close()
    after = pp._tracked_file_hashes(repo)
    assert before == after
    assert (repo / ".hypermnesic" / "index.db").exists()
    # excluded via .git/info/exclude → git stays clean (state dir is invisible)
    assert ".hypermnesic" not in pp._git_status_porcelain(repo)
    assert (repo / ".gitignore").exists() is False  # we never created/modified one


def test_run_probe_requires_both_kinds(make_corpus, fake_embedder):
    md = make_corpus(MD)
    code = make_corpus({"README.md": "# c\n\ncode repo readme\n"})
    only_md = pp.run_probe([{"path": str(md), "kind": "markdown", "queries": ["Hetzner"]}],
                           fake_embedder)
    assert only_md["passed"] is False     # missing the coding kind
    both = pp.run_probe([
        {"path": str(md), "kind": "markdown", "queries": ["Hetzner"]},
        {"path": str(code), "kind": "coding", "queries": ["code"]},
    ], fake_embedder)
    assert both["passed"] is True
    assert sorted(both["covered_kinds"]) == ["coding", "markdown"]
