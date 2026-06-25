"""Greeting + disclaimer when the bot is added to a group."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated

from bot.db import repo
from bot.db.session import SessionLocal

router = Router()

WELCOME = (
    "💪 Так, заходим. Я ваш пищевой тренер и я не нянька.\n\n"
    "Кидайте фото еды — узнаю, кто прислал, прикину калории и БЖУ, поставлю зону "
    "🟢🟡🔴 и скажу всё как есть, без подлизывания. Вечером — разбор дня по каждому.\n\n"
    "Забыл сфоткать? Пиши /ate и что съел. /stats — твои дни по зонам. /help — всё остальное.\n\n"
    "⚠️ Я не врач и не диетолог, оценки примерные — это ориентир, а не диагноз.\n\n"
    "👉 Важно: у @BotFather должен быть выключен Group Privacy, иначе я не вижу ваши фото."
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
