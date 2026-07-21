"""User administration and identity introspection.

Creating users is an ``admin``-only operation; the raw token is returned exactly once
at creation and only its hash is stored. ``GET /v1/users/me`` lets any authenticated
caller confirm the identity and role the server resolved from their token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ... import auth
from ...auth import Principal
from ...schemas import CurrentUser, UserCreate, UserCreated
from ..deps import db_session
from ..security import require_admin, require_user

router = APIRouter()


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
