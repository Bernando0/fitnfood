"""Text-based meal logging via the explicit /ate command.

The bot stays silent on ordinary chat: it only reacts to commands and photos.
For when a photo was forgotten, /ate <description> logs a meal from words.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.db import repo
from bot.db.session import SessionLocal
from bot.handlers.callbacks import meal_kb
from bot.llm.client import analyze_text
from bot.llm.prompts import analyze_user_context
from bot.services.meal_slot import SLOTS_RU, meal_slot
from bot.services.zones import ZONE_EMOJI

router = Router()

_HINT = (
    "Опиши, что съел: /ate овсянка с омлетом и творогом, средняя порция. "
    "А ещё можно просто кинуть фото еды 📷"
)


@router.message(Command("ate", "eat_text", "съел", "ел", "еда"))
async def cmd_ate(message: Message, command: CommandObject) -> None:
    if settings.allowed_chat_id and message.chat.id != settings.allowed_chat_id:
        return
    if message.from_user is None:
        return
    description = (command.args or "").strip()
    if not description:
        await message.reply(_HINT)
        return

    tg = message.from_user
    name = tg.full_name

    meal_id = None
    async with SessionLocal() as session:
        group = await repo.get_or_create_group(session, chat_id=message.chat.id)
        tone = group.tone
        now = datetime.now(ZoneInfo(group.timezone or settings.tz)).replace(tzinfo=None)
        slot = meal_slot(now)
        user = await repo.get_or_create_user(
            session,
            tg_user_id=tg.id,
            chat_id=message.chat.id,
            display_name=name,
            username=tg.username,
        )
        if not user.is_active:
            await session.commit()
            return

        earlier = await repo.meals_today(session, user_id=user.id, now=now)
        earlier_desc = [
            f"{m.dish_name} (~{m.kcal_min}-{m.kcal_max} ккал)"
            for m in earlier
            if m.dish_name
        ]
        context = analyze_user_context(name, SLOTS_RU[slot], earlier_desc, user.goal)

        result = await analyze_text(description, context, tone=tone)
        is_food = bool(result.get("is_food"))
        if is_food:
            meal = await repo.add_meal(
                session,
                user_id=user.id,
                chat_id=message.chat.id,
                tg_message_id=message.message_id,
                eaten_at=now,
                meal_slot=slot,
                dish_name=result.get("dish_name"),
                kcal_min=result.get("kcal_min"),
                kcal_max=result.get("kcal_max"),
                protein_g=result.get("protein_g"),
                fat_g=result.get("fat_g"),
                carbs_g=result.get("carbs_g"),
                health_score=result.get("health_score"),
                coach_reply=result.get("coach_message"),
            )
            meal_id = meal.id
        await session.commit()

    if not is_food:
        await message.reply("Это не похоже на еду. " + _HINT)
        return
    reply = result.get("coach_message")
    if reply:
        prefix = ZONE_EMOJI.get(result.get("health_score"), "")
        keyboard = meal_kb(meal_id) if meal_id else None
        await message.reply(f"{prefix} {reply}".strip(), reply_markup=keyboard)
