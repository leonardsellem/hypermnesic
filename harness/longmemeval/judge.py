"""U8 — LongMemEval autoeval judge [Phase 2].

Grades reader answers with the **canonical judge** (`gpt-4o-2024-08-06`,
`temperature=0`, `max_tokens=10`, label = ``'yes' in response.lower()``) and the
**5 per-`question_type` prompt templates** of the official ``evaluate_qa.py``
``get_anscheck_prompt()``:

- **default** — the response is correct iff it contains the correct answer.
- **temporal** (temporal-reasoning) — allow off-by-one / approximate-but-consistent
  time tolerance.
- **knowledge-update** — the **latest** value is correct; restating the old value
  as current is incorrect.
- **preference** (single-session-preference) — rubric: correct iff the response
  respects the user's stated preference.
- **abstention** (the `_abs` instances) — correct iff the model **abstains**
  (the question is not answerable from the history); fabricating an answer is wrong.

The judge model string is pinned to exactly ``gpt-4o-2024-08-06`` so the official
aggregator (which hard-asserts this snapshot, R11) would accept the labels. The
keyless ``CodexJudge`` lane in ``harness/judge_labels.py`` is for cheap dev
iteration only — the headline MUST use this keyed judge. Modeled on
``OpenAIJudge``: lazy keyed client, graceful failure, injectable for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from longmemeval import manifest as mf
from longmemeval.materialize import normalize_question_type

if TYPE_CHECKING:
    from openai import OpenAI

JUDGE_MODEL = mf.JUDGE_MODEL  # "gpt-4o-2024-08-06"
MAX_TOKENS = 10
TEMPERATURE = 0

_DEFAULT = (
    "I will give you a question, the correct answer, and a model's response. "
    "Reply 'yes' if the response contains the correct answer to the question, "
    "otherwise reply 'no'.\n\n"
    "Question: {question}\nCorrect Answer: {answer}\nModel Response: {response}\n\n"
    "Does the model response contain the correct answer? Answer yes or no:"
)
_TEMPORAL = (
    "I will give you a question, the correct answer, and a model's response. This "
    "is a temporal-reasoning question: allow reasonable tolerance — a response that "
    "is off by one (day/week/unit) or uses an approximate but consistent time "
    "reference still counts as correct. Reply 'yes' if the response conveys the "
    "correct temporal answer within that tolerance, otherwise 'no'.\n\n"
    "Question: {question}\nCorrect Answer: {answer}\nModel Response: {response}\n\n"
    "Is the model response correct? Answer yes or no:"
)
_KNOWLEDGE_UPDATE = (
    "I will give you a question, the correct answer, and a model's response. This "
    "is a knowledge-update question: the user's information changed over time and "
    "the LATEST (most recent) value is the correct one. Reply 'yes' only if the "
    "response reflects the most recent value; restating the old/superseded value as "
    "current is incorrect.\n\n"
    "Question: {question}\nCorrect (latest) Answer: {answer}\nModel Response: {response}\n\n"
    "Does the response give the latest correct answer? Answer yes or no:"
)
_PREFERENCE = (
    "I will give you a question, a reference answer, and a model's response. This "
    "is a preference question — judge by rubric: the response is correct if it is "
    "consistent with and respects the user's stated preference, even if phrased "
    "differently from the reference. Reply 'yes' if it satisfies the preference, "
    "otherwise 'no'.\n\n"
    "Question: {question}\nReference Answer: {answer}\nModel Response: {response}\n\n"
    "Does the response respect the user's preference? Answer yes or no:"
)
_ABSTENTION = (
    "I will give you a question and a model's response. This question CANNOT be "
    "answered from the conversation history — the correct behavior is to abstain "
    "(state that it doesn't know or that the information is not available). Reply "
    "'yes' if the model correctly abstains or declines to answer; reply 'no' if it "
    "fabricates a specific answer.\n\n"
    "Question: {question}\nModel Response: {response}\n\n"
    "Does the model correctly abstain? Answer yes or no:"
)

_TEMPLATES = {
    "default": _DEFAULT,
    "temporal": _TEMPORAL,
    "knowledge-update": _KNOWLEDGE_UPDATE,
    "preference": _PREFERENCE,
    "abstention": _ABSTENTION,
}


@dataclass
class JudgeResult:
    correct: bool
    judge_model: str
    prompt_kind: str
    raw: str
    error: str | None = None


def prompt_kind(question_type: str, is_abstention: bool) -> str:
    """Select the template kind from question_type + the `_abs` flag."""
    if is_abstention:
        return "abstention"
    qt = normalize_question_type(question_type)
    if qt == "temporal-reasoning":
        return "temporal"
    if qt == "knowledge-update":
        return "knowledge-update"
    if qt == "single-session-preference":
        return "preference"
    return "default"


def build_prompt(question: str, answer: str, response: str,
                 question_type: str, is_abstention: bool) -> str:
    kind = prompt_kind(question_type, is_abstention)
    return _TEMPLATES[kind].format(question=question, answer=answer, response=response)


def parse_label(text: str) -> bool:
    """The official rule, verbatim: a correct label is ``'yes' in response.lower()``
    (a substring match — replicated exactly for aggregator comparability)."""
    return "yes" in (text or "").lower()


class Judge:
    def __init__(self, model: str = JUDGE_MODEL, *, api_key: str | None = None,
                 client=None, temperature: int = TEMPERATURE, max_tokens: int = MAX_TOKENS):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._client = client

    def _get_client(self) -> OpenAI:
        if self._client is None:
            from openai import OpenAI

            from hypermnesic import config
            self._client = OpenAI(api_key=self._api_key or config.get_api_key())
        return self._client

    def request_body(self, *, question: str, answer: str, response: str,
                     question_type: str, is_abstention: bool) -> tuple[dict, str]:
        """The chat.completions request body + the selected prompt ``kind``, without
        calling the API — shared by the sync call and the Batch API path."""
        kind = prompt_kind(question_type, is_abstention)
        prompt = build_prompt(question, answer, response, question_type, is_abstention)
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature, "max_tokens": self.max_tokens}
        return body, kind

    def grade_from_content(self, content: str | None, *, kind: str,
                           error: str | None = None) -> JudgeResult:
        """Wrap a completion's content (or an error) into a ``JudgeResult`` — shared
        by the sync call and the Batch API result parser."""
        if error is not None:
            return JudgeResult(False, self.model, kind, "", error)
        return JudgeResult(parse_label(content or ""), self.model, kind, content or "")

    def grade(self, *, question: str, answer: str, response: str,
              question_type: str, is_abstention: bool) -> JudgeResult:
        body, kind = self.request_body(question=question, answer=answer, response=response,
                                       question_type=question_type, is_abstention=is_abstention)
        try:
            resp = self._get_client().chat.completions.create(**body)
            content = resp.choices[0].message.content
        except Exception as exc:  # graceful — a judge outage doesn't crash the run
            return self.grade_from_content(None, kind=kind, error=repr(exc))
        return self.grade_from_content(content, kind=kind)
