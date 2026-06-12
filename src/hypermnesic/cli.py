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

DEFAULT_CLIENT_SCOPES_ENV = "HYPERMNESIC_DEFAULT_CLIENT_SCOPES"


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _default_client_scopes(args_value) -> list[str] | None:
    import os
    raw = args_value if args_value is not None else os.environ.get(DEFAULT_CLIENT_SCOPES_ENV)
    if raw is None:
        return None
    items = raw if isinstance(raw, list) else [raw]
    scopes: list[str] = []
    for item in items:
        scopes.extend(str(item).replace(",", " ").split())
    return scopes or None


def _cmd_index(args) -> int:
    from hypermnesic import embed, index

    repo = Path(args.repo)
    embed.smoke_embed_or_die(repo=repo)  # fail loud before any indexing work
    embedder = embed.OpenAIEmbedder(repo=repo)
    state_dir = Path(args.state_dir) if args.state_dir else None
    idx = index.build_index(repo, embedder, rebuild=not args.no_rebuild,
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

    repo = Path(args.repo)
    embed.smoke_embed_or_die(repo=repo)  # fail loud before touching the index
    db = Path(args.index_db) if args.index_db else index.state_dir_for(repo) / "index.db"
    idx = index.Index(db)
    res = index.embed_stale(idx, repo, embed.OpenAIEmbedder(repo=repo))
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

    repo = Path(args.repo)
    embed.smoke_embed_or_die(repo=repo)
    embedder = embed.OpenAIEmbedder(repo=repo)
    state_dir = Path(args.state_dir) if args.state_dir else None
    if args.isolated:
        res = index.reindex_isolated(repo, embedder, state_dir=state_dir)
    else:
        index.build_index(repo, embedder, state_dir=state_dir).close()
        res = {"status": "rebuilt-inplace"}
    _print_json(res) if args.json else print(res["status"])
    return 0


def _cmd_init(args) -> int:
    """Zero-infra drop-in: index a repo in place (in-repo .hypermnesic/ state)."""
    from hypermnesic import embed, index

    repo = Path(args.repo)
    embed.smoke_embed_or_die(repo=repo)
    embedder = embed.OpenAIEmbedder(repo=repo)
    idx = index.build_index(repo, embedder, rebuild=not args.no_rebuild)
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

    repo = Path(args.repo)
    db = Path(args.index_db) if args.index_db else index.state_dir_for(repo) / "index.db"
    idx = index.Index(db)
    try:  # dense channel is optional — degrade to lexical+graph if no key (same as the server)
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder(repo=repo)
    except Exception:
        embedder = None
    converge_mod.converge(repo, idx, embedder)   # catch up before reading (U28)
    g = graph_mod.Graph.from_index(idx)                     # graph after convergence
    r = think.think(idx, args.topic, embedder=embedder, graph=g, k=args.k,
                    path=args.path, repo=repo)
    idx.close()
    if args.json:
        _print_json(r.as_dict())
    else:
        print(f"# thinking about: {r.topic}  (wrote={r.wrote})")
        for h in r.related:
            print(f"  - {h['path']}: {h['title']}")
        for q in r.questions:
            print(f"  ? {q}")
        for u in r.unlinked:
            print(f"  ~ {u['a_title']} ↔ {u['b_title']}  (related, not yet linked)")
        if r.note:
            print(f"  ({r.note})")
    return 0


def _cmd_retrieve(args) -> int:
    """Hybrid retrieve (read-only): converge first, then search — the CLI twin of
    the MCP ``search`` tool (same hit shape). Degrades to lexical if no key."""
    from hypermnesic import converge as converge_mod
    from hypermnesic import index, retrieve

    repo = Path(args.repo)
    db = Path(args.index_db) if args.index_db else index.state_dir_for(repo) / "index.db"
    idx = index.Index(db)
    try:  # dense channel optional — same graceful degradation as `think` / the server
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder(repo=repo)
    except Exception:
        embedder = None
    # U1: --now forces a non-debounced converge (debounce_seconds=0) so a self-write
    # committed within the 5 s window is caught in a single `retrieve --now`.
    cr = converge_mod.converge(repo, idx, embedder,
                               debounce_seconds=(0 if args.now else None))
    res = retrieve.search(idx, args.query, embedder=embedder, k=args.k,
                          recency_fn=retrieve.git_commit_recency(repo))
    idx.close()
    out = {
        "query": args.query,
        "degraded_lexical_only": res.degraded or cr.degraded,
        "manual_reindex_recommended": cr.manual_reindex_recommended,   # U1: surface (was dropped)
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


def _cmd_local_proof(args) -> int:
    """Local-first value proof: create/read a local vault, retrieve, and preview a write."""
    from hypermnesic import local_proof

    embedder = None
    repo = Path(args.repo) if args.repo else None
    if args.dense:
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder(repo=repo)
    try:
        result = local_proof.run_local_proof(
            repo=repo,
            demo_dir=(Path(args.demo_dir) if args.demo_dir else None),
            query=args.query,
            seed_sample=args.seed_sample,
            preview_path=args.preview_path,
            embedder=embedder,
        )
    except local_proof.LocalProofError as exc:
        out = exc.as_dict()
        if args.json:
            _print_json(out)
        else:
            print(f"local-proof failed: {exc.message}", file=sys.stderr)
            print(f"next: {exc.next_action}", file=sys.stderr)
        return 1

    out = result.as_dict()
    if args.json:
        _print_json(out)
    else:
        print("Local memory works")
        print(f"  source: {out['source_path']}")
        print(f"  index: {out['index']['state_path']} (disposable projection)")
        print(f"  recall: {out['retrieval']['hit']['heading'] or out['source_path']}")
        print(f"  preview: {out['write_preview']['destination']} (dry-run, no commit)")
        if out["degraded_capabilities"]["degraded_lexical_only"]:
            print(f"  note: {out['degraded_capabilities']['message']}")
        print(f"  next: {out['next_action']}")
    return 0


def _cmd_resolve(args) -> int:
    """Entity resolution (read-only): name → existing page path, or null (U1).

    gbrain's ``get`` role as a first-class verb. Converges first (``--now`` forces a
    non-debounced pass so a fresh self-write resolves), builds the graph, then resolves
    the name to a page. Ambiguous/missing → ``null`` (never a wrong guess). The caller
    wikilinks ``slug`` (the ``.md``-stripped path)."""
    from hypermnesic import converge as converge_mod
    from hypermnesic import graph as graph_mod
    from hypermnesic import index

    repo = Path(args.repo)
    db = Path(args.index_db) if args.index_db else index.state_dir_for(repo) / "index.db"
    idx = index.Index(db)
    try:  # dense optional — same graceful degradation as `retrieve` / the server
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder(repo=repo)
    except Exception:
        embedder = None
    converge_mod.converge(repo, idx, embedder,
                          debounce_seconds=(0 if args.now else None))
    g = graph_mod.Graph.from_index(idx)
    resolved = g.resolve(args.name)
    idx.close()
    slug = resolved[:-3] if resolved and resolved.endswith(".md") else resolved
    out = {"name": args.name, "resolved": resolved, "slug": slug}
    if args.json:
        _print_json(out)
    else:
        print(resolved or "")          # empty line on null → scriptable
    return 0


def _cmd_list_folders(args) -> int:
    """Folder discovery (read-only): the vault's writable folder taxonomy — the CLI twin of
    the MCP ``list_folders`` tool (same output shape). Converges first (``--now`` forces a
    non-debounced pass), then derives child folders under ``--root`` to ``--depth`` levels,
    each with its writability, protected reason, and recursive note count. JSON output also
    includes direct root-local ``AGENTS.md``/``CLAUDE.md`` guidance when present. ``--allowlist``
    previews writability under a narrowed surface; omit it for the engine default. Reads the
    on-disk index with no OAuth (CLI-for-engine-host-local). Degrades to lexical if no key."""
    from hypermnesic import converge as converge_mod
    from hypermnesic import folders, index, mcp_server

    repo = Path(args.repo)
    db = Path(args.index_db) if args.index_db else index.state_dir_for(repo) / "index.db"
    idx = index.Index(db)
    try:  # dense optional — same graceful degradation as `resolve` / the server
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder(repo=repo)
    except Exception:
        embedder = None
    cr = converge_mod.converge(repo, idx, embedder,
                               debounce_seconds=(0 if args.now else None))
    # Reuse the server's SOLE coercion so the CLI preview matches the live write surface (and
    # flips with Phase B by construction): None → the engine default; an explicit --allowlist
    # narrows the previewed surface (R7/R12/AE3).
    effective_surface = mcp_server._effective_write_surface(args.allowlist)
    try:
        listing = folders.derive_folders(idx.all_paths(), root=args.root, depth=args.depth,
                                         effective_surface=effective_surface)
        instruction = folders.agent_instruction_for_root(repo, listing["root"])
    except ValueError as exc:
        idx.close()
        print(f"list-folders failed: {exc}", file=sys.stderr)   # bad --root (absolute/..)
        return 1
    idx.close()
    out = {
        **listing,
        "manual_reindex_recommended": cr.manual_reindex_recommended,
        "agent_instruction": instruction,
    }
    if args.json:
        _print_json(out)
    else:
        header = out["root"] or "(vault root)"
        print(f"# folders under {header}  (depth={out['depth']}"
              f"{', truncated' if out['truncated'] else ''})")
        if instruction is not None:
            print(f"  (agent instructions: {instruction['source']})")
        for e in out["folders"]:
            flag = "w" if e["writable"] else "-"
            reason = "" if e["writable"] else f"  [{e['protected_reason']}]"
            print(f"  [{flag}] {e['path']}  ({e['note_count']}){reason}")
        if out["manual_reindex_recommended"]:
            print("  (manual reindex recommended)")
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


def _cmd_daily_review(args) -> int:
    """Generate a review-gated daily workflow surface."""
    from hypermnesic import audit_log, daily_review, graph, index

    repo = Path(args.repo)
    db = Path(args.index_db) if args.index_db else index.state_dir_for(repo) / "index.db"
    idx = index.Index(db) if db.exists() else None
    g = graph.Graph.from_index(idx) if idx is not None else None
    log_path = (Path(args.audit_log) if args.audit_log
                else index.state_dir_for(repo) / "audit.jsonl")
    log = audit_log.AuditLog(log_path)
    degraded = [] if idx is not None else ["partial: no index found; review uses files/audit only"]
    res = daily_review.review_proposal(
        repo,
        idx,
        g,
        audit_log=log,
        digest_rel=args.digest_rel,
        nav_rel=args.nav_rel,
        connections_rel=args.connections_rel,
        degraded=degraded,
        gh_create=None,
    )
    if idx is not None:
        idx.close()
    out = {
        "generated": True,
        "files": res.files,
        "branch": res.branch,
        "noop": res.noop,
        "cleanup_actions": daily_review.CLEANUP_ACTIONS,
    }
    if args.json:
        _print_json(out)
    else:
        print(f"daily review → {res.files[0]} ({'noop' if res.noop else 'proposal'})")
    return 0


def _cmd_converge(args) -> int:
    """Pre-warm: catch the index up to HEAD + a bounded dense fill (U27). The
    post-merge hook's entrypoint; also a manual warm. Lazy read-time convergence
    is the correctness guarantee — this never fails a pull (no index → clean no-op)."""
    from hypermnesic import converge as converge_mod
    from hypermnesic import index

    repo = Path(args.repo)
    db = Path(args.index_db) if args.index_db else index.state_dir_for(repo) / "index.db"
    if not db.exists():
        out = {"status": "no-index"}
        _print_json(out) if args.json else print("no index yet — run `hypermnesic init` first")
        return 0
    idx = index.Index(db)
    try:  # dense optional — degrade to lexical catch-up if no key (same as the server)
        from hypermnesic import embed
        embedder = embed.OpenAIEmbedder(repo=repo)
    except Exception:
        embedder = None
    res = converge_mod.converge(repo, idx, embedder,   # U1: --now forces a pass
                                authoring_host=args.authoring_host,
                                debounce_seconds=(0 if args.now else None))
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

    # repo defaults to None → build_server derives it from the index-db grandparent.
    # write_allowlist is None when --allowlist is omitted → build_server applies the blocklist
    # default (protected-path + governance fence only); an explicit empty allowlist is refused
    # at startup (U1); pass prefixes to narrow the surface (e.g. the legacy note-zones).
    # audit_actor_fn is left to default to the verified Tailscale node identity.
    #
    # U2: --auth-* enables OAuth2 RS mode. Enabling auth requires BOTH issuer + resource
    # URLs (make_auth_settings enforces it); the token verifier introspects opaque tokens
    # against the AS discovered from the issuer (RS credentials from the env, never flags).
    token_verifier = None
    auth_settings = None
    try:
        if args.auth_issuer_url or args.auth_resource_url:
            from hypermnesic import auth as auth_mod
            auth_settings = auth_mod.make_auth_settings(
                issuer_url=args.auth_issuer_url, resource_server_url=args.auth_resource_url,
                required_scopes=args.required_scope or [])
            verify_raw = auth_mod.verify_raw_from_discovery(
                issuer_url=args.auth_issuer_url, resource_server_url=args.auth_resource_url,
                required_scopes=args.required_scope or [])
            token_verifier = auth_mod.build_token_verifier(
                resource_server_url=args.auth_resource_url, verify_raw=verify_raw)
        srv = mcp_server.build_server(
            Path(args.index_db), host=args.host, port=args.port, path=args.path,
            repo=(Path(args.repo) if args.repo else None),
            write_enabled=args.enable_write, write_allowlist=args.allowlist,
            token_verifier=token_verifier, auth=auth_settings,
            trust_tailnet_write=args.allow_tailnet_write)
    except ValueError as exc:
        print(f"serve failed: {exc}", file=sys.stderr)   # fail loud; no half-open server
        return 1
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
            master_url=args.master_url, mcp_config_path=args.mcp_config,
            auth_issuer_url=args.auth_issuer_url, auth_resource_url=args.auth_resource_url,
            required_scope=args.required_scope)
    except (install.InstallError, FileNotFoundError) as exc:
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


def _cmd_serve_cloud(args) -> int:
    """Run the PUBLIC cloud OAuth MCP (ChatGPT/Claude mobile lane): the SDK authorization_code
    + DCR + PKCE AS + the operator-authenticated /consent gate + a write-enabled serve. Exposed
    publicly via Funnel. The operator approval token is read from the environment, NEVER a flag
    (it would otherwise leak via the process table / logs; it gates every public connection)."""
    import os

    from hypermnesic import auth_cloud, mcp_server

    approval = os.environ.get("HYPERMNESIC_CLOUD_APPROVAL_TOKEN")
    if not approval:
        print("serve-cloud failed: set HYPERMNESIC_CLOUD_APPROVAL_TOKEN (the operator approval "
              "token) in the environment — never a flag; it gates every public connection",
              file=sys.stderr)
        return 1
    if len(approval) < auth_cloud.MIN_APPROVAL_TOKEN_LEN:
        print(f"serve-cloud failed: the approval token is too weak — it is the only gate on every "
              f"public write, so use at least {auth_cloud.MIN_APPROVAL_TOKEN_LEN} characters "
              "(e.g. `python -c \"import secrets; print(secrets.token_urlsafe(32))\"`)",
              file=sys.stderr)
        return 1
    try:
        srv = mcp_server.build_cloud_server(
            Path(args.index_db), host=args.host, port=args.port, path=args.path,
            repo=(Path(args.repo) if args.repo else None),
            resource=args.resource, public_url=args.public_url, approval_token=approval,
            token_ttl_seconds=args.token_ttl,
            default_client_scopes=_default_client_scopes(args.default_client_scopes),
            write_allowlist=args.allowlist)
    except ValueError as exc:
        print(f"serve-cloud failed: {exc}", file=sys.stderr)   # fail loud; no half-open server
        return 1
    srv.run(transport="streamable-http")
    return 0


def _cmd_setup(args) -> int:
    """`hypermnesic setup`: one idempotent command to bring the unified public OAuth endpoint
    online — render + start the cloud service, persist the operator consent secret, configure the
    Tailscale funnel (MCP path + discovery well-knowns), verify the real HTTPS discovery chain, and
    print the URL + login instructions. Fail-closed: any failure leaves no partial state."""
    from hypermnesic import install

    try:
        res = install.setup(
            Path(args.repo), public_url=args.public_url,
            resource=(args.resource or args.public_url),
            host=args.host, port=args.port, path=args.path,
            env_file=(Path(args.env_file) if args.env_file else None),
            allowlist=args.allowlist, token_ttl=args.token_ttl,
            default_client_scopes=_default_client_scopes(args.default_client_scopes))
    except (install.InstallError, FileNotFoundError) as exc:
        print(f"setup failed: {exc}", file=sys.stderr)   # fail loud; nothing half-provisioned
        return 1
    if args.json:
        _print_json(res)
    else:
        print(f"hypermnesic unified endpoint live: {res['public_url']}")
        if res.get("what_this_means"):
            print(f"  what this means: {res['what_this_means']}")
        print(f"  service: {res['service']}  (consent secret: {res['env_file']})")
        for m in res.get("milestones", []):
            print(f"  [{m['status']}] {m['id']}: {m['summary']}")
        for step in res.get("next_steps", []):
            print(f"  next: {step}")
    return 0


def _cmd_doctor(args) -> int:
    """Non-mutating setup/status diagnostics."""
    from hypermnesic import doctor

    result = doctor.run_doctor(
        Path(args.repo),
        public_url=args.public_url,
        resource=args.resource,
        env_file=(Path(args.env_file) if args.env_file else None),
        check_dense_live=args.check_dense_live,
    )
    out = result.as_dict()
    if args.json:
        _print_json(out)
    else:
        print(f"hypermnesic {args.command}: {out['status']}")
        print(f"what this means: {out['what_this_means']}")
        for check in out["checks"]:
            print(f"  [{check['status']}] {check['id']}: {check['summary']}")
            action = check["next_action"]
            if action["code"] != "none":
                next_line = action["command"] or action["summary"]
                print(f"      next: {next_line}")
        for action in out["next_actions"].values():
            if action.get("available"):
                print(f"  next: {action['label']}: {action['next_action']}")
    return 0


def _cmd_memory(args) -> int:
    """Owner-facing memory control center."""
    from hypermnesic import (
        audit_log,
        index,
        memory_control,
        serialize,
    )
    from hypermnesic import (
        converge as converge_mod,
    )

    repo = Path(args.repo)
    db = Path(args.index_db) if args.index_db else index.state_dir_for(repo) / "index.db"
    idx = index.Index(db)
    try:
        try:
            from hypermnesic import embed
            embedder = embed.OpenAIEmbedder(repo=repo)
        except Exception:
            embedder = None
        converge_mod.converge(repo, idx, embedder, debounce_seconds=(0 if args.now else None))
        log_path = (Path(args.audit_log) if args.audit_log
                    else index.state_dir_for(repo) / "audit.jsonl")
        log = audit_log.AuditLog(log_path)

        if args.memory_command == "list":
            writable = True if args.writable else False if args.protected else None
            out = memory_control.list_memories(
                repo, idx, log=log, folder=args.folder, writable=writable,
                source_type=args.source_type, allowlist=args.allowlist, recent=args.recent)
        elif args.memory_command == "inspect":
            out = memory_control.inspect_memory(
                repo, idx, args.path, log=log, allowlist=args.allowlist)
        elif args.memory_command == "write-scope":
            out = memory_control.write_scope(
                repo, idx, allowlist=args.allowlist, root=args.root, depth=args.depth)
        elif args.memory_command == "export":
            out = memory_control.export_memories(
                repo, idx, args.dest, log=log, folder=args.folder, paths=args.path,
                allowlist=args.allowlist)
        elif args.memory_command == "forget":
            if args.apply:
                out = memory_control.apply_forget(
                    repo, idx, args.path, log=log, allowlist=args.allowlist)
            else:
                out = memory_control.preview_forget(
                    repo, idx, args.path, allowlist=args.allowlist)
        elif args.memory_command == "revert":
            if args.apply:
                out = memory_control.apply_revert(repo, idx, args.commit, log=log)
            else:
                out = memory_control.preview_revert(repo, args.commit)
        elif args.memory_command == "audit":
            out = memory_control.audit_view(log, limit=args.limit)
        else:
            raise ValueError(f"unknown memory command: {args.memory_command}")
    except (FileNotFoundError, ValueError, serialize.WriteGuardError, serialize.DirtyTreeError,
            serialize.HeadDriftError) as exc:
        idx.close()
        print(f"memory {args.memory_command} failed: {exc}", file=sys.stderr)
        return 1
    idx.close()

    if args.json:
        _print_json(out)
    else:
        _print_memory_human(args.memory_command, out)
    return 0


def _cmd_clients(args) -> int:
    """Owner-facing OAuth client/grant control."""
    from hypermnesic import client_control

    store = (Path(args.grant_store) if args.grant_store
             else client_control.grant_store_path(Path(args.repo)))
    try:
        if args.clients_command == "list":
            out = client_control.list_grants(store)
        elif args.clients_command == "revoke":
            out = client_control.revoke_grant(store, args.grant_id, apply=args.apply)
        else:
            raise ValueError(f"unknown clients command: {args.clients_command}")
    except (OSError, ValueError) as exc:
        print(f"clients {args.clients_command} failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(out)
    else:
        _print_clients_human(args.clients_command, out)
    return 0


def _print_memory_human(command: str, out: dict) -> None:
    if command == "list":
        print(f"# memory ({out['count']})")
        for item in out["items"]:
            flag = "writable" if item["writable"] else item["protected_reason"]
            print(f"  - {item['path']} [{item['source_type']}; {flag}]")
    elif command == "inspect":
        if out["status"] == "not_found":
            print(f"not found: {out['path']}")
        else:
            print(f"{out['path']} — {out['title']}")
            print(f"  provenance: {out['provenance']['source']} {out['last_commit']}")
            print(f"  actor: {out['actor']}")
    elif command == "write-scope":
        print(out["summary"]["answer"])
        for folder in out["folders"]:
            flag = "w" if folder["writable"] else "-"
            reason = "" if folder["writable"] else f" [{folder['protected_reason']}]"
            print(f"  [{flag}] {folder['path']}{reason}")
    elif command == "export":
        print(f"{out['status']}: {out['count']} file(s) -> {out['dest']}")
    elif command == "forget":
        print(f"{out['stage']}: {out.get('path') or out['target']['path']}")
        for line in out.get("limits", []):
            print(f"  note: {line}")
    elif command == "revert":
        print(f"{out['stage']}: {out.get('commit') or out.get('reverted')}")
        if "paths" in out:
            for path in out["paths"]:
                print(f"  path: {path}")
    elif command == "audit":
        print(f"# memory audit ({out['count']})")
        for entry in out["entries"]:
            print(f"  - {entry['verb']} {entry.get('path') or ''}: {entry.get('summary') or ''}")


def _print_clients_human(command: str, out: dict) -> None:
    if command == "list":
        print(f"# clients ({out['count']})")
        for grant in out["grants"]:
            access = "write" if grant["write_enabled"] else "read"
            print(f"  - {grant['grant_id']} {grant.get('client_name') or grant['client_id']} "
                  f"[{access}; {grant['status']}]")
    elif command == "revoke":
        if out.get("stage") == "preview":
            print(f"preview revoke: {out['grant_id']}")
        else:
            print(f"{out['status']}: {out['grant_id']}")


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
    p_think.add_argument("--path", default=None,
                         help="active note's repo-relative path to exclude from its own results")
    p_think.add_argument("--json", action="store_true")
    p_think.set_defaults(func=_cmd_think)

    p_retrieve = sub.add_parser("retrieve",
                                help="hybrid retrieve (read-only): converge first, then search")
    p_retrieve.add_argument("repo", help="repo whose index to search")
    p_retrieve.add_argument("query", help="the search query")
    p_retrieve.add_argument("--index-db", default=None,
                            help="index db (default: <repo>/.hypermnesic)")
    p_retrieve.add_argument("--k", type=int, default=10)
    p_retrieve.add_argument("--now", action="store_true",
                            help="force a non-debounced converge (catch a self-write "
                                 "committed within the debounce window)")
    p_retrieve.add_argument("--json", action="store_true")
    p_retrieve.set_defaults(func=_cmd_retrieve)

    p_local = sub.add_parser(
        "local-proof",
        help="prove local memory works before remote setup",
        description="prove local memory works before remote setup")
    p_local.add_argument("repo", nargs="?",
                         help="existing markdown git repo to prove locally")
    p_local.add_argument("--demo-dir", default=None,
                         help="create or reuse a tiny git-backed demo vault at DIR")
    p_local.add_argument("--query", default=None,
                         help="natural question to retrieve (demo mode has a default)")
    p_local.add_argument("--seed-sample", action="store_true",
                         help="explicitly add the deterministic sample note to an existing repo")
    p_local.add_argument("--preview-path", default="memory/local-proof-preview.md",
                         help="repo-relative dry-run write destination")
    p_local.add_argument("--dense", action="store_true",
                         help="try the dense embedding channel; default is local lexical proof")
    p_local.add_argument("--json", action="store_true")
    p_local.set_defaults(func=_cmd_local_proof)

    p_resolve = sub.add_parser("resolve",
                               help="entity resolution (read-only): name → existing page, or null")
    p_resolve.add_argument("repo", help="repo whose index to resolve against")
    p_resolve.add_argument("name", help="the entity name to resolve to a page")
    p_resolve.add_argument("--index-db", default=None,
                           help="index db (default: <repo>/.hypermnesic)")
    p_resolve.add_argument("--now", action="store_true",
                           help="force a non-debounced converge before resolving")
    p_resolve.add_argument("--json", action="store_true")
    p_resolve.set_defaults(func=_cmd_resolve)

    p_lf = sub.add_parser(
        "list-folders",
        help="folder discovery (read-only): the vault's writable folder taxonomy")
    p_lf.add_argument("repo", help="repo whose index to list folders from")
    p_lf.add_argument("--root", default="",
                      help="repo-relative prefix to drill into (default: vault root)")
    p_lf.add_argument("--depth", type=int, default=1,
                      help="levels to descend under root (default: 1)")
    p_lf.add_argument("--index-db", default=None,
                      help="index db (default: <repo>/.hypermnesic)")
    p_lf.add_argument("--now", action="store_true",
                      help="force a non-debounced converge before listing")
    p_lf.add_argument("--allowlist", action="append", default=None, metavar="PREFIX",
                      help="preview writability under a narrowed surface (default: engine surface)")
    p_lf.add_argument("--json", action="store_true")
    p_lf.set_defaults(func=_cmd_list_folders)

    p_capture = sub.add_parser("capture", help="frictionless capture: land raw text in sources/")
    p_capture.add_argument("repo", help="repo to capture into")
    p_capture.add_argument("text", help="the raw text to capture")
    p_capture.add_argument("--json", action="store_true")
    p_capture.set_defaults(func=_cmd_capture)

    p_daily = sub.add_parser("daily-review",
                             help="generate the capture/triage/recall/review cleanup surface")
    p_daily.add_argument("repo", help="repo to review")
    p_daily.add_argument("--index-db", default=None,
                         help="index db (default: <repo>/.hypermnesic)")
    p_daily.add_argument("--audit-log", default=None,
                         help="audit log path (default: <repo>/.hypermnesic/audit.jsonl)")
    p_daily.add_argument("--nav-rel", default="dashboards/MOC.md",
                         help="navigation surface link")
    p_daily.add_argument("--digest-rel", default="dashboards/salience-digest.md",
                         help="salience digest link")
    p_daily.add_argument("--connections-rel", default=None,
                         help="suggested connections surface link")
    p_daily.add_argument("--json", action="store_true")
    p_daily.set_defaults(func=_cmd_daily_review)

    p_conv = sub.add_parser("converge",
                            help="pre-warm: catch the index up to HEAD + bounded dense fill")
    p_conv.add_argument("repo", help="repo whose index to converge")
    p_conv.add_argument("--index-db", default=None,
                        help="index db (default: <repo>/.hypermnesic)")
    p_conv.add_argument("--authoring-host", action="store_true",
                        help="also refresh the uncommitted working-tree overlay")
    p_conv.add_argument("--now", action="store_true",
                        help="force a non-debounced converge (ignore a fresh stamp)")
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
    p_serve.add_argument("--allow-tailnet-write", action="store_true",
                         help="accept tailnet membership AS the write boundary: permit a "
                              "write-enabled auth-off serve on a Tailscale IP (100.64.0.0/10). "
                              "Explicit opt-out of write⇒auth-required; bounded to the tailnet.")
    p_serve.add_argument("--allowlist", action="append", default=None, metavar="PREFIX",
                         help="repeatable writable path prefix to NARROW the write surface "
                              "(write-enabled serve). Omit for the blocklist default "
                              "(protected-path + governance fence only); empty refused at startup")
    p_serve.add_argument("--repo", default=None,
                         help="git repo the index projects (default: index-db grandparent)")
    p_serve.add_argument("--auth-issuer-url", default=None,
                         help="OAuth2 AS issuer URL (enables RS auth; needs --auth-resource-url)")
    p_serve.add_argument("--auth-resource-url", default=None,
                         help="this RS's resource identifier (RFC 8707 audience); "
                              "e.g. https://example.ts.net/mcp")
    p_serve.add_argument("--required-scope", action="append", default=None, metavar="SCOPE",
                         help="repeatable required OAuth2 scope (e.g. write)")
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
    p_install.add_argument("--auth-issuer-url", default=None,
                           help="OAuth2 AS issuer URL for the master ExecStart (U2)")
    p_install.add_argument("--auth-resource-url", default=None,
                           help="this RS's resource identifier (RFC 8707 audience) for the master")
    p_install.add_argument("--required-scope", action="append", default=None, metavar="SCOPE",
                           help="repeatable required OAuth2 scope rendered on the master ExecStart")
    p_install.add_argument("--json", action="store_true")
    p_install.set_defaults(func=_cmd_install)

    p_cloud = sub.add_parser("serve-cloud",
                             help="run the PUBLIC cloud OAuth MCP (ChatGPT/Claude mobile lane)")
    p_cloud.add_argument("--index-db", required=True, help="path to the index .db")
    p_cloud.add_argument("--host", default="127.0.0.1",
                         help="local bind (Funnel proxies the public hostname to it)")
    p_cloud.add_argument("--port", type=int, default=8850)
    p_cloud.add_argument("--path", default="/mcp")
    p_cloud.add_argument("--public-url", required=True,
                         help="the public AS/issuer URL (e.g. https://<host>.ts.net/cloud)")
    p_cloud.add_argument("--resource", required=True,
                         help="the public MCP resource identifier (RFC 8707 audience)")
    p_cloud.add_argument("--repo", default=None, help="git repo the index projects")
    p_cloud.add_argument("--token-ttl", type=int, default=3600,
                         help="access-token lifetime ceiling (seconds)")
    p_cloud.add_argument("--allowlist", action="append", default=None, metavar="PREFIX",
                         help="writable path prefix to narrow the write surface "
                              "(default: blocklist — protected-path + governance fence only)")
    p_cloud.add_argument("--default-client-scopes", nargs="+", default=None, metavar="SCOPE",
                         help="OAuth scopes requested by default when a dynamically registered "
                              "client omits scope (default: read; env: "
                              "HYPERMNESIC_DEFAULT_CLIENT_SCOPES=read,write)")
    p_cloud.set_defaults(func=_cmd_serve_cloud)

    p_setup = sub.add_parser("setup",
                             help="one-command bring-up of the unified public OAuth MCP endpoint")
    p_setup.add_argument("repo", help="repo whose index the endpoint serves (engine host)")
    p_setup.add_argument("--public-url", required=True,
                         help="the public HTTPS issuer/MCP URL (e.g. https://<host>.ts.net/mcp)")
    p_setup.add_argument("--resource", default=None,
                         help="the public MCP resource identifier (RFC 8707 audience); "
                              "defaults to --public-url")
    p_setup.add_argument("--host", default="127.0.0.1",
                         help="local bind (the Funnel proxies the public hostname to it)")
    p_setup.add_argument("--port", type=int, default=8850)
    p_setup.add_argument("--path", default="/",
                         help="internal serve path (default '/': the funnel maps the public "
                              "/mcp mount to it, so /mcp/authorize etc. resolve)")
    p_setup.add_argument("--env-file", default=None,
                         help="owner-only env file for the consent secret "
                              "(default: ~/.config/hypermnesic-cloud/cloud.env)")
    p_setup.add_argument("--allowlist", action="append", default=None, metavar="PREFIX",
                         help="writable path prefix to narrow the write surface "
                              "(default: blocklist — protected-path + governance fence only)")
    p_setup.add_argument("--default-client-scopes", nargs="+", default=None, metavar="SCOPE",
                         help="OAuth scopes requested by default when a dynamically registered "
                              "client omits scope (default: read; env: "
                              "HYPERMNESIC_DEFAULT_CLIENT_SCOPES=read,write)")
    p_setup.add_argument("--token-ttl", type=int, default=3600)
    p_setup.add_argument("--json", action="store_true")
    p_setup.set_defaults(func=_cmd_setup)

    for name in ("doctor", "status"):
        p_diag = sub.add_parser(name, help="non-mutating setup diagnostics and next actions")
        p_diag.add_argument("repo", help="repo whose local/remote setup to diagnose")
        p_diag.add_argument("--public-url", default=None,
                            help="public HTTPS MCP URL to verify (optional)")
        p_diag.add_argument("--resource", default=None,
                            help="OAuth resource identifier; defaults to --public-url")
        p_diag.add_argument("--env-file", default=None,
                            help="owner-only env file to check for existence/permissions")
        p_diag.add_argument("--check-dense-live", action="store_true",
                            help="run an opt-in live embedding smoke check for dense retrieval")
        p_diag.add_argument("--json", action="store_true")
        p_diag.set_defaults(func=_cmd_doctor)

    p_memory = sub.add_parser("memory", help="owner memory control center")
    mem = p_memory.add_subparsers(dest="memory_command", required=True)

    def add_memory_common(p):
        p.add_argument("repo", help="repo whose memory to control")
        p.add_argument("--index-db", default=None,
                       help="index db (default: <repo>/.hypermnesic)")
        p.add_argument("--audit-log", default=None,
                       help="audit log path (default: <repo>/.hypermnesic/audit.jsonl)")
        p.add_argument("--allowlist", action="append", default=None, metavar="PREFIX",
                       help="preview/control under a narrowed writable surface")
        p.add_argument("--now", action="store_true",
                       help="force a non-debounced converge before reading")
        p.add_argument("--json", action="store_true")

    p_mem_list = mem.add_parser("list", help="list remembered files")
    add_memory_common(p_mem_list)
    p_mem_list.add_argument("--folder", default=None)
    p_mem_list.add_argument("--source-type", choices=["authored", "captured", "generated"],
                            default=None)
    p_mem_list.add_argument("--writable", action="store_true")
    p_mem_list.add_argument("--protected", action="store_true")
    p_mem_list.add_argument("--recent", action="store_true")
    p_mem_list.set_defaults(func=_cmd_memory)

    p_mem_inspect = mem.add_parser("inspect", help="inspect one remembered file")
    add_memory_common(p_mem_inspect)
    p_mem_inspect.add_argument("path", help="repo-relative memory path")
    p_mem_inspect.set_defaults(func=_cmd_memory)

    p_mem_scope = mem.add_parser("write-scope", help="answer what an agent may write")
    add_memory_common(p_mem_scope)
    p_mem_scope.add_argument("--root", default="")
    p_mem_scope.add_argument("--depth", type=int, default=1)
    p_mem_scope.set_defaults(func=_cmd_memory)

    p_mem_export = mem.add_parser("export", help="export selected memory as markdown")
    add_memory_common(p_mem_export)
    p_mem_export.add_argument("--dest", required=True, help="destination directory")
    p_mem_export.add_argument("--folder", default=None)
    p_mem_export.add_argument("--path", action="append", default=None,
                              help="explicit repo-relative path to export")
    p_mem_export.set_defaults(func=_cmd_memory)

    p_mem_forget = mem.add_parser("forget", help="preview/apply git-backed memory removal")
    add_memory_common(p_mem_forget)
    p_mem_forget.add_argument("path", help="repo-relative memory path")
    p_mem_forget.add_argument("--apply", action="store_true",
                              help="apply the removal as a git commit")
    p_mem_forget.set_defaults(func=_cmd_memory)

    p_mem_revert = mem.add_parser("revert", help="preview/apply a safe recent memory revert")
    add_memory_common(p_mem_revert)
    p_mem_revert.add_argument("commit", help="commit sha to revert")
    p_mem_revert.add_argument("--apply", action="store_true",
                              help="apply the revert as a new git commit")
    p_mem_revert.set_defaults(func=_cmd_memory)

    p_mem_audit = mem.add_parser("audit", help="show recent memory writes/refusals")
    add_memory_common(p_mem_audit)
    p_mem_audit.add_argument("--limit", type=int, default=None)
    p_mem_audit.set_defaults(func=_cmd_memory)

    p_clients = sub.add_parser("clients", help="owner client and grant control")
    clients = p_clients.add_subparsers(dest="clients_command", required=True)

    def add_clients_common(p):
        p.add_argument("repo", help="repo whose client grants to control")
        p.add_argument("--grant-store", default=None,
                       help="client grant metadata file (default: <repo>/.hypermnesic)")
        p.add_argument("--json", action="store_true")

    p_clients_list = clients.add_parser("list", help="list known client grants")
    add_clients_common(p_clients_list)
    p_clients_list.set_defaults(func=_cmd_clients)

    p_clients_revoke = clients.add_parser("revoke", help="revoke a client grant")
    add_clients_common(p_clients_revoke)
    p_clients_revoke.add_argument("grant_id", help="grant id to revoke")
    p_clients_revoke.add_argument("--apply", action="store_true",
                                  help="write the revocation marker to the metadata store")
    p_clients_revoke.set_defaults(func=_cmd_clients)
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
