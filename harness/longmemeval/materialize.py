"""U2 — deterministic session→markdown materializer + gold reconstruction.

Turns one LongMemEval instance into a byte-reproducible markdown corpus at two
granularities and reconstructs the retrieval gold sets:

- **Per-session** (the QA corpus): one file per haystack session, preserving the
  full conversational context. Session-level gold = ``answer_session_ids``.
- **Per-user-turn** (the turn diagnostic corpus): one file per *round* — a user
  turn plus the assistant reply(ies) that follow it before the next user turn.
  Turn-level gold = the rounds whose turns carry ``has_answer: true``.

Content is copied **verbatim** — no summarization or fact-extraction (R4). The
session date is written in the **body** (``Session Date: …``), not frontmatter,
because ``ingest.strip_frontmatter`` removes frontmatter from the indexed body
and both retrieval and the reader need the date inline (R6). File naming +
ordering are a pure function of the instance, so re-materializing yields
byte-identical files (R5). The 30 ``_abs`` (abstention) instances carry **no**
retrieval gold — matching the official ``run_retrieval.py``, which excludes them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_TURN_SUFFIX = re.compile(r"_turn\d+$")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class Turn:
    role: str
    content: str
    has_answer: bool = False


@dataclass(frozen=True)
class Session:
    session_id: str
    date: str
    turns: list[Turn]


@dataclass(frozen=True)
class Instance:
    question_id: str
    question_type: str
    question: str
    answer: str
    question_date: str
    sessions: list[Session]
    answer_session_ids: list[str]

    @property
    def is_abstention(self) -> bool:
        # The official convention: a trailing ``_abs`` marks an abstention question
        # whose answer is not derivable from the history.
        return self.question_id.endswith("_abs")


@dataclass
class Materialized:
    instance_id: str
    granularity: str                       # "session" | "turn"
    corpus_dir: Path
    path_to_unit: dict[str, str]           # repo-relative md path -> unit id
    gold_units: set[str] = field(default_factory=set)  # empty for `_abs`


def parse_instance(raw: dict) -> Instance:
    """Parse one raw LongMemEval instance dict into an ``Instance``.

    Zips the parallel ``haystack_session_ids`` / ``haystack_dates`` /
    ``haystack_sessions`` lists into ``Session`` objects; each turn dict's
    optional ``has_answer`` flag becomes ``Turn.has_answer``.
    """
    ids = raw["haystack_session_ids"]
    dates = raw.get("haystack_dates") or [""] * len(ids)
    sessions_raw = raw["haystack_sessions"]
    sessions = [
        Session(
            session_id=sid,
            date=date,
            turns=[Turn(role=t.get("role", ""), content=t.get("content", ""),
                        has_answer=bool(t.get("has_answer", False)))
                   for t in turns],
        )
        for sid, date, turns in zip(ids, dates, sessions_raw, strict=True)
    ]
    return Instance(
        question_id=raw["question_id"],
        question_type=raw.get("question_type", ""),
        question=raw.get("question", ""),
        answer=raw.get("answer", ""),
        question_date=raw.get("question_date", ""),
        sessions=sessions,
        answer_session_ids=list(raw.get("answer_session_ids") or []),
    )


def load_dataset(path: Path) -> list[Instance]:
    """Parse the downloaded LongMemEval JSON (a list of instance dicts) into
    ``Instance`` objects, preserving dataset order."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [parse_instance(d) for d in data]


def turn_to_session(turn_id: str) -> str:
    """Recover the parent session id from a turn id by stripping the ``_turnN``
    suffix (the official turn→session derivation)."""
    return _TURN_SUFFIX.sub("", turn_id)


def _slug(text: str) -> str:
    return _UNSAFE.sub("-", text).strip("-")[:60] or "x"


def _render_turns(turns: list[Turn]) -> str:
    # Verbatim role-tagged turns, blank-line separated (R4). The role tag mirrors
    # the official `history_format=json` role labels in plain markdown form.
    return "\n\n".join(f"**{t.role}:** {t.content}" for t in turns)


def _session_body(date: str, turns: list[Turn]) -> str:
    # Date FIRST and in the body (not frontmatter) so it survives strip_frontmatter
    # and lands in the index alongside the conversation (R6).
    return f"Session Date: {date}\n\n{_render_turns(turns)}\n"


def _session_gold(inst: Instance) -> set[str]:
    if inst.is_abstention:
        return set()
    if inst.answer_session_ids:
        return set(inst.answer_session_ids)
    # Fallback to the `answer` substring convention when answer_session_ids is absent.
    return {s.session_id for s in inst.sessions if "answer" in s.session_id}


def materialize_sessions(inst: Instance, dest_dir: Path) -> Materialized:
    """Write one markdown file per session (the QA corpus) and reconstruct the
    session-level gold set."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path_to_unit: dict[str, str] = {}
    for i, s in enumerate(inst.sessions):
        name = f"{i:04d}__{_slug(s.session_id)}.md"
        (dest_dir / name).write_text(_session_body(s.date, s.turns), encoding="utf-8")
        path_to_unit[name] = s.session_id
    return Materialized(instance_id=inst.question_id, granularity="session",
                        corpus_dir=dest_dir, path_to_unit=path_to_unit,
                        gold_units=_session_gold(inst))


def _rounds(session: Session) -> list[tuple[int, list[Turn]]]:
    """Group a session's turns into rounds, each starting at a user turn.

    Any leading non-user turns form their own (index-0) round so no content is
    dropped. Returns ``(start_index, turns_in_round)`` pairs.
    """
    rounds: list[tuple[int, list[Turn]]] = []
    cur: list[Turn] = []
    start = 0
    for ti, turn in enumerate(session.turns):
        if turn.role == "user" and cur:
            rounds.append((start, cur))
            cur, start = [], ti
        if not cur:
            start = ti
        cur.append(turn)
    if cur:
        rounds.append((start, cur))
    return rounds


def materialize_turns(inst: Instance, dest_dir: Path) -> Materialized:
    """Write one markdown file per user-turn round (the turn diagnostic corpus)
    and reconstruct the turn-level gold set (rounds carrying ``has_answer``)."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path_to_unit: dict[str, str] = {}
    gold: set[str] = set()
    abstain = inst.is_abstention
    for si, s in enumerate(inst.sessions):
        for start, turns in _rounds(s):
            unit_id = f"{s.session_id}_turn{start}"
            name = f"{si:04d}_{start:04d}__{_slug(s.session_id)}.md"
            (dest_dir / name).write_text(_session_body(s.date, turns), encoding="utf-8")
            path_to_unit[name] = unit_id
            if not abstain and any(t.has_answer for t in turns):
                gold.add(unit_id)
    return Materialized(instance_id=inst.question_id, granularity="turn",
                        corpus_dir=dest_dir, path_to_unit=path_to_unit, gold_units=gold)


def session_units(inst: Instance) -> dict[str, tuple[str, str]]:
    """Map session id → (date, verbatim conversation text), for assembling the
    reader's retrieved context (the QA reader needs each retrieved session's text
    and date, not just its id)."""
    return {s.session_id: (s.date, _render_turns(s.turns)) for s in inst.sessions}


def materialize_instance(inst: Instance, base_dir: Path) -> tuple[Materialized, Materialized]:
    """Materialize both granularities under ``base_dir`` (``sessions/`` + ``turns/``).

    The two corpora live in separate directories so a per-haystack index built
    over one never picks up the other's files.
    """
    base_dir = Path(base_dir)
    return (materialize_sessions(inst, base_dir / "sessions"),
            materialize_turns(inst, base_dir / "turns"))
