"""Session authentication middleware.

Reads are public; state-changing requests need a valid session cookie. The
check fails closed: with the session store down, writes are rejected rather
than waved through.
"""

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..core.config import AUTH_ENABLED, SESSION_COOKIE_NAME

# The module, not the name: ``sessions.session_store`` is filled by the
# lifespan long after this module is imported, so binding the value here would
# freeze it at None.
from ..storage import sessions

# HTTP methods that mutate state and therefore require authentication.
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# Write paths that must stay open (the login/logout endpoints themselves).
AUTH_EXEMPT_WRITE = ("/auth/login", "/auth/logout")


def _requires_auth(method: str, path: str) -> bool:
    """Return True if the request is a state-changing call that needs a session."""
    return method in WRITE_METHODS and path not in AUTH_EXEMPT_WRITE


class AuthMiddleware(BaseHTTPMiddleware):
    """Require a valid session for state-changing requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        store = sessions.session_store
        if AUTH_ENABLED and store is not None and _requires_auth(request.method, request.url.path):
            token = request.cookies.get(SESSION_COOKIE_NAME)
            user = await store.get(token) if token else None
            if user is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )

        return await call_next(request)
