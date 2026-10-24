import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot import jobs
from bot.config import settings
from bot.db import init_db
from bot.handlers import callbacks, commands, mention

log = logging.getLogger("bot")


class SessionMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker):
        self.sessionmaker = sessionmaker

    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            return await handler(event, data)


COMMANDS = [
    ("note", "Zametka qo'shish"), ("notes", "Ochiq zametkalar"), ("done", "Bajarildi deb belgilash"),
    ("done_list", "Bajarilganlar"), ("undo", "Qayta ochish"), ("del", "O'chirish"), ("edit", "Tahrirlash"),
    ("find", "Qidirish"), ("client", "Mijoz qo'shish"), ("clients", "Mijozlar"), ("worked", "Mijoz bilan ishladim"),
    ("notworked", "Ishlanmagan mijozlar"), ("workedlist", "Ishlangan mijozlar"), ("card", "Mijoz kartochkasi"),
    ("archive", "Mijozni arxivlash"), ("categories", "Kategoriyalar"), ("stats", "Statistika"),
    ("diary", "Kundalik"), ("remind", "Eslatma qo'yish"), ("reminders", "Eslatmalar"), ("export", "CSV eksport"),
    ("my", "Mening ishlarim"), ("agenda", "Kun rejasi"), ("recurring", "Takroriy vazifalar"),
    ("settings", "Sozlamalar"), ("help", "Yordam"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN topilmadi — .env faylga yozing")

    sessionmaker = await init_db(f"sqlite+aiosqlite:///{settings.db_path}")
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()

    dp = Dispatcher(bot_username=me.username, bot_id=me.id)
    dp.update.middleware(SessionMiddleware(sessionmaker))
    dp.include_routers(commands.router, callbacks.router, mention.router)

    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in COMMANDS])

    scheduler = AsyncIOScheduler(timezone=settings.zone)
    args = [bot, sessionmaker]
    scheduler.add_job(jobs.tick, "interval", seconds=30, args=args)
    scheduler.add_job(jobs.send_morning, "cron", hour=settings.morning_summary_hour, minute=0, args=args)
    scheduler.add_job(jobs.send_daily, "cron", hour=settings.daily_summary_hour, minute=0, args=args)
    scheduler.add_job(jobs.send_weekly, "cron", day_of_week="fri", hour=18, minute=0, args=args)
    scheduler.start()

    log.info("@%s ishga tushdi", me.username)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
