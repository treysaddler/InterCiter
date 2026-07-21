"""Browser-session (BFF) and account-management tests.

Covers the cookie login/logout flow, CSRF enforcement on cookie-auth writes, idle
and absolute session expiry, deactivation revoking access, and the admin
account-management surface (list / role change / activation / token rotation) with
the last-admin self-lockout guard.
"""

from __future__ import annotations

from datetime import timedelta

from helpers import load_sample

from interciter import auth, models
from interciter.auth import _now
from interciter.db import SessionLocal
from interciter.enums import Role


def _new_token(role: Role = Role.user, name: str = "sess-user") -> str:
    with SessionLocal() as db:
        _, token = auth.create_user(db, name, role)
    return token


# --- login / cookie auth ----------------------------------------------------


def test_login_sets_cookies_and_returns_csrf(client):
    token = _new_token()
    resp = client.post("/v1/auth/login", json={"api_token": token})
    assert resp.status_code == 200
    assert resp.json()["csrf_token"]
    assert client.cookies.get("interciter_session")
    assert client.cookies.get("interciter_csrf")


def test_login_rejects_bad_token(client):
    assert client.post("/v1/auth/login", json={"api_token": "nope"}).status_code == 401


def test_session_cookie_authenticates_me(client):
    token = _new_token(Role.reviewer, "revcookie")
    client.post("/v1/auth/login", json={"api_token": token})
    me = client.get("/v1/users/me")  # cookie only, no Authorization header
    assert me.status_code == 200
    assert me.json()["role"] == "reviewer"


# --- CSRF -------------------------------------------------------------------


def test_cookie_write_requires_csrf(client):
    token = _new_token()
    login = client.post("/v1/auth/login", json={"api_token": token}).json()
    xml = load_sample("paper_b.xml")

    # A cookie-authenticated write without the CSRF header is rejected.
    assert client.post("/v1/papers", json={"xml": xml}).status_code == 403

    # With the CSRF header it succeeds.
    ok = client.post(
        "/v1/papers",
        json={"xml": xml},
        headers={"X-CSRF-Token": login["csrf_token"]},
    )
    assert ok.status_code == 202


def test_bad_csrf_rejected(client):
    token = _new_token()
    client.post("/v1/auth/login", json={"api_token": token})
    resp = client.post(
        "/v1/papers",
        json={"xml": load_sample("paper_b.xml")},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert resp.status_code == 403


# --- logout -----------------------------------------------------------------


def test_logout_revokes_session(client):
    token = _new_token()
    login = client.post("/v1/auth/login", json={"api_token": token}).json()
    assert client.get("/v1/users/me").status_code == 200

    out = client.post("/v1/auth/logout", headers={"X-CSRF-Token": login["csrf_token"]})
    assert out.status_code == 204
    assert client.get("/v1/users/me").status_code == 401


# --- expiry (unit-level, no time travel needed) -----------------------------


def test_session_absolute_expiry(session):
    user, _ = auth.create_user(session, "abs-exp", Role.user)
    row, secret = auth.create_session(session, user, absolute_lifetime_hours=12)
    row.absolute_expires_at = _now() - timedelta(hours=1)
    session.commit()

    assert auth.authenticate_session(session, secret, idle_timeout_minutes=30) is None
    assert session.get(models.UserSession, row.session_id) is None  # revoked


def test_session_idle_expiry(session):
    user, _ = auth.create_user(session, "idle-exp", Role.user)
    row, secret = auth.create_session(session, user, absolute_lifetime_hours=12)
    row.last_seen_at = _now() - timedelta(minutes=31)
    session.commit()

    assert auth.authenticate_session(session, secret, idle_timeout_minutes=30) is None


# --- deactivation -----------------------------------------------------------


def test_deactivated_user_loses_access(client):
    with SessionLocal() as db:
        _, admin_token = auth.create_user(db, "admin-d", Role.admin)
        victim, victim_token = auth.create_user(db, "victim", Role.user)

    client.post("/v1/auth/login", json={"api_token": victim_token})
    assert client.get("/v1/users/me").status_code == 200

    # Admin deactivates via bearer (bearer beats the ambient cookie; no CSRF needed).
    resp = client.patch(
        f"/v1/users/{victim.user_id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Existing session revoked and re-login refused.
    assert client.get("/v1/users/me").status_code == 401
    assert client.post("/v1/auth/login", json={"api_token": victim_token}).status_code == 401


# --- account management -----------------------------------------------------


def test_list_users_admin_only(client, user_headers, admin_headers):
    assert client.get("/v1/users", headers=user_headers).status_code == 403
    resp = client.get("/v1/users", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list) and resp.json()


def test_admin_changes_role_and_activation(client, admin_headers):
    created = client.post(
        "/v1/users", json={"display_name": "x", "role": "user"}, headers=admin_headers
    ).json()
    uid = created["user_id"]

    promoted = client.patch(
        f"/v1/users/{uid}", json={"role": "reviewer"}, headers=admin_headers
    )
    assert promoted.status_code == 200 and promoted.json()["role"] == "reviewer"

    disabled = client.patch(
        f"/v1/users/{uid}", json={"is_active": False}, headers=admin_headers
    )
    assert disabled.status_code == 200 and disabled.json()["is_active"] is False


def test_rotate_token_invalidates_old(client, admin_headers):
    created = client.post(
        "/v1/users", json={"display_name": "rot", "role": "user"}, headers=admin_headers
    ).json()
    uid, old = created["user_id"], created["api_token"]
    old_h = {"Authorization": f"Bearer {old}"}
    assert client.get("/v1/users/me", headers=old_h).status_code == 200

    rotated = client.post(f"/v1/users/{uid}/rotate-token", headers=admin_headers)
    assert rotated.status_code == 200
    new = rotated.json()["api_token"]
    assert new != old

    assert client.get("/v1/users/me", headers=old_h).status_code == 401
    assert (
        client.get("/v1/users/me", headers={"Authorization": f"Bearer {new}"}).status_code
        == 200
    )


def test_cannot_orphan_last_admin(client, admin_headers):
    me = client.get("/v1/users/me", headers=admin_headers).json()
    uid = me["user_id"]
    assert (
        client.patch(f"/v1/users/{uid}", json={"role": "user"}, headers=admin_headers).status_code
        == 409
    )
    assert (
        client.patch(
            f"/v1/users/{uid}", json={"is_active": False}, headers=admin_headers
        ).status_code
        == 409
    )


def test_update_unknown_user_404(client, admin_headers):
    assert (
        client.patch(
            "/v1/users/user_nope", json={"role": "user"}, headers=admin_headers
        ).status_code
        == 404
    )
