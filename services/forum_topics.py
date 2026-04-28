import re

from aiogram import Bot

from database.models import ParsedOrder


class ForumTopicsService:
    def __init__(self, bot: Bot, forum_chat_id: int, topic_title_max_length: int = 120) -> None:
        self.bot = bot
        self.forum_chat_id = forum_chat_id
        self.topic_title_max_length = topic_title_max_length

    async def ensure_topic(self, title: str) -> int:
        topic = await self.bot.create_forum_topic(chat_id=self.forum_chat_id, name=title)
        return int(topic.message_thread_id)

    async def ensure_ollama_topic(self, topic_name: str) -> int:
        normalized = topic_name.strip() or "Ollama"
        return await self.ensure_topic(normalized[: self.topic_title_max_length])

    def build_order_topic_title(self, order: ParsedOrder) -> str:
        budget = f"{order.min_budget or 0} ₽"
        if order.max_budget and order.max_budget != order.min_budget:
            budget = f"{order.min_budget or 0}-{order.max_budget} ₽"
        raw_title = f"[#{order.external_id}] {order.title} • {budget}"
        safe_title = re.sub(r"\s+", " ", raw_title).strip()
        return safe_title[: self.topic_title_max_length]
