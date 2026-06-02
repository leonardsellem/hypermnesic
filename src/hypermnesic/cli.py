"""hypermnesic command-line entrypoint.

Mirrors the vault tooling convention: a standalone ``main()`` with ``argparse``
subcommands and ``--json`` (``ensure_ascii=False``) output. Credential values are
never echoed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hypermnesic import __version__


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _cmd_index(args) -> int:
    from hypermnesic import embed, index

    embed.smoke_embed_or_die()  # fail loud before any indexing work
    embedder = embed.OpenAIEmbedder()
    state_dir = Path(args.state_dir) if args.state_dir else None
    idx = index.build_index(Path(args.repo), embedder, rebuild=not args.no_rebuild,
                            state_dir=state_dir)
    stats = idx.stats()
    idx.close()
    if args.json:
        _print_json(stats)
    else:
        print(f"Indexed {stats['chunks']} chunks across {stats['docs']} docs "
              f"(model={stats['model']} dim={stats['dim']} checkpoint={stats['checkpoint']})")
    return 0


def _cmd_embed(args) -> int:
    """Async embed-stale pass: fill dense vectors that lag lexical (AE5)."""
    from hypermnesic import embed, index

    embed.smoke_embed_or_die()  # fail loud before touching the index
    db = Path(args.index_db) if args.index_db else index.state_dir_for(Path(args.repo)) / "index.db"
    idx = index.Index(db)
    res = index.embed_stale(idx, Path(args.repo), embed.OpenAIEmbedder())
    idx.close()
    if args.json:
        _print_json(res)
    else:
        print(f"embedded {res['chunks_embedded']} stale chunks, "
              f"{res['docs_embedded']} doc surfaces")
    return 0


def _cmd_commit_note(args) -> int:
    """Preview what a commit_note write would do (dry-run; read-only)."""
    from hypermnesic import commit_note as cn

    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    r = cn.commit_note(Path(args.repo), args.path, body=body, summary=args.summary,
                       dry_run=True)
    if args.json:
        _print_json({"path": r.path, "created": r.created, "noop": r.noop, "diff": r.diff})
    else:
        print(r.diff or "(no change)")
    return 0


def _cmd_reindex(args) -> int:
    """Broad reindex; --isolated builds in a worktree and swaps atomically (U14)."""
    from hypermnesic import embed, index

    embed.smoke_embed_or_die()
    embedder = embed.OpenAIEmbedder()
    state_dir = Path(args.state_dir) if args.state_dir else None
    if args.isolated:
        res = index.reindex_isolated(Path(args.repo), embedder, state_dir=state_dir)
    else:
        index.build_index(Path(args.repo), embedder, state_dir=state_dir).close()
        res = {"status": "rebuilt-inplace"}
    _print_json(res) if args.json else print(res["status"])
    return 0


def _cmd_init(args) -> int:
    """Zero-infra drop-in: index a repo in place (in-repo .hypermnesic/ state)."""
    from hypermnesic import embed, index

    embed.smoke_embed_or_die()
    embedder = embed.OpenAIEmbedder()
    idx = index.build_index(Path(args.repo), embedder, rebuild=not args.no_rebuild)
    stats = idx.stats()
    idx.close()
    if args.json:
        _print_json(stats)
    else:
        print(f"initialized hypermnesic for {args.repo}: "
              f"{stats['chunks']} chunks / {stats['docs']} docs "
              f"(state in {index.state_dir_for(Path(args.repo))})")
    return 0


def _cmd_think(args) -> int:
    """Thinking-mode (read-only): related notes + Socratic prompts, never writes."""
    from hypermnesic import converge as converge_mod
    from hypermnesic import graph as graph_mod
    from hypermnesic import index, think

    db = Path(args.index_db) if args.index_db else index.state_dir_for(Path(args.repo)) / "index.db"
    idx = index.Index(db)
    try:  # dense channel is optional — degrade to lexical+graph if no key (same as the server)
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder()
    except Exception:
        embedder = None
    converge_mod.converge(Path(args.repo), idx, embedder)   # catch up before reading (U28)
    g = graph_mod.Graph.from_index(idx)                     # graph after convergence
    r = think.think(idx, args.topic, embedder=embedder, graph=g, k=args.k)
    idx.close()
    if args.json:
        _print_json(r.as_dict())
    else:
        print(f"# thinking about: {r.topic}  (wrote={r.wrote})")
        for h in r.related:
            print(f"  - {h['path']}: {h['heading']}")
        for q in r.questions + r.tensions:
            print(f"  ? {q}")
        if r.note:
            print(f"  ({r.note})")
    return 0


def _cmd_retrieve(args) -> int:
    """Hybrid retrieve (read-only): converge first, then search — the CLI twin of
    the MCP ``search`` tool (same hit shape). Degrades to lexical if no key."""
    from hypermnesic import converge as converge_mod
    from hypermnesic import index, retrieve

    db = Path(args.index_db) if args.index_db else index.state_dir_for(Path(args.repo)) / "index.db"
    idx = index.Index(db)
    try:  # dense channel optional — same graceful degradation as `think` / the server
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder()
    except Exception:
        embedder = None
    converge_mod.converge(Path(args.repo), idx, embedder)   # catch up before reading (U28)
    res = retrieve.search(idx, args.query, embedder=embedder, k=args.k,
                          recency_fn=retrieve.git_commit_recency(Path(args.repo)))
    idx.close()
    out = {
        "query": args.query,
        "degraded_lexical_only": res.degraded,
        "hits": [
            {"path": h.path, "heading": h.heading, "score": round(h.score, 6),
             "channels": sorted(h.channels), "snippet": h.text[:280], "recency": h.recency}
            for h in res.hits
        ],
    }
    if args.json:
        _print_json(out)
    else:
        print(f"# retrieve: {args.query}  (degraded={res.degraded})")
        for h in out["hits"]:
            print(f"  - {h['path']}: {h['heading']}  ({h['score']})")
    return 0


def _cmd_capture(args) -> int:
    """Frictionless capture: land raw text in sources/ immediately (free-append)."""
    from hypermnesic import capture, index

    db = index.state_dir_for(Path(args.repo)) / "index.db"
    idx = index.Index(db) if db.exists() else None
    res = capture.capture(Path(args.repo), args.text, idx=idx)
    if idx is not None:
        idx.close()
    out = {"fast_path": res.fast_path, "files": res.files, "commit": res.commit_sha}
    if args.json:
        _print_json(out)
    else:
        print(f"captured → {res.files[0]} (committed)")
    return 0


def _cmd_converge(args) -> int:
    """Pre-warm: catch the index up to HEAD + a bounded dense fill (U27). The
    post-merge hook's entrypoint; also a manual warm. Lazy read-time convergence
    is the correctness guarantee — this never fails a pull (no index → clean no-op)."""
    from hypermnesic import converge as converge_mod
    from hypermnesic import index

    db = Path(args.index_db) if args.index_db else index.state_dir_for(Path(args.repo)) / "index.db"
    if not db.exists():
        out = {"status": "no-index"}
        _print_json(out) if args.json else print("no index yet — run `hypermnesic init` first")
        return 0
    idx = index.Index(db)
    try:  # dense optional — degrade to lexical catch-up if no key (same as the server)
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder()
    except Exception:
        embedder = None
    res = converge_mod.converge(Path(args.repo), idx, embedder,
                                authoring_host=args.authoring_host)
    idx.close()
    if args.json:
        _print_json(res.as_dict())
    else:
        print(f"converged: {res.status} (replayed={res.replayed}, "
              f"embedded={res.chunks_embedded}, degraded={res.degraded})")
    return 0


def _cmd_install_hooks(args) -> int:
    """Opt-in: install (or uninstall) the post-merge convergence hook. Idempotent,
    non-destructive (managed block), uninstall removes only the managed block."""
    from hypermnesic import install

    res = (install.uninstall_hooks(Path(args.repo)) if args.uninstall
           else install.install_hooks(Path(args.repo)))
    action = "uninstalled" if args.uninstall else "installed"
    if args.json:
        _print_json({"action": action, **res})
    else:
        print(f"{action} convergence hook(s): {res}")
    return 0


def _cmd_serve(args) -> int:
    from hypermnesic import mcp_server

    srv = mcp_server.build_server(Path(args.index_db), host=args.host,
                                  port=args.port, path=args.path,
                                  write_enabled=args.enable_write)
    srv.run(transport="streamable-http")
    return 0


def _cmd_install(args) -> int:
    """Provision a host into a role (single|master|client) — render artifacts,
    write role config, install the convergence hook. Live service start + index
    build are returned as manual steps (host-specific; never run from a unit test)."""
    from hypermnesic import install

    try:
        res = install.install(
            args.role, repo=(Path(args.repo) if args.repo else None),
            bind=args.bind, port=args.port, path=args.path, service=args.service,
            master_url=args.master_url, mcp_config_path=args.mcp_config)
    except install.InstallError as exc:
        print(f"install failed: {exc}", file=sys.stderr)   # fail loud; nothing provisioned
        return 1
    if args.json:
        _print_json(res)
    else:
        print(f"installed role={res['role']}")
        for a in res.get("artifacts", []):
            print(f"  wrote {a}")
        for s in res.get("manual_steps", []):
            print(f"  next: {s}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hypermnesic", description="hypermnesic CLI")
    parser.add_argument("--version", action="version", version=f"hypermnesic {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_index = sub.add_parser("index", help="build the read-only index over a repo")
    p_index.add_argument("repo", help="path to the repo/corpus to index")
    p_index.add_argument("--state-dir", default=None,
                         help="external state dir (keeps the corpus untouched)")
    p_index.add_argument("--no-rebuild", action="store_true",
                         help="do not delete an existing index first")
    p_index.add_argument("--json", action="store_true")
    p_index.set_defaults(func=_cmd_index)

    p_embed = sub.add_parser("embed", help="async embed pass: fill dense vectors that lag lexical")
    p_embed.add_argument("repo", help="repo whose files supply doc surfaces")
    p_embed.add_argument("--index-db", default=None, help="index db (default: <repo>/.hypermnesic)")
    p_embed.add_argument("--json", action="store_true")
    p_embed.set_defaults(func=_cmd_embed)

    p_cn = sub.add_parser("commit-note", help="preview a commit_note write (dry-run, read-only)")
    p_cn.add_argument("repo")
    p_cn.add_argument("path", help="repo-relative note path")
    p_cn.add_argument("--body", default=None)
    p_cn.add_argument("--body-file", default=None)
    p_cn.add_argument("--summary", default=None)
    p_cn.add_argument("--json", action="store_true")
    p_cn.set_defaults(func=_cmd_commit_note)

    p_reindex = sub.add_parser("reindex", help="rebuild the index (--isolated = worktree + swap)")
    p_reindex.add_argument("repo")
    p_reindex.add_argument("--state-dir", default=None)
    p_reindex.add_argument("--isolated", action="store_true",
                           help="build in an isolated worktree, swap atomically (non-blocking)")
    p_reindex.add_argument("--json", action="store_true")
    p_reindex.set_defaults(func=_cmd_reindex)

    p_init = sub.add_parser("init", help="zero-infra drop-in: index a repo in place")
    p_init.add_argument("repo", help="path to the repo to index")
    p_init.add_argument("--no-rebuild", action="store_true")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=_cmd_init)

    p_think = sub.add_parser("think",
                             help="thinking-mode (read-only): related notes + prompts, no write")
    p_think.add_argument("repo", help="repo whose index to think over")
    p_think.add_argument("topic", help="the topic/question to think about")
    p_think.add_argument("--index-db", default=None, help="index db (default: <repo>/.hypermnesic)")
    p_think.add_argument("--k", type=int, default=8)
    p_think.add_argument("--json", action="store_true")
    p_think.set_defaults(func=_cmd_think)

    p_retrieve = sub.add_parser("retrieve",
                                help="hybrid retrieve (read-only): converge first, then search")
    p_retrieve.add_argument("repo", help="repo whose index to search")
    p_retrieve.add_argument("query", help="the search query")
    p_retrieve.add_argument("--index-db", default=None,
                            help="index db (default: <repo>/.hypermnesic)")
    p_retrieve.add_argument("--k", type=int, default=10)
    p_retrieve.add_argument("--json", action="store_true")
    p_retrieve.set_defaults(func=_cmd_retrieve)

    p_capture = sub.add_parser("capture", help="frictionless capture: land raw text in sources/")
    p_capture.add_argument("repo", help="repo to capture into")
    p_capture.add_argument("text", help="the raw text to capture")
    p_capture.add_argument("--json", action="store_true")
    p_capture.set_defaults(func=_cmd_capture)

    p_conv = sub.add_parser("converge",
                            help="pre-warm: catch the index up to HEAD + bounded dense fill")
    p_conv.add_argument("repo", help="repo whose index to converge")
    p_conv.add_argument("--index-db", default=None,
                        help="index db (default: <repo>/.hypermnesic)")
    p_conv.add_argument("--authoring-host", action="store_true",
                        help="also refresh the uncommitted working-tree overlay")
    p_conv.add_argument("--json", action="store_true")
    p_conv.set_defaults(func=_cmd_converge)

    p_hooks = sub.add_parser("install-hooks",
                             help="opt-in: install/uninstall the post-merge convergence hook")
    p_hooks.add_argument("repo", help="repo to install the git hook into")
    p_hooks.add_argument("--uninstall", action="store_true",
                         help="remove only the managed block")
    p_hooks.add_argument("--json", action="store_true")
    p_hooks.set_defaults(func=_cmd_install_hooks)

    p_serve = sub.add_parser("serve", help="run the read-only tailnet MCP server")
    p_serve.add_argument("--index-db", required=True, help="path to the index .db")
    p_serve.add_argument("--host", required=True, help="Tailscale interface IP (not 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=8848)
    p_serve.add_argument("--path", default="/mcp")
    p_serve.add_argument("--enable-write", action="store_true",
                         help="register the git-first commit_note write tool (master role)")
    p_serve.set_defaults(func=_cmd_serve)

    p_install = sub.add_parser("install",
                               help="provision a host into a role (single|master|client)")
    p_install.add_argument("repo", nargs="?", default=None,
                           help="repo to provision (engine roles: single|master)")
    p_install.add_argument("--role", required=True, choices=["single", "master", "client"])
    p_install.add_argument("--bind", default=None, help="tailnet IP to bind (master)")
    p_install.add_argument("--service", default="systemd", choices=["systemd", "docker"],
                           help="always-on master service flavor")
    p_install.add_argument("--master-url", default=None,
                           help="master MCP endpoint the client points at")
    p_install.add_argument("--mcp-config", default=None,
                           help="MCP client config file to write/patch (client role)")
    p_install.add_argument("--port", type=int, default=8848)
    p_install.add_argument("--path", default="/mcp")
    p_install.add_argument("--json", action="store_true")
    p_install.set_defaults(func=_cmd_install)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
