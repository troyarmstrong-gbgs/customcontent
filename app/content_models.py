"""Tables this app owns: guest submissions and the store dropdown.

Kept separate from `app/models.py` (the platform's user/access tables)
so template updates to the access layer stay easy to merge.

Naming follows the warehouse conventions we use elsewhere: snake_case
columns, `*_at` timestamps, a surrogate integer key plus an opaque
public reference the guest sees.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Submission(Base):
    """One guest's custom content, as submitted, plus reviewer edits.

    `content_json` holds the validated rows keyed by game id. It is
    written by the public endpoint and may be rewritten by a reviewer
    accepting a spelling fix; everything else on the row is
    reviewer-owned.
    """

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # What the guest is shown and quotes back to us in email.
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True,
                                           nullable=False)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), index=True, nullable=False)
    group_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    store: Mapped[str] = mapped_column(String(160), index=True, default="",
                                       nullable=False)
    event_date: Mapped[str] = mapped_column(String(10), index=True, default="",
                                            nullable=False)

    games_csv: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    content_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    # Reviewer-owned.
    special_event_id: Mapped[str] = mapped_column(String(120), default="",
                                                  nullable=False)
    uploaded_to_chippy: Mapped[bool] = mapped_column(Boolean, default=False,
                                                     nullable=False)

    # Light provenance for abuse triage. Truncated, never shown in the UI.
    source_ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False
    )

    def game_list(self) -> list[str]:
        return [g for g in (self.games_csv or "").split(",") if g]

    def __repr__(self) -> str:
        return f"<Submission {self.reference} {self.name!r}>"


class StoreOption(Base):
    """A store the guest can pick. Maintained from the producer view.

    Kept as rows rather than a config blob so a store can be retired
    (`active = False`) without disturbing submissions that already name it.
    """

    __tablename__ = "store_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_key: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<StoreOption {self.name!r} active={self.active}>"
