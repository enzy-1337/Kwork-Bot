from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from config.settings import Settings

BASE_URL = "https://kwork.ru"


@dataclass(slots=True)
class ApplyResult:
    ok: bool
    message: str


class KworkApplyService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Cookie": settings.kwork_cookie or "",
        }

    async def submit_offer(self, order_url: str, text: str, price: int, days: int) -> ApplyResult:
        if not self.settings.kwork_cookie:
            return ApplyResult(False, "Не задан KWORK_COOKIE в .env")

        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
            async with session.get(order_url) as response:
                response.raise_for_status()
                html = await response.text()

            form_payload, post_url = self._build_payload(order_url, html, text=text, price=price, days=days)
            if not post_url:
                return ApplyResult(False, "Не удалось найти форму отклика на странице заказа")

            async with session.post(post_url, data=form_payload, allow_redirects=True) as response:
                resp_text = await response.text()
                if response.status >= 400:
                    return ApplyResult(False, f"Kwork вернул ошибку {response.status}")
                lowered = resp_text.lower()
                if "ошиб" in lowered and "отклик" in lowered:
                    return ApplyResult(False, "Kwork отклонил отклик. Проверьте цену/текст/доступность отклика.")
                if any(marker in lowered for marker in ("предложение отправ", "отклик отправ", "ваш отклик")):
                    return ApplyResult(True, "Отклик отправлен")
                return ApplyResult(True, "Запрос отправлен, но успех не удалось подтвердить по тексту страницы")

    @staticmethod
    def _build_payload(
        order_url: str,
        html: str,
        text: str,
        price: int,
        days: int,
    ) -> tuple[dict[str, str], str | None]:
        soup = BeautifulSoup(html, "html.parser")
        form = None
        for candidate in soup.select("form"):
            form_text = candidate.get_text(" ", strip=True).lower()
            if "отклик" in form_text or "предложен" in form_text:
                form = candidate
                break
        if form is None:
            return {}, None

        payload: dict[str, str] = {}
        for input_node in form.select("input[name], textarea[name], select[name]"):
            name = str(input_node.get("name", "")).strip()
            if not name:
                continue
            payload[name] = str(input_node.get("value", "") or "")

        for field_name in ("message", "text", "description", "offer_text", "comment"):
            if field_name in payload:
                payload[field_name] = text
        for field_name in ("price", "offer_price", "budget", "amount"):
            if field_name in payload:
                payload[field_name] = str(price)
        for field_name in ("days", "duration", "term", "deadline_days"):
            if field_name in payload:
                payload[field_name] = str(days)

        # Fallback if site uses non-standard names.
        if not any(k in payload for k in ("message", "text", "description", "offer_text", "comment")):
            payload["message"] = text
        if not any(k in payload for k in ("price", "offer_price", "budget", "amount")):
            payload["price"] = str(price)
        if not any(k in payload for k in ("days", "duration", "term", "deadline_days")):
            payload["days"] = str(days)

        action = str(form.get("action") or "").strip()
        post_url = urljoin(BASE_URL, action) if action else order_url
        return payload, post_url
