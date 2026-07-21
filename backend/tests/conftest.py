"""Test fixtures.

The database engine is module-level, so the test database URL is set *before* the
package is imported. Each test gets a freshly created schema.
"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="interciter-test-")
os.environ["INTERCITER_DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from interciter import auth  # noqa: E402
from interciter.db import SessionLocal, engine  # noqa: E402
from interciter.enums import Role  # noqa: E402
from interciter.models import Base  # noqa: E402
from interciter.api.app import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user():
    def _make(role: Role = Role.user, name: str = "tester") -> tuple[str, dict]:
        with SessionLocal() as db:
            user, token = auth.create_user(db, name, role)
            return user.user_id, {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
def user_headers(make_user):
    return make_user(Role.user, "user1")[1]


@pytest.fixture
def reviewer_headers(make_user):
    return make_user(Role.reviewer, "reviewer1")[1]


@pytest.fixture
def admin_headers(make_user):
    return make_user(Role.admin, "admin1")[1]


def load_sample(name: str) -> str:
    from importlib import resources

    return (
        resources.files("interciter.data.sample")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
