---
title: Project Atlas — hybrid search
status: active
created: 2026-05-04
tags:
- project
- search
---
# Project Atlas — hybrid search

Atlas replaces the old keyword-only lookup with **hybrid retrieval**: lexical FTS5
fused with dense vectors, so a query matches on wording *and* meaning.

The dense lane uses the decision recorded in [[decisions/use-sqlite-vec]]. Deploy and
rollout are owned by [[people/dana-ops]].

Open thread: tune the fusion weights once we have real query logs.
