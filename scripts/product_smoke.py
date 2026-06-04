#!/usr/bin/env python3
"""Deterministic local product smoke for first-class readiness.

Runs on a disposable fixture vault only. Output is intentionally path-relative and secret-free.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hypermnesic import (  # noqa: E402
    capture,
    commit_note,
    config,  # noqa: E402
    doctor,
    index,
    memory_control,
    retrieve,
)


class SmokeEmbedder:
    dim = config.EMBED_DIM

    def embed(self, texts):
        out = []
        for text in texts:
            seed = sum(ord(ch) for ch in text) or 1
            out.append([((seed + i) % 97) / 97 for i in range(self.dim)])
        return out


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _init_repo(work_dir: Path) -> Path:
    repo = work_dir / "fixture-vault"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "smoke@example.invalid")
    _git(repo, "config", "user.name", "Hypermnesic Smoke")
    (repo / "projects").mkdir()
    (repo / "projects" / "atlas.md").write_text(
        "# Project Atlas\n\nProject Atlas uses Hypermnesic for durable project memory.\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed fixture vault")
    return repo


def _stage(name: str, status: str = "pass", **evidence) -> dict:
    return {"name": name, "status": status, "evidence": evidence}


def run_product_smoke(work_dir: str | Path, *, fail_stage: str | None = None) -> dict:
    work = Path(work_dir)
    repo = _init_repo(work)
    embedder = SmokeEmbedder()
    idx = index.build_index(repo, embedder)
    stages: list[dict] = []
    loop = [
        "capture",
        "retrieve",
        "write_preview",
        "memory_inspect",
        "forget_preview",
        "recall_after_change",
        "doctor_status",
    ]

    def maybe_fail(name: str) -> bool:
        if fail_stage == name:
            stages.append(_stage(name, "fail", reason="injected failure"))
            return True
        return False

    try:
        if maybe_fail("capture"):
            return _result("fail", stages, loop, failed_stage="capture")
        cap = capture.capture(repo, "Atlas smoke capture", idx=idx, now="20260604T000000")
        stages.append(_stage("capture", file=cap.files[0], committed=bool(cap.commit_sha)))

        if maybe_fail("retrieve"):
            return _result("fail", stages, loop, failed_stage="retrieve")
        found = retrieve.search(idx, "Project Atlas durable memory", embedder=embedder, k=3)
        hit = found.hits[0].path if found.hits else ""
        stages.append(_stage("retrieve", source_path=hit, degraded="lexical-only"))

        if maybe_fail("write_preview"):
            return _result("fail", stages, loop, failed_stage="write_preview")
        preview = commit_note.commit_note(
            repo,
            "memory/smoke-preview.md",
            body="# Smoke Preview\n\nA dry-run product smoke note.\n",
            dry_run=True,
        )
        stages.append(_stage("write_preview", path=preview.path, dry_run=preview.dry_run))

        if maybe_fail("memory_inspect"):
            return _result("fail", stages, loop, failed_stage="memory_inspect")
        inspected = memory_control.inspect_memory(repo, idx, "projects/atlas.md")
        stages.append(_stage("memory_inspect", path=inspected["path"],
                             inspect_status=inspected["status"]))

        if maybe_fail("forget_preview"):
            return _result("fail", stages, loop, failed_stage="forget_preview")
        forget = memory_control.preview_forget(repo, idx, "projects/atlas.md")
        stages.append(_stage("forget_preview", path=forget["target"]["path"],
                             preview_stage=forget["stage"]))

        if maybe_fail("recall_after_change"):
            return _result("fail", stages, loop, failed_stage="recall_after_change")
        cap_hit = retrieve.search(idx, "Atlas smoke capture", embedder=embedder, k=3)
        stages.append(_stage("recall_after_change", hit_count=len(cap_hit.hits)))

        if maybe_fail("doctor_status"):
            return _result("fail", stages, loop, failed_stage="doctor_status")
        status = doctor.run_doctor(repo).as_dict()
        stages.append(_stage("doctor_status", doctor_status=status["status"]))
        return _result("pass", stages, loop)
    finally:
        idx.close()


def _result(status: str, stages: list[dict], loop: list[str], *, failed_stage: str | None = None):
    out = {
        "status": status,
        "failed_stage": failed_stage,
        "first_class_loop": loop,
        "degraded_capabilities": ["lexical-only"],
        "stages": stages,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--fail-stage")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    out = run_product_smoke(args.work_dir, fail_stage=args.fail_stage)
    if args.json:
        print(json.dumps(out, sort_keys=True))
    else:
        print(f"Local product smoke {out['status']}")
        for stage in out["stages"]:
            print(f"- {stage['name']}: {stage['status']}")
    return 0 if out["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
