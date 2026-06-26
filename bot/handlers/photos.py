"""The core loop: food photo -> attribution -> analysis -> threaded reply."""
from __future__ import annotations

import io
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.types import Message

from bot.config import settings
from bot.db import repo
from bot.db.session import SessionLocal
from bot.llm.client import analyze_photo
from bot.llm.prompts import analyze_user_context
from bot.handlers.callbacks import meal_kb
from bot.services.images import to_jpeg_base64
from bot.services.meal_slot import SLOTS_RU, meal_slot
from bot.services.zones import ZONE_EMOJI

log = logging.getLogger(__name__)
router = Router()


@router.message(F.photo)
async def on_photo(message: Message, bot: Bot) -> None:
    if settings.allowed_chat_id and message.chat.id != settings.allowed_chat_id:
        return
    if message.from_user is None:
        return

    tg_user = message.from_user
    name = tg_user.full_name

    # Download the largest available photo size.
    buf = io.BytesIO()
    await bot.download(message.photo[-1], destination=buf)
    try:
        image_b64 = to_jpeg_base64(buf.getvalue())
    except Exception:  # noqa: BLE001
        log.exception("failed to decode photo")
        return

    meal_id = None
    async with SessionLocal() as session:
        group = await repo.get_or_create_group(session, chat_id=message.chat.id)
        tone = group.tone
        # Timestamp in the chat's own timezone so day windows / reports line up.
        now = datetime.now(ZoneInfo(group.timezone or settings.tz)).replace(tzinfo=None)
        slot = meal_slot(now)
        user = await repo.get_or_create_user(
            session,
            tg_user_id=tg_user.id,
            chat_id=message.chat.id,
            display_name=name,
            username=tg_user.username,
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
        context = analyze_user_context(
            name, SLOTS_RU[slot], earlier_desc, user.goal, caption=message.caption
        )

        result = await analyze_photo(image_b64, context, tone=tone)
        is_food = bool(result.get("is_food"))

        # Only real (human) food becomes a tracked meal that affects the zones.
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

    # Always react: food -> zone emoji + coach verdict + delete button; non-food -> roast.
    reply = result.get("coach_message")
    if not reply:
        return
    prefix = ZONE_EMOJI.get(result.get("health_score"), "") if is_food else "🤨"
    keyboard = meal_kb(meal_id) if meal_id else None
    await message.reply(f"{prefix} {reply}".strip(), reply_markup=keyboard)
