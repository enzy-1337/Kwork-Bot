import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from config.settings import get_settings
from database.session import create_engine_and_factory, init_db
from handlers import admin, callbacks
from middlewares.owner_only import OwnerOnlyMiddleware
from parsers.kwork_parser import KworkParser
from services.ai_service import AIService
from services.monitoring import MonitoringService
from utils.logging import setup_logging

LOGGER = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    engine, session_factory = create_engine_and_factory(settings)
    await init_db(engine)

    if settings.bot_proxychains_enabled:
        LOGGER.info("Bot runs via proxychains entrypoint; direct Telegram connections are blocked by runtime policy.")
        bot = Bot(token=settings.bot_token)
    elif settings.telegram_proxy_required and not settings.telegram_proxy_url:
        raise RuntimeError(
            "TELEGRAM_PROXY_REQUIRED=true, но TELEGRAM_PROXY_URL не задан. "
            "Бот остановлен, чтобы не отправлять Telegram-трафик напрямую."
        )
    elif settings.telegram_proxy_url:
        LOGGER.info("Telegram API traffic is routed through proxy: %s", settings.telegram_proxy_url)
        bot_session = AiohttpSession(proxy=settings.telegram_proxy_url)
        bot = Bot(token=settings.bot_token, session=bot_session)
    else:
        LOGGER.warning("Telegram proxy is disabled. Traffic goes directly to Telegram API.")
        bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    owner_middleware = OwnerOnlyMiddleware(settings.owner_telegram_id)
    dp.message.middleware(owner_middleware)
    dp.callback_query.middleware(owner_middleware)

    dp.include_router(admin.router)
    dp.include_router(callbacks.router)

    ai_service = AIService(settings)
    parser = KworkParser(settings)
    monitor = MonitoringService(
        parser=parser,
        bot=bot,
        owner_id=settings.owner_telegram_id,
        parse_interval_seconds=settings.parse_interval_seconds,
        session_factory=session_factory,
    )

    dp["session_factory"] = session_factory
    dp["owner_id"] = settings.owner_telegram_id
    dp["ai_service"] = ai_service

    monitor_task = asyncio.create_task(monitor.run_forever(), name="kwork-monitor")
    try:
        await dp.start_polling(bot)
    finally:
        monitor.stop()
        await monitor_task
        await bot.session.close()
        await engine.dispose()
        LOGGER.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
