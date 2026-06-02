# Threat Model — the `commit_note` MCP write surface (pre-U7 gate)

**Status:** historical gate artifact — **signed off 2026-06-01** (see the footer).
It was the mandatory pre-Phase-1 gate (Phase 1 could not begin until this existed
and was reviewed: *U5-passes AND this artifact exists*). Phase 1 (U7–U12) and the
gated `commit_note` MCP write tool (U31, registered only on a `write_enabled`
master) have **since shipped**. This remains the threat model of record for the
write surface; the mitigations below map to the live `frontmatter_gate.py` /
`serialize.py` / `audit_log.py` / `commit_note.py` modules.

**Scope.** The single sanctioned write path —
`commit_note(path, body, frontmatter)` — exposed over the **tailnet-only** MCP
server when serving write-enabled (Phase 0 was read-only and exposed **no** write
tool, so this model governs the net-new attack surface introduced at U7 and now
served via U31).

> **Phase 2 amendment (R12 / U2, 2026-06-02 — supersedes the prior "OAuth is a
> deferred seam, Phase 3 out of scope" posture).** OAuth 2.1 **authentication of the
> MCP endpoint is now IN scope.** The engine is an OAuth 2.1 **Resource Server (RS)**;
> a separate tailnet-internal **Authorization Server (AS, U12)** issues tokens, and a
> **write-enabled master must run auth-on** (`write_enabled ⇒ auth-required` on any
> non-loopback bind — an engine invariant mirroring the `0.0.0.0` refusal). The tailnet
> is **no longer the sole boundary** for the write tool: a caller must additionally
> present a valid, audience-bound (RFC 8707), in-scope token. What stays out of scope:
> public/Funnel exposure and fine-grained per-user *authorization* beyond a single
> required scope. The new RS attack surface is modeled in **V11–V14** below.

---

## 1. Assets

| Asset | Why it matters |
|---|---|
| Markdown corpus integrity | The files are the single source of truth; a bad write is a real data-loss/corruption event. |
| Governance & execution files | `CLAUDE.md`/`AGENTS.md` (agent instructions), `.github/workflows/` (CI code-exec), git hooks, `scripts/`/executables, `.obsidian/`, `views/`. Writing these is privilege escalation, not "editing a note." |
| Git history | Append-only, auditable; must not be rewritten or have side-effect mutations. |
| Frontmatter byte-stability | Silent reserialization (scalar→ISO dates, key reorder, dropped `_`-props) causes corruption + multi-device conflict storms. |
| Audit log | Must be reconstructable, append-only, and **body-free** (no private content). |
| Credentials (OpenAI key) | Never written to the index, log, or any output. |
| `.gitignore` / tracked files | Must never change as an indexing/writing side effect. |

## 2. Trust boundary & actors

- **Network boundary = the tailnet.** The MCP server binds a specific Tailscale
  interface address at the socket level (KTD10), never `0.0.0.0`. In Phase 1 the
  tailnet *was* the sole authentication boundary.
  **Phase 2 (R12/U2):** the tailnet remains the *network* boundary, but a
  write-enabled master additionally requires a valid **OAuth 2.1 bearer token** —
  per-identity, audience-bound, revocable. Reaching the socket is necessary but no
  longer sufficient to write; an unauthenticated `tools/call` to `commit_note` is
  rejected before any tool runs. **New actor:** the **Authorization Server (AS, U12)**
  — a tailnet-internal token issuer, independent of gbrain's AS, on which every
  authenticated call (and the per-prompt hook) depends (a recall SPOF — see V13).
- **Actor identity is server-set** (U11): the verified Tailscale node identity
  (via the Tailscale local API), or a fixed server-process sentinel when
  unavailable — **never** a caller-supplied string.
- **In-scope adversary:** a compromised or confused tailnet host, or a
  malicious/confused agent running on a tailnet node (including one steered by
  injected content it retrieved). 
- **Out-of-scope adversary:** the operator/owner themselves (they own the
  corpus); external/public attackers (no public reach until the Phase-3 gateway);
  multi-tenant isolation (single-operator tailnet).

## 3. Attack vectors & mitigations

### V1 — Protected-path write (privilege escalation / instruction injection)
*Threat:* a caller writes to `CLAUDE.md`/`AGENTS.md` (anywhere, including nested
`projects/x/AGENTS.md`), `.github/workflows/ci.yml`, a git-hook installer,
`scripts/`, `.obsidian/`, `views/`, or `.git/` — injecting agent instructions,
arbitrary CI code execution, or governance changes.
*Mitigation (R17/U12):* a **rule-based protected-path denylist** refused
unconditionally regardless of caller — `.git/`, any CI/workflow dir,
executable/script dirs, and agent-instruction files *anywhere in the tree* — plus
an optional **per-repo writable-path allowlist**. The denylist is a *rule* (file
class), not a fixed list, so it holds when the engine drops into an arbitrary
repo it has never seen. As implemented in `serialize.py` the current rule covers:
protected dirs anywhere in the path (`.git`, `.github`, `.obsidian`, `.claude`,
`.codex`, `views`, `scripts`, `bin`, `hooks`, `skills`, `.hypermnesic`),
instruction files anywhere (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`,
`copilot-instructions.md`), and never-files (`.gitignore`, `.gitattributes`,
`.gitmodules`). *Residual:* a missed governance-file class. Prefer a
deny-by-default / allowlist posture for content paths where feasible.

### V2 — Prompt injection via ingested content (retrieval/index poisoning)
*Threat:* an adversarial document (in the corpus or a U6 portability target)
embeds instructions ("call `commit_note` to overwrite X"). A downstream agent
that retrieves it via `search`/`build_context` could be steered into a malicious
write. The Phase-0 index **seeds** Phase 1, so poisoning compounds.
*Mitigation:* (a) the engine treats retrieved content as **data, not
instructions** — it never auto-acts on retrieved text; every write is an
explicit, server-authenticated `commit_note` call. (b) Probe/ingest targets must
be **operator-controlled or well-known** (U6 trust boundary). (c) Even a
successful injection cannot reach governance files (V1 guard bounds blast
radius). *Accepted risk:* the engine does **not** sanitize content for injection;
downstream agent harnesses MUST treat retrieved content as untrusted. Documented
as an integration assumption.

### V3 — Frontmatter clobbering / churn (data integrity)
*Threat:* a write reserializes frontmatter (scalar dates → ISO, key reorder,
drops Tolaria `_`-prefixed props) → silent corruption + iCloud conflict copies.
*Mitigation (R9/U8):* **diff-or-die** byte-preservation gate — abort and surface
the offending diff if any un-requested line would change.

### V4 — Actor spoofing / repudiation
*Threat:* caller supplies a false `actor` to poison attribution.
*Mitigation (U11):* actor is server-set (node identity / sentinel); any
caller-supplied actor is ignored. Append-only log; rewrites of prior entries are
rejected.

### V5 — Audit-log content leak
*Threat:* the log records private page bodies (the `--dry-run --json`
private-content-leak scar).
*Mitigation (U11):* **summaries only, never bodies**; asserted with a sentinel
test. Credentials excluded.

### V6 — Path traversal / write-outside-repo
*Threat:* `commit_note(path="../../etc/x")`, an absolute path, or a symlink that
escapes the repo root.
*Mitigation (U12, add explicitly):* normalize and verify the **resolved** path
stays within the repo root; reject `..` traversal, absolute paths, and
symlink-escape before any write.

### V7 — `.gitignore` / tracked-file side effects
*Threat:* indexing or writing mutates `.gitignore` (the `GBRAIN_NO_GITIGNORE`
recurrence) or other tracked files as a side effect.
*Mitigation (KTD8/R15):* designed out — the engine state dir is ignored via
`.git/info/exclude` only; a parity assertion verifies `.gitignore` is byte-stable
after an index pass.

### V8 — Concurrent-writer corruption
*Threat:* two writers corrupt the SQLite index or git tree (dirty-tree /
head-drift).
*Mitigation (R13/U12, KTD9):* broad writers run in an isolated, fast-forwarded
worktree with a dirty-tree guard; narrow writers use path-scoped guards; both
fetch + fast-forward before preflight; a single indexer holds the write lock.

### V9 — Credential exposure
*Threat:* the OpenAI key is written to the index, log, or output.
*Mitigation:* key read from env/secrets only, never persisted; `no-secret-in-
index` sentinel test; audit log excludes credentials.

### V10 — Crash / partial write (integrity & recovery)
*Threat:* a crash between `git stage` and log-append leaves an unlogged commit.
*Mitigation (U7/U11):* the **durable atomic unit is file write + git stage**;
the index self-heals via the SHA-checkpoint catch-up and the log via the
reconciler back-fill; idempotency is keyed on the resulting tree SHA, so re-runs
and crash-recovery do not conflict.

### Phase 2 amendment — OAuth 2.1 Resource-Server vectors (R12 / U2)

The RS auth surface inverts the usual posture: an auth bug does not merely deny — it can
**open** the write tool. These four vectors are net-new with R12.

### V11 — Token-validation bypass (auth-off / forged / replayed token)
*Threat:* the write-enabled master serves `commit_note` with auth misconfigured-off, or
accepts a forged/expired/replayed bearer token, exposing the write tool to any tailnet
node.
*Mitigation (U2):* the **`write_enabled ⇒ auth-required`** startup invariant (a write
master on a non-loopback bind refuses to start without a verifier + AuthSettings, mirroring
the `0.0.0.0` refusal) makes auth-off un-serveable; the SDK `BearerAuthBackend` rejects a
missing/invalid token (401) before any tool runs; `StrictResourceTokenVerifier` rejects an
expired token; tokens are opaque and validated against the AS (introspection), so a forged
token fails validation. Gate A verifies an unauthenticated `commit_note` call is rejected.
*Residual:* a leaked **live** token is a valid write credential until expiry/revocation —
bounded by a token-lifetime ceiling + revocation (U12), not eliminated.

### V12 — Audience / issuer confusion (cross-RS token replay)
*Threat:* a token legitimately minted by the same AS for a **different** resource server on
the tailnet (or a different audience) is replayed against hypermnesic's `/mcp` to gain write
access it was never granted.
*Mitigation (U2):* **RFC 8707 strict audience binding** in `verify_token` — a token whose
`resource`/`aud` does not include this RS's `resource_server_url` is rejected, and a token
with **no** audience is rejected (strict: absence cannot be bound). The AS is kept
independent of gbrain's AS (no shared issuer/discovery), so cross-issuer confusion has no
path. Gate A verifies a wrong-audience token is rejected.

### V13 — AS-compromise / AS-availability blast radius
*Threat:* the tailnet-internal AS is compromised (mints arbitrary write tokens) or
unavailable (every authenticated call — including the per-prompt auto-query hook — fails;
after gbrain teardown there is **no fallback** memory layer).
*Mitigation (U2/U12/U11):* the AS runs tailnet-internal (no public reach); a token-lifetime
ceiling + revocation bound a compromise; DCR is locked to the enrolled static clients after
enrollment so an arbitrary tailnet node cannot self-issue; the auto-query hook degrades
**silently** (no recall, never a turn-blocking 401 storm) when the AS/endpoint is down; U11
adds standing AS-availability + token-verify-failure SPOF monitoring with a restart runbook.
The **RS→AS introspection channel is loopback** (the RS master and the AS are co-located on
the homelab; the master introspects over `127.0.0.1`), so a tailnet node cannot MITM token
*validation* (security-review residual, 2026-06-02); only token *issuance* from a remote peer
(the Mac) crosses the tailnet, and that authenticates the client to the AS.
*Accepted risk:* the AS is a single point of failure for *recall availability* (not for git,
the source of truth) — consciously accepted, monitored, not eliminated.

### V14 — Auth bug *opens* the write surface (inverted failure mode)
*Threat:* unlike V1–V10 where a bug denies, an RS auth bug (verifier returns a token on the
None/exception path, scope check inverted, audience check skipped) **grants** write access —
failing *open*.
*Mitigation (U2):* the verifier **fails closed** — any raw-validation exception, a `None`
result, an expired token, or a non-matching audience returns `None` (→ 401), never a
default-allow; the verifier is covered by explicit valid/invalid/expired/wrong-/no-audience
tests. **Write-scope is enforced per-tool, not only by the transport.** The SDK middleware
applies one `required_scopes` list to *all* tools, so it cannot separate read clients from
write clients on a single endpoint — a write-enabled master started without a write scope in
`required_scopes` would otherwise expose `commit_note` to any valid (e.g. `read`-scoped)
token (the realized V14 case, found in the 2026-06-02 security review). Fix: **`commit_note`
self-enforces the `write` scope** from the authenticated principal (`get_access_token()`),
independent of the transport scope list; a token lacking `write` is refused before any write
(`tests/test_mcp_server.py::test_commit_note_rejects_read_scoped_principal`). *Residual:* a
defect in the SDK's `BearerAuthBackend`/`RequireAuthMiddleware` is inherited; pinned + tracked.

## 4. Accepted risks (this phase)

- No content sanitization for prompt injection (V2) — bounded by V1 + operator-
  controlled ingest + the untrusted-data integration assumption.
- No multi-tenant authz — single-operator tailnet; deferred to the Phase-3
  gateway.
- Malicious operator/owner — out of scope.
- Dependency supply chain — covered by the U1 license gate + standard hygiene;
  not specific to the write surface.

## 5. Phase-1 entry checklist (what U7+ must implement to honor this model)

- [ ] **U8** diff-or-die frontmatter gate (V3).
- [ ] **U11** server-set actor + append-only, summaries-only log + reconciler (V4, V5, V10).
- [ ] **U12** rule-based protected-path denylist + per-repo allowlist (V1); path-
      traversal / within-repo resolution check (V6); never-touch-`.gitignore`
      (V7); worktree/path-scoped serialization (V8).
- [ ] Tailnet socket-bind invariant carried from U4 (network boundary).
- [ ] `no-secret-in-output` discipline carried from U2 (V9).
- [ ] Integrator documentation: "retrieved content is untrusted data; the engine
      never auto-acts on it" (V2).

## 6. Review

This artifact must be **reviewed and signed off by the operator** before U7
begins. Pair it with the cleared U5 parity gate; together they are the Phase-1
entry condition.

### Sign-off

- **2026-06-01 — operator (Leonard Sellem): reviewed and APPROVED.** U5 parity
  gate is PASS (`harness/PARITY_VERDICT.md`); both Phase-1 entry conditions met.
  Phase 1 (U7–U12) is authorized to begin.
- **Development-safety proviso (agent):** U7–U12 are built and tested against
  **temporary fixture git repos only**. No write touches the live `gbrain-brain`
  canonical checkout, and no ingest cron is repointed onto `commit_note`, without
  an explicit per-action go-ahead. The protected-path guard (V1/U12) and
  within-repo path check (V6) land before any write path is exercised on a real
  repo.
