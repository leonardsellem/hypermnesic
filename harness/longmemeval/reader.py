"""U7 — reader (GPT-4.1 + GPT-4o columns) [Phase 2].

Answers each question from the retrieved context, matching the official
LongMemEval reading conventions (`run_generation.py`):

- **`con` (chain-of-note)** reading method: read the dated history, note the
  relevant evidence, then answer concisely.
- **`history_format=json`**: the retrieved units are presented as a JSON array.
- Units **re-sorted ascending by date**; the question's **`Current Date`** is
  threaded through; **`has_answer` is never present** (the materializer writes a
  clean verbatim body, so the reader cannot see which turn is the evidence).
- **Token budget** = ``model_max − gen_length − 1000`` counted with tiktoken
  ``o200k_base`` (GPT-4o/4.1). GPT-4.1's 1M context fits `_s` untruncated; the
  GPT-4o column truncates the *oldest* units if a haystack exceeds 128k.

The model is a **parameter**, so the same reader runs all columns — the GPT-4.1
lead (`gpt-4.1-2025-04-14`), the GPT-4o apples-to-apples anchor
(`gpt-4o-2024-08-06`), and the cheap dev/CI reader (`gpt-4.1-mini`). Every answer
is tagged with its reader model and a ``headline`` flag (AE3). Modeled on
``hypermnesic.expand.OpenAIExpander`` / ``harness/judge_labels.OpenAIJudge``:
lazy keyed client, ``temperature=0``, graceful failure, injectable for tests.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_GEN_LENGTH = 512
RESERVE_TOKENS = 1000  # the official reader's fixed budget reserve

# Context windows of the pinned snapshots (tokens). GPT-4.1 = 1M ⇒ `_s` untruncated.
MODEL_MAX_TOKENS = {
    "gpt-4.1-2025-04-14": 1_000_000,
    "gpt-4.1-mini": 1_000_000,
    "gpt-4o-2024-08-06": 128_000,
}
# The two published headline reader columns; `gpt-4.1-mini` is dev/CI only (AE3).
HEADLINE_READERS = frozenset({"gpt-4.1-2025-04-14", "gpt-4o-2024-08-06"})

_SYSTEM = (
    "You are answering a question from a user's conversation history using the "
    "chain-of-note method. The history is a JSON array of dated entries, ordered "
    "oldest to newest. First note the entries relevant to the question, then give "
    "a concise, direct answer. Resolve relative time expressions against the "
    "Current Date. If the answer is not in the history, say you don't know."
)


@dataclass(frozen=True)
class RetrievedUnit:
    unit_id: str
    date: str          # the session date (for date-ascending ordering + reasoning)
    text: str          # verbatim conversation text (no `has_answer` markers)


@dataclass
class ReaderAnswer:
    answer: str
    reader_model: str
    headline: bool
    truncated: bool
    units_used: int
    error: str | None = None


def tiktoken_token_counter(model: str = "gpt-4o") -> Callable[[str], int]:
    """A token counter using tiktoken ``o200k_base`` (GPT-4o/4.1). Lazily imports
    tiktoken (the ``bench`` extra) so the module imports without it for offline
    tests, which inject their own counter."""
    import tiktoken

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("o200k_base")
    return lambda text: len(enc.encode(text))


class Reader:
    def __init__(self, model: str, *, api_key: str | None = None, client=None,
                 token_counter: Callable[[str], int] | None = None,
                 gen_length: int = DEFAULT_GEN_LENGTH, model_max: int | None = None,
                 temperature: float = 0.0):
        self.model = model
        self.headline = model in HEADLINE_READERS
        self.gen_length = gen_length
        self.model_max = model_max or MODEL_MAX_TOKENS.get(model, 128_000)
        self.temperature = temperature
        self._api_key = api_key
        self._client = client
        self._counter = token_counter  # lazily built from tiktoken if None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            from hypermnesic import config
            self._client = OpenAI(api_key=self._api_key or config.get_api_key())
        return self._client

    def _count(self, text: str) -> int:
        if self._counter is None:
            self._counter = tiktoken_token_counter()
        return self._counter(text)

    @property
    def budget(self) -> int:
        return self.model_max - self.gen_length - RESERVE_TOKENS

    def _build_messages(self, question: str, question_date: str,
                        units: list[RetrievedUnit]) -> tuple[list[dict], bool, int]:
        """Assemble the con/json prompt; truncate the oldest units to fit budget."""
        ordered = sorted(units, key=lambda u: (u.date, u.unit_id))  # ascending by date
        truncated = False
        kept = list(ordered)
        while kept:
            messages = self._messages(question, question_date, kept)
            if self._count(_text_of(messages)) <= self.budget or len(kept) == 1:
                return messages, truncated, len(kept)
            kept = kept[1:]  # drop the oldest unit and retry
            truncated = True
        # no units at all
        return self._messages(question, question_date, []), truncated, 0

    def _messages(self, question: str, question_date: str,
                  units: list[RetrievedUnit]) -> list[dict]:
        history = [{"date": u.date, "content": u.text} for u in units]
        user = (
            f"Current Date: {question_date}\n\n"
            f"Conversation history (JSON, oldest first):\n"
            f"{json.dumps(history, ensure_ascii=False)}\n\n"
            f"Question: {question}\n\n"
            f"Notes, then answer:"
        )
        return [{"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user}]

    def answer(self, question: str, question_date: str,
               units: list[RetrievedUnit]) -> ReaderAnswer:
        messages, truncated, used = self._build_messages(question, question_date, units)
        try:
            resp = self._get_client().chat.completions.create(
                model=self.model, messages=messages,
                temperature=self.temperature, max_tokens=self.gen_length,
            )
            text = (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # graceful — never crash a 500-Q run on one call
            return ReaderAnswer("", self.model, self.headline, truncated, used, repr(exc))
        return ReaderAnswer(text, self.model, self.headline, truncated, used)


def _text_of(messages: list[dict]) -> str:
    return "\n".join(m["content"] for m in messages)
