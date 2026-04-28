from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.models import GenerationHistory
from database.repositories import OrdersRepository
from keyboards.inline import generation_keyboard
from parsers.kwork_parser import KworkParser
from services.ai_service import AIService
from services.scoring import evaluate_order

router = Router(name="callbacks")


def _parse_data(data: str) -> tuple[str, int, str]:
    parts = data.split(":")
    action = parts[0]
    order_id = int(parts[1])
    style = parts[2] if len(parts) > 2 else "business"
    return action, order_id, style


@router.callback_query(F.data.startswith("gen:") | F.data.startswith("regen:"))
async def generate_callback(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
    ai_service: AIService,
) -> None:
    if not callback.data:
        return
    _, order_id, style = _parse_data(callback.data)
    async with session_factory() as session:
        repo = OrdersRepository(session)
        order = await repo.get_by_id(order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        evaluation = evaluate_order(order)
        text = await ai_service.generate_reply(order=order, evaluation=evaluation, style=style)
        session.add(
            GenerationHistory(
                order_id=order.id,
                style=style,
                generated_text=text,
                recommended_price=evaluation.recommended_price,
                recommended_eta_days=evaluation.recommended_eta_days,
                score=evaluation.score,
            )
        )
        await session.commit()

    await callback.message.answer(
        "🤖 Вариант ответа:\n\n"
        f"{text}\n\n"
        f"💰 Рекомендуемая цена: ~{evaluation.recommended_price} ₽\n"
        f"⏱ Рекомендуемый срок: ~{evaluation.recommended_eta_days} дней",
        reply_markup=generation_keyboard(order_id),
    )
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("price:"))
async def price_callback(callback: CallbackQuery, session_factory: async_sessionmaker) -> None:
    if not callback.data:
        return
    _, order_id, _ = _parse_data(callback.data)
    async with session_factory() as session:
        order = await OrdersRepository(session).get_by_id(order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        evaluation = evaluate_order(order)
    await callback.message.answer(f"💰 Рекомендуемая цена отклика: ~{evaluation.recommended_price} ₽")
    await callback.answer()


@router.callback_query(F.data.startswith("eta:"))
async def eta_callback(callback: CallbackQuery, session_factory: async_sessionmaker) -> None:
    if not callback.data:
        return
    _, order_id, _ = _parse_data(callback.data)
    async with session_factory() as session:
        order = await OrdersRepository(session).get_by_id(order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        evaluation = evaluate_order(order)
    await callback.message.answer(f"⏱ Примерный срок: {evaluation.eta_text}")
    await callback.answer()


@router.callback_query(F.data.startswith("copy:"))
async def copy_callback(callback: CallbackQuery) -> None:
    await callback.answer("Скопируйте текст из предыдущего сообщения", show_alert=True)


@router.callback_query(F.data.startswith("refresh:"))
async def refresh_order_callback(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
    kwork_parser: KworkParser,
) -> None:
    if not callback.data:
        return
    _, order_id, _ = _parse_data(callback.data)
    async with session_factory() as session:
        order = await OrdersRepository(session).get_by_id(order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

    await callback.answer("Обновляю данные объявления...")
    status = await kwork_parser.fetch_order_status(order.url)

    responses_text = (
        str(status.responses_count)
        if status.responses_count is not None
        else "не удалось определить"
    )
    completed_text = "да" if status.is_completed else "нет/неизвестно"
    assigned_text = status.assigned_to or "не найдено"
    status_text = status.raw_status or "нет явной метки на странице"

    await callback.message.answer(
        "🔄 Обновление объявления\n\n"
        f"🔗 {order.url}\n"
        f"💬 Откликов: {responses_text}\n"
        f"✅ Выполнен/закрыт: {completed_text}\n"
        f"👤 Кому присвоили: {assigned_text}\n"
        f"🧾 Статус на странице: {status_text}"
    )
