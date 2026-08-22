import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..core.exceptions import (
    BusProtocolError,
    BusTimeoutError,
    BusUnavailableError,
    GatewayError,
    TaskNotFoundError,
    UpstreamFailureError,
)

logger = logging.getLogger(__name__)

# Domain error -> what the HTTP client is told. The wording is API surface:
# the client knows about a tasks service, not about a bus or a worker.
STATUS: dict[type[GatewayError], tuple[int, str]] = {
    TaskNotFoundError: (404, "Task not found"),
    BusUnavailableError: (503, "Service temporarily unavailable"),
    BusTimeoutError: (504, "Tasks service timeout"),
    BusProtocolError: (500, "Internal server error"),
    UpstreamFailureError: (500, "Internal server error"),
}

FALLBACK = (500, "Internal server error")


async def handle_gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
    """Translate a domain error into an HTTP answer, and leave a trace of it."""
    status, detail = STATUS.get(type(exc), FALLBACK)

    # str(exc) is the operator's half of the story and stays here; `detail` is
    # the client's half and comes from the table.
    if status >= 500:
        logger.error(f"{request.method} {request.url.path} -> {status}: {exc}")
    else:
        logger.debug(f"{request.method} {request.url.path} -> {status}: {exc}")

    return JSONResponse(status_code=status, content={"detail": detail})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(GatewayError, handle_gateway_error)
