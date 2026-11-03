import time

import pytest

from tda import tracing
from tda.config import get_settings


@pytest.fixture
def settings_env(monkeypatch):
    """Let a test flip TDA_TRACING; the settings cache is cleared before and after."""
    get_settings.cache_clear()
    yield monkeypatch
    tracing.shutdown_tracing()
    get_settings.cache_clear()


def test_tracing_off_by_default(settings_env):
    settings_env.delenv("TDA_TRACING", raising=False)
    assert tracing.setup_tracing() is False
    assert tracing.active() is False


def test_tracing_on_with_dead_endpoint_does_not_raise(settings_env):
    settings_env.setenv("TDA_TRACING", "1")
    assert tracing.setup_tracing(endpoint="http://127.0.0.1:9/v1/traces") is True
    with tracing.get_tracer().start_as_current_span("probe"):
        pass
    started = time.monotonic()
    tracing.shutdown_tracing()  # flushes the span to the dead endpoint: must give up, not hang
    assert time.monotonic() - started < 10
    assert tracing.active() is False
