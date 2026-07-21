"""FastAPI authentication/authorization dependencies.

Reads a ``Authorization: Bearer <token>`` header, resolves it to a ``Principal``, and
enforces the minimal role model. Reads stay open in the MVP; only writes require a
principal, and specific operations require ``reviewer``/``admin`` or ownership.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import Principal, authenticate_token, to_principal
from ..enums import Role
from .deps import db_session


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def get_principal(
    authorization: str | None = Header(default=None),
    session: Session = Depends(db_session),
) -> Principal:
    token = _bearer(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = authenticate_token(session, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return to_principal(user)


def require_roles(*roles: Role) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.can_act_as(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires one of roles: {', '.join(r.value for r in roles)}",
            )
        return principal

    return dependency


# Any authenticated user.
require_user = get_principal
# reviewer or admin.
require_reviewer = require_roles(Role.reviewer)
# admin only.
require_admin = require_roles(Role.admin)
