"""Ask the coach a question (/ask) and get a what-to-eat recommendation (/eat)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.db import repo
from bot.db.session import SessionLocal
from bot.llm.client import ask_coach, eat_advice
from bot.services.status import build_status_text

router = Router()


async def _tone_and_status(message: Message) -> tuple[str, str]:
    now = datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)
    async with SessionLocal() as session:
        group = await repo.get_or_create_group(session, chat_id=message.chat.id)
        user = await repo.get_or_create_user(
            session,
            tg_user_id=message.from_user.id,
            chat_id=message.chat.id,
            display_name=message.from_user.full_name,
            username=message.from_user.username,
        )
        status = await build_status_text(session, user, now)
        await session.commit()
        return group.tone, status


@router.message(Command("ask", "спроси", "вопрос"))
async def cmd_ask(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    question = (command.args or "").strip()
    if not question:
        await message.reply(
            "Спроси что-нибудь про еду: /ask что лучше съесть после тренировки?"
        )
        return
    tone, status = await _tone_and_status(message)
    await message.reply(await ask_coach(question, status, tone))


@router.message(Command("eat", "поесть", "посоветуй", "что_поесть"))
async def cmd_eat(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    products = (command.args or "").strip() or None
    tone, status = await _tone_and_status(message)
    await message.reply(await eat_advice(status, products, tone))
