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


async def init_db() -> None:
    """Create tables if they do not exist yet (good enough for the MVP)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
