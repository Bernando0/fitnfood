"""SQLAlchemy 2.0 ORM models — users, meals, per-group settings."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    """One participant, scoped to a single group chat."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tg_user_id", "chat_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    display_name: Mapped[str | None] = mapped_column(default=None)
    username: Mapped[str | None] = mapped_column(default=None)
    # 0 after /stop — the bot keeps quiet for this person but stays in the chat.
    is_active: Mapped[int] = mapped_column(default=1)
    # optional personal goal: lose | gain | maintain
    goal: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Meal(Base):
    """A single logged meal (one food photo)."""

    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger, default=None)

    eaten_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    meal_slot: Mapped[str | None] = mapped_column(default=None)  # breakfast/lunch/dinner/snack

    dish_name: Mapped[str | None] = mapped_column(default=None)
    kcal_min: Mapped[int | None] = mapped_column(default=None)
    kcal_max: Mapped[int | None] = mapped_column(default=None)
    protein_g: Mapped[float | None] = mapped_column(default=None)
    fat_g: Mapped[float | None] = mapped_column(default=None)
    carbs_g: Mapped[float | None] = mapped_column(default=None)
    health_score: Mapped[str | None] = mapped_column(default=None)  # green/yellow/red

    coach_reply: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GroupSettings(Base):
    """Per-group configuration for the daily report."""

    __tablename__ = "group_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    summary_hour: Mapped[int] = mapped_column(default=22)
    timezone: Mapped[str] = mapped_column(default="Europe/Moscow")
    onboarded: Mapped[int] = mapped_column(default=0)
    # Communication tone: savage | coach | friendly
    tone: Mapped[str] = mapped_column(default="savage")
