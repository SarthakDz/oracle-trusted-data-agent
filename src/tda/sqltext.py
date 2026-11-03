"""Turn a model's reply into one executable SQL statement."""

import re

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"```[A-Za-z]*\s*\n?(.*?)```", re.DOTALL)


def extract_sql(text: str) -> str:
    """Pull the SQL out of a model reply; python-oracledb rejects fences and a trailing ';'."""
    text = _THINK.sub("", text)
    fence = _FENCE.search(text)
    sql = (fence.group(1) if fence else text).strip()
    return sql[:-1].rstrip() if sql.endswith(";") else sql


def is_select(sql: str) -> bool:
    """True for a query (SELECT or WITH)."""
    words = sql.split(maxsplit=1)
    return bool(words) and words[0].lower() in ("select", "with")
