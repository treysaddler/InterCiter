"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from ..db import get_session


def db_session() -> Iterator[Session]:
    yield from get_session()
