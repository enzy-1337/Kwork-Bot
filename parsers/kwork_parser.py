import logging
import json
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


@dataclass(slots=True)
class KworkOrderStatus:
    responses_count: int | None
    assigned_to: str | None
    is_completed: bool
    raw_status: str | None


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

    async def fetch_order_status(self, order_url: str) -> KworkOrderStatus:
        html = await self._fetch_url_with_retry(order_url)
        return self._parse_order_status(html)

    async def _fetch_html_with_retry(self) -> str:
        return await self._fetch_url_with_retry(self.settings.kwork_projects_url)

    async def _fetch_url_with_retry(self, url: str) -> str:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_fixed(2),
            retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        ):
            with attempt:
                timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
                async with aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        return await response.text()
        return ""

    @staticmethod
    def _parse_order_status(html: str) -> KworkOrderStatus:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        lowered = text.lower()

        responses_count: int | None = None
        responses_patterns = (
            r"(\d+)\s*отклик",
            r"отклик[а-я]*\s*[:\-]?\s*(\d+)",
            r"предложени[яй]\s*[:\-]?\s*(\d+)",
        )
        for pattern in responses_patterns:
            match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if match:
                responses_count = int(match.group(1))
                break

        is_completed = any(
            marker in lowered
            for marker in (
                "заказ выполнен",
                "проект завершен",
                "проект завершён",
                "заказ закрыт",
                "исполнитель выбран",
            )
        )

        assigned_to: str | None = None
        assignee_patterns = (
            r"(?:исполнитель|выполнил|назначен)\s*[:\-]?\s*@?([A-Za-z0-9_\-\.]{2,})",
            r"(?:победитель|выбран)\s*[:\-]?\s*@?([A-Za-z0-9_\-\.]{2,})",
        )
        for pattern in assignee_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                assigned_to = match.group(1).strip()
                break

        raw_status: str | None = None
        status_patterns = (
            r"(Заказ\s+(?:выполнен|закрыт)[^.!\n]{0,120})",
            r"(Проект\s+(?:завершен|завершён)[^.!\n]{0,120})",
            r"(Исполнитель\s+[^.!\n]{0,120})",
        )
        for pattern in status_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                raw_status = match.group(1).strip()
                break

        return KworkOrderStatus(
            responses_count=responses_count,
            assigned_to=assigned_to,
            is_completed=is_completed,
            raw_status=raw_status,
        )

    def _parse_orders(self, html: str) -> list[ParsedKworkOrder]:
        result = self._parse_from_state_data(html)
        if result:
            LOGGER.info("Parsed %s orders from Kwork (stateData)", len(result))
            return result

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.project-item, div.wants-card, article")
        result = []
        seen_external_ids: set[str] = set()

        for card in cards:
            order = self._extract_order_from_node(card)
            if not order:
                continue
            if order.external_id in seen_external_ids:
                continue
            seen_external_ids.add(order.external_id)
            result.append(order)

        # Fallback: если вёрстка изменилась и карточки не нашлись, достаем по ссылкам проектов.
        if not result:
            for anchor in soup.select("a[href*='/projects/']"):
                order = self._extract_order_from_node(anchor)
                if not order:
                    continue
                if order.external_id in seen_external_ids:
                    continue
                seen_external_ids.add(order.external_id)
                result.append(order)

        if not result:
            page_title = soup.title.get_text(" ", strip=True) if soup.title else "unknown"
            LOGGER.warning("No orders parsed. Page title: %s", page_title)
        LOGGER.info("Parsed %s orders from Kwork", len(result))
        return result

    def _parse_from_state_data(self, html: str) -> list[ParsedKworkOrder]:
        raw_json = self._extract_state_data_json(html)
        if not raw_json:
            return []
        try:
            state_data = json.loads(raw_json)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to decode window.stateData JSON")
            return []

        wants = []
        wants_list_data = state_data.get("wantsListData", {})
        if isinstance(wants_list_data, dict):
            wants = wants_list_data.get("wants", []) or []

        if not isinstance(wants, list):
            return []

        result: list[ParsedKworkOrder] = []
        seen_external_ids: set[str] = set()
        for item in wants:
            if not isinstance(item, dict):
                continue
            external_id = str(item.get("id", "")).strip()
            if not external_id or external_id in seen_external_ids:
                continue

            title = str(item.get("name", "")).strip() or "Без названия"
            description = str(item.get("description", "")).strip()
            combined_text = f"{title} {description}".lower()
            if not self._is_it_related(combined_text):
                continue

            price_limit_raw = str(item.get("priceLimit", "")).strip()
            min_budget, max_budget = self._extract_budget_from_price_limit(price_limit_raw)
            category = self._detect_category(combined_text)
            user = item.get("user", {}) if isinstance(item.get("user"), dict) else {}
            author = str(user.get("username", "kwork_user")).strip() or "kwork_user"
            is_urgent = any(word in combined_text for word in ("срочно", "urgent"))

            result.append(
                ParsedKworkOrder(
                    external_id=external_id,
                    title=title[:300],
                    description=description[:2500],
                    url=f"{BASE_URL}/projects/{external_id}",
                    author=author,
                    min_budget=min_budget,
                    max_budget=max_budget,
                    category=category,
                    is_urgent=is_urgent,
                )
            )
            seen_external_ids.add(external_id)

        return result

    @staticmethod
    def _extract_budget_from_price_limit(price_limit: str) -> tuple[int | None, int | None]:
        if not price_limit:
            return None, None
        try:
            value = int(float(price_limit))
            return value, value
        except ValueError:
            return None, None

    @staticmethod
    def _extract_state_data_json(html: str) -> str | None:
        marker = "window.stateData="
        start = html.find(marker)
        if start == -1:
            return None

        i = start + len(marker)
        while i < len(html) and html[i].isspace():
            i += 1
        if i >= len(html) or html[i] != "{":
            return None

        depth = 0
        in_string = False
        escaped = False
        for j in range(i, len(html)):
            ch = html[j]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    return html[i : j + 1]
        return None

    @staticmethod
    def _is_it_related(text: str) -> bool:
        return any(hint in text for hint in IT_HINTS)

    def _extract_order_from_node(self, node: object) -> ParsedKworkOrder | None:
        if not hasattr(node, "select_one"):
            return None

        title_node = node.select_one("a.wants-card__header-title, a.project-name, a[href*='/projects/'], a")
        if not title_node:
            return None

        title = title_node.get_text(" ", strip=True) or "Без названия"
        href = title_node.get("href") or ""
        full_url = urljoin(BASE_URL, href)
        ext_id = self._extract_external_id(full_url)
        if not ext_id:
            return None

        description_node = node.select_one("div.wants-card__description, .project-description")
        description = description_node.get_text(" ", strip=True) if description_node else ""
        raw_text = node.get_text(" ", strip=True)
        if not description:
            description = raw_text

        combined_text = f"{title} {description} {raw_text}".lower()
        if not self._is_it_related(combined_text):
            return None

        min_budget, max_budget = self._extract_budget(raw_text)
        category = self._detect_category(combined_text)
        is_urgent = any(word in raw_text.lower() for word in ("срочно", "urgent"))

        return ParsedKworkOrder(
            external_id=ext_id,
            title=title[:300],
            description=description[:2500],
            url=full_url,
            author="kwork_user",
            min_budget=min_budget,
            max_budget=max_budget,
            category=category,
            is_urgent=is_urgent,
        )

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
