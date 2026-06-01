#!/usr/bin/env python3
"""LLM-as-judge relevance labeling for the parity harness (automates KTD6 review).

For each query, pool the candidate docs from BOTH systems (hypermnesic top-k ∪
gbrain top-k ∪ the current primary), strip every rank/source tag, shuffle, and
ask an LLM which candidates are relevant to the query — **judging on document
content alone**. Because the judge never sees which engine retrieved a doc (or
its rank), the labels stay independent of the ranking under test, so the
hyp-vs-gbrain comparison is not circular (standard pooling + LLM-as-judge).

These are **LLM-judged** labels (system-blind, content-based) — stronger than
agent-title labels but not human-judged; an operator can still spot-check via the
`label_review` file. Output overwrites `relevant` in the (gitignored) query set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from hypermnesic import ingest, retrieve

_JSON_ARRAY = re.compile(r"\[[^\]]*\]")


def _excerpt(corpus: Path, rel: str, n: int = 900) -> str | None:
    p = Path(corpus) / rel
    if not p.is_file():
        return None
    body = ingest.strip_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
    return " ".join(body.split())[:n]


def _shuffled(paths: list[str]) -> list[str]:
    # deterministic, content-independent order (so position can't encode source)
    return sorted(paths, key=lambda p: hashlib.sha256(p.encode()).hexdigest())


def judge_query(query: str, candidates: list[tuple[str, str]], judge_fn) -> list[str]:
    """candidates: [(path, excerpt)] already shuffled. Returns relevant paths."""
    if not candidates:
        return []
    rel_idx = judge_fn(query, [c[1] for c in candidates])  # 1-based indices
    out = []
    for i in rel_idx:
        if isinstance(i, int) and 1 <= i <= len(candidates):
            out.append(candidates[i - 1][0])
    return out


def build_labels(queries, baseline, idx, embedder, corpus, judge_fn, *, k=10,
                 expand=0, expander=None) -> tuple[list[dict], list[str]]:
    report = []
    for q in queries:
        res = retrieve.search(idx, q["query"], embedder=embedder, k=max(k, 50),
                              expand=expand, expander=expander)
        hyp, seen = [], set()
        for h in res.hits:
            if h.path not in seen:
                seen.add(h.path)
                hyp.append(h.path)
            if len(hyp) >= k:
                break
        gb = baseline.get(q["id"], [])[:k]
        pool = list(dict.fromkeys(hyp + gb + list(q.get("relevant", []))))
        cands = []
        for p in _shuffled(pool):
            ex = _excerpt(corpus, p)
            if ex:
                cands.append((p, ex))
        relevant = judge_query(q["query"], cands, judge_fn)
        if not relevant:  # judge found nothing / failed — keep prior labels as safety
            relevant = ([q["relevant_primary"]] if q.get("relevant_primary")
                        else q.get("relevant", []))
            report.append(f"{q['id']}: judge empty → kept prior")
        else:
            report.append(f"{q['id']}: {len(relevant)}/{len(cands)} relevant")
        prim = q.get("relevant_primary")
        q["relevant"] = sorted(dict.fromkeys(relevant))
        if prim not in q["relevant"]:
            q["relevant_primary"] = relevant[0]
        q["method"] = "llm-judged-pooled-system-blind"
    return queries, report


_PROMPT = (
    "You are a strict retrieval-relevance judge. Judge on content only; do not use "
    "any tools. Given a QUERY and numbered candidate document excerpts, output ONLY "
    "a JSON array of the numbers that are genuinely relevant (directly address the "
    "query's information need). If none are relevant, output []."
)


def _judge_prompt(query: str, excerpts: list[str]) -> str:
    numbered = "\n".join(f"[{i + 1}] {e}" for i, e in enumerate(excerpts))
    return f"{_PROMPT}\n\nQUERY: {query}\n\nCANDIDATES:\n{numbered}"


def _parse_indices(text: str) -> list[int]:
    m = _JSON_ARRAY.search(text or "")
    if not m:
        return []
    try:
        return [int(x) for x in json.loads(m.group(0)) if isinstance(x, int)]
    except (ValueError, json.JSONDecodeError):
        return []


def _codex_agent_message(jsonl: str) -> str:
    """Last agent_message text from `codex exec --json` JSONL output."""
    text = ""
    for line in (jsonl or "").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = ev.get("item") or {}
        if item.get("type") == "agent_message":
            text = item.get("text") or text
    return text


class CodexJudge:
    """judge_fn via `codex exec` — uses the ChatGPT (Pro) login, not the API key.

    Returns 1-based relevant indices; [] on any failure.
    """

    def __init__(self, model: str | None = None, codex: str = "codex",
                 cwd: str = "/tmp", timeout: int = 150):
        self.model = model
        self.codex = codex
        self.cwd = cwd
        self.timeout = timeout

    def __call__(self, query: str, excerpts: list[str]) -> list[int]:
        cmd = [self.codex, "exec", "--json", "--ignore-user-config", "--ignore-rules",
               "--ephemeral", "--skip-git-repo-check", "-s", "read-only", "-C", self.cwd]
        if self.model:
            cmd += ["-m", self.model]
        cmd.append(_judge_prompt(query, excerpts))
        try:
            out = subprocess.run(cmd, input="", capture_output=True, text=True,
                                 timeout=self.timeout).stdout
        except Exception:
            return []
        return _parse_indices(_codex_agent_message(out))


class OpenAIJudge:
    """judge_fn via the OpenAI chat API (consumes the API key). [] on failure."""

    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None):
        self.model = model
        self._api_key = api_key
        self._client = None

    def _client_(self):
        if self._client is None:
            from openai import OpenAI

            from hypermnesic import config
            self._client = OpenAI(api_key=self._api_key or config.get_api_key())
        return self._client

    def __call__(self, query: str, excerpts: list[str]) -> list[int]:
        try:
            resp = self._client_().chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": _judge_prompt(query, excerpts)}],
            )
            text = resp.choices[0].message.content or "[]"
        except Exception:
            return []
        return _parse_indices(text)


def _load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="LLM-as-judge pooled relevance labeling")
    p.add_argument("--index-db", required=True)
    p.add_argument("--queries", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--corpus", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--judge", choices=["codex", "openai"], default="codex",
                   help="codex = ChatGPT (Pro) login via codex exec; openai = API key")
    p.add_argument("--judge-model", default=None, help="override the judge model")
    p.add_argument("--expand", type=int, default=0)
    args = p.parse_args(argv)

    from hypermnesic import embed, index
    embed.smoke_embed_or_die()  # query embeddings for pooling (pinned index model)
    expander = None
    if args.expand:
        from hypermnesic import expand as expand_mod
        expander = expand_mod.OpenAIExpander()
    if args.judge == "codex":
        judge = CodexJudge(model=args.judge_model)
    else:
        judge = OpenAIJudge(model=args.judge_model or "gpt-4o-mini")
    idx = index.Index(Path(args.index_db))
    queries, report = build_labels(
        _load_jsonl(args.queries),
        {r["id"]: r["top10"] for r in _load_jsonl(args.baseline)},
        idx, embed.OpenAIEmbedder(), Path(args.corpus),
        judge, expand=args.expand, expander=expander)
    idx.close()
    with open(args.out, "w", encoding="utf-8") as fh:
        for q in queries:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")
    for line in report:
        print("  " + line)
    print(f"wrote LLM-judged labels → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
