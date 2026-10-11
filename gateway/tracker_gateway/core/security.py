"""Credentials: password hashing and the JWT access tokens.

Everything about proving who a caller is lives in one place, next to its
owner, the way the mentor's template keeps ``src/core/security.py``: the
bcrypt rounds for passwords and the signing key for tokens. Services call
these helpers; no layer above them sees a plaintext password or the secret.

HS256 on purpose: the same gateway signs and verifies, so there is one
secret and no key pair to distribute. RS256 earns its keep the day a second
process must verify tokens without being allowed to mint them.

Access tokens are stateless: logout deletes the session, not the token,
which stays valid until it expires. Revocation would take a denylist keyed
by ``jti`` -- that is a discussion to have, not a default to ship.
"""

from datetime import UTC, datetime
from typing import Any

import bcrypt
import jwt

from .config import JWT_ACCESS_TTL, JWT_ISSUER, JWT_SECRET

# A real bcrypt hash used as a constant-time decoy when the username is
# unknown, so a failed login does the same work whether or not the user exists.
DUMMY_HASH = "$2b$12$oOUmtFn7fm50bdt91.qyEelpY.SIYTtITMl8s4/O4evApDalGS.R2"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Blocking; call via a thread."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time bcrypt check. Never raises on a malformed or empty hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def bearer_token(authorization: str | None) -> str | None:
    """The token out of an ``Authorization: Bearer <token>`` header value.

    None when the header is absent or names another scheme: the caller then
    falls back to whatever the second authentication path is.
    """
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def create_access_token(user: dict[str, Any], *, ttl: int = JWT_ACCESS_TTL) -> str:
    """Sign a short-lived access token carrying the session's identity shape.

    ``user`` is the shape a session record is created from -- ``id``,
    ``username``, ``email`` -- so a token and a session are interchangeable
    identities downstream. ``ttl`` exists for tests; everything else uses
    the configured lifetime.
    """
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "iss": JWT_ISSUER,
        # JWT convention: ``sub`` is a string.
        "sub": str(user["id"]),
        "username": user["username"],
        "email": user["email"],
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify a token's signature, issuer and expiry, and return its claims.

    Raises ``jwt.ExpiredSignatureError`` or ``jwt.InvalidTokenError``; the
    caller decides what that means on its wire.
    """
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
