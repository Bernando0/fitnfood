"""Build a short text summary of a user's status for Q&A / eat advice."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import User
from bot.services.zones import ZONE_EMOJI, ZONE_RU, day_total_kcal, day_zone

_GOAL_RU = {"lose": "снижение веса", "gain": "набор массы", "maintain": "поддержание"}
_DAY_LABELS = {0: "Сегодня", 1: "Вчера", 2: "Позавчера"}


async def build_status_text(session: AsyncSession, user: User, now: datetime) -> str:
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yest_start = today_start - timedelta(days=1)

    meals = await repo.meals_for_user_since(session, user_id=user.id, since=yest_start)
    today = [m for m in meals if m.eaten_at >= today_start]
    yest = [m for m in meals if yest_start <= m.eaten_at < today_start]

    lines = [
        f"Имя: {user.display_name or 'Участник'}.",
        f"Цель: {_GOAL_RU.get(user.goal or '', 'не задана')}.",
    ]
    if today:
        lo, hi = day_total_kcal(today)
        items = "; ".join(f"{m.dish_name} ({m.health_score})" for m in today if m.dish_name)
        lines.append(
            f"Сегодня уже ел — {ZONE_RU[day_zone(today)]} зона, ~{lo}-{hi} ккал: {items}."
        )
    else:
        lines.append("Сегодня ещё ничего не ел.")
    lines.append(
        f"Вчера день был {ZONE_RU[day_zone(yest)]}." if yest else "Вчера данных нет."
    )
    return "\n".join(lines)


async def build_stats_text(session: AsyncSession, user: User, now: datetime) -> str:
    """7-day per-day colour history for /stats and the menu button."""
    since = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    meals = await repo.meals_for_user_since(session, user_id=user.id, since=since)
    by_date: dict = {}
    for m in meals:
        by_date.setdefault(m.eaten_at.date(), []).append(m)

    lines = [f"📊 {user.display_name or 'Твоя'} аналитика по дням:"]
    for i in range(7):
        d = (now - timedelta(days=i)).date()
        day_meals = by_date.get(d, [])
        zone = day_zone(day_meals)
        label = _DAY_LABELS.get(i, d.strftime("%d.%m"))
        if day_meals:
            lo, hi = day_total_kcal(day_meals)
            lines.append(
                f"{ZONE_EMOJI[zone]} {label} — {ZONE_RU[zone]} зона, "
                f"~{lo}-{hi} ккал ({len(day_meals)} приёмов)"
            )
        else:
            lines.append(f"{ZONE_EMOJI['gray']} {label} — серая зона (еды не было)")
    return "\n".join(lines)
