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

from sqlalchemy import select
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
    return session.scalar(
        select(models.User).where(models.User.api_token_hash == _hash_token(token))
    )


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
