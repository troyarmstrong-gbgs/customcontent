"""Local user record + per-app access-control models.

`LocalUser` tracks who has signed in. The access-control models
(`AppCustomRole`, `AppRolePage`, `AppPagePermission`,
`AppGroupRoleMapping`) implement per-app user management — assign
built-in or custom roles to individual users or Google groups, with
per-page granularity. See `app/access.py` for the resolution logic.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LocalUser(Base):
    __tablename__ = "local_users"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    # Mirror of the JWT claims from the service app — useful for guards
    # but the platform also enforces these globally.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Per-app role: pending | viewer | editor | admin. "pending" = signed
    # in but not yet granted access (deny by default).
    role: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    # Optional named custom role overriding per-page access.
    custom_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_custom_roles.id", ondelete="SET NULL"), nullable=True
    )
    # Cached Google group memberships (comma-joined emails), refreshed at
    # sign-in. Used to resolve group-based role mappings + page overrides.
    group_emails: Mapped[str] = mapped_column(String(4096), default="", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def group_list(self) -> list[str]:
        return [g for g in (self.group_emails or "").split(",") if g]

    def __repr__(self) -> str:
        return f"<LocalUser email={self.email!r} role={self.role!r}>"


class AppCustomRole(Base):
    """A named, admin-defined role with per-page access (AppRolePage)."""
    __tablename__ = "app_custom_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    # Fallback level for pages with no explicit AppRolePage entry, and the
    # role's rank for "highest role wins" resolution.
    base_role: Mapped[str] = mapped_column(String(16), default="viewer", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AppCustomRole {self.name!r} base={self.base_role!r}>"


class AppRolePage(Base):
    """Per-page access level (hide/view/edit) for a custom role."""
    __tablename__ = "app_role_pages"
    __table_args__ = (UniqueConstraint("role_id", "page_path", name="uq_role_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("app_custom_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_path: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)  # hide|view|edit


class AppPagePermission(Base):
    """Per-(user-or-group, page) override of the role default."""
    __tablename__ = "app_page_permissions"
    __table_args__ = (UniqueConstraint("email", "page_path", name="uq_email_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # User OR group email (same convention as the role mapping table).
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    page_path: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)  # hide|view|edit
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppGroupRoleMapping(Base):
    """Grant a role to an individual email OR a Google group email.

    On sign-in, a user gets the highest role across their own email
    mapping + any group they belong to. An optional custom_role_id binds
    per-page access for everyone the mapping covers.
    """
    __tablename__ = "app_group_role_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="viewer", nullable=False)
    custom_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_custom_roles.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    is_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AppGroupRoleMapping {self.group_email!r} role={self.role!r}>"
