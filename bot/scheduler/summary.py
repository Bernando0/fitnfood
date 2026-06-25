"""End-of-day report: one warm summary message per group."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import settings
from bot.db import repo
from bot.db.models import Meal, User
from bot.db.session import SessionLocal
from bot.llm.client import daily_summary

log = logging.getLogger(__name__)


def _build_report_text(rows: list[tuple[User, Meal]]) -> str | None:
    """Turn (user, meal) rows into the text we feed the summary model."""
    by_user: dict[str, list[Meal]] = defaultdict(list)
    names: dict[str, str] = {}
    for user, meal in rows:
        key = str(user.id)
        names[key] = user.display_name or user.username or "Участник"
        by_user[key].append(meal)

    if not by_user:
        return None

    blocks: list[str] = []
    for key, meals in by_user.items():
        lines = [f"{names[key]}:"]
        total_min = total_max = 0
        for m in meals:
            kcal = ""
            if m.kcal_min and m.kcal_max:
                kcal = f" ~{m.kcal_min}-{m.kcal_max} ккал"
                total_min += m.kcal_min
                total_max += m.kcal_max
            slot = m.meal_slot or ""
            lines.append(f"  - [{slot}] {m.dish_name or 'блюдо'}{kcal}")
        lines.append(f"  Итого за день: ~{total_min}-{total_max} ккал")
        blocks.append("\n".join(lines))

    return (
        "Данные за день по участникам. Сделай вечернюю сводку по инструкции:\n\n"
        + "\n\n".join(blocks)
    )


async def send_report_for_chat(bot: Bot, chat_id: int) -> None:
    now = datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    async with SessionLocal() as session:
        rows = await repo.meals_for_chat_since(session, chat_id=chat_id, since=since)

    report_text = _build_report_text(rows)
    if report_text is None:
        await bot.send_message(chat_id, "Сегодня ещё нет ни одного фото еды 🤷 Жду ваши приёмы пищи!")
        return

    try:
        summary = await daily_summary(report_text)
    except Exception:  # noqa: BLE001
        log.exception("daily_summary failed for chat %s", chat_id)
        return
    if summary:
        await bot.send_message(chat_id, summary)


async def send_all_reports(bot: Bot) -> None:
    async with SessionLocal() as session:
        chat_ids = await repo.active_chat_ids(session)
    for chat_id in chat_ids:
        try:
            await send_report_for_chat(bot, chat_id)
        except Exception:  # noqa: BLE001
            log.exception("failed to send report for chat %s", chat_id)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.tz)
    scheduler.add_job(
        send_all_reports,
        CronTrigger(hour=settings.daily_report_hour, minute=0),
        args=[bot],
        id="daily_report",
        replace_existing=True,
    )
    return scheduler
