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
                if column.name in existing:
                    continue
                ddl = (
                    f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" '
                    f"{column.type.compile(engine.dialect)}"
                )
                if not column.nullable:
                    server_default = _default_literal(column)
                    if server_default is None:
                        # No safe fill value for existing rows — leave for a real
                        # migration rather than guessing.
                        continue
                    ddl += f" DEFAULT {server_default} NOT NULL"
                conn.execute(text(ddl))


def _default_literal(column) -> str | None:
    """SQL literal for a column's Python-side default, or None if underivable."""
    default = column.default
    if default is None:
        return None
    if default.is_callable:
        # mapped_column(default=list/dict) — empty JSON container.
        origin = getattr(default, "arg", None)
        # SQLAlchemy wraps the callable; unwrap common empty-container factories.
        wrapped = getattr(origin, "__wrapped__", origin)
        if wrapped is list:
            return "'[]'"
        if wrapped is dict:
            return "'{}'"
        return None
    if not default.is_scalar:
        return None
    value = default.arg
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
