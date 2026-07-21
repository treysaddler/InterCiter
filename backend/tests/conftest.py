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

from interciter.db import SessionLocal, engine  # noqa: E402
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


def load_sample(name: str) -> str:
    from importlib import resources

    return (
        resources.files("interciter.data.sample")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
