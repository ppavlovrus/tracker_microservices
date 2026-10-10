"""Process-wide telemetry setup shared by the gateway and the workers.

The tracing configuration is identical in every process that opts in: a
resource naming the process and one exporter sending spans out over OTLP.
The only per-process inputs are the service name and whether asyncpg should
be instrumented -- which is why this lives in common rather than in each
component. Today the gateway and the tasks worker call it; the remaining
workers adopt it as they migrate.

Whoever owns a process lifecycle (the gateway lifespan, each worker's
``main``) calls ``setup_telemetry`` at startup and ``shutdown_telemetry`` at
shutdown, the same init/close pair every other collaborator follows. The
batch processor buffers spans in memory, so a process that exits without
the shutdown call loses whatever had not been flushed yet.
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
from opentelemetry.trace import ProxyTracerProvider

logger = logging.getLogger(__name__)

# Outside compose, jaeger listens on localhost; inside, compose points the
# processes at the service name through OTEL_EXPORTER_OTLP_ENDPOINT.
DEFAULT_ENDPOINT = "http://localhost:4318"


def setup_telemetry(service_name: str, *, instrument_db: bool = False) -> TracerProvider:
    """Install the global tracer provider for this process.

    Sampling stays ALWAYS_ON, which is right for a dev stand: the interesting
    question there is "what did this one request do", not a statistically
    honest sample.

    ``instrument_db=True`` wraps asyncpg globally, so every connection of
    every pool answers with one span per query. The wrap must happen before
    the pool is created: the pool captures the connect callable at birth.
    """
    current = trace.get_tracer_provider()
    if not isinstance(current, ProxyTracerProvider):
        logger.warning("Tracer provider already installed; leaving it alone")
        return current  # type: ignore[return-value]

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or DEFAULT_ENDPOINT

    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name}),
    )
    provider.add_span_processor(_processor(endpoint))
    trace.set_tracer_provider(provider)

    if instrument_db:
        AsyncPGInstrumentor().instrument()

    logger.info(f"Tracing enabled: service={service_name}, endpoint={endpoint}")
    return provider


def shutdown_telemetry() -> None:
    """Flush buffered spans and release the provider; safe to call twice."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()


def _processor(endpoint: str) -> SpanProcessor:
    """Build the batched OTLP span processor for an endpoint.

    The exporter uses an explicit ``endpoint`` verbatim -- only the
    env-variable resolution appends the signal path (verified the hard way:
    a bare base URL answers 404). Compose hands us the base form, so the
    path is appended here, once.
    """
    if not endpoint.rstrip("/").endswith("/v1/traces"):
        endpoint = endpoint.rstrip("/") + "/v1/traces"
    return BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
