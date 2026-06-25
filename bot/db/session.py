"""Async engine / session factory and schema bootstrap."""
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from bot.db.models import Base

# Ensure the parent directory for the SQLite file exists.
os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)

engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.db_path}", echo=False
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _ensure_columns(conn) -> None:
    """Lightweight migration: add columns missing from a pre-existing DB."""
    existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(group_settings)").fetchall()}
    if "tone" not in existing:
        conn.exec_driver_sql("ALTER TABLE group_settings ADD COLUMN tone TEXT DEFAULT 'savage'")


async def init_db() -> None:
    """Create tables if needed, then apply lightweight column migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_columns)
