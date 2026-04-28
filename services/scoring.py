from dataclasses import dataclass
from random import randint

from database.models import ParsedOrder


@dataclass(slots=True)
class OrderEvaluation:
    score: int
    win_probability: int
    complexity: str
    eta_text: str
    recommended_price: int
    recommended_eta_days: int


def evaluate_order(order: ParsedOrder) -> OrderEvaluation:
    budget = order.max_budget or order.min_budget or 3000
    text = f"{order.title} {order.description}".lower()

    score = 5
    if any(word in text for word in ("telegram", "бот", "parser", "парсер", "automation", "автоматизация")):
        score += 2
    if budget >= 10_000:
        score += 1
    if order.is_urgent:
        score += 1
    score = max(1, min(score + randint(0, 2), 10))

    if budget < 7000:
        complexity = "Легко"
        eta_days = randint(2, 4)
        price_ratio = 0.9
    elif budget < 20_000:
        complexity = "Средне"
        eta_days = randint(4, 8)
        price_ratio = 0.8
    else:
        complexity = "Сложно"
        eta_days = randint(7, 14)
        price_ratio = 0.75

    return OrderEvaluation(
        score=score,
        win_probability=max(35, min(90, score * 9)),
        complexity=complexity,
        eta_text=f"{max(1, eta_days - 1)}-{eta_days} дней",
        recommended_price=int(budget * price_ratio),
        recommended_eta_days=eta_days,
    )
