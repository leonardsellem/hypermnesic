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
served via U31). Public/cloud reach (OAuth2.1/DCR gateway) is Phase 3 and
explicitly out of scope here.

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
  interface address at the socket level (KTD10), never `0.0.0.0`. There is **no
  OAuth in Phase 1** — the tailnet *is* the authentication boundary. Anything
  that can reach the socket can attempt a call.
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
