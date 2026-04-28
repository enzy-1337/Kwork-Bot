import logging
import re
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
        self._recent_offer_texts: list[str] = []

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
                text = await self._generate_ollama(prompt)
                return self._finalize_offer_text(text, order, evaluation, style)
            return self._finalize_offer_text(
                self._fallback_reply(order, evaluation, style),
                order,
                evaluation,
                style,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("AI generation error: %s", exc)
            return self._finalize_offer_text(
                self._fallback_reply(order, evaluation, style),
                order,
                evaluation,
                style,
            )

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

    def _finalize_offer_text(
        self,
        text: str,
        order: ParsedOrder,
        evaluation: OrderEvaluation,
        style: str,
    ) -> str:
        normalized = self._normalize_text(text)
        if not normalized:
            text = self._fallback_reply(order, evaluation, style)
            normalized = self._normalize_text(text)

        if self._is_repetitive(normalized):
            text = self._fallback_reply(order, evaluation, style, variant_seed=randint(100, 999))
            normalized = self._normalize_text(text)

        self._recent_offer_texts.append(normalized)
        if len(self._recent_offer_texts) > 30:
            self._recent_offer_texts = self._recent_offer_texts[-30:]
        return text.strip()[:900]

    def _is_repetitive(self, normalized: str) -> bool:
        if not normalized:
            return True
        if normalized in self._recent_offer_texts:
            return True
        # Простая защита от почти одинаковых шаблонов.
        for old in self._recent_offer_texts[-8:]:
            same_prefix = normalized[:140] == old[:140]
            if same_prefix and len(normalized) > 120 and len(old) > 120:
                return True
        return False

    @staticmethod
    def _normalize_text(text: str) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip().lower()
        return compact

    @staticmethod
    def _prompt(order: ParsedOrder, evaluation: OrderEvaluation, style: str, seed: int | None) -> str:
        randomizer = seed if seed is not None else randint(1000, 9999)
        return f"""
Ты пишешь отклик на Kwork от моего лица.
Пиши живо, по-человечески, как реальный исполнитель, а не как робот.
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
- только от первого лица единственного числа: "я сделаю", "я могу", "мне удобно"
- никогда не использовать "мы", "наша команда", "наши"
- без списков, без канцелярита и без клише
- коротко обозначь релевантный опыт и конкретный план работы
- не повторяй предыдущие формулировки, используй новые слова и новый заход
- можно иногда (не всегда) допускать 0-1 мелкую пунктуационную неровность, чтобы звучало естественнее
"""

    @staticmethod
    def _fallback_reply(order: ParsedOrder, evaluation: OrderEvaluation, style: str, variant_seed: int | None = None) -> str:
        variant = (variant_seed or randint(1, 3)) % 3
        if variant == 0:
            return (
                f"Здравствуйте. Я посмотрел задачу '{order.title}' и мне она подходит по опыту. "
                f"Сначала быстро уточню детали, потом сразу соберу рабочую версию и доведу до результата под ваш сценарий. "
                f"По сроку ориентир {evaluation.eta_text}, по цене предлагаю около {evaluation.recommended_price} ₽."
            )
        if variant == 1:
            return (
                f"Добрый день! Я уже делал похожие задачи, поэтому могу взять '{order.title}' в работу без долгого старта. "
                f"Сделаю поэтапно: сначала базовый рабочий вариант, потом точные правки под вас. "
                f"Ориентир по сроку {evaluation.eta_text}, по бюджету примерно {evaluation.recommended_price} ₽."
            )
        return (
            f"Привет. Задача '{order.title}' выглядит понятной, я могу подключиться сразу и вести работу в {style} формате. "
            f"С моей стороны будет понятный план и аккуратная коммуникация по ходу. "
            f"По срокам это примерно {evaluation.eta_text}, по цене вижу адекватным около {evaluation.recommended_price} ₽"
        )
