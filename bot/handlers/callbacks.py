"""Inline-button callbacks: delete a logged meal, switch chat tone."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.db import repo
from bot.db.session import SessionLocal
from bot.llm.prompts import TONE_LABELS

router = Router()


def meal_kb(meal_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard with a 'delete this meal' button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить приём", callback_data=f"del:{meal_id}")]
        ]
    )


@router.callback_query(F.data.startswith("del:"))
async def on_delete_meal(cb: CallbackQuery) -> None:
    try:
        meal_id = int(cb.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка")
        return

    async with SessionLocal() as session:
        result = await repo.delete_meal_owned(
            session, meal_id=meal_id, tg_user_id=cb.from_user.id
        )
        await session.commit()

    if result is None:
        await cb.answer("Приём уже удалён")
        if cb.message:
            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except Exception:  # noqa: BLE001
                pass
        return
    if result is False:
        await cb.answer("Это не твой приём — удалить может только автор", show_alert=True)
        return

    await cb.answer("Удалено ✅")
    if cb.message:
        try:
            await cb.message.edit_text(f"🗑 Удалено: {result}. В аналитику не пойдёт.")
        except Exception:  # noqa: BLE001
            await cb.message.answer(f"🗑 Удалено: {result}.")


@router.callback_query(F.data.startswith("tone:"))
async def on_set_tone(cb: CallbackQuery) -> None:
    tone = cb.data.split(":", 1)[1] if ":" in cb.data else ""
    if tone not in TONE_LABELS or cb.message is None:
        await cb.answer("Неизвестный режим")
        return
    async with SessionLocal() as session:
        await repo.set_group_tone(session, chat_id=cb.message.chat.id, tone=tone)
        await session.commit()
    await cb.answer("Готово ✅")
    try:
        await cb.message.edit_text(f"Режим общения: {TONE_LABELS[tone]}")
    except Exception:  # noqa: BLE001
        await cb.message.answer(f"Режим общения: {TONE_LABELS[tone]}")
