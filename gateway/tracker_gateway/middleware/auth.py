"""Authentication middleware: a session cookie or a Bearer token.

Reads are public; state-changing requests must prove who they are, in either
of two ways. The browser sends the session cookie -- it cannot set headers on
a WebSocket or an EventSource, and a redirect flow cannot hand it a token.
An API client sends ``Authorization: Bearer <jwt>``: stateless, so it keeps
working with the session backend down, and it expires on its own.

The check fails closed: with neither proof, writes are rejected rather than
waved through.
"""

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..core.config import AUTH_ENABLED, SESSION_COOKIE_NAME
from ..core.security import bearer_token, decode_access_token

# The module, not the name: ``sessions.session_store`` is filled by the
# lifespan long after this module is imported, so binding the value here would
# freeze it at None.
from ..storage import sessions

# HTTP methods that mutate state and therefore require authentication.
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# Write paths that must stay open (the login/logout endpoints themselves).
AUTH_EXEMPT_WRITE = ("/auth/login", "/auth/logout")


def _requires_auth(method: str, path: str) -> bool:
    """Return True if the request is a state-changing call that needs a proof."""
    return method in WRITE_METHODS and path not in AUTH_EXEMPT_WRITE


class AuthMiddleware(BaseHTTPMiddleware):
    """Require a valid session cookie or Bearer token for state-changing requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if AUTH_ENABLED and _requires_auth(request.method, request.url.path):
            token = bearer_token(request.headers.get("Authorization"))
            if token is not None:
                try:
                    decode_access_token(token)
                except jwt.ExpiredSignatureError:
                    return JSONResponse(status_code=401, content={"detail": "Token expired"})
                except jwt.InvalidTokenError:
                    return JSONResponse(status_code=401, content={"detail": "Invalid token"})
                return await call_next(request)

            store = sessions.session_store
            if store is not None:
                cookie = request.cookies.get(SESSION_COOKIE_NAME)
                user = await store.get(cookie) if cookie else None
                if user is None:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Authentication required"},
                    )

        return await call_next(request)
