"""OpenTelemetry tracing to Phoenix: one trace per agent run, with graph-node and LLM-call spans.

Plain OpenTelemetry plus OpenInference instrumentors, because arize-phoenix-otel needs
Python 3.11. Off unless TDA_TRACING=1. The exporter times out after 3 s, so a stopped
Phoenix never blocks the agent.
"""

from opentelemetry import trace

from tda.config import get_settings

_provider = None
_instrumentors: list = []


def setup_tracing(endpoint: str | None = None, project: str = "tda") -> bool:
    global _provider
    if _provider is not None:
        return True
    if not get_settings().tracing:
        return False
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"openinference.project.name": project, "service.name": project}))
    exporter = OTLPSpanExporter(endpoint=endpoint or get_settings().phoenix_endpoint, timeout=3)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    for instrumentor in (LangChainInstrumentor(), LiteLLMInstrumentor()):
        instrumentor.instrument(tracer_provider=provider)
        _instrumentors.append(instrumentor)
    _provider = provider
    return True


def active() -> bool:
    return _provider is not None


def get_tracer(name: str = "tda") -> trace.Tracer:
    return _provider.get_tracer(name) if _provider is not None else trace.get_tracer(name)


def shutdown_tracing() -> None:
    """Flush pending spans and remove the instrumentation. Safe to call when tracing is off."""
    global _provider
    if _provider is None:
        return
    _provider.shutdown()
    for instrumentor in _instrumentors:
        instrumentor.uninstrument()
    _instrumentors.clear()
    _provider = None
