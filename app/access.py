"""Per-app access control: roles, custom roles, per-page permissions.

Modeled on the CapEx Hub access system. Lets an admin grant access to
individual users OR Google groups, assign a built-in role
(admin/editor/viewer) or a named custom role with per-page granularity,
and override any single page for any user/group.

Identity comes from Curiosity Games SSO. This module only decides what
a known, signed-in person is allowed to SEE and EDIT within THIS app.

Resolution precedence for a given (user, page), highest first:
  1. Custom role bound to the user (or to a group they're in) — uses
     that role's per-page level, falling back to the role's base_role.
  2. Per-page permission overrides (PagePermission) for the user's email
     or any of their group emails — highest level wins.
  3. The user's built-in enum role default:
       admin/editor -> EDIT, viewer -> VIEW, pending -> HIDE.

Group membership is resolved at sign-in by fetching the platform
directory (/api/directory/groups, which includes member emails) and
caching the user's groups on their LocalUser row.
"""
from __future__ import annotations

# --- Levels + roles --------------------------------------------------------

HIDE, VIEW, EDIT = "hide", "view", "edit"
_LEVEL_RANK = {HIDE: 0, VIEW: 1, EDIT: 2}

# Built-in roles, weakest -> strongest. "pending" = signed in but not
# yet granted anything (deny by default).
PENDING, VIEWER, EDITOR, ADMIN = "pending", "viewer", "editor", "admin"
_ROLE_RANK = {PENDING: 0, VIEWER: 1, EDITOR: 2, ADMIN: 3}


def role_rank(role: str) -> int:
    return _ROLE_RANK.get((role or "").lower(), 0)


def higher_role(a: str, b: str) -> str:
    return a if role_rank(a) >= role_rank(b) else b


def _role_default_level(role: str) -> str:
    r = (role or "").lower()
    if r in (ADMIN, EDITOR):
        return EDIT
    if r == VIEWER:
        return VIEW
    return HIDE


# --- Managed pages registry ------------------------------------------------
#
# The pages whose access an admin can customize. Add your app's pages
# here as you build them. `path` is matched against the request path;
# `label` is the human name shown in the access matrix.
#
# Pages NOT listed here aren't access-customizable — they fall back to
# the enum-role default (admins/editors edit, viewers view, pending
# hidden). The /admin/* pages are always admin-only regardless.

MANAGED_PAGES: list[dict[str, str]] = [
    {"path": "/", "label": "Training manual"},
    {"path": "/databases", "label": "Databases"},
    # Add your own, e.g.:
    # {"path": "/reports", "label": "Reports"},
]


def managed_page_paths() -> list[str]:
    return [p["path"] for p in MANAGED_PAGES]


# --- Resolution ------------------------------------------------------------


