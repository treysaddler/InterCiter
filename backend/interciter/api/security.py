"""FastAPI authentication/authorization dependencies.

Two credential paths resolve to the same ``Principal``:

* ``Authorization: Bearer <token>`` — API/CLI clients. No CSRF (no ambient cookies).
* an ``HttpOnly`` session cookie — the browser BFF path (docs/ui-design.md §11). On
  unsafe methods it additionally requires a matching CSRF header (double-submit).

Reads stay open in the MVP; only writes require a principal, and specific operations
require ``reviewer``/``admin`` or ownership.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..auth import Principal, authenticate_session, authenticate_token, to_principal
from ..config import get_settings
from ..enums import Role
from .deps import db_session

SESSION_COOKIE = "interciter_session"
CSRF_COOKIE = "interciter_csrf"
CSRF_HEADER = "x-csrf-token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_principal(
    request: Request,
    session: Session = Depends(db_session),
) -> Principal:
    # 1. Bearer token (API / CLI). No CSRF: there is no ambient credential to forge.
    token = _bearer(request.headers.get("authorization"))
    if token is not None:
        user = authenticate_token(session, token)
        if user is None:
            raise _unauthorized("invalid token")
        return to_principal(user)

    # 2. Browser session cookie (BFF).
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        settings = get_settings()
        row = authenticate_session(
            session, cookie, idle_timeout_minutes=settings.session_idle_timeout_minutes
        )
        if row is None:
            raise _unauthorized("invalid or expired session")
        if request.method.upper() not in _SAFE_METHODS:
            supplied = request.headers.get(CSRF_HEADER)
            if not supplied or not secrets.compare_digest(supplied, row.csrf_token):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="missing or invalid CSRF token",
                )
        return to_principal(row.user)

    raise _unauthorized("missing or malformed credentials")


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
