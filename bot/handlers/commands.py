"""User-facing commands: help, tone, goal, stats, opt-out, report, deletion."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.db import repo
from bot.db.session import SessionLocal
from bot.handlers.callbacks import goal_kb, tone_kb
from bot.llm.prompts import TONE_LABELS, TONES
from bot.services.status import build_stats_text

router = Router()

HELP = (
    "🍽 Что я умею\n"
    "• Кидай фото еды — разберу: калории (примерно), зона 🟢🟡🔴 и честный вердикт.\n"
    "• Помню каждого отдельно и веду аналитику по дням.\n"
    "• Вечером — разбор дня по всем.\n\n"
    "Проще всего — через /menu (кнопки). Команды:\n"
    "/menu — меню с кнопками\n"
    "📷 фото еды (можно с подписью: состав, порция)\n"
    "✍️ /ate и что съел — лог текстом (в личке можно без команды)\n"
    "/ask — спросить совет · /eat — что поесть сейчас\n"
    "/undo — удалить последний приём (или кнопкой 🗑 под ответом)\n"
    "/stats — аналитика по дням · /tone — тон чата · /goal — цель\n"
    "/report — сводка сейчас · /stop · /resume · /delete\n\n"
    "⚠️ Оценки приблизительные, это не медицинский совет."
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.reply(HELP)


@router.message(Command("tone", "режим"))
async def cmd_tone(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip().lower()
    if arg in TONES:
        async with SessionLocal() as session:
            await repo.set_group_tone(session, chat_id=message.chat.id, tone=arg)
            await session.commit()
        await message.reply(f"Режим общения: {TONE_LABELS[arg]}")
        return
    await message.reply("⚙️ Выбери тон общения для этого чата:", reply_markup=tone_kb())


@router.message(Command("goal"))
async def cmd_goal(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    arg = (command.args or "").strip().lower()
    if arg not in {"lose", "gain", "maintain"}:
        await message.reply("🎯 Какая у тебя цель?", reply_markup=goal_kb())
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
    await message.reply(f"🎯 Цель: {labels[arg]}. Учту в разборах.")


@router.message(Command("undo", "отмена"))
async def cmd_undo(message: Message) -> None:
    if message.from_user is None:
        return
    async with SessionLocal() as session:
        user = await repo.get_or_create_user(
            session,
            tg_user_id=message.from_user.id,
            chat_id=message.chat.id,
            display_name=message.from_user.full_name,
            username=message.from_user.username,
        )
        name = await repo.delete_last_meal(session, user_id=user.id)
        await session.commit()
    if name:
        await message.reply(f"🗑 Удалил последний приём: {name}. В аналитику не пойдёт.")
    else:
        await message.reply("Нечего удалять — приёмов пока нет.")


@router.message(Command("stats", "stat", "история", "итоги"))
async def cmd_stats(message: Message) -> None:
    if message.from_user is None:
        return
    now = datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)
    async with SessionLocal() as session:
        user = await repo.get_or_create_user(
            session,
            tg_user_id=message.from_user.id,
            chat_id=message.chat.id,
            display_name=message.from_user.full_name,
            username=message.from_user.username,
        )
        text = await build_stats_text(session, user, now)
        await session.commit()
    await message.reply(text)


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


@router.message(Command("report"))
async def cmd_report(message: Message, bot: Bot) -> None:
    # Imported here to avoid a circular import at module load.
    from bot.scheduler.summary import send_report_for_chat

    await send_report_for_chat(bot, message.chat.id)
