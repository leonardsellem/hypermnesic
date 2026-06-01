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
