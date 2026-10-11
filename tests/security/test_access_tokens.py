"""The access token itself: what goes in, what comes back, what is refused.

No stack needed -- these exercise the signing round-trips, not the endpoints.
"""

import jwt
import pytest
from tracker_gateway.core.config import JWT_ACCESS_TTL, JWT_ISSUER, JWT_SECRET
from tracker_gateway.core.security import create_access_token, decode_access_token

USER = {"id": 7, "username": "seven", "email": "seven@example.com"}


def test_a_token_round_trips_its_identity():
    claims = decode_access_token(create_access_token(USER))

    assert claims["sub"] == "7"
    assert claims["username"] == "seven"
    assert claims["email"] == "seven@example.com"
    assert claims["iss"] == JWT_ISSUER


def test_a_token_lives_the_configured_lifetime():
    claims = decode_access_token(create_access_token(USER))

    assert claims["exp"] - claims["iat"] == JWT_ACCESS_TTL


def test_an_expired_token_is_refused():
    token = create_access_token(USER, ttl=-10)

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_a_foreign_signature_is_refused():
    # Signed by someone else: a valid JWT shape that our key did not mint.
    token = jwt.encode({"sub": "7", "exp": 9999999999}, "a-secret-that-is-definitely-not-ours", algorithm="HS256")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_a_foreign_issuer_is_refused():
    # Correctly signed, but by an issuer we did not expect.
    token = jwt.encode({"sub": "7", "iss": "someone-else", "exp": 9999999999}, JWT_SECRET, algorithm="HS256")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_garbage_is_refused():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-token-at-all")
