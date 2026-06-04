# Glossary

Project-specific terms, defined by how hypermnesic actually uses them. See
[`ARCHITECTURE.md`](ARCHITECTURE.md) for how they fit together.

**Vault** — the git repository of markdown notes that hypermnesic indexes. The files are
the single source of truth.

**Disposable index / projection** — the SQLite search index is a *projection* of the
committed git tree, not a database of record. It can be rebuilt from git at any time and
a reindex never loses a committed write.

**Convergence** — the read-path step (`converge.py`) that catches the index up to `HEAD`
(lexical delta-replay) and closes a bounded slice of the dense-embedding lag before
answering, so a just-committed note is recall-able without a manual reindex. Bounded by
the convergence tunables (see [configuration](docs/reference/configuration.md)).

**RRF (Reciprocal Rank Fusion)** — the rank-combination method that fuses the lexical
(FTS5) and dense (sqlite-vec KNN) result lists into one ranking, without needing
comparable raw scores.

**Hybrid retrieval** — search that runs both the lexical and dense channels and fuses
them with RRF, degrading to lexical-only when embeddings are unavailable.

**Degraded (lexical-only)** — the state where the dense channel is unavailable (no key /
API down); results still come from FTS5 + the graph, flagged `degraded_lexical_only`.

**Thinking-mode** — a read-only reasoning surface (`think`): related notes + Socratic
prompts + tensions. It never writes (`wrote: false` is an observable assertion).

**Salience** — a scoring of notes for resurfacing; drives the spaced-review digest
(`salience.py`).

**Serendipity / connection proposals** — surfaced non-obvious links between notes
(`connect.py`), offered as review-gated proposals, never auto-applied.

**MOC (Map of Content)** — a generated index/dashboard note that organizes a topic area;
part of the always-organized navigation surface (`nav_surface.py`).

**Sidecar** — a content-addressed markdown extraction of a non-markdown source
(PDF/DOCX/XLSX/PPTX/PNG) via permissive extractors (`sidecar.py`), hash-gated so an
unchanged source isn't re-extracted.

**Capture** — frictionless landing of raw text into a free-append zone (`sources/`) with
zero ceremony (`capture.py`), triaged later in thinking-mode.

**Durable project memory** — memory that should survive beyond the current session as
markdown/git truth: durable facts, decisions, source episodes, policies, generated
summaries with source paths, raw captures, and current-state mirrors.

**Semantic memory** — stable factual knowledge about a project, entity, person, system,
or decision, written so future agents can retrieve it by topic or entity.

**Episodic/source memory** — dated source evidence: meeting notes, imported excerpts,
incident observations, raw transcripts, or other source episodes that should remain
traceable.

**Procedural/policy memory** — durable operating instructions, policies, runbooks, and
guardrails that describe how work should be done.

**Generated summary** — an explicitly generated synthesis over source material. It should
cite source paths and remain traceable to raw captures or episodic/source memory.

**Raw capture** — unprocessed source text landed for later triage. It should not be
silently overwritten by a generated summary.

**Current-state mirror** — a maintained note that mirrors external reality, such as a
service topology, deployment state, or owner-approved configuration. It must be updated
when the external state changes.

**Adjacent behavioural memory layer** — a separate short-term, session, or preference
memory layer such as Honcho. Behavioural preferences like "user likes terse replies" do
not belong in Hypermnesic by default.

**Git-first write** — the write model: `commit_note` writes the file and commits it to
git *first*; the index follows as a projection. The agent never merges.

**`commit_note`** — the one sanctioned write tool/path; gated and git-first.

**Diff-or-die frontmatter gate** — the write guard (`frontmatter_gate.py`) that aborts a
write if it would change any frontmatter key the caller didn't explicitly request,
surfacing the diff instead of silently reserializing.

**Blocklist write surface (write-anywhere-under-guards)** — the default write model: a
note may land anywhere in the vault *except* the protected classes (protected-path
refusal + governance-file fence in `serialize.py`); an explicit **allowlist** is an
opt-in way to *narrow* that surface.

**Protected-path / governance fence** — the caller-independent rules that refuse writes
to dangerous classes (`.git/`, `.github/`, agent-instruction files, `scripts/`/`hooks/`/
`skills/`, build/CI/credential files) regardless of any allowlist.

**Audit log** — the append-only JSONL record of writes (`audit_log.py`): summaries only,
never note bodies, never credentials; the actor is server-set (the verified Tailscale
node identity), never caller-supplied.

**Tailnet** — your private Tailscale network. hypermnesic binds a specific Tailscale
interface address (never `0.0.0.0`).

**Tailnet read lane / companion** — the auth-off, read-only serving lane (`:8848`) for
the Obsidian companion and the recall hook on tailnet devices; tailnet membership is the
boundary.

**Unified OAuth `/mcp` endpoint** — the single public network lane every remote client
uses, exposed via Tailscale Funnel.

**Tailscale Funnel** — the Tailscale feature that exposes a tailnet service publicly over
HTTPS with automatic TLS (no reverse proxy or cert to manage).

**CGNAT range** — `100.64.0.0/10`, the address range Tailscale assigns. The bounded
`--allow-tailnet-write` opt-in is permitted only on a bind inside this range.

**DCR (Dynamic Client Registration)** — the OAuth 2.1 mechanism that lets a client
register itself with the Authorization Server at connect time, so no pre-shared client
config is needed.

**PKCE (Proof Key for Code Exchange)** — the OAuth extension that binds an authorization
code to the client that requested it, preventing code interception.

**RFC 8707 audience-binding** — issuing tokens scoped to a specific resource (audience),
so a token minted for one resource can't be replayed against another.

**`write` scope** — the OAuth scope `commit_note` requires of its caller; self-enforced
per-tool, independent of the transport's global scope list, so read clients can't reach
the write tool on a shared endpoint.

**Consent secret / approval token** — the owner-only token (`HYPERMNESIC_CLOUD_APPROVAL_TOKEN`)
that gates every public connection; entered on the consent page to authorize a client.
Read from the environment only, never a flag.
