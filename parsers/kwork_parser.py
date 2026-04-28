import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from config.settings import Settings

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://kwork.ru"
IT_HINTS = (
    "разработка и it",
    "разработка",
    "it",
    "айти",
    "программирование",
    "разработчик",
    "backend",
    "frontend",
    "fullstack",
    "python",
    "django",
    "fastapi",
    "flask",
    "javascript",
    "typescript",
    "node",
    "react",
    "vue",
    "php",
    "laravel",
    "wordpress",
    "битрикс",
    "1с",
    "c#",
    "java",
    "kotlin",
    "swift",
    "go",
    "sql",
    "postgres",
    "mysql",
    "telegram",
    "бот",
    "parser",
    "парсер",
    "scraping",
    "автоматизац",
    "скрипт",
    "api",
    "интеграц",
    "веб",
    "сайт",
    "лендинг",
    "мобильн",
    "ios",
    "android",
    "ai",
    "gpt",
    "llm",
    "нейросет",
)


@dataclass(slots=True)
class ParsedKworkOrder:
    external_id: str
    title: str
    description: str
    url: str
    author: str
    min_budget: int | None
    max_budget: int | None
    category: str
    is_urgent: bool


class KworkParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }

    async def fetch_orders(self) -> list[ParsedKworkOrder]:
        html = await self._fetch_html_with_retry()
        return self._parse_orders(html)

    async def _fetch_html_with_retry(self) -> str:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_fixed(2),
            retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        ):
            with attempt:
                timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
                async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
                    async with session.get(self.settings.kwork_projects_url) as response:
                        response.raise_for_status()
                        return await response.text()
        return ""

    def _parse_orders(self, html: str) -> list[ParsedKworkOrder]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.project-item, div.wants-card, article")
        result: list[ParsedKworkOrder] = []

        for card in cards:
            title_node = card.select_one("a.wants-card__header-title, a.project-name, a")
            if not title_node:
                continue
            title = title_node.get_text(" ", strip=True)
            href = title_node.get("href") or ""
            full_url = urljoin(BASE_URL, href)
            ext_id = self._extract_external_id(full_url)
            if not ext_id:
                continue

            description = (card.select_one("div.wants-card__description, .project-description") or card).get_text(
                " ", strip=True
            )
            price_text = card.get_text(" ", strip=True)
            combined_card_text = f"{title} {description} {price_text}".lower()
            if not self._is_it_related(combined_card_text):
                continue
            min_budget, max_budget = self._extract_budget(price_text)
            category = self._detect_category(f"{title} {description}")
            is_urgent = any(word in price_text.lower() for word in ("срочно", "urgent"))

            result.append(
                ParsedKworkOrder(
                    external_id=ext_id,
                    title=title,
                    description=description[:2500],
                    url=full_url,
                    author="kwork_user",
                    min_budget=min_budget,
                    max_budget=max_budget,
                    category=category,
                    is_urgent=is_urgent,
                )
            )
        LOGGER.info("Parsed %s orders from Kwork", len(result))
        return result

    @staticmethod
    def _is_it_related(text: str) -> bool:
        return any(hint in text for hint in IT_HINTS)

    @staticmethod
    def _extract_external_id(url: str) -> str | None:
        match = re.search(r"/(?:projects|project)/(\d+)", url)
        return match.group(1) if match else None

    @staticmethod
    def _extract_budget(text: str) -> tuple[int | None, int | None]:
        values = [int(item.replace(" ", "")) for item in re.findall(r"(\d[\d ]{2,})\s*₽", text)]
        if not values:
            return None, None
        if len(values) == 1:
            return values[0], values[0]
        return min(values), max(values)

    @staticmethod
    def _detect_category(text: str) -> str:
        raw = text.lower()
        if "telegram" in raw or "телеграм" in raw or "бот" in raw:
            return "telegram"
        if "парсер" in raw or "parser" in raw:
            return "parser"
        if "ai" in raw or "gpt" in raw or "llm" in raw:
            return "ai"
        if "автоматизац" in raw or "automation" in raw:
            return "automation"
        if "script" in raw or "скрипт" in raw:
            return "script"
        return "web"
