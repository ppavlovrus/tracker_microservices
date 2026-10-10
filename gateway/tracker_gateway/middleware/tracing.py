"""One span per HTTP request, continuing the caller's trace when there is one.

Hand-rolled after the mentor's template rather than
opentelemetry-instrumentation-fastapi: the span holds exactly the four facts
we show in demos, and it adds no dependency. The one deliberate addition
over the template is ``extract``: an incoming ``traceparent`` header (from
curl, or from another service some day) continues that trace instead of
starting a fresh one at the edge.
"""

import logging

from opentelemetry import propagate, trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """Wrap every HTTP request in an OpenTelemetry span."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Open a span around the whole request, parented by the caller's context."""
        span_name = f"{request.method} {request.url.path}"

        # Starlette's Headers.get is case-insensitive, which is what the
        # propagator's lookup needs; a plain dict would miss "Traceparent"
        # as HTTP/1.1 spells it.
        context = propagate.extract(request.headers)

        with tracer.start_as_current_span(span_name, context=context) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.route", request.url.path)

            response: Response = await call_next(request)

            span.set_attribute("http.status_code", response.status_code)

            if response.status_code >= 500:
                span.set_status(trace.StatusCode.ERROR)

            return response
