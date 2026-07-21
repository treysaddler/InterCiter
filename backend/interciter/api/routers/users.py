"""User administration and identity introspection.

Creating users is an ``admin``-only operation; the raw token is returned exactly once
at creation and only its hash is stored. Admins can also list accounts, change a
user's role, activate/deactivate an account, and rotate its token — the manual
account-management surface for the MVP (docs/ui-design.md Epic 4). ``GET /v1/users/me``
lets any authenticated caller confirm the identity and role the server resolved.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ... import auth
from ...auth import LastAdminError, Principal
from ...enums import Role
from ...schemas import (
    CurrentUser,
    TokenRotated,
    UserCreate,
    UserCreated,
    UserUpdate,
    UserView,
)
from ..deps import db_session
from ..security import require_admin, require_user

router = APIRouter()


def _view(user) -> UserView:
    return UserView(
        user_id=user.user_id,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/users", response_model=UserCreated, status_code=201)
def create_user(
    payload: UserCreate,
    session: Session = Depends(db_session),
    _: Principal = Depends(require_admin),
) -> UserCreated:
    user, token = auth.create_user(session, payload.display_name, payload.role)
    return UserCreated(
        user_id=user.user_id,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        api_token=token,
    )


@router.get("/users", response_model=list[UserView])
def list_users(
    session: Session = Depends(db_session),
    _: Principal = Depends(require_admin),
) -> list[UserView]:
    return [_view(u) for u in auth.list_users(session)]


def _load_user(session: Session, user_id: str):
    user = auth.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such user")
    return user


@router.patch("/users/{user_id}", response_model=UserView)
def update_user(
    user_id: str,
    payload: UserUpdate,
    session: Session = Depends(db_session),
    _: Principal = Depends(require_admin),
) -> UserView:
    user = _load_user(session, user_id)
    try:
        if payload.role is not None:
            auth.set_user_role(session, user, Role(payload.role))
        if payload.is_active is not None:
            auth.set_user_active(session, user, payload.is_active)
    except LastAdminError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _view(user)


@router.post("/users/{user_id}/rotate-token", response_model=TokenRotated)
def rotate_token(
    user_id: str,
    session: Session = Depends(db_session),
    _: Principal = Depends(require_admin),
) -> TokenRotated:
    user = _load_user(session, user_id)
    token = auth.rotate_api_token(session, user)
    return TokenRotated(
        user_id=user.user_id,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        api_token=token,
    )


@router.get("/users/me", response_model=CurrentUser)
def whoami(principal: Principal = Depends(require_user)) -> CurrentUser:
    return CurrentUser(
        user_id=principal.user_id,
        display_name=principal.display_name,
        role=principal.role,
    )
