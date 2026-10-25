import pytest

from test.conftest import PASSWORD, token_from_last_email


def register(client, email="ada@example.com", name="Ada", password=PASSWORD, **extra):
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password, **extra})


def test_email_is_validated_and_normalised(new_client, outbox):
    client = new_client()
    for bad in ["plainaddress", "a@", "@example.com", "a b@example.com", "a@@example.com"]:
        response = register(client, email=bad)
        assert response.status_code == 422, bad
        assert "email" in response.json()["fields"]

    assert register(client, email="  Ada@Example.COM ").status_code == 201
    assert outbox[-1].to == "ada@example.com"
    # the same address in a different case is the same account
    assert register(client, email="ADA@example.com").status_code == 409


@pytest.mark.parametrize("password", ["short1", "allletters", "12345678"])
def test_weak_passwords_are_rejected(new_client, password):
    response = register(new_client(), password=password)
    assert response.status_code == 422
    assert "password" in response.json()["fields"]


def test_login_requires_verified_email(new_client, outbox):
    client = new_client()
    register(client)
    blocked = client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "email_not_verified"

    token = token_from_last_email(outbox, "ada@example.com")
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    # a verification link works once
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 200
    assert client.get("/api/me").json()["email_verified"] is True


def test_resending_verification_invalidates_the_old_link(new_client, outbox):
    client = new_client()
    register(client)
    first = token_from_last_email(outbox, "ada@example.com")
    assert client.post("/api/auth/resend-verification", json={"email": "ada@example.com"}).status_code == 202
    second = token_from_last_email(outbox, "ada@example.com")
    assert first != second
    assert client.post("/api/auth/verify-email", json={"token": first}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200


def test_resend_does_not_reveal_whether_an_account_exists(new_client, outbox):
    client = new_client()
    response = client.post("/api/auth/resend-verification", json={"email": "ghost@example.com"})
    assert response.status_code == 202
    assert outbox == []


def test_registering_cannot_choose_a_role(signup, new_client):
    client = new_client()
    response = register(client, role="lead", is_admin=True)
    assert response.status_code == 201  # unknown fields are ignored, never applied
    user = signup("Bob", "bob@example.com")
    assert user.get("/api/me/organisations").json() == []


def test_wrong_password_and_unknown_user_look_the_same(signup, new_client):
    signup("Ada", "ada@example.com")
    client = new_client()
    wrong = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "nope-nope-1"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "nope-nope-1"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_logout_ends_the_session_for_real(signup):
    client = signup("Ada", "ada@example.com")
    stolen_refresh = client.cookies.get("refresh_token")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401
    client.cookies.set("refresh_token", stolen_refresh, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401  # the server-side session is gone


def test_refresh_rotates_and_detects_replay(signup, new_client):
    client = signup("Ada", "ada@example.com")
    old = client.cookies.get("refresh_token")
    assert client.post("/api/auth/refresh").status_code == 200
    new = client.cookies.get("refresh_token")
    assert new != old

    thief = new_client()
    thief.cookies.set("refresh_token", old, path="/api/auth")
    assert thief.post("/api/auth/refresh").status_code == 401
    # replaying a rotated token is treated as theft: every session for the account is revoked
    assert client.post("/api/auth/refresh").status_code == 401


def test_endpoints_need_authentication(new_client):
    client = new_client()
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/orgs/1").status_code == 401
    assert client.get("/api/me/todos").status_code == 401


def test_password_reset_flow(signup, new_client, outbox):
    ada = signup("Ada", "ada@example.com")
    client = new_client()
    assert client.post("/api/auth/forgot-password", json={"email": "ada@example.com"}).status_code == 202
    token = token_from_last_email(outbox, "ada@example.com")
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "brand-new-pass-2"}).status_code == 204
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "another-pass-3"}).status_code == 400
    assert ada.post("/api/auth/refresh").status_code == 401  # old sessions were revoked
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "brand-new-pass-2"}).status_code == 200


def test_login_is_rate_limited(signup, new_client):
    signup("Ada", "ada@example.com")
    client = new_client()
    codes = [
        client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-pass-1"}).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_change_password_keeps_this_device_signed_in(signup, new_client):
    ada = signup("Ada", "ada@example.com")
    other_device = new_client()
    other_device.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct-horse-1"})
    bad = ada.post("/api/auth/change-password", json={"current_password": "wrong", "new_password": "new-secret-pass-9"})
    assert bad.status_code == 400
    ok = ada.post("/api/auth/change-password", json={"current_password": "correct-horse-1", "new_password": "new-secret-pass-9"})
    assert ok.status_code == 204
    assert ada.post("/api/auth/refresh").status_code == 200
    assert other_device.post("/api/auth/refresh").status_code == 401
