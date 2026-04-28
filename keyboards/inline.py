from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def order_actions_keyboard(order_id: int, order_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔗 Открыть заказ", url=order_url),
            ],
            [
                InlineKeyboardButton(text="🤖 Сгенерировать ответ", callback_data=f"gen:{order_id}:business"),
                InlineKeyboardButton(text="💰 Рассчитать цену", callback_data=f"price:{order_id}"),
            ],
            [
                InlineKeyboardButton(text="⏱ Оценить сроки", callback_data=f"eta:{order_id}"),
            ],
        ]
    )


def generation_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Сгенерировать заново", callback_data=f"regen:{order_id}:business"),
                InlineKeyboardButton(text="📋 Скопировать", callback_data=f"copy:{order_id}"),
            ],
            [
                InlineKeyboardButton(text="Деловой", callback_data=f"regen:{order_id}:business"),
                InlineKeyboardButton(text="Дружелюбный", callback_data=f"regen:{order_id}:friendly"),
            ],
            [
                InlineKeyboardButton(text="Экспертный", callback_data=f"regen:{order_id}:expert"),
                InlineKeyboardButton(text="Краткий", callback_data=f"regen:{order_id}:short"),
            ],
        ]
    )
