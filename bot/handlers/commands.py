"""User-facing commands: help, opt-out, goals, on-demand report, data deletion."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.db import repo
from bot.db.session import SessionLocal

router = Router()

HELP = (
    "🍽 <b>Что я умею</b>\n"
    "• Скидывайте фото еды — отвечу разбором: калории (примерно), что хорошего и одна мягкая "
    "идея, что можно улучшить.\n"
    "• Помню каждого участника отдельно и веду аналитику.\n"
    "• Вечером — общая сводка дня.\n\n"
    "<b>Команды</b>\n"
    "/help — эта справка\n"
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


@router.message(Command("report"))
async def cmd_report(message: Message, bot: Bot) -> None:
    # Imported here to avoid a circular import at module load.
    from bot.scheduler.summary import send_report_for_chat

    await send_report_for_chat(bot, message.chat.id)
