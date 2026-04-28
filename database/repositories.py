from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotStats, ParsedOrder, UserSettings


IT_CATEGORIES = [
    "telegram",
    "parser",
    "web",
    "ai",
    "automation",
    "script",
]


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, owner_id: int) -> UserSettings:
        stmt: Select[tuple[UserSettings]] = select(UserSettings).where(UserSettings.owner_telegram_id == owner_id)
        model = await self.session.scalar(stmt)
        if model:
            return model

        model = UserSettings(owner_telegram_id=owner_id, categories=IT_CATEGORIES.copy(), keywords=[], blacklist_words=[])
        self.session.add(model)
        await self.session.flush()
        return model


class OrdersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists(self, external_id: str) -> bool:
        stmt = select(ParsedOrder.id).where(ParsedOrder.external_id == external_id).limit(1)
        return (await self.session.scalar(stmt)) is not None

    async def save(self, order: ParsedOrder) -> ParsedOrder:
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_by_id(self, order_id: int) -> ParsedOrder | None:
        stmt = select(ParsedOrder).where(ParsedOrder.id == order_id)
        return await self.session.scalar(stmt)

    async def recent(self, limit: int = 10) -> Sequence[ParsedOrder]:
        stmt = select(ParsedOrder).order_by(ParsedOrder.id.desc()).limit(limit)
        result = await self.session.scalars(stmt)
        return result.all()


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def increment(self, metric: str, amount: int = 1) -> None:
        stmt = select(BotStats).where(BotStats.metric == metric)
        row = await self.session.scalar(stmt)
        if row is None:
            row = BotStats(metric=metric, value=amount)
            self.session.add(row)
            await self.session.flush()
            return
        row.value += amount

    async def all_stats(self) -> dict[str, int]:
        rows = await self.session.scalars(select(BotStats))
        return {item.metric: item.value for item in rows}

    async def total_orders(self) -> int:
        return int(await self.session.scalar(select(func.count(ParsedOrder.id))) or 0)

    async def get_metric(self, metric: str) -> int | None:
        stmt = select(BotStats).where(BotStats.metric == metric)
        row = await self.session.scalar(stmt)
        return row.value if row is not None else None

    async def set_metric(self, metric: str, value: int) -> None:
        stmt = select(BotStats).where(BotStats.metric == metric)
        row = await self.session.scalar(stmt)
        if row is None:
            row = BotStats(metric=metric, value=value)
            self.session.add(row)
            await self.session.flush()
            return
        row.value = value
