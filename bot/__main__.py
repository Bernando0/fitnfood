"""Entry point: wire up the bot, routers, scheduler and start long-polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.db.session import init_db
from bot.handlers import commands, onboarding, photos
from bot.scheduler.summary import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("fitfood")


async def main() -> None:
    await init_db()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    # Order matters: commands & onboarding before the broad photo handler.
    dp.include_router(commands.router)
    dp.include_router(onboarding.router)
    dp.include_router(photos.router)

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
