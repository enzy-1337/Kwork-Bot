import logging
from random import randint

import aiohttp

from config.settings import Settings
from database.models import ParsedOrder
from services.scoring import OrderEvaluation

LOGGER = logging.getLogger(__name__)


class AIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._thread_histories: dict[str, list[str]] = {}

    async def generate_reply(
        self,
        order: ParsedOrder,
        evaluation: OrderEvaluation,
        style: str = "деловой",
        regenerate_seed: int | None = None,
    ) -> str:
        prompt = self._prompt(order, evaluation, style, regenerate_seed)
        try:
            if self.settings.ai_provider == "ollama":
                return await self._generate_ollama(prompt)
            return self._fallback_reply(order, evaluation, style)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("AI generation error: %s", exc)
            return self._fallback_reply(order, evaluation, style)

    async def generate_free_text(self, prompt: str, thread_key: str | None = None) -> str:
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            return "Пустой запрос. Напишите текст после команды."
        final_prompt = cleaned_prompt
        if thread_key:
            history = self._thread_histories.setdefault(thread_key, [])
            context_lines = history[-8:]
            if context_lines:
                context = "\n".join(context_lines)
                final_prompt = (
                    "Продолжай диалог с учетом контекста ниже.\n"
                    f"{context}\n"
                    f"Пользователь: {cleaned_prompt}\n"
                    "Ответ:"
                )
        try:
            if self.settings.ai_provider == "ollama":
                result = await self._generate_ollama(final_prompt)
                if thread_key:
                    self._remember_thread_messages(thread_key, cleaned_prompt, result)
                return result
            return (
                "Сейчас активен не Ollama-провайдер. "
                "Для свободной генерации включите AI_PROVIDER=ollama."
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Free text generation error: %s", exc)
            return "Ошибка генерации. Проверьте доступность Ollama и повторите запрос."

    def clear_thread_history(self, thread_key: str) -> None:
        self._thread_histories.pop(thread_key, None)

    async def _generate_ollama(self, prompt: str) -> str:
        payload = {"model": self.settings.ollama_model, "prompt": prompt, "stream": False}
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.settings.ollama_url, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                return str(data.get("response", "")).strip()

    def _remember_thread_messages(self, thread_key: str, prompt: str, result: str) -> None:
        history = self._thread_histories.setdefault(thread_key, [])
        history.append(f"Пользователь: {prompt}")
        history.append(f"Ассистент: {result}")
        if len(history) > 20:
            self._thread_histories[thread_key] = history[-20:]

    @staticmethod
    def _prompt(order: ParsedOrder, evaluation: OrderEvaluation, style: str, seed: int | None) -> str:
        randomizer = seed if seed is not None else randint(1000, 9999)
        return f"""
Ты профессиональный фрилансер на Kwork. Напиши уникальный отклик, без шаблонности.
Стиль: {style}
Случайный маркер вариативности: {randomizer}
Название заказа: {order.title}
Описание: {order.description}
Бюджет: {order.min_budget or 0}-{order.max_budget or 0}
Сложность: {evaluation.complexity}
Оценка интересности: {evaluation.score}/10
Ожидаемый срок: {evaluation.eta_text}
Рекомендуемая цена: {evaluation.recommended_price}
Требования:
- до 900 символов
- естественно, по-человечески
- без списков и без шаблонных фраз
- коротко обозначь опыт и предложи план
"""

    @staticmethod
    def _fallback_reply(order: ParsedOrder, evaluation: OrderEvaluation, style: str) -> str:
        return (
            f"Здравствуйте! Интересная задача по теме '{order.title}'. "
            f"Могу взять проект в работу в {style} формате взаимодействия: аккуратно согласуем этапы, "
            f"сначала сделаю базовый результат, затем доработки под ваши детали. "
            f"По сроку ориентир {evaluation.eta_text}, по бюджету предлагаю около {evaluation.recommended_price} ₽."
        )
