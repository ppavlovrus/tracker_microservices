import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..core.exceptions import (
    AttachmentNotFoundError,
    BusProtocolError,
    BusTimeoutError,
    BusUnavailableError,
    CommentNotFoundError,
    CreatorNotFoundError,
    EmailTakenError,
    GatewayError,
    InvalidCredentialsError,
    SessionStoreUnavailableError,
    StatusNotFoundError,
    TagNameTakenError,
    TagNotFoundError,
    TaskNotFoundError,
    UpstreamFailureError,
    UserHasTasksError,
    UsernameTakenError,
    UserNotFoundError,
)

logger = logging.getLogger(__name__)

# Domain error -> what the HTTP client is told. The wording is API surface:
# the client knows about the resources, not about a bus or a worker. The
# timeout wording is deliberately service-neutral: one exception type serves
# every bus client, so it cannot name the service that went quiet.
STATUS: dict[type[GatewayError], tuple[int, str]] = {
    TaskNotFoundError: (404, "Task not found"),
    # A body that names a row nobody answers to. Not a 404: the addressed
    # resource is fine, it is the reference inside the request that is not.
    CreatorNotFoundError: (400, "Unknown creator_id"),
    StatusNotFoundError: (400, "Unknown status_id"),
    UserNotFoundError: (404, "User not found"),
    EmailTakenError: (409, "Email already exists"),
    UsernameTakenError: (409, "Username already exists"),
    UserHasTasksError: (409, "User still has tasks"),
    TagNotFoundError: (404, "Tag not found"),
    TagNameTakenError: (409, "Tag with this name already exists"),
    CommentNotFoundError: (404, "Comment not found"),
    AttachmentNotFoundError: (404, "Attachment not found"),
    InvalidCredentialsError: (401, "Invalid username or password"),
    SessionStoreUnavailableError: (503, "Session backend unavailable"),
    BusUnavailableError: (503, "Service temporarily unavailable"),
    BusTimeoutError: (504, "Upstream service timeout"),
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
