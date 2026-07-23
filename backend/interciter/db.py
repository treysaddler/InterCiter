"""Database engine and session management.

The write model is a normalized relational store (PostgreSQL in production, SQLite
for local dev). ``init_db`` creates tables for the MVP; a real deployment would use
migrations (e.g. Alembic) instead of ``create_all``.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Base

_settings = get_settings()

_connect_args = (
    {"check_same_thread": False}
    if _settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    _settings.database_url,
    echo=_settings.echo_sql,
    connect_args=_connect_args,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables. Idempotent; safe to call on startup for the MVP."""
    Base.metadata.create_all(bind=engine)
    _apply_additive_columns()


def _apply_additive_columns() -> None:
    """Add columns the models have gained since a table was first created.

    ``create_all`` never alters existing tables, and the MVP has no migration
    tool, so purely additive nullable columns are applied here by comparing each
    mapped table against the live database.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                ddl = (
                    f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" '
                    f"{column.type.compile(engine.dialect)}"
                )
                conn.execute(text(ddl))


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
