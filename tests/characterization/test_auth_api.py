"""Characterization of the two authentication paths: cookie and Bearer.

The expectations were recorded from a live run, not designed. If one of them
turns red during a refactor, the refactor changed behaviour -- decide whether
that was intended before touching the assertion.
"""

from datetime import UTC, datetime, timedelta

import jwt as forged_jwt
from contracts import LoginResponseContract, UserPublicContract

# The signing secret and issuer are settings, not behaviour: the test forges
# tokens with them the way an attacker who knew both would. They are read
# from the config defaults, which only works while the test runner and the
# stand agree on the environment -- a mismatch shows up as confusing reds.
from tracker_gateway.core.config import JWT_ISSUER, JWT_SECRET


async def _login_token(client) -> str:
    response = await client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert response.status_code == 200, response.text
    return LoginResponseContract.model_validate(response.json()).access_token


async def test_login_answers_an_access_token_besides_the_cookie(auth_client):
    response = await auth_client.post("/auth/login", json={"username": "admin", "password": "admin"})

    assert response.status_code == 200
    body = LoginResponseContract.model_validate(response.json())
    assert body.user.username == "admin"
    assert body.access_token
    # The browser's half is unchanged: the cookie is still set.
    assert len(response.cookies.jar) >= 1


async def test_a_bearer_token_authenticates_a_write_without_any_cookie(client, trash):
    token = await _login_token(client)

    response = await client.post(
        "/tasks",
        json={"title": "bearer probe", "creator_id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text
    trash.append(response.json()["id"])


async def test_an_expired_bearer_answers_401(client):
    # Forged independently: correctly signed, already expired.
    now = datetime.now(UTC)
    expired = forged_jwt.encode(
        {"iss": JWT_ISSUER, "sub": "1", "username": "admin", "iat": now - timedelta(minutes=30),
         "exp": now - timedelta(minutes=15)},
        JWT_SECRET,
        algorithm="HS256",
    )

    response = await client.post(
        "/tasks",
        json={"title": "expired probe", "creator_id": 1},
        headers={"Authorization": f"Bearer {expired}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token expired"


async def test_a_tampered_bearer_answers_401(client):
    response = await client.post(
        "/tasks",
        json={"title": "tampered probe", "creator_id": 1},
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.not-our-signature"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


async def test_me_answers_to_a_bearer_token(client):
    token = await _login_token(client)

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    user = UserPublicContract.model_validate(response.json())
    assert user.username == "admin"


async def test_a_non_bearer_scheme_falls_back_to_the_cookie(auth_client, trash):
    # A client speaking a scheme we do not must not lose its cookie path:
    # the Bearer branch only claims requests that actually carry a Bearer.
    response = await auth_client.post(
        "/tasks",
        json={"title": "scheme probe", "creator_id": 1},
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )

    assert response.status_code == 201, response.text
    trash.append(response.json()["id"])


async def test_me_with_a_garbage_bearer_stays_generic(client):
    # The distinct expired/invalid wording belongs to the middleware, which
    # serves clients that act on it; /me is a binary "who am I" and stays
    # generic even for a token that does not parse.
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


async def test_me_still_answers_to_the_cookie(auth_client):
    response = await auth_client.get("/auth/me")

    assert response.status_code == 200
    user = UserPublicContract.model_validate(response.json())
    assert user.username == "admin"
