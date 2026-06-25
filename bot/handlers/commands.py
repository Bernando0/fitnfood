"""User-facing commands: help, opt-out, goals, on-demand report, data deletion."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.db import repo
from bot.db.session import SessionLocal
from bot.services.zones import ZONE_EMOJI, ZONE_RU, day_total_kcal, day_zone

router = Router()

HELP = (
    "🍽 Что я умею\n"
    "• Кидай фото еды — разберу: калории (примерно), зона 🟢🟡🔴 и жёсткий честный вердикт.\n"
    "• Помню каждого отдельно и веду аналитику по дням.\n"
    "• Вечером — разбор дня по всем.\n\n"
    "Команды\n"
    "/help — эта справка\n"
    "📷 Просто кинь фото еды (можно с подписью: состав, порция).\n"
    "✍️ Забыл сфоткать? /ate и что съел — напр. /ate овсянка с омлетом и творогом, средняя порция (в личке можно без команды).\n"
    "/stats — твоя аналитика по дням (🟢🟡🔴⚪ за неделю)\n"
    "/goal lose|gain|maintain — задать личную цель (снизить/набрать/держать)\n"
    "/report — прислать сводку за сегодня прямо сейчас\n"
    "/stop — перестать анализировать мои фото\n"
    "/resume — снова анализировать мои фото\n"
    "/delete — удалить все мои данные\n\n"
    "⚠️ Оценки приблизительные, это не медицинский совет."
)


@router.message(Command("start", "help"))
async def cmd_help(message: Message) -> None:
    await message.reply(HELP)


@router.message(Command("goal"))
async def cmd_goal(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    arg = (command.args or "").strip().lower()
    if arg not in {"lose", "gain", "maintain"}:
        await message.reply("Использование: /goal lose | gain | maintain")
        return
    async with SessionLocal() as session:
        user = await repo.get_or_create_user(
            session,
            tg_user_id=message.from_user.id,
            chat_id=message.chat.id,
            display_name=message.from_user.full_name,
            username=message.from_user.username,
        )
        user.goal = arg
        await session.commit()
    labels = {"lose": "снижение веса", "gain": "набор массы", "maintain": "поддержание"}
    await message.reply(f"Принято 👍 Цель: {labels[arg]}. Буду учитывать мягко, без давления.")


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        await repo.set_active(
            session, tg_user_id=message.from_user.id, chat_id=message.chat.id, active=False
        )
        await session.commit()
    await message.reply("Ок, больше не анализирую твои фото. Вернуться — /resume.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        await repo.set_active(
            session, tg_user_id=message.from_user.id, chat_id=message.chat.id, active=True
        )
        await session.commit()
    await message.reply("С возвращением! Снова на связи 🙂")


@router.message(Command("delete"))
async def cmd_delete(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        await repo.delete_user_data(
            session, tg_user_id=message.from_user.id, chat_id=message.chat.id
        )
        await session.commit()
    await message.reply("Все твои данные удалены.")


_DAY_LABELS = {0: "Сегодня", 1: "Вчера", 2: "Позавчера"}


@router.message(Command("stats", "stat", "история", "итоги"))
async def cmd_stats(message: Message) -> None:
    """Per-day colour history for the sender over the last 7 days."""
    if message.from_user is None:
        return
    name = message.from_user.full_name
    now = datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)
    since = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

    async with SessionLocal() as session:
        user = await repo.get_or_create_user(
            session,
            tg_user_id=message.from_user.id,
            chat_id=message.chat.id,
            display_name=name,
            username=message.from_user.username,
        )
        meals = await repo.meals_for_user_since(session, user_id=user.id, since=since)
        await session.commit()

    by_date: dict = {}
    for m in meals:
        by_date.setdefault(m.eaten_at.date(), []).append(m)

    lines = [f"📊 {name}, аналитика по дням:"]
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
    await message.reply("\n".join(lines))


@router.message(Command("report"))
async def cmd_report(message: Message, bot: Bot) -> None:
    # Imported here to avoid a circular import at module load.
    from bot.scheduler.summary import send_report_for_chat

    await send_report_for_chat(bot, message.chat.id)
