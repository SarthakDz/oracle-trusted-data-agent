"""Every model call goes through here: LiteLLM to Ollama, with timeouts and one error type.

The timeout matters on this machine: with WSL mirrored networking a dead port hangs
instead of refusing the connection, so an unbounded call would never return.
"""

import hashlib
import json
import re
import urllib.request
from pathlib import Path

from tda.config import get_settings

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(RuntimeError):
    """A model call failed: connection, timeout, or an aborted generation."""


def chat(prompt: str, *, think: bool, model: str | None = None) -> str:
    import litellm  # imported lazily: slow to import, and unit tests replace it

    s = get_settings()
    model = model or s.agent_model
    options = {"num_ctx": s.llm_num_ctx, "max_tokens": s.llm_max_tokens}
    cached = None
    if s.llm_cache_dir:
        # shortcut: the key has the model tag, not its digest, so a model re-pulled under the same tag reuses old replies; clear .cache/llm after ollama pull.
        key = hashlib.sha256(json.dumps([model, think, prompt, options], sort_keys=True).encode()).hexdigest()
        cached = Path(s.llm_cache_dir) / f"{key}.json"
        if cached.exists():
            return json.loads(cached.read_text())["reply"]
    try:
        response = litellm.completion(
            model=f"ollama_chat/{model}",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            seed=42,
            think=think,
            api_base=s.ollama_base,
            timeout=s.llm_timeout_s,
            **options,
        )
    except Exception as e:
        raise LLMError(f"{model}: {type(e).__name__}: {e}") from e
    reply = _THINK.sub("", response.choices[0].message.content or "").strip()
    if cached is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"model": model, "think": think, "reply": reply}))
    return reply


def model_digest(model: str | None = None) -> str:
    """The pulled model's digest from Ollama, recorded with every eval run."""
    s = get_settings()
    model = model or s.agent_model
    try:
        with urllib.request.urlopen(f"{s.ollama_base}/api/tags", timeout=5) as response:
            models = json.load(response)["models"]
    except Exception as e:
        raise LLMError(f"{model}: {type(e).__name__}: {e}") from e
    for m in models:
        if m["name"] == model:
            return m["digest"]
    raise LLMError(f"{model}: not pulled")


def embed(texts: list[str]) -> list[list[float]]:
    import litellm

    s = get_settings()
    try:
        response = litellm.embedding(
            model=f"ollama/{s.embed_model}", input=texts, api_base=s.ollama_base, timeout=s.llm_timeout_s
        )
    except Exception as e:
        raise LLMError(f"{s.embed_model}: {type(e).__name__}: {e}") from e
    return [item["embedding"] if isinstance(item, dict) else item.embedding for item in response.data]
