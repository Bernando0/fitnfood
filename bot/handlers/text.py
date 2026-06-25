"""Text-based meal logging: '/ate <что съел>' anywhere, or plain text in a DM.

For when someone forgot to photograph the meal. Shares the same analysis,
zoning and storage as photo meals.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.db import repo
from bot.db.session import SessionLocal
from bot.handlers.advice import tone_and_status
from bot.handlers.callbacks import meal_kb
from bot.llm.client import analyze_text, ask_coach
from bot.llm.prompts import analyze_user_context
from bot.services.meal_slot import SLOTS_RU, meal_slot
from bot.services.zones import ZONE_EMOJI

router = Router()

_HINT = (
    "Опиши, что съел — например: «на обед борщ с хлебом, средняя порция» "
    "или /ate овсянка с омлетом и творогом, средняя порция."
)


async def _log_meal_text(
    message: Message, description: str | None, *, answer_if_not_food: bool = False
) -> None:
    if settings.allowed_chat_id and message.chat.id != settings.allowed_chat_id:
        return
    if message.from_user is None:
        return
    description = (description or "").strip()
    if not description:
        await message.reply(_HINT)
        return

    now = datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)
    slot = meal_slot(now)
    tg = message.from_user
    name = tg.full_name

    meal_id = None
    async with SessionLocal() as session:
        group = await repo.get_or_create_group(session, chat_id=message.chat.id)
        tone = group.tone
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
        # Not a meal report. In a DM treat it as a question and answer it;
        # for the /ate command just nudge with the usage hint.
        if answer_if_not_food:
            tone, status = await tone_and_status(message.chat.id, message.from_user)
            await message.reply(await ask_coach(description, status, tone))
        else:
            await message.reply(_HINT)
        return
    reply = result.get("coach_message")
    if reply:
        prefix = ZONE_EMOJI.get(result.get("health_score"), "")
        keyboard = meal_kb(meal_id) if meal_id else None
        await message.reply(f"{prefix} {reply}".strip(), reply_markup=keyboard)


@router.message(Command("ate", "eat", "съел", "ел", "еда"))
async def cmd_ate(message: Message, command: CommandObject) -> None:
    await _log_meal_text(message, command.args)


@router.message(F.chat.type == ChatType.PRIVATE, F.text, ~F.text.startswith("/"))
async def private_text_meal(message: Message) -> None:
    # In a 1:1 chat: a meal report is logged; a question/chat is answered.
    await _log_meal_text(message, message.text, answer_if_not_food=True)
