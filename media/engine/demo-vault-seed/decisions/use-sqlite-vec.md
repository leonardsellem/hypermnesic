---
title: Decision — use sqlite-vec for dense retrieval
status: active
created: 2026-05-06
tags:
- decision
- search
---
# Decision — use sqlite-vec for dense retrieval

We chose **sqlite-vec** as the vector-search extension for the dense lane of
[[projects/atlas-search]]. It stores embeddings in the same SQLite file as the FTS5
index, so the whole searchable projection is one disposable file rebuilt from the
markdown — no separate vector database to run or back up.

Rejected alternatives: a hosted vector DB (adds an external service and a second
source of truth) and a pure-lexical index (misses paraphrased recall).
