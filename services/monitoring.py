import asyncio
import logging

from aiogram import Bot
from cachetools import TTLCache
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.models import ParsedOrder
from database.repositories import OrdersRepository, SettingsRepository, StatsRepository
from keyboards.inline import order_actions_keyboard
from parsers.kwork_parser import KworkParser
from services.filtering import order_matches_settings
from services.forum_topics import ForumTopicsService
from services.scoring import evaluate_order
from utils.markdown import escape_markdown_v2

LOGGER = logging.getLogger(__name__)


class MonitoringService:
    def __init__(
        self,
        parser: KworkParser,
        bot: Bot,
        owner_id: int,
        parse_interval_seconds: int,
        session_factory: async_sessionmaker,
        forum_topics: ForumTopicsService | None = None,
    ) -> None:
        self.parser = parser
        self.bot = bot
        self.owner_id = owner_id
        self.parse_interval_seconds = parse_interval_seconds
        self.session_factory = session_factory
        self.forum_topics = forum_topics
        self._stop_event = asyncio.Event()
        self._seen_cache: TTLCache[str, bool] = TTLCache(maxsize=20_000, ttl=60 * 60 * 4)

    async def run_forever(self) -> None:
        LOGGER.info("Monitoring loop started")
        while not self._stop_event.is_set():
            try:
                await self._iteration()
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Monitoring iteration failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.parse_interval_seconds)
            except TimeoutError:
                continue

    def stop(self) -> None:
        self._stop_event.set()

    async def _iteration(self) -> None:
        fetched = await self.parser.fetch_orders()
        async with self.session_factory() as session:
            settings_repo = SettingsRepository(session)
            orders_repo = OrdersRepository(session)
            stats_repo = StatsRepository(session)
            settings = await settings_repo.get_or_create(self.owner_id)

            for item in fetched:
                if item.external_id in self._seen_cache:
                    continue
                if await orders_repo.exists(item.external_id):
                    self._seen_cache[item.external_id] = True
                    continue

                order = ParsedOrder(
                    external_id=item.external_id,
                    title=item.title,
                    description=item.description,
                    url=item.url,
                    author=item.author,
                    min_budget=item.min_budget,
                    max_budget=item.max_budget,
                    category=item.category,
                    is_urgent=item.is_urgent,
                )

                if not order_matches_settings(order, settings):
                    self._seen_cache[item.external_id] = True
                    await stats_repo.increment("orders_filtered")
                    continue

                order = await orders_repo.save(order)
                await stats_repo.increment("orders_sent")
                self._seen_cache[item.external_id] = True
                await self._send_new_order(order)

            await session.commit()

    async def _send_new_order(self, order: ParsedOrder) -> None:
        evaluation = evaluate_order(order)
        budget = f"{order.min_budget or 0} ₽"
        if order.max_budget and order.max_budget != order.min_budget:
            budget = f"{order.min_budget or 0} ₽ (макс. {order.max_budget} ₽)"
        text = (
            "*🔥 Новый заказ на Kwork*\n\n"
            f"*📌 Название:*\n{escape_markdown_v2(order.title)}\n\n"
            f"*👤 Автор:*\n{escape_markdown_v2(order.author)}\n\n"
            f"*💰 Бюджет:*\n{escape_markdown_v2(budget)}\n\n"
            f"*📊 Интересность:*\n{escape_markdown_v2(str(evaluation.score))}/10\n\n"
            f"*🎯 Вероятность получения:*\n{escape_markdown_v2(str(evaluation.win_probability))}%\n\n"
            f"*🧠 Сложность:*\n{escape_markdown_v2(evaluation.complexity)}\n\n"
            f"*⏱ Примерный срок:*\n{escape_markdown_v2(evaluation.eta_text)}\n\n"
            f"*🏷 Категория:*\n{escape_markdown_v2(order.category)}\n\n"
            f"*📝 Описание:*\n{escape_markdown_v2(order.description[:1000])}"
        )
        send_kwargs: dict[str, int | str | bool] = {"chat_id": self.owner_id}
        if self.forum_topics:
            thread_id = await self.forum_topics.ensure_topic(self.forum_topics.build_order_topic_title(order))
            send_kwargs = {"chat_id": self.forum_topics.forum_chat_id, "message_thread_id": thread_id}

        await self.bot.send_message(
            **send_kwargs,
            text=text,
            reply_markup=order_actions_keyboard(order.id, order.url),
            disable_web_page_preview=True,
            parse_mode="MarkdownV2",
        )
