import io
import json
import types
import urllib.request

import litellm
import pytest

from tda.config import get_settings
from tda.llm import LLMError, chat, embed, model_digest


def _fake_completion(sent: dict, content: str = "<think>hmm</think>\n select 1 from dual "):
    def completion(**kwargs):
        sent.update(kwargs)
        message = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    return completion


def test_litellm_uses_bundled_cost_map():
    # Without this, every litellm import tries to download a price list from GitHub,
    # which stalls on networks where GitHub is slow or IPv4 is missing.
    import os

    import tda  # noqa: F401

    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True"


def test_chat_forwards_think_and_timeout(monkeypatch):
    sent: dict = {}
    monkeypatch.setattr(litellm, "completion", _fake_completion(sent))
    chat("q", think=False)
    assert sent["think"] is False
    assert sent["timeout"] == 300.0
    assert sent["model"] == "ollama_chat/qwen3:8b"
    assert (sent["temperature"], sent["seed"]) == (0, 42)


def test_chat_sets_context_window_and_generation_cap(monkeypatch):
    # Ollama's default 4096-token context made long thinking runs shift out the start of the
    # prompt (instructions, schema, question) on Day 3; the cap ends a runaway run before the window fills.
    sent: dict = {}
    monkeypatch.setattr(litellm, "completion", _fake_completion(sent))
    chat("q", think=True)
    assert (sent["num_ctx"], sent["max_tokens"]) == (8192, 7000)
    assert sent["max_tokens"] + 1024 <= sent["num_ctx"]  # room for the longest prompt (about 800 tokens)


def test_chat_strips_thinking(monkeypatch):
    monkeypatch.setattr(litellm, "completion", _fake_completion({}))
    assert chat("q", think=True) == "select 1 from dual"


def test_chat_wraps_errors(monkeypatch):
    def refuse(**kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(litellm, "completion", refuse)
    with pytest.raises(LLMError) as err:
        chat("q", think=False)
    assert "qwen3:8b" in str(err.value) and "ConnectionError" in str(err.value)


def test_embed_returns_vectors(monkeypatch):
    sent: dict = {}

    def embedding(**kwargs):
        sent.update(kwargs)
        return types.SimpleNamespace(data=[{"embedding": [0.1, 0.2]}])

    monkeypatch.setattr(litellm, "embedding", embedding)
    assert embed(["text"]) == [[0.1, 0.2]]
    assert sent["model"] == "ollama/nomic-embed-text"
    assert sent["input"] == ["text"]


def test_embed_wraps_errors(monkeypatch):
    def refuse(**kwargs):
        raise TimeoutError("slow")

    monkeypatch.setattr(litellm, "embedding", refuse)
    with pytest.raises(LLMError) as err:
        embed(["text"])
    assert "nomic-embed-text" in str(err.value)


@pytest.fixture
def cache_dir(monkeypatch, tmp_path):
    """Turn the response cache on for one test; the settings cache is cleared around it."""
    get_settings.cache_clear()
    monkeypatch.setenv("TDA_LLM_CACHE", str(tmp_path))
    yield tmp_path
    get_settings.cache_clear()


def _counting_completion(calls: list, replies: list):
    def completion(**kwargs):
        calls.append(kwargs)
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(reply, Exception):
            raise reply
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=reply))])

    return completion


def test_cache_hit_skips_model(monkeypatch, cache_dir):
    calls: list = []
    monkeypatch.setattr(litellm, "completion", _counting_completion(calls, ["select 1 from dual"]))
    assert chat("q", think=True) == chat("q", think=True) == "select 1 from dual"
    assert len(calls) == 1


def test_cache_key_includes_model_and_think(monkeypatch, cache_dir):
    calls: list = []
    monkeypatch.setattr(litellm, "completion", _counting_completion(calls, ["x"]))
    chat("q", think=True)
    chat("q", think=False)
    chat("q", think=True, model="other:1b")
    assert len(calls) == 3


def test_cache_key_includes_generation_options(monkeypatch, cache_dir):
    # Replies made with another context window are another measurement.
    calls: list = []
    monkeypatch.setattr(litellm, "completion", _counting_completion(calls, ["x"]))
    chat("q", think=True)
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_NUM_CTX", "4096")
    chat("q", think=True)
    assert len(calls) == 2


def test_errors_are_not_cached(monkeypatch, cache_dir):
    # A cached failure would repeat on every re-run of the eval.
    calls: list = []
    monkeypatch.setattr(litellm, "completion", _counting_completion(calls, [ConnectionError("down"), "ok"]))
    with pytest.raises(LLMError):
        chat("q", think=False)
    assert chat("q", think=False) == "ok"
    assert len(calls) == 2
    assert len(list(cache_dir.glob("*.json"))) == 1


def _fake_tags(monkeypatch, models: list[dict]):
    body = json.dumps({"models": models}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: io.BytesIO(body))


def test_model_digest_reads_tags(monkeypatch):
    _fake_tags(monkeypatch, [{"name": "nomic-embed-text:latest", "digest": "e1"}, {"name": "qwen3:8b", "digest": "abc123"}])
    assert model_digest("qwen3:8b") == "abc123"


def test_model_digest_unknown_model_raises(monkeypatch):
    # An hour-long eval must stop before the first case if its model is not pulled.
    _fake_tags(monkeypatch, [{"name": "qwen3:8b", "digest": "abc123"}])
    with pytest.raises(LLMError, match="not pulled"):
        model_digest("ornith-1.5:9b")
