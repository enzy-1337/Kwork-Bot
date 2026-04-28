from __future__ import annotations

from dataclasses import dataclass

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.repositories import OrdersRepository
from services.kwork_apply import KworkApplyService

router = Router(name="apply")


@dataclass(slots=True)
class ApplyDraft:
    order_id: int
    order_url: str
    text: str | None = None
    price: int | None = None
    days: int | None = None


_drafts: dict[int, ApplyDraft] = {}


def _parse_order_id(data: str) -> int:
    parts = data.split(":")
    return int(parts[1])


@router.callback_query(F.data.startswith("apply:"))
async def apply_start(callback: CallbackQuery, session_factory: async_sessionmaker) -> None:
    if not callback.data or not callback.from_user:
        return
    order_id = _parse_order_id(callback.data)
    async with session_factory() as session:
        order = await OrdersRepository(session).get_by_id(order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return
    _drafts[callback.from_user.id] = ApplyDraft(order_id=order_id, order_url=order.url)
    await callback.message.answer("✍️ Напишите текст отклика одним сообщением.")
    await callback.answer("Ожидаю текст отклика")


@router.message(F.text)
async def apply_flow_message(message: Message, kwork_apply_service: KworkApplyService) -> None:
    if not message.from_user:
        return
    draft = _drafts.get(message.from_user.id)
    if not draft:
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Сообщение пустое. Напишите текст отклика.")
        return

    if draft.text is None:
        draft.text = text
        await message.answer("💰 Укажите цену в рублях (только число), например: 5000")
        return

    if draft.price is None:
        if not text.isdigit():
            await message.answer("Цена должна быть числом. Пример: 5000")
            return
        draft.price = int(text)
        await message.answer("⏱ Укажите срок в днях (только число), например: 5")
        return

    if draft.days is None:
        if not text.isdigit():
            await message.answer("Срок должен быть числом дней. Пример: 5")
            return
        draft.days = int(text)
        await message.answer("⏳ Отправляю отклик на Kwork...")
        result = await kwork_apply_service.submit_offer(
            order_url=draft.order_url,
            text=draft.text or "",
            price=draft.price,
            days=draft.days,
        )
        _drafts.pop(message.from_user.id, None)
        await message.answer(f"{'✅' if result.ok else '❌'} {result.message}")
