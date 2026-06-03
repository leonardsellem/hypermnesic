"""U2 — pure folder-taxonomy derivation: index path set → bounded, sorted folder
entries (path, writable, protected_reason, recursive note count) under a sanitized
root/depth/effective-surface. No server, no git: a pure function over a path set."""

from __future__ import annotations

import pytest

from hypermnesic import folders, index


def _by_path(listing) -> dict:
    return {e["path"]: e for e in listing["folders"]}


def test_happy_path_top_level_counts_and_writable():
    paths = {"projects/acme/a.md", "projects/hermes/b.md", "people/x.md", "notes/n.md"}
    out = folders.derive_folders(paths, root="", depth=1, effective_surface=None,
                                 max_nodes=200, max_depth=6)
    by = _by_path(out)
    assert set(by) == {"projects/", "people/", "notes/"}        # top-level folders only
    assert by["projects/"]["note_count"] == 2                   # recursive count
    assert by["people/"]["note_count"] == 1 and by["notes/"]["note_count"] == 1
    assert all(e["writable"] and e["protected_reason"] is None for e in out["folders"])
    assert out["truncated"] is False and out["omitted"] == 0
    assert out["root"] == "" and out["depth"] == 1


def test_drill_down_lists_children_of_root():
    paths = {"projects/acme/a.md", "projects/hermes/b.md", "people/x.md"}
    out = folders.derive_folders(paths, root="projects/", depth=1, effective_surface=None,
                                 max_nodes=200, max_depth=6)
    by = _by_path(out)
    assert set(by) == {"projects/acme/", "projects/hermes/"}     # children of projects/ only
    assert by["projects/acme/"]["note_count"] == 1
    assert all(e["writable"] for e in out["folders"])
    assert out["root"] == "projects/"


def test_top_level_protected_folders_marked_non_writable():
    paths = {"scripts/r.md", "views/v.md", "notes/n.md"}
    out = folders.derive_folders(paths, root="", depth=1, effective_surface=None,
                                 max_nodes=200, max_depth=6)
    by = _by_path(out)
    assert by["scripts/"]["writable"] is False and "scripts/" in by["scripts/"]["protected_reason"]
    assert by["views/"]["writable"] is False and "views/" in by["views/"]["protected_reason"]
    assert by["notes/"]["writable"] is True                     # the writable one still appears


def test_nested_protected_folder_is_the_parity_lie_guard():
    # projects/ is writable but projects/scripts/ is NOT — commit_note refuses
    # projects/scripts/anything (parts[:-1] hits the protected 'scripts'). Probing a file
    # UNDER the folder (not the bare prefix) makes discovery agree with that refusal.
    paths = {"projects/scripts/x.md", "projects/acme/a.md"}
    out = folders.derive_folders(paths, root="projects/", depth=1, effective_surface=None,
                                 max_nodes=200, max_depth=6)
    by = _by_path(out)
    assert by["projects/scripts/"]["writable"] is False         # discovery agrees with the guard
    assert "scripts/" in by["projects/scripts/"]["protected_reason"]
    assert by["projects/acme/"]["writable"] is True
    # and projects/ itself (the parent) is writable at the top level
    top = _by_path(folders.derive_folders(paths, root="", depth=1, effective_surface=None,
                                          max_nodes=200, max_depth=6))
    assert top["projects/"]["writable"] is True


def test_recursive_count_does_not_bleed_into_sibling_prefix():
    paths = {"projects/a.md", "projects-archive/b.md"}
    by = _by_path(folders.derive_folders(paths, root="", depth=1, effective_surface=None,
                                         max_nodes=200, max_depth=6))
    assert set(by) == {"projects/", "projects-archive/"}
    assert by["projects/"]["note_count"] == 1                   # trailing-slash match, no bleed
    assert by["projects-archive/"]["note_count"] == 1


def test_depth_descends_multiple_levels_and_clamps():
    paths = {"projects/acme/sub/deep/a.md"}
    # depth=2 surfaces two levels under root
    out2 = folders.derive_folders(paths, root="", depth=2, effective_surface=None,
                                  max_nodes=200, max_depth=6)
    assert set(_by_path(out2)) == {"projects/", "projects/acme/"}
    # depth above the clamp is reduced; the echoed depth reflects the clamp
    out_clamped = folders.derive_folders(paths, root="", depth=99, effective_surface=None,
                                         max_nodes=200, max_depth=3)
    assert out_clamped["depth"] == 3
    assert set(_by_path(out_clamped)) == {"projects/", "projects/acme/", "projects/acme/sub/"}


def test_empty_root_lists_vault_root_folders_and_no_descendants_is_empty():
    paths = {"notes/n.md"}
    assert set(_by_path(folders.derive_folders(
        paths, root="", depth=1, effective_surface=None, max_nodes=200, max_depth=6))) == {"notes/"}
    # a root with no files under it → empty list (no error)
    empty = folders.derive_folders(paths, root="nope/", depth=1, effective_surface=None,
                                   max_nodes=200, max_depth=6)
    assert empty["folders"] == [] and empty["truncated"] is False


def test_bounding_sorts_before_cap_and_signals_truncation():
    paths = {f"folder{i:02d}/n.md" for i in range(5)}            # folder00..folder04
    out = folders.derive_folders(paths, root="", depth=1, effective_surface=None,
                                 max_nodes=3, max_depth=6)
    assert out["truncated"] is True and out["omitted"] == 2
    got = [e["path"] for e in out["folders"]]
    assert got == ["folder00/", "folder01/", "folder02/"]       # sorted, deterministic tail dropped
    assert len(got) == 3


def test_root_sanitization_rejects_traversal_and_absolute():
    paths = {"notes/n.md"}
    for bad in ("../etc", "../../secrets", "/etc/passwd", "projects/../../etc"):
        with pytest.raises(ValueError):
            folders.derive_folders(paths, root=bad, depth=1, effective_surface=None,
                                   max_nodes=200, max_depth=6)


def test_allowlist_surface_marks_outside_folders_non_writable():
    paths = {"notes/n.md", "projects/p.md"}
    by = _by_path(folders.derive_folders(paths, root="", depth=1, effective_surface=["notes/"],
                                         max_nodes=200, max_depth=6))
    assert by["notes/"]["writable"] is True and by["notes/"]["protected_reason"] is None
    assert by["projects/"]["writable"] is False
    assert by["projects/"]["protected_reason"] == "not in writable allowlist"


def test_index_derived_paths_never_surface_skip_dirs(make_corpus, fake_embedder):
    # AE5: the taxonomy is structurally limited to indexed markdown — .obsidian/ (a
    # skip dir) never reaches all_paths(), so it can never be discovered.
    repo = make_corpus({"notes/n.md": "# N\n\nbody.\n",
                        ".obsidian/workspace.json": "{}\n",
                        ".obsidian/plugins/x.md": "# x\n\nignored.\n"})
    index.build_index(repo, fake_embedder).close()
    idx = index.Index(index.state_dir_for(repo) / "index.db")
    out = folders.derive_folders(idx.all_paths(), root="", depth=2, effective_surface=None,
                                 max_nodes=200, max_depth=6)
    idx.close()
    assert all(not e["path"].startswith(".obsidian") for e in out["folders"])
    assert "notes/" in _by_path(out)                            # the real note folder is present
