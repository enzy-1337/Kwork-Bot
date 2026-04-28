from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.repositories import SettingsRepository, StatsRepository

router = Router(name="admin")


def _panel_text() -> str:
    return (
        "Панель управления:\n"
        "/stats - статистика\n"
        "/settings - текущие фильтры\n"
        "/settings <min> <max> <urgent 0|1> - обновить бюджет/срочность\n"
        "/categories list|add <name>|remove <name>\n"
        "/keywords list|add <word>|remove <word>\n"
        "/blacklist list|add <word>|remove <word>"
    )


@router.message(Command("start"))
async def start_cmd(message: Message) -> None:
    await message.answer("Kwork monitor bot запущен. Используйте /panel")


@router.message(Command("panel"))
async def panel_cmd(message: Message) -> None:
    await message.answer(_panel_text())


@router.message(Command("stats"))
async def stats_cmd(message: Message, session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        repo = StatsRepository(session)
        stats = await repo.all_stats()
        total = await repo.total_orders()
    lines = [f"{k}: {v}" for k, v in sorted(stats.items())]
    await message.answer(f"Всего сохраненных заказов: {total}\n" + ("\n".join(lines) if lines else "Пока пусто"))


@router.message(Command("settings"))
async def settings_cmd(message: Message, session_factory: async_sessionmaker, owner_id: int) -> None:
    args = (message.text or "").split()
    async with session_factory() as session:
        repo = SettingsRepository(session)
        model = await repo.get_or_create(owner_id)
        if len(args) >= 4:
            try:
                model.min_budget = int(args[1])
                model.max_budget = int(args[2])
                model.only_urgent = args[3] == "1"
            except ValueError:
                await message.answer("Формат: /settings <min> <max> <urgent 0|1>")
                await session.rollback()
                return
        await session.commit()
    await message.answer(
        "Текущие фильтры:\n"
        f"- Бюджет: {model.min_budget}-{model.max_budget}\n"
        f"- Категории: {', '.join(model.categories)}\n"
        f"- Keywords: {', '.join(model.keywords) or '-'}\n"
        f"- Blacklist: {', '.join(model.blacklist_words) or '-'}\n"
        f"- Только срочные: {'да' if model.only_urgent else 'нет'}"
    )


@router.message(Command("categories"))
async def categories_cmd(message: Message, session_factory: async_sessionmaker, owner_id: int) -> None:
    args = (message.text or "").split(maxsplit=2)
    async with session_factory() as session:
        model = await SettingsRepository(session).get_or_create(owner_id)
        if len(args) >= 3 and args[1] in {"add", "remove"}:
            category = args[2].strip().lower()
            categories = [item.lower() for item in model.categories]
            if args[1] == "add" and category not in categories:
                categories.append(category)
            if args[1] == "remove":
                categories = [item for item in categories if item != category]
            model.categories = categories
        await session.commit()
    await message.answer("Категории мониторинга: " + ", ".join(model.categories))


@router.message(Command("keywords"))
async def keywords_cmd(message: Message, session_factory: async_sessionmaker, owner_id: int) -> None:
    args = (message.text or "").split(maxsplit=2)
    async with session_factory() as session:
        model = await SettingsRepository(session).get_or_create(owner_id)
        if len(args) >= 3 and args[1] in {"add", "remove"}:
            value = args[2].strip().lower()
            values = [item.lower() for item in model.keywords]
            if args[1] == "add" and value not in values:
                values.append(value)
            if args[1] == "remove":
                values = [item for item in values if item != value]
            model.keywords = values
        await session.commit()
    await message.answer("Ключевые слова: " + (", ".join(model.keywords) if model.keywords else "не заданы"))


@router.message(Command("blacklist"))
async def blacklist_cmd(message: Message, session_factory: async_sessionmaker, owner_id: int) -> None:
    args = (message.text or "").split(maxsplit=2)
    async with session_factory() as session:
        model = await SettingsRepository(session).get_or_create(owner_id)
        if len(args) >= 3 and args[1] in {"add", "remove"}:
            value = args[2].strip().lower()
            values = [item.lower() for item in model.blacklist_words]
            if args[1] == "add" and value not in values:
                values.append(value)
            if args[1] == "remove":
                values = [item for item in values if item != value]
            model.blacklist_words = values
        await session.commit()
    await message.answer("Черный список: " + (", ".join(model.blacklist_words) if model.blacklist_words else "пусто"))
