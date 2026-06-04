from __future__ import annotations

import json
import subprocess

import pytest

from hypermnesic import index
from hypermnesic.local_proof import LocalProofError, run_local_proof


def _head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def _init_empty_repo(path):
    path.mkdir()
    subprocess.run(["git", "-C", str(path), "init", "-q", "-b", "main"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.t"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "--allow-empty", "-q", "-m", "empty"],
                   check=True, capture_output=True)
    return path


def test_demo_local_proof_creates_git_vault_and_retrieves_source(tmp_path):
    demo = tmp_path / "demo-vault"
    result = run_local_proof(demo_dir=demo)
    out = result.as_dict()

    assert out["status"] == "local_memory_works"
    assert out["mode"] == "demo"
    assert out["source_path"] == "memory/local-proof-memory.md"
    assert out["retrieval"]["hit"]["path"] == "memory/local-proof-memory.md"
    assert out["write_preview"]["dry_run"] is True
    assert out["write_preview"]["destination"] == "memory/local-proof-preview.md"
    assert "local proof preview" in out["write_preview"]["diff"]
    assert out["index"]["state_path"] == ".hypermnesic/index.db"
    assert out["files_are_source_of_truth"] is True
    assert (demo / ".git").exists()
    assert _head(demo)


def test_existing_vault_local_proof_is_read_only_by_default(make_corpus):
    repo = make_corpus({
        "notes/alpha.md": (
            "# Alpha\n\n"
            "Question answered: what should Hypermnesic remember about alpha\n\n"
            "Hypermnesic remembers alpha from a plain markdown file.\n"
        )
    })
    head = _head(repo)

    result = run_local_proof(repo=repo, query="what should Hypermnesic remember about alpha")
    out = result.as_dict()

    assert out["status"] == "local_memory_works"
    assert out["mode"] == "existing"
    assert out["source_path"] == "notes/alpha.md"
    assert _head(repo) == head
    assert not (repo / "memory" / "local-proof-preview.md").exists()


def test_existing_vault_without_query_identifies_a_memory(make_corpus):
    repo = make_corpus({
        "notes/alpha.md": (
            "# Alpha\n\n"
            "Question answered: what should Hypermnesic remember about auto query\n\n"
            "The proof can identify a usable local memory without sample writes.\n"
        )
    })

    out = run_local_proof(repo=repo).as_dict()

    assert out["status"] == "local_memory_works"
    assert out["retrieval"]["question"] == "what should Hypermnesic remember about auto query"
    assert out["source_path"] == "notes/alpha.md"


def test_existing_vault_empty_without_seed_fails_without_writing(tmp_path):
    repo = _init_empty_repo(tmp_path / "empty-vault")
    head = _head(repo)

    with pytest.raises(LocalProofError) as excinfo:
        run_local_proof(repo=repo, query="what should Hypermnesic remember about alpha")

    err = excinfo.value.as_dict()
    assert err["status"] == "needs_action"
    assert err["error"]["code"] == "no_retrieval_hit"
    assert "add a markdown note" in err["next_action"].lower()
    assert _head(repo) == head
    assert list(repo.glob("**/*.md")) == []


def test_non_git_existing_vault_is_refused_before_writes(tmp_path):
    repo = tmp_path / "not-git"
    repo.mkdir()

    with pytest.raises(LocalProofError) as excinfo:
        run_local_proof(repo=repo)

    assert excinfo.value.as_dict()["error"]["code"] == "not_git_repo"
    assert list(repo.iterdir()) == []


def test_local_proof_lexical_degradation_is_product_language(make_corpus):
    repo = make_corpus({
        "notes/local.md": (
            "# Local\n\n"
            "Question answered: what should Hypermnesic remember about lexical proof\n\n"
            "Lexical recall still finds this source-grounded note.\n"
        )
    })

    out = run_local_proof(
        repo=repo,
        query="what should Hypermnesic remember about lexical proof",
        embedder=None,
    ).as_dict()

    assert out["degraded_capabilities"]["degraded_lexical_only"] is True
    assert "still works from exact text" in out["degraded_capabilities"]["message"]
    assert "embeddings improve ranking" in out["degraded_capabilities"]["message"]


def test_local_proof_dense_enabled_path_is_not_marked_degraded(make_corpus, fake_embedder):
    repo = make_corpus({
        "notes/dense.md": (
            "# Dense\n\n"
            "Question answered: what should Hypermnesic remember about dense proof\n\n"
            "Dense recall is enabled for this proof.\n"
        )
    })

    out = run_local_proof(
        repo=repo,
        query="what should Hypermnesic remember about dense proof",
        embedder=fake_embedder,
    ).as_dict()

    assert out["degraded_capabilities"]["degraded_lexical_only"] is False
    assert "dense" in out["retrieval"]["hit"]["channels"]


def test_local_proof_protected_preview_is_refused_without_commit(make_corpus):
    repo = make_corpus({
        "notes/source.md": (
            "# Source\n\n"
            "Question answered: what should Hypermnesic remember about protected preview\n\n"
            "This source proves retrieval before the preview refusal.\n"
        )
    })
    head = _head(repo)

    with pytest.raises(LocalProofError) as excinfo:
        run_local_proof(
            repo=repo,
            query="what should Hypermnesic remember about protected preview",
            preview_path="AGENTS.md",
        )

    err = excinfo.value.as_dict()
    assert err["error"]["code"] == "write_preview_refused"
    assert _head(repo) == head


def test_local_proof_uses_repo_relative_paths_only(make_corpus):
    repo = make_corpus({
        "notes/source.md": (
            "# Source\n\n"
            "Question answered: what should Hypermnesic remember about relative paths\n\n"
            "Only repo-relative paths should leave the proof contract.\n"
        )
    })

    text = str(run_local_proof(
        repo=repo,
        query="what should Hypermnesic remember about relative paths",
    ).as_dict())

    assert str(repo) not in text
    assert "notes/source.md" in text
    assert ".hypermnesic/index.db" in text


def test_local_proof_redacts_secret_like_values_from_snippet(make_corpus):
    bearer = "Bearer " + "abc.def.ghi"
    api_key = "sk-" + "abcdefghijklmnopqrst"
    operator_path = "/home/" + "ubuntu/private-vault"
    repo = make_corpus({
        "notes/secretish.md": (
            "# Secretish\n\n"
            "Question answered: what should Hypermnesic remember about redaction\n\n"
            f"{bearer} and {api_key} should not leave the proof. "
            f"A local path {operator_path} should not leave it either.\n"
        )
    })

    out = run_local_proof(
        repo=repo,
        query="what should Hypermnesic remember about redaction",
    ).as_dict()
    text = json.dumps(out)

    assert bearer not in text
    assert api_key not in text
    assert operator_path not in text
    assert "[redacted-token]" in text
    assert "[redacted-path]" in text


def test_local_proof_reuses_existing_index_primitives(make_corpus):
    repo = make_corpus({
        "notes/source.md": (
            "# Source\n\n"
            "Question answered: what should Hypermnesic remember about index projection\n\n"
            "The disposable index projects committed markdown files.\n"
        )
    })

    run_local_proof(repo=repo, query="what should Hypermnesic remember about index projection")
    idx = index.Index(index.state_dir_for(repo) / "index.db")
    try:
        assert "notes/source.md" in idx.all_paths()
    finally:
        idx.close()
