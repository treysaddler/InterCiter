"""Authentication and authorization.

The design's auth model is deliberately small: a minimal role layer (``user`` /
``reviewer`` / ``admin``) plus **first-class ownership**, modeled from day one because
retrofitting it is painful (docs/architecture.md). Public/community scoring is deferred,
which keeps most identity and abuse surface out of the MVP.

Credentials are opaque bearer tokens. Only a hash of each token is stored, so a database
leak never exposes usable credentials. ``admin`` implies every right.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import models
from .enums import Role
from .ids import new_id


class AuthError(Exception):
    """Base class for authentication/authorization failures."""


class NotAuthenticated(AuthError):
    """No valid credentials were supplied (maps to HTTP 401)."""


class NotAuthorized(AuthError):
    """Authenticated, but lacking the required role/ownership (maps to HTTP 403)."""


@dataclass(frozen=True)
class Principal:
    """A resolved, session-detached identity for the current request."""

    user_id: str
    display_name: str
    role: Role

    def can_act_as(self, *roles: Role) -> bool:
        return self.role is Role.admin or (not roles) or self.role in roles


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user(
    session: Session, display_name: str, role: Role = Role.user
) -> tuple[models.User, str]:
    """Create a user and return the row plus its **raw** token (shown only once)."""
    token = secrets.token_urlsafe(32)
    user = models.User(
        user_id=new_id("User"),
        display_name=display_name,
        role=role,
        api_token_hash=_hash_token(token),
    )
    session.add(user)
    session.commit()
    return user, token


def authenticate_token(session: Session, token: str) -> models.User | None:
    if not token:
        return None
    user = session.scalar(
        select(models.User).where(models.User.api_token_hash == _hash_token(token))
    )
    if user is None or not user.is_active:
        return None
    return user


def to_principal(user: models.User) -> Principal:
    return Principal(
        user_id=user.user_id, display_name=user.display_name, role=user.role
    )


def bootstrap_admin(session: Session, display_name: str = "bootstrap-admin") -> tuple[models.User, str] | None:
    """Create the first admin if no users exist yet. Returns (user, raw_token) or None."""
    exists = session.scalar(select(models.User.user_id).limit(1))
    if exists is not None:
        return None
    return create_user(session, display_name, Role.admin)


# ---------------------------------------------------------------------------------
# Account management
# ---------------------------------------------------------------------------------


def list_users(session: Session) -> list[models.User]:
    return list(
        session.scalars(
            select(models.User).order_by(models.User.created_at.asc())
        ).all()
    )


def get_user(session: Session, user_id: str) -> models.User | None:
    return session.get(models.User, user_id)


def active_admin_count(session: Session, *, excluding: str | None = None) -> int:
    stmt = select(func.count()).select_from(models.User).where(
        models.User.role == Role.admin, models.User.is_active.is_(True)
    )
    if excluding is not None:
        stmt = stmt.where(models.User.user_id != excluding)
    return int(session.scalar(stmt) or 0)


class LastAdminError(AuthError):
    """Refuses an operation that would remove the last active admin (self-lockout)."""


def set_user_role(session: Session, user: models.User, role: Role) -> models.User:
    if user.role is Role.admin and role is not Role.admin and active_admin_count(
        session, excluding=user.user_id
    ) == 0:
        raise LastAdminError("cannot demote the last active admin")
    user.role = role
    session.commit()
    return user


def set_user_active(session: Session, user: models.User, active: bool) -> models.User:
    if not active and user.role is Role.admin and active_admin_count(
        session, excluding=user.user_id
    ) == 0:
        raise LastAdminError("cannot deactivate the last active admin")
    user.is_active = active
    if not active:
        revoke_user_sessions(session, user.user_id)
    session.commit()
    return user


def rotate_api_token(session: Session, user: models.User) -> str:
    """Issue a fresh token (invalidating the old one) and drop the user's sessions."""
    token = secrets.token_urlsafe(32)
    user.api_token_hash = _hash_token(token)
    revoke_user_sessions(session, user.user_id)
    session.commit()
    return token


# ---------------------------------------------------------------------------------
# Browser sessions (BFF — docs/ui-design.md §11)
# ---------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat stored timestamps as UTC for comparison."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def create_session(
    session: Session, user: models.User, *, absolute_lifetime_hours: int
) -> tuple[models.UserSession, str]:
    """Create a server-side session. Returns the row and the **raw** cookie secret."""
    secret = secrets.token_urlsafe(32)
    now = _now()
    row = models.UserSession(
        session_id=new_id("UserSession"),
        user_id=user.user_id,
        session_hash=_hash_token(secret),
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=now + timedelta(hours=absolute_lifetime_hours),
    )
    session.add(row)
    session.commit()
    return row, secret


def authenticate_session(
    session: Session, secret: str, *, idle_timeout_minutes: int
) -> models.UserSession | None:
    """Resolve a cookie secret to a live session, enforcing idle + absolute timeouts.

    Expired, idle, or deactivated-owner sessions are revoked and treated as absent.
    On success, ``last_seen_at`` is refreshed (sliding idle window).
    """
    if not secret:
        return None
    row = session.scalar(
        select(models.UserSession).where(
            models.UserSession.session_hash == _hash_token(secret)
        )
    )
    if row is None:
        return None
    now = _now()
    idle_cutoff = _as_aware(row.last_seen_at) + timedelta(minutes=idle_timeout_minutes)
    if now >= _as_aware(row.absolute_expires_at) or now >= idle_cutoff:
        revoke_session(session, row)
        return None
    if not row.user.is_active:
        revoke_session(session, row)
        return None
    row.last_seen_at = now
    session.commit()
    return row


def revoke_session(session: Session, row: models.UserSession) -> None:
    session.delete(row)
    session.commit()


def revoke_session_by_secret(session: Session, secret: str) -> None:
    if not secret:
        return
    row = session.scalar(
        select(models.UserSession).where(
            models.UserSession.session_hash == _hash_token(secret)
        )
    )
    if row is not None:
        revoke_session(session, row)


def revoke_user_sessions(session: Session, user_id: str) -> None:
    session.execute(
        delete(models.UserSession).where(models.UserSession.user_id == user_id)
    )
