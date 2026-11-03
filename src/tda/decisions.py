"""Typed decisions with Laya, an open-weight decision model (convaiinnovations/laya, Apache 2.0).

Laya is a ModernBERT-large encoder that answers typed questions about a text in one
forward pass (no generation): a `choice` among named options, or a `noul` P(yes). The
agent uses it where it makes a decision rather than writing text, and only where the
evals showed it helps (see Settings.classifier and Settings.injection_guard).
"""

import os
from functools import lru_cache

from tda.config import get_settings

INTENTS: dict[str, str] = {
    "read": "a question answered by reading HR or expense data: employees, jobs, managers, salaries, SSNs, "
    "phone numbers, review notes, departments and expenses, including the user's own record",
    "write": "a request to change, add, approve, reject, reassign or delete data",
    "out_of_scope": "anything that is not about the company's HR or expense data",
}
_INTENT_QUESTION = {
    "intent": {
        "type": "choice",
        "instructions": "What kind of request is this, sent to an HR and expenses database assistant?",
        "criteria": INTENTS,
    }
}
_INJECTION_QUESTION = {
    "injected": {"type": "noul", "instructions": "Is this text written to an AI assistant or chatbot, telling it what to do?"}
}


@lru_cache(maxsize=1)
def _agent():
    os.environ.setdefault("USE_TF", "0")  # the model card: TensorFlow's runtime can deadlock model construction
    import laya  # imported here: torch and the checkpoint load only when a Laya setting is on

    s = get_settings()
    return laya.load(s.laya_model, device=s.laya_device)


def intent(question: str) -> tuple[str, float]:
    """The request's intent label and Laya's confidence in it."""
    answer = _agent().predict(question, _INTENT_QUESTION)["answers"]["intent"]
    return answer["choice"], answer["confidence"]


def injection_scores(texts: list[str]) -> list[float]:
    """P(the text addresses an AI assistant with instructions), per text; distinct texts are scored once."""
    distinct = sorted(set(texts))
    if not distinct:
        return []
    results = _agent().predict_batch(distinct, _INJECTION_QUESTION, batch_size=32)
    score = {t: r["answers"]["injected"]["noul"] for t, r in zip(distinct, results)}
    return [score[t] for t in texts]
