"""SQLAlchemy async engine + session factory.

Schema is managed with `Base.metadata.create_all` on app startup — fine
for the starter template. As your schema grows, swap in Alembic when
you start needing versioned migrations.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _normalize_db_url(url: str) -> str:
    """Map a plain connection URL to the right async SQLAlchemy driver.

    - Railway hands us `postgresql://...` -> needs `postgresql+asyncpg://`.
    - Local preview uses SQLite -> `sqlite://` -> `sqlite+aiosqlite://`.
      (SQLite stores only THIS app's own tables; data still comes from
      the broker over HTTP, so SQLite is a fine local stand-in for the
      production Postgres.)
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


_settings = get_settings()
_engine = create_async_engine(
    _normalize_db_url(_settings.database_url), echo=False, future=True
)
SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create tables if they don't exist. Called once on app startup."""
    # Import models so they register on Base.metadata.
    from app import content_models, models  # noqa: F401
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
