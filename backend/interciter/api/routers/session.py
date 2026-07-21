"""Browser session endpoints — the BFF boundary (docs/ui-design.md §11).

The single-page app authenticates once by POSTing a raw API token (sent over TLS,
never persisted in the browser). The server validates it, opens a server-side
session, and sets an ``HttpOnly`` session cookie plus a readable CSRF cookie. From
then on the browser holds only opaque cookies; the token is discarded client-side.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ... import auth
from ...auth import Principal
from ...config import get_settings
from ...schemas import LoginRequest, SessionInfo
from ..deps import db_session
from ..security import CSRF_COOKIE, SESSION_COOKIE, require_user

router = APIRouter()


def _set_session_cookies(
    response: Response, secret: str, csrf_token: str, *, max_age: int, secure: bool
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        secret,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    # Readable by JS so the SPA can echo it in the CSRF header (double-submit).
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/auth/login", response_model=SessionInfo)
def login(
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(db_session),
) -> SessionInfo:
    user = auth.authenticate_token(session, payload.api_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token or inactive account",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    row, secret = auth.create_session(
        session, user, absolute_lifetime_hours=settings.session_absolute_lifetime_hours
    )
    _set_session_cookies(
        response,
        secret,
        row.csrf_token,
        max_age=settings.session_absolute_lifetime_hours * 3600,
        secure=settings.session_cookie_secure,
    )
    return SessionInfo(
        user_id=user.user_id,
        display_name=user.display_name,
        role=user.role,
        csrf_token=row.csrf_token,
        expires_at=row.absolute_expires_at,
    )


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(db_session),
    _: Principal = Depends(require_user),
) -> Response:
    # CSRF is enforced by require_user for the cookie path (this is an unsafe method).
    secret = request.cookies.get(SESSION_COOKIE)
    if secret:
        auth.revoke_session_by_secret(session, secret)
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/csrf", response_model=SessionInfo)
def csrf(
    request: Request,
    session: Session = Depends(db_session),
) -> SessionInfo:
    """Return the current session's CSRF token (lets the SPA recover it after reload)."""
    secret = request.cookies.get(SESSION_COOKIE)
    settings = get_settings()
    row = (
        auth.authenticate_session(
            session, secret, idle_timeout_minutes=settings.session_idle_timeout_minutes
        )
        if secret
        else None
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="no active session"
        )
    return SessionInfo(
        user_id=row.user.user_id,
        display_name=row.user.display_name,
        role=row.user.role,
        csrf_token=row.csrf_token,
        expires_at=row.absolute_expires_at,
    )
