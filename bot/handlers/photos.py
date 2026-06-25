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
from bot.services.images import to_jpeg_base64
from bot.services.meal_slot import SLOTS_RU, meal_slot

log = logging.getLogger(__name__)
router = Router()


@router.message(F.photo)
async def on_photo(message: Message, bot: Bot) -> None:
    if settings.allowed_chat_id and message.chat.id != settings.allowed_chat_id:
        return
    if message.from_user is None:
        return

    # Local (naive) "now" so day windows line up with the report timezone.
    now = datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)
    slot = meal_slot(now)
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

    async with SessionLocal() as session:
        await repo.get_or_create_group(session, chat_id=message.chat.id)
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
        context = analyze_user_context(name, SLOTS_RU[slot], earlier_desc, user.goal)

        result = await analyze_photo(image_b64, context)
        if not result.get("is_food"):
            await session.commit()  # stay silent on non-food
            return

        await repo.add_meal(
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
        await session.commit()

    reply = result.get("coach_message")
    if reply:
        await message.reply(reply)
