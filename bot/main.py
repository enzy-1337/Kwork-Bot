import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from config.settings import get_settings
from database.session import create_engine_and_factory, init_db
from handlers import admin, apply, callbacks, forum
from middlewares.owner_only import OwnerOnlyMiddleware
from parsers.kwork_parser import KworkParser
from services.ai_service import AIService
from services.forum_topics import ForumTopicsService
from services.kwork_apply import KworkApplyService
from services.monitoring import MonitoringService
from utils.logging import setup_logging

LOGGER = logging.getLogger(__name__)


async def _init_forum_topics(
    *,
    bot: Bot,
    settings,
) -> tuple[ForumTopicsService | None, int | None]:
    if not settings.telegram_forum_chat_id or not settings.forum_auto_create_topics:
        return None, None

    forum_topics = ForumTopicsService(
        bot=bot,
        forum_chat_id=settings.telegram_forum_chat_id,
        topic_title_max_length=settings.forum_topic_title_max_length,
    )
    try:
        chat = await bot.get_chat(settings.telegram_forum_chat_id)
    except TelegramNetworkError as exc:
        LOGGER.warning(
            "Не удалось проверить forum-чат из-за сети: %s. "
            "Forum mode оставлен включенным, повторная попытка будет при отправке заказов.",
            exc,
        )
        return forum_topics, None
    except TelegramBadRequest as exc:
        LOGGER.warning("Forum mode disabled: TelegramBadRequest during startup: %s", exc)
        return None, None

    if not getattr(chat, "is_forum", False):
        LOGGER.warning(
            "TELEGRAM_FORUM_CHAT_ID=%s не является forum-чатом. "
            "Forum mode отключен, сообщения будут отправляться владельцу.",
            settings.telegram_forum_chat_id,
        )
        return None, None

    try:
        ollama_thread_id = await forum_topics.ensure_ollama_topic(settings.ollama_topic_name)
        return forum_topics, ollama_thread_id
    except TelegramNetworkError as exc:
        LOGGER.warning(
            "Не удалось создать Ollama topic на старте из-за сети: %s. "
            "Forum mode оставлен включенным, топики заказов будут создаваться при отправке.",
            exc,
        )
        return forum_topics, None
    except TelegramBadRequest as exc:
        LOGGER.warning("Forum mode disabled during Ollama topic init: %s", exc)
        return None, None


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    engine, session_factory = create_engine_and_factory(settings)
    await init_db(engine)

    bot: Bot | None = None
    monitor: MonitoringService | None = None
    monitor_task: asyncio.Task[None] | None = None
    try:
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
        dp.include_router(apply.router)
        dp.include_router(forum.router)

        ai_service = AIService(settings)
        kwork_apply_service = KworkApplyService(settings)
        parser = KworkParser(settings)
        forum_topics, ollama_thread_id = await _init_forum_topics(bot=bot, settings=settings)

        monitor = MonitoringService(
            parser=parser,
            bot=bot,
            owner_id=settings.owner_telegram_id,
            parse_interval_seconds=settings.parse_interval_seconds,
            session_factory=session_factory,
            forum_topics=forum_topics,
        )

        dp["session_factory"] = session_factory
        dp["owner_id"] = settings.owner_telegram_id
        dp["ai_service"] = ai_service
        dp["kwork_apply_service"] = kwork_apply_service
        dp["kwork_parser"] = parser
        dp["ollama_thread_id"] = ollama_thread_id

        monitor_task = asyncio.create_task(monitor.run_forever(), name="kwork-monitor")
        await dp.start_polling(bot)
    finally:
        if monitor:
            monitor.stop()
        if monitor_task:
            await monitor_task
        if bot:
            await bot.session.close()
        await engine.dispose()
        LOGGER.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
