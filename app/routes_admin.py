"""Admin user-management for this app.

A per-app access console modeled on CapEx Hub:
  - Users          — who's signed in, their role, custom role, groups
  - Role mappings   — grant a role to a user email OR a Google group
  - Custom roles    — named roles with per-page (hide/view/edit) access
  - Page matrix     — per-(user/group, page) overrides
  - Directory search— Google typeahead (proxied via the service app)

Identity + the global kill-switch are the platform's job (SSO). This
console only decides what a known person can see/edit inside THIS app.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import access
from app.config import get_settings
from app.db import get_session
from app.models import (
    AppCustomRole,
    AppGroupRoleMapping,
    AppPagePermission,
    AppRolePage,
    LocalUser,
)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

_BUILTIN_ROLES = [access.ADMIN, access.EDITOR, access.VIEWER]
_LEVELS = [access.HIDE, access.VIEW, access.EDIT]


def require_admin(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    # Admin = a service-app admin OR this app's own admin (the owner, or
    # anyone granted the 'admin' role here). The owner is auto-granted
    # admin on sign-in (see app/access.py) so they can manage access.
    is_admin = (
        user.get("is_admin")
        or user.get("is_super_admin")
        or (user.get("app_role") == "admin")
    )
    if not is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


# --- Users console ---------------------------------------------------------


@router.get("/users", response_class=HTMLResponse)
async def users_console(
    request: Request,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    users = (
        await db.execute(select(LocalUser).order_by(LocalUser.email.asc()))
    ).scalars().all()
    mappings = (
        await db.execute(
            select(AppGroupRoleMapping).order_by(
                AppGroupRoleMapping.active.desc(), AppGroupRoleMapping.group_email.asc()
            )
        )
    ).scalars().all()
    custom_roles = (
        await db.execute(select(AppCustomRole).order_by(AppCustomRole.name.asc()))
    ).scalars().all()
    role_pages = (await db.execute(select(AppRolePage))).scalars().all()
    page_perms = (
        await db.execute(
            select(AppPagePermission).order_by(
                AppPagePermission.email.asc(), AppPagePermission.page_path.asc()
            )
        )
    ).scalars().all()

    # Build the page-permission matrix: rows = every email we know about
    # (users + mapping emails + override emails), cols = managed pages.
    roles_by_id = {r.id: r for r in custom_roles}
    perm_lookup = {(p.email.lower(), p.page_path): p.level for p in page_perms}
    matrix_emails = sorted({
        *(u.email.lower() for u in users),
        *(m.group_email.lower() for m in mappings),
        *(p.email.lower() for p in page_perms),
    })
    matrix = []
    for em in matrix_emails:
        cells = []
        for pg in access.MANAGED_PAGES:
            cells.append({
                "page": pg["path"],
                "level": perm_lookup.get((em, pg["path"]), ""),  # "" = default
            })
        matrix.append({"email": em, "cells": cells})

    # Pages-per-custom-role for the role editor display.
    role_page_map: dict[int, dict[str, str]] = {}
    for rp in role_pages:
        role_page_map.setdefault(rp.role_id, {})[rp.page_path] = rp.level

    settings = get_settings()
    return templates.TemplateResponse(
        request, "admin/users.html",
        {
            "user": user,
            "users": users,
            "mappings": mappings,
            "custom_roles": custom_roles,
            "roles_by_id": roles_by_id,
            "role_page_map": role_page_map,
            "matrix": matrix,
            "managed_pages": access.MANAGED_PAGES,
            "builtin_roles": _BUILTIN_ROLES,
            "levels": _LEVELS,
            "directory_enabled": bool(settings.service_app_permissions_key),
            "flash": request.query_params.get("flash"),
        },
    )


# --- Directory typeahead (proxy the service app) ---------------------------


@router.get("/directory-search")
async def directory_search(
    q: str = "",
    kind: str = "user",
    user: dict = Depends(require_admin),
):
    """Typeahead against the platform directory. Proxies the service
    app's /api/directory/users or /groups and filters by prefix.

    Returns {"available": bool, "matches": [{email, name, kind, members?}]}.
    Degrades to available=false if the bearer key isn't set or the
    service app is unreachable (admin can still add manually).
    """
    s = get_settings()
    q = (q or "").strip().lower()
    if not s.service_app_permissions_key:
        return JSONResponse({"available": False, "matches": []})
    endpoint = "groups" if kind == "group" else "users"
    url = f"{s.sso_issuer.rstrip('/')}/api/directory/{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {s.service_app_permissions_key}"},
            )
        if resp.status_code >= 400:
            return JSONResponse({"available": False, "matches": []})
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"available": False, "matches": []})

    matches = []
    if kind == "group":
        for g in payload.get("groups", []):
            em = (g.get("email") or "").lower()
            nm = g.get("name") or em
            if not q or q in em or q in nm.lower():
                matches.append({
                    "kind": "group", "email": em, "name": nm,
                    "members": len(g.get("members", [])),
                })
    else:
        for u in payload.get("users", []):
            em = (u.get("email") or "").lower()
            nm = u.get("full_name") or u.get("name") or em
            if not q or q in em or q in nm.lower():
                matches.append({"kind": "user", "email": em, "name": nm})
    matches.sort(key=lambda m: m["email"])
    return JSONResponse({"available": True, "matches": matches[:25]})


# --- Role mappings (grant a role to a user/group) --------------------------


@router.post("/mappings")
async def add_mapping(
    group_email: str = Form(...),
    role: str = Form("viewer"),
    custom_role_id: str = Form(""),
    description: str = Form(""),
    is_group: str = Form(""),
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    em = (group_email or "").strip().lower()
    if not em or "@" not in em:
        return _flash("Enter a valid email or group address.")
    role = role if role in _BUILTIN_ROLES else access.VIEWER
    cr_id = int(custom_role_id) if custom_role_id.isdigit() else None

    existing = (
        await db.execute(
            select(AppGroupRoleMapping).where(AppGroupRoleMapping.group_email == em)
        )
    ).scalar_one_or_none()
    if existing:
        existing.role = role
        existing.custom_role_id = cr_id
        existing.description = description.strip()
        existing.active = True
        existing.is_group = bool(is_group)
    else:
        db.add(AppGroupRoleMapping(
            group_email=em, role=role, custom_role_id=cr_id,
            description=description.strip(), is_group=bool(is_group), active=True,
        ))
    # Pre-seed a LocalUser for individual emails so they appear in the
    # console + pickers before first sign-in (groups don't get a row).
    if not is_group:
        lu = (
            await db.execute(select(LocalUser).where(LocalUser.email == em))
        ).scalar_one_or_none()
        if lu is None:
            db.add(LocalUser(email=em, name=em, role=role))
        else:
            lu.role = access.higher_role(lu.role, role)
    await db.commit()
    return _flash(f"Granted {role} to {em}.")


@router.post("/mappings/{mapping_id}/delete")
async def delete_mapping(
    mapping_id: int,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    m = (
        await db.execute(select(AppGroupRoleMapping).where(AppGroupRoleMapping.id == mapping_id))
    ).scalar_one_or_none()
    if m:
        await db.delete(m)
        await db.commit()
    return _flash("Mapping removed.")


# --- Per-user role + custom-role assignment --------------------------------


@router.post("/users/{email}/role")
async def set_user_role(
    email: str,
    role: str = Form(""),
    custom_role_id: str = Form(""),
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    lu = (
        await db.execute(select(LocalUser).where(LocalUser.email == email.lower()))
    ).scalar_one_or_none()
    if lu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    # Guard against self-demotion below admin.
    if user["email"].lower() == lu.email and role and role != access.ADMIN:
        return _flash("You can't lower your own role below admin.")
    if role in _BUILTIN_ROLES:
        lu.role = role
    lu.custom_role_id = int(custom_role_id) if custom_role_id.isdigit() else None
    await db.commit()
    return _flash(f"Updated {lu.email}.")


# --- Custom roles ----------------------------------------------------------


@router.post("/custom-roles")
async def add_custom_role(
    request: Request,
    name: str = Form(...),
    base_role: str = Form("viewer"),
    description: str = Form(""),
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    name = name.strip()
    if not name:
        return _flash("Custom role needs a name.")
    base_role = base_role if base_role in _BUILTIN_ROLES else access.VIEWER
    existing = (
        await db.execute(select(AppCustomRole).where(AppCustomRole.name == name))
    ).scalar_one_or_none()
    if existing:
        role = existing
        role.base_role = base_role
        role.description = description.strip()
    else:
        role = AppCustomRole(name=name, base_role=base_role, description=description.strip())
        db.add(role)
    await db.commit()
    await db.refresh(role)

    # Per-page levels come through as level_<path> form fields.
    body = await request.form()
    # Clear + rewrite this role's page entries.
    old = (
        await db.execute(select(AppRolePage).where(AppRolePage.role_id == role.id))
    ).scalars().all()
    for rp in old:
        await db.delete(rp)
    for pg in access.MANAGED_PAGES:
        lvl = body.get(f"level_{pg['path']}", "")
        if lvl in _LEVELS:
            db.add(AppRolePage(role_id=role.id, page_path=pg["path"], level=lvl))
    await db.commit()
    return _flash(f"Saved custom role '{name}'.")


@router.post("/custom-roles/{role_id}/delete")
async def delete_custom_role(
    role_id: int,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    role = (
        await db.execute(select(AppCustomRole).where(AppCustomRole.id == role_id))
    ).scalar_one_or_none()
    if role:
        await db.delete(role)
        await db.commit()
    return _flash("Custom role deleted.")


# --- Page-permission overrides ---------------------------------------------


@router.post("/page-permissions")
async def set_page_permission(
    email: str = Form(...),
    page_path: str = Form(...),
    level: str = Form(""),
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    em = (email or "").strip().lower()
    existing = (
        await db.execute(
            select(AppPagePermission)
            .where(AppPagePermission.email == em)
            .where(AppPagePermission.page_path == page_path)
        )
    ).scalar_one_or_none()
    if level not in _LEVELS:
        # Empty/invalid level = clear the override (revert to default).
        if existing:
            await db.delete(existing)
            await db.commit()
        return _flash(f"Cleared override for {em} on {page_path}.")
    if existing:
        existing.level = level
        existing.active = True
    else:
        db.add(AppPagePermission(email=em, page_path=page_path, level=level, active=True))
    await db.commit()
    return _flash(f"Set {em} → {level} on {page_path}.")


# --- Local user revoke/reactivate (kept from the original template) --------


@router.post("/users/sync")
async def sync_users(
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Deactivate local users no longer in the Workspace directory."""
    s = get_settings()
    if not s.service_app_permissions_key:
        return _flash("SERVICE_APP_PERMISSIONS_KEY not set; can't sync.")
    url = f"{s.sso_issuer.rstrip('/')}/api/directory/users"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {s.service_app_permissions_key}"},
            )
        if resp.status_code >= 400:
            return _flash(f"Sync failed: {resp.status_code}")
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        return _flash(f"Sync failed: {e}")
    ws = {(u.get("email") or "").lower() for u in payload.get("users", []) if u.get("email")}
    suspended = {(u.get("email") or "").lower() for u in payload.get("users", []) if u.get("is_suspended")}
    if not ws:
        return _flash("Sync aborted: directory returned 0 users.")
    revoked = []
    for lu in (await db.execute(select(LocalUser))).scalars().all():
        if lu.is_active and (lu.email not in ws or lu.email in suspended):
            lu.is_active = False
            revoked.append(lu.email)
    await db.commit()
    return _flash(f"Synced {len(ws)} users." + (f" Revoked: {','.join(revoked)}" if revoked else " No changes."))


@router.post("/users/{email}/revoke")
async def revoke_user(
    email: str,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    if user["email"].lower() == email.lower():
        return _flash("You can't revoke yourself.")
    lu = (
        await db.execute(select(LocalUser).where(LocalUser.email == email.lower()))
    ).scalar_one_or_none()
    if lu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    lu.is_active = False
    await db.commit()
    return _flash(f"Revoked {email}.")


@router.post("/users/{email}/reactivate")
async def reactivate_user(
    email: str,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    lu = (
        await db.execute(select(LocalUser).where(LocalUser.email == email.lower()))
    ).scalar_one_or_none()
    if lu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    lu.is_active = True
    await db.commit()
    return _flash(f"Re-enabled {email}.")


def _flash(msg: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/admin/users?flash={msg.replace(' ', '+')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
