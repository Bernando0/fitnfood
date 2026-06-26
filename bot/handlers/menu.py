"""Button-driven UX: a main menu, goal picker, and a tap-to-ask flow."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db import repo
from bot.db.session import SessionLocal
from bot.handlers.advice import tone_and_status
from bot.handlers.callbacks import (
    ASK_PROMPT,
    ask_force_reply,
    goal_kb,
    main_menu_kb,
    tone_kb,
    tz_kb,
)
from bot.llm.client import ask_coach, eat_advice
from bot.services.status import build_stats_text

router = Router()

MENU_TEXT = "Меню FitnFood 👇 Выбери, что нужно:"
_GOAL_LABELS = {"lose": "снижение веса", "gain": "набор массы", "maintain": "поддержание"}


@router.message(Command("start", "menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer(MENU_TEXT, reply_markup=main_menu_kb())


@router.callback_query(F.data == "menu:home")
async def cb_home(cb: CallbackQuery) -> None:
    await cb.answer()
    if cb.message:
        try:
            await cb.message.edit_text(MENU_TEXT, reply_markup=main_menu_kb())
        except Exception:  # noqa: BLE001
            await cb.message.answer(MENU_TEXT, reply_markup=main_menu_kb())


@router.callback_query(F.data == "menu:stats")
async def cb_stats(cb: CallbackQuery) -> None:
    await cb.answer()
    now = datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)
    async with SessionLocal() as session:
        user = await repo.get_or_create_user(
            session,
            tg_user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            display_name=cb.from_user.full_name,
            username=cb.from_user.username,
        )
        text = await build_stats_text(session, user, now)
        await session.commit()
    await cb.message.answer(text)


@router.callback_query(F.data == "menu:eat")
async def cb_eat(cb: CallbackQuery) -> None:
    await cb.answer("Думаю…")
    tone, status = await tone_and_status(cb.message.chat.id, cb.from_user)
    advice = await eat_advice(status, None, tone)
    await cb.message.answer(
        advice + "\n\n💡 Хочешь из своих продуктов — напиши: /eat курица, рис, овощи"
    )


@router.callback_query(F.data == "menu:goal")
async def cb_goal(cb: CallbackQuery) -> None:
    await cb.answer()
    if cb.message:
        await cb.message.edit_text("🎯 Какая у тебя цель?", reply_markup=goal_kb())


@router.callback_query(F.data == "menu:tone")
async def cb_tone(cb: CallbackQuery) -> None:
    await cb.answer()
    if cb.message:
        await cb.message.edit_text("⚙️ Выбери тон общения чата:", reply_markup=tone_kb())


@router.callback_query(F.data == "menu:tz")
async def cb_tz_menu(cb: CallbackQuery) -> None:
    await cb.answer()
    if cb.message:
        await cb.message.edit_text("🕐 Выбери часовой пояс чата:", reply_markup=tz_kb())


@router.callback_query(F.data == "menu:help")
async def cb_help(cb: CallbackQuery) -> None:
    from bot.handlers.commands import HELP

    await cb.answer()
    if cb.message:
        await cb.message.answer(HELP)


@router.callback_query(F.data.startswith("goal:"))
async def cb_set_goal(cb: CallbackQuery) -> None:
    goal = cb.data.split(":", 1)[1]
    if goal not in _GOAL_LABELS or cb.message is None:
        await cb.answer("?")
        return
    async with SessionLocal() as session:
        user = await repo.get_or_create_user(
            session,
            tg_user_id=cb.from_user.id,
            chat_id=cb.message.chat.id,
            display_name=cb.from_user.full_name,
            username=cb.from_user.username,
        )
        user.goal = goal
        await session.commit()
    await cb.answer("Готово ✅")
    try:
        await cb.message.edit_text(f"🎯 Цель: {_GOAL_LABELS[goal]}. Учту в разборах.")
    except Exception:  # noqa: BLE001
        await cb.message.answer(f"🎯 Цель: {_GOAL_LABELS[goal]}.")


# --- tap-to-ask (stateless: ForceReply + reply detection) -------------------


@router.callback_query(F.data == "menu:ask")
async def cb_ask(cb: CallbackQuery) -> None:
    await cb.answer()
    if cb.message:
        # ForceReply auto-focuses the input as a reply to this prompt; we then
        # match that reply below — no FSM state to get lost.
        await cb.message.answer(ASK_PROMPT, reply_markup=ask_force_reply())


@router.message(
    F.reply_to_message.text == ASK_PROMPT,
    F.text,
    ~F.text.startswith("/"),
)
async def ask_reply(message: Message) -> None:
    tone, status = await tone_and_status(message.chat.id, message.from_user)
    await message.reply(await ask_coach(message.text.strip(), status, tone))
