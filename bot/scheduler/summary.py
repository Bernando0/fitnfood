"""End-of-day report: per-chat, in each chat's own timezone.

A job ticks at the top of every hour. For each chat, if the local hour has
reached its summary_hour and we haven't sent today, we send the report. This
uses ZoneInfo per chat (reliable) instead of relying on APScheduler's tz.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import settings
from bot.db import repo
from bot.db.session import SessionLocal
from bot.llm.client import daily_summary
from bot.services.zones import ZONE_EMOJI, ZONE_RU, day_total_kcal, day_zone

log = logging.getLogger(__name__)


def _chat_now(tz: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz)).replace(tzinfo=None)
    except Exception:  # noqa: BLE001 — bad tz string -> fall back to default
        return datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)


def _build_report_text(rows: list[tuple[str, str, list]]) -> tuple[str | None, int]:
    total_meals = sum(len(meals) for _, _, meals in rows)
    blocks: list[str] = []
    for name, zone, meals in rows:
        emoji = ZONE_EMOJI[zone]
        if not meals:
            blocks.append(f"{name}: {emoji} серая зона — за день не прислал ни одного фото еды.")
            continue
        lo, hi = day_total_kcal(meals)
        lines = [f"{name}: {emoji} {ZONE_RU[zone]} зона, итог дня ~{lo}-{hi} ккал."]
        for m in meals:
            kcal = f" ~{m.kcal_min}-{m.kcal_max} ккал" if m.kcal_min and m.kcal_max else ""
            lines.append(f"  - [{m.meal_slot or ''}] {m.dish_name or 'блюдо'}{kcal} ({m.health_score})")
        blocks.append("\n".join(lines))

    if not blocks:
        return None, 0
    prompt = (
        "Вечерний разбор дня по участникам (зона уже посчитана — используй её и не меняй). "
        "Дай по каждому жёсткий, честный вердикт тренера: что налажал, что ок, что исправить "
        "завтра. Серая зона — отдельно подколи, что человек вообще не отчитывался.\n\n"
        + "\n\n".join(blocks)
    )
    return prompt, total_meals


async def send_report_for_chat(bot: Bot, chat_id: int) -> None:
    async with SessionLocal() as session:
        group = await repo.get_or_create_group(session, chat_id=chat_id)
        tz = group.timezone or settings.tz
        tone = group.tone
        now = _chat_now(tz)
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        users = await repo.active_users_in_chat(session, chat_id=chat_id)
        rows: list[tuple[str, str, list]] = []
        for u in users:
            meals = await repo.meals_for_user_since(session, user_id=u.id, since=since)
            name = u.display_name or u.username or "Участник"
            rows.append((name, day_zone(meals), meals))

    if not rows:
        return

    prompt, total_meals = _build_report_text(rows)
    if total_meals == 0:
        await bot.send_message(
            chat_id,
            "⚪ Сегодня у всех серая зона — ни одного фото еды. "
            "Так мы никуда не двигаемся. Завтра жду отчёты. 💪",
        )
        return

    try:
        summary = await daily_summary(prompt, tone=tone)
    except Exception:  # noqa: BLE001
        log.exception("daily_summary failed for chat %s", chat_id)
        return
    if summary:
        await bot.send_message(chat_id, summary)


async def tick(bot: Bot) -> None:
    """Hourly: send each chat's report once it reaches its local summary_hour."""
    async with SessionLocal() as session:
        groups = await repo.all_groups(session)

    for g in groups:
        try:
            tz = g.timezone or settings.tz
            local = _chat_now(tz)
            today = local.date().isoformat()
            target_hour = g.summary_hour if g.summary_hour is not None else settings.daily_report_hour
            # Fire once per day, at or after the target hour (catch-up after downtime).
            if local.hour >= target_hour and g.last_summary_date != today:
                await send_report_for_chat(bot, g.chat_id)
                async with SessionLocal() as s:
                    await repo.set_last_summary_date(s, chat_id=g.chat_id, date=today)
                    await s.commit()
        except Exception:  # noqa: BLE001
            log.exception("report tick failed for chat %s", g.chat_id)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    # Every hour at :00 — per-chat timezone is handled inside tick().
    scheduler.add_job(
        tick, CronTrigger(minute=0), args=[bot], id="report_tick", replace_existing=True
    )
    return scheduler
