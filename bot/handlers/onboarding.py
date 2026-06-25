"""Greeting + disclaimer when the bot is added to a group."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated

from bot.db import repo
from bot.db.session import SessionLocal

router = Router()

WELCOME = (
    "👋 Привет! Я — ваш общий пищевой коуч.\n\n"
    "Скидывайте сюда <b>фото еды</b> — я узнаю, кто прислал, прикину калории и БЖУ, "
    "и отвечу тёплым коротким разбором: что хорошего и что можно мягко улучшить. "
    "А вечером пришлю общую сводку дня.\n\n"
    "⚠️ Я <b>не</b> медицинский сервис и не диетолог — мои оценки приблизительные, "
    "это ориентир для привычек, а не диагноз.\n\n"
    "Команды: /help — справка, /stop — перестать анализировать меня, "
    "/report — сводка прямо сейчас.\n\n"
    "👉 Важно: в настройках бота у @BotFather должен быть <b>выключен Group Privacy</b>, "
    "иначе я не увижу ваши фото."
)


@router.my_chat_member()
async def on_added(event: ChatMemberUpdated, bot: Bot) -> None:
    status = event.new_chat_member.status
    if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        async with SessionLocal() as session:
            group = await repo.get_or_create_group(session, chat_id=event.chat.id)
            already = group.onboarded
            group.onboarded = 1
            await session.commit()
        if not already:
            await bot.send_message(event.chat.id, WELCOME)
