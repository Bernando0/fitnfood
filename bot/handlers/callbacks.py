"""Inline-button callbacks: delete a logged meal, switch chat tone."""
from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from bot.db import repo
from bot.db.session import SessionLocal
from bot.llm.prompts import TONE_LABELS

router = Router()

# Common timezones offered as buttons; any IANA name also works via /tz.
TZ_OPTIONS = [
    ("🇰🇿 Алматы / Астана", "Asia/Almaty"),
    ("🇷🇺 Москва", "Europe/Moscow"),
    ("🇺🇿 Ташкент", "Asia/Tashkent"),
    ("🇬🇪 Тбилиси", "Asia/Tbilisi"),
    ("🇦🇪 Дубай", "Asia/Dubai"),
]

# Shared by the /ask command and the menu button. The reply to this exact text
# is detected statelessly (see handlers/menu.py ask_reply).
ASK_PROMPT = "❓ Напиши свой вопрос про еду и отправь ответом на это сообщение:"


def ask_force_reply() -> ForceReply:
    return ForceReply(
        selective=True, input_field_placeholder="Например: что съесть после трени?"
    )


def meal_kb(meal_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard with a 'delete this meal' button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить приём", callback_data=f"del:{meal_id}")]
        ]
    )


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Мои дни", callback_data="menu:stats"),
                InlineKeyboardButton(text="🍳 Что поесть", callback_data="menu:eat"),
            ],
            [
                InlineKeyboardButton(text="❓ Спросить совет", callback_data="menu:ask"),
                InlineKeyboardButton(text="🎯 Цель", callback_data="menu:goal"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Тон общения", callback_data="menu:tone"),
                InlineKeyboardButton(text="🕐 Часовой пояс", callback_data="menu:tz"),
            ],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help")],
        ]
    )


def tz_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"tz:{tz}")]
            for label, tz in TZ_OPTIONS
        ]
    )


def tone_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TONE_LABELS[t], callback_data=f"tone:{t}")]
            for t in TONE_LABELS
        ]
    )


def goal_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔻 Снизить вес", callback_data="goal:lose")],
            [InlineKeyboardButton(text="🔺 Набрать массу", callback_data="goal:gain")],
            [InlineKeyboardButton(text="⚖️ Держать вес", callback_data="goal:maintain")],
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


@router.callback_query(F.data.startswith("tz:"))
async def on_set_tz(cb: CallbackQuery) -> None:
    tz = cb.data.split(":", 1)[1] if ":" in cb.data else ""
    if cb.message is None:
        await cb.answer()
        return
    try:
        ZoneInfo(tz)
    except Exception:  # noqa: BLE001
        await cb.answer("Неизвестная зона")
        return
    async with SessionLocal() as session:
        group = await repo.get_or_create_group(session, chat_id=cb.message.chat.id)
        group.timezone = tz
        hour = group.summary_hour
        await session.commit()
    await cb.answer("Готово ✅")
    text = f"🕐 Часовой пояс чата: {tz}. Вечерний отчёт — в {hour:02d}:00 по нему."
    try:
        await cb.message.edit_text(text)
    except Exception:  # noqa: BLE001
        await cb.message.answer(text)


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
