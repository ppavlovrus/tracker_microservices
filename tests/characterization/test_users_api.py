"""Characterization of the users HTTP API as it behaves today.

Written right after the updated_at migration un-broke the vertical: until then
every /users read and write answered 500, so these are the first tests this
API has ever had. Expectations were recorded from a live run, not designed.

The auth invariants at the bottom are the part worth reading twice: login must
answer the same thing for an unknown username and for a wrong password, and no
response anywhere may carry a password hash.
"""

from contracts import LoginResponseContract, UserContract, UserListContract


async def test_create_user_returns_201_without_password_hash(auth_client, make_user):
    user, payload = await make_user()

    # UserContract has extra="forbid": if password_hash (or anything else)
    # were in the body, make_user's validation would already have failed.
    assert user.username == payload["username"]
    assert user.email == payload["email"]


async def test_create_user_without_session_returns_401(client):
    payload = {
        "username": "no_session_probe",
        "email": "no_session_probe@example.com",
        "password": "probe-pass-123",
    }
    # Registration is a write like any other: without a session the middleware
    # answers 401 before the router ever sees the body.
    response = await client.post("/users", json=payload)
    assert response.status_code == 401


async def test_duplicate_email_returns_409(auth_client, make_user):
    _, payload = await make_user()

    clone = {
        "username": payload["username"] + "_clone",
        "email": payload["email"],
        "password": "probe-pass-123",
    }
    response = await auth_client.post("/users", json=clone)
    assert response.status_code == 409
    assert response.json()["detail"] == "Email already exists"


async def test_update_to_taken_email_returns_409(auth_client, make_user):
    _, victim_payload = await make_user()
    other, _ = await make_user()

    response = await auth_client.put(f"/users/{other.id}", json={"email": victim_payload["email"]})
    assert response.status_code == 409
    assert response.json()["detail"] == "Email already exists"


async def test_get_missing_user_returns_404(auth_client, make_user):
    user, _ = await make_user()
    deleted = await auth_client.delete(f"/users/{user.id}")
    assert deleted.status_code == 204

    response = await auth_client.get(f"/users/{user.id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


async def test_delete_missing_user_returns_404(auth_client, make_user):
    user, _ = await make_user()
    first = await auth_client.delete(f"/users/{user.id}")
    assert first.status_code == 204

    second = await auth_client.delete(f"/users/{user.id}")
    assert second.status_code == 404


async def test_list_users_envelope_and_delta(auth_client, make_user):
    before = UserListContract.model_validate((await auth_client.get("/users")).json())

    user, _ = await make_user()

    response = await auth_client.get("/users")
    assert response.status_code == 200
    after = UserListContract.model_validate(response.json())

    # Delta, not absolutes: the database may hold anyone else's users.
    assert after.total - before.total == 1
    # Newest-first ordering puts the fresh user on the first page.
    assert user.id in {listed.id for listed in after.users}


async def test_update_username_round_trips(auth_client, make_user):
    user, _ = await make_user()
    new_name = f"{user.username}_renamed"

    response = await auth_client.put(f"/users/{user.id}", json={"username": new_name})
    assert response.status_code == 200
    updated = UserContract.model_validate(response.json())
    assert updated.username == new_name
    # A partial update touches what it names and nothing else.
    assert updated.email == user.email

    reread = await auth_client.get(f"/users/{user.id}")
    assert reread.status_code == 200
    assert UserContract.model_validate(reread.json()).username == new_name


async def test_login_unknown_user_and_wrong_password_are_indistinguishable(client, make_user):
    user, _ = await make_user()

    wrong_password = await client.post("/auth/login", json={"username": user.username, "password": "definitely-wrong"})
    unknown_user = await client.post(
        "/auth/login", json={"username": "no_such_user_anywhere", "password": "definitely-wrong"}
    )

    # The two failures must be one failure to the outside: a difference in
    # status or body would let a caller enumerate valid usernames.
    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["detail"] == "Invalid username or password"


async def test_login_with_created_user_succeeds(client, make_user):
    user, payload = await make_user()

    response = await client.post("/auth/login", json={"username": payload["username"], "password": payload["password"]})
    assert response.status_code == 200

    body = LoginResponseContract.model_validate(response.json())
    assert body.user.id == user.id
    assert body.user.username == payload["username"]
    assert body.user.email == payload["email"]
    assert response.cookies.get("session") is not None
