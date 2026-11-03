"""Ask a local model for one Oracle SQL query, and clean up what it sends back."""

from tda.config import get_settings
from tda.sqltext import extract_sql, is_select  # noqa: F401  (re-exported: the bake-off imports them from here)

PROMPT = """You write SQL for Oracle AI Database 26ai.

Schema:
{schema}

Write one SELECT statement that answers the question. Use only the tables and
columns above, prefix every table with the hr schema, and use FETCH FIRST n ROWS
ONLY instead of LIMIT. Reply with the SQL only.

Question: {question}"""


def generate_sql(model: str, question: str, schema_text: str, think: bool | None = None) -> str:
    """think=None leaves the model's default; True/False switches Ollama's reasoning mode."""
    import litellm  # imported lazily: slow to import, and unit tests never call a model

    extra = {} if think is None else {"think": think}
    response = litellm.completion(
        model=f"ollama_chat/{model}",
        messages=[{"role": "user", "content": PROMPT.format(schema=schema_text, question=question)}],
        temperature=0,
        seed=42,
        api_base=get_settings().ollama_base,
        **extra,
    )
    return extract_sql(response.choices[0].message.content or "")
