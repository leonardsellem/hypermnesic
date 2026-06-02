"""LongMemEval V1 head-to-head benchmark harness.

A reproducible harness that ingests LongMemEval conversation sessions verbatim as
markdown, indexes them with the shipped read path, and reports Hypermnesic
head-to-head with the SOTA memory systems.

Phase 1 (``manifest`` → ``materialize`` → ``adapter`` → ``diagnostic``) is the
embeddings-only retrieval diagnostic. Phase 2 (``reader`` → ``judge`` → ``qa``)
lands the end-to-end QA headline code; its paid 500-Q run is a deliberate, gated
step (see ``harness/BENCHMARKS.md``).

This subpackage lives under ``harness/`` (which ``tests/conftest.py`` puts on
``sys.path``), so it imports as ``longmemeval`` by stem alongside the existing
parity harness — it is not part of the installed ``hypermnesic`` wheel.
"""
