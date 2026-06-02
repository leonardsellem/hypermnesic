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
    from hypermnesic import graph as graph_mod
    from hypermnesic import index, think

    db = Path(args.index_db) if args.index_db else index.state_dir_for(Path(args.repo)) / "index.db"
    idx = index.Index(db)
    g = graph_mod.Graph.from_index(idx)
    try:  # dense channel is optional — degrade to lexical+graph if no key (same as the server)
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder()
    except Exception:
        embedder = None
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


def _cmd_serve(args) -> int:
    from hypermnesic import mcp_server

    srv = mcp_server.build_server(Path(args.index_db), host=args.host,
                                  port=args.port, path=args.path)
    srv.run(transport="streamable-http")
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

    p_serve = sub.add_parser("serve", help="run the read-only tailnet MCP server")
    p_serve.add_argument("--index-db", required=True, help="path to the index .db")
    p_serve.add_argument("--host", required=True, help="Tailscale interface IP (not 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=8848)
    p_serve.add_argument("--path", default="/mcp")
    p_serve.set_defaults(func=_cmd_serve)
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
