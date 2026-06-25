"""Entry point: wire up the bot, routers, scheduler and start long-polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.db.session import init_db
from bot.handlers import advice, callbacks, commands, menu, onboarding, photos, text
from bot.scheduler.summary import setup_scheduler

BOT_COMMANDS = [
    BotCommand(command="menu", description="Меню с кнопками"),
    BotCommand(command="stats", description="Мои дни 🟢🟡🔴"),
    BotCommand(command="eat", description="Что лучше съесть сейчас"),
    BotCommand(command="ask", description="Спросить совет"),
    BotCommand(command="ate", description="Записать еду текстом"),
    BotCommand(command="goal", description="Моя цель"),
    BotCommand(command="tone", description="Тон общения чата"),
    BotCommand(command="undo", description="Удалить последний приём"),
    BotCommand(command="help", description="Помощь"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("fitfood")


async def main() -> None:
    await init_db()

    # Plain text by default: the coach's replies are free-form and may contain
    # characters like '<' or '>' that would break HTML/Markdown parsing.
    bot = Bot(token=settings.telegram_bot_token)
    # MemoryStorage backs the tap-to-ask FSM flow.
    dp = Dispatcher(storage=MemoryStorage())
    # Order matters: callbacks + commands + menu (incl. FSM states) before the
    # text/photo catch-alls, so an in-progress "ask" captures the next message.
    dp.include_router(callbacks.router)
    dp.include_router(commands.router)
    dp.include_router(menu.router)
    dp.include_router(advice.router)
    dp.include_router(text.router)
    dp.include_router(onboarding.router)
    dp.include_router(photos.router)

    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except Exception:  # noqa: BLE001
        log.exception("set_my_commands failed")

    scheduler = setup_scheduler(bot)
    scheduler.start()
    log.info(
        "FitFood bot started. Daily report at %02d:00 %s",
        settings.daily_report_hour,
        settings.tz,
    )

    try:
        # Only subscribe to the update types our handlers use (messages +
        # my_chat_member) so Telegram sends less traffic; drop the backlog on
        # restart so downtime doesn't replay a flood of old photos.
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down.")
