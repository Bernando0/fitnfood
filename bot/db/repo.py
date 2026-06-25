"""Data-access helpers. All functions take an AsyncSession."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import GroupSettings, Meal, User


async def get_or_create_user(
    session: AsyncSession,
    *,
    tg_user_id: int,
    chat_id: int,
    display_name: str | None,
    username: str | None,
) -> User:
    res = await session.execute(
        select(User).where(User.tg_user_id == tg_user_id, User.chat_id == chat_id)
    )
    user = res.scalar_one_or_none()
    if user is None:
        user = User(
            tg_user_id=tg_user_id,
            chat_id=chat_id,
            display_name=display_name,
            username=username,
        )
        session.add(user)
        await session.flush()
    else:
        # Keep the display name fresh — people rename themselves.
        if display_name and user.display_name != display_name:
            user.display_name = display_name
        if username and user.username != username:
            user.username = username
    return user


async def set_active(session: AsyncSession, *, tg_user_id: int, chat_id: int, active: bool) -> None:
    res = await session.execute(
        select(User).where(User.tg_user_id == tg_user_id, User.chat_id == chat_id)
    )
    user = res.scalar_one_or_none()
    if user is not None:
        user.is_active = 1 if active else 0


async def delete_user_data(session: AsyncSession, *, tg_user_id: int, chat_id: int) -> None:
    res = await session.execute(
        select(User).where(User.tg_user_id == tg_user_id, User.chat_id == chat_id)
    )
    user = res.scalar_one_or_none()
    if user is None:
        return
    meals = await session.execute(select(Meal).where(Meal.user_id == user.id))
    for meal in meals.scalars():
        await session.delete(meal)
    await session.delete(user)


async def add_meal(session: AsyncSession, **fields) -> Meal:
    meal = Meal(**fields)
    session.add(meal)
    await session.flush()
    return meal


async def meals_today(session: AsyncSession, *, user_id: int, now: datetime) -> list[Meal]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    res = await session.execute(
        select(Meal)
        .where(Meal.user_id == user_id, Meal.eaten_at >= start)
        .order_by(Meal.eaten_at)
    )
    return list(res.scalars())


async def meals_for_chat_since(
    session: AsyncSession, *, chat_id: int, since: datetime
) -> list[tuple[User, Meal]]:
    """All meals in a chat since `since`, paired with their active user."""
    res = await session.execute(
        select(User, Meal)
        .join(Meal, Meal.user_id == User.id)
        .where(Meal.chat_id == chat_id, Meal.eaten_at >= since, User.is_active == 1)
        .order_by(User.id, Meal.eaten_at)
    )
    return [(row[0], row[1]) for row in res.all()]


async def meals_for_user_since(
    session: AsyncSession, *, user_id: int, since: datetime
) -> list[Meal]:
    res = await session.execute(
        select(Meal)
        .where(Meal.user_id == user_id, Meal.eaten_at >= since)
        .order_by(Meal.eaten_at)
    )
    return list(res.scalars())


async def active_users_in_chat(session: AsyncSession, *, chat_id: int) -> list[User]:
    """All participants the bot still tracks in this chat (group members, or the
    single user in a private chat)."""
    res = await session.execute(
        select(User)
        .where(User.chat_id == chat_id, User.is_active == 1)
        .order_by(User.id)
    )
    return list(res.scalars())


async def active_chat_ids(session: AsyncSession) -> list[int]:
    res = await session.execute(select(GroupSettings.chat_id))
    return [row[0] for row in res.all()]


async def get_or_create_group(session: AsyncSession, *, chat_id: int) -> GroupSettings:
    res = await session.execute(select(GroupSettings).where(GroupSettings.chat_id == chat_id))
    group = res.scalar_one_or_none()
    if group is None:
        group = GroupSettings(chat_id=chat_id)
        session.add(group)
        await session.flush()
    return group


def day_window(now: datetime) -> datetime:
    """Start of the current day for `now`."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=0)
