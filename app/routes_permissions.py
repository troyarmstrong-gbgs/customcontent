"""Expose this app's user-role data to the Curiosity Games service app.

GET /service-app/permissions
Authorization: Bearer ${SERVICE_APP_PERMISSIONS_KEY}

Returns:
  { "users": [
      {"email": "alice@theescapegame.com", "roles": ["admin"], "custom": {}},
      ...
  ]}

The default implementation returns an empty list — replace `_collect_users`
with a real query against your app's user/role data once you have any.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import AppCustomRole, LocalUser

router = APIRouter(prefix="/service-app", tags=["service-app"])


async def _collect_users(db: AsyncSession) -> list[dict]:
    """Return all users this app knows about, with their roles.

    Reports each LocalUser's built-in role + custom role (if any) so the
    service app's /admin/apps/<id> permissions view reflects this app's
    real access state.
    """
    roles = {
        r.id: r.name
        for r in (await db.execute(select(AppCustomRole))).scalars().all()
    }
    out = []
    for lu in (await db.execute(select(LocalUser))).scalars().all():
        role_list = [lu.role] if lu.role and lu.role != "pending" else []
        custom = {}
        if lu.custom_role_id and lu.custom_role_id in roles:
            custom["custom_role"] = roles[lu.custom_role_id]
        out.append({
            "email": lu.email,
            "roles": role_list,
            "active": lu.is_active,
            "custom": custom,
        })
    return out


def _check_key(authorization: str) -> None:
    expected = f"Bearer {get_settings().service_app_permissions_key}"
    if not authorization or authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SERVICE_APP_PERMISSIONS_KEY",
        )


@router.get("/permissions")
async def permissions(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_session),
):
    _check_key(authorization)
    return {"users": await _collect_users(db)}


@router.post("/revoke-user")
async def revoke_user(
    payload: dict,
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_session),
):
    """Let the service app remove a user from THIS app.

    Called by the platform's All-Users console when an admin removes
    someone from this app. Deactivates the local user so they lose
    access here, while their global SSO + other apps are untouched.

    Body: {"email": "alice@theescapegame.com"}
    Auth: Bearer SERVICE_APP_PERMISSIONS_KEY.
    """
    _check_key(authorization)
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "email required")
    lu = (
        await db.execute(select(LocalUser).where(LocalUser.email == email))
    ).scalar_one_or_none()
    if lu is None:
        return {"ok": True, "note": "user not present in this app"}
    lu.is_active = False
    await db.commit()
    return {"ok": True, "revoked": email}


@router.post("/set-role")
async def set_role(
    payload: dict,
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_session),
):
    """Let the service app grant a user a role in THIS app.

    Called when an admin adds someone as a teammate from the platform's
    app page and assigns an app role. Creates or updates the LocalUser
    with the role so they get access here on next sign-in (and show up
    in /service-app/permissions, so the platform sees them as that role).

    Body: {"email": "...", "role": "admin|editor|viewer"}
    Auth: Bearer SERVICE_APP_PERMISSIONS_KEY.
    """
    _check_key(authorization)
    email = (payload.get("email") or "").strip().lower()
    role = (payload.get("role") or "").strip().lower()
    if not email or role not in ("admin", "editor", "viewer"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "email + role (admin|editor|viewer) required"
        )
    lu = (
        await db.execute(select(LocalUser).where(LocalUser.email == email))
    ).scalar_one_or_none()
    if lu is None:
        db.add(LocalUser(email=email, name=email, role=role, is_active=True))
    else:
        lu.role = role
        lu.is_active = True
    await db.commit()
    return {"ok": True, "email": email, "role": role}