async def resolve_page_level(db, email: str, group_emails: list[str], page_path: str) -> str:
    """Effective HIDE/VIEW/EDIT for `email` on `page_path`.

    `group_emails` is the user's cached Google group memberships.
    """
    from sqlalchemy import select

    from app.models import (
        AppCustomRole,
        AppGroupRoleMapping,
        AppPagePermission,
        AppRolePage,
        LocalUser,
    )

    email = (email or "").lower()
    idents = [email] + [g.lower() for g in (group_emails or [])]

    user = (
        await db.execute(select(LocalUser).where(LocalUser.email == email))
    ).scalar_one_or_none()

    # --- 1. Custom role (user's own, or via a group mapping) ---
    custom_role_ids: list[int] = []
    if user and user.custom_role_id:
        custom_role_ids.append(user.custom_role_id)
    mappings = (
        await db.execute(
            select(AppGroupRoleMapping)
            .where(AppGroupRoleMapping.active == True)  # noqa: E712
            .where(AppGroupRoleMapping.group_email.in_(idents))
        )
    ).scalars().all()
    for m in mappings:
        if m.custom_role_id:
            custom_role_ids.append(m.custom_role_id)

    if custom_role_ids:
        # If several custom roles apply, pick the one whose base_role
        # ranks highest, then read its per-page level.
        roles = (
            await db.execute(
                select(AppCustomRole).where(AppCustomRole.id.in_(set(custom_role_ids)))
            )
        ).scalars().all()
        if roles:
            best = max(roles, key=lambda r: role_rank(r.base_role))
            rp = (
                await db.execute(
                    select(AppRolePage)
                    .where(AppRolePage.role_id == best.id)
                    .where(AppRolePage.page_path == page_path)
                )
            ).scalar_one_or_none()
            if rp:
                return rp.level
            return _role_default_level(best.base_role)

    # --- 2. Per-page permission overrides (highest wins) ---
    overrides = (
        await db.execute(
            select(AppPagePermission)
            .where(AppPagePermission.active == True)  # noqa: E712
            .where(AppPagePermission.email.in_(idents))
            .where(AppPagePermission.page_path == page_path)
        )
    ).scalars().all()
    if overrides:
        return max((o.level for o in overrides), key=lambda lv: _LEVEL_RANK.get(lv, 0))

    # --- 3. Enum role default ---
    return _role_default_level(user.role if user else PENDING)


async def resolve_role_on_login(db, email: str, group_emails: list[str]) -> str:
    """Compute + persist the user's built-in role at sign-in.

    Highest of: the user's own group-role-mapping (by email) and any
    group mapping for groups they belong to. If nothing matches, the
    role is left as-is for an existing user, or 'pending' for a brand
    new one (deny by default).
    """
    from sqlalchemy import select

    from app.models import AppGroupRoleMapping, LocalUser

    email = (email or "").lower()
    idents = [email] + [g.lower() for g in (group_emails or [])]

    mappings = (
        await db.execute(
            select(AppGroupRoleMapping)
            .where(AppGroupRoleMapping.active == True)  # noqa: E712
            .where(AppGroupRoleMapping.group_email.in_(idents))
        )
    ).scalars().all()

    user = (
        await db.execute(select(LocalUser).where(LocalUser.email == email))
    ).scalar_one_or_none()

    granted = PENDING
    for m in mappings:
        granted = higher_role(granted, m.role)

    # The app owner is always admin of their own app — this is what makes
    # a freshly-bootstrapped app start locked to its creator instead of
    # open to the whole org.
    from app.config import get_settings
    owner = (get_settings().app_owner_email or "").lower()
    if owner and email == owner:
        granted = higher_role(granted, ADMIN)

    if user is not None:
        # Admins from the SSO claim are always at least admin here.
        if user.is_admin or user.is_super_admin:
            granted = higher_role(granted, ADMIN)
        # Don't downgrade an explicitly-set role below what mappings grant;
        # take the stronger of the existing role and the freshly granted.
        if mappings or user.role in (None, "", PENDING):
            user.role = higher_role(user.role or PENDING, granted)
        await db.commit()
        return user.role
    return granted


async def fetch_user_group_emails(email: str) -> list[str]:
    """Ask the platform directory which groups `email` belongs to.

    Calls the service app's /api/directory/groups (returns all groups
    with member emails) and filters to the ones containing `email`.
    Returns [] on any failure — group mappings just won't apply, which
    is safe (deny by default).
    """
    import httpx

    from app.config import get_settings

    s = get_settings()
    if not s.service_app_permissions_key:
        return []
    url = f"{s.sso_issuer.rstrip('/')}/api/directory/groups"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {s.service_app_permissions_key}"},
            )
        if resp.status_code >= 400:
            return []
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return []
    email = (email or "").lower()
    out: list[str] = []
    for g in payload.get("groups", []):
        members = [(m or "").lower() for m in g.get("members", [])]
        if email in members:
            ge = (g.get("email") or "").lower()
            if ge:
                out.append(ge)
    return out
