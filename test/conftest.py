import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

import app.schemas.models  # noqa: F401  (register tables)
from app.config.settings import make_engine
from app.core.rate_limit import ALL_LIMITERS
from app.dependencies import get_session
from app.main import app
from app.services.email_service import get_email_backend

import app.core.security as security
from argon2 import PasswordHasher

PASSWORD = "correct-horse-1"

# Production uses argon2's strong defaults; tests use a cheap setting so the suite stays fast.
security._hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)


@pytest.fixture
def engine():
    test_engine = make_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def outbox():
    backend = get_email_backend()
    backend.outbox.clear()
    return backend.outbox


@pytest.fixture
def new_client(engine, outbox):
    """Factory for independent browsers (separate cookie jars) talking to the same app and database."""

    def override_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    for limiter in ALL_LIMITERS:
        limiter.clear()
    created: list[TestClient] = []

    def factory() -> TestClient:
        client = TestClient(app)
        created.append(client)
        return client

    yield factory
    app.dependency_overrides.clear()


def token_from_last_email(outbox, to: str) -> str:
    message = [m for m in outbox if m.to == to][-1]
    return re.search(r"token=([^\s&]+)", message.text).group(1)


@pytest.fixture
def signup(new_client, outbox):
    """signup("Ada", "ada@example.com") -> a logged-in client for a verified user."""

    def _signup(name: str, email: str, password: str = PASSWORD) -> TestClient:
        client = new_client()
        assert client.post("/api/auth/register", json={"name": name, "email": email, "password": password}).status_code == 201
        token = token_from_last_email(outbox, email)
        assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
        assert client.post("/api/auth/login", json={"email": email, "password": password}).status_code == 200
        client.email = email
        client.user_id = client.get("/api/me").json()["id"]
        return client

    return _signup


@pytest.fixture
def make_org(signup):
    """make_org(owner_client, "Acme") -> org id."""

    def _make(client: TestClient, name: str) -> int:
        response = client.post("/api/orgs", json={"name": name})
        assert response.status_code == 201, response.text
        return response.json()["organisation"]["id"]

    return _make


@pytest.fixture
def join_org(outbox):
    """join_org(inviter_client, org_id, invitee_client, role) -> invitee joins through a real invitation."""

    def _join(inviter: TestClient, org_id: int, invitee: TestClient, role: str = "member") -> None:
        sent = inviter.post(f"/api/orgs/{org_id}/invitations", json={"email": invitee.email, "role": role})
        assert sent.status_code == 201, sent.text
        accepted = invitee.post(f"/api/me/invitations/{sent.json()['id']}/accept")
        assert accepted.status_code == 200, accepted.text

    return _join
