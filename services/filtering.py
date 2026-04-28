from database.models import ParsedOrder, UserSettings


def order_matches_settings(order: ParsedOrder, settings: UserSettings) -> bool:
    text = f"{order.title} {order.description}".lower()
    category = order.category.lower()
    budget = order.max_budget or order.min_budget or 0

    if budget < settings.min_budget or budget > settings.max_budget:
        return False
    if settings.only_urgent and not order.is_urgent:
        return False
    if settings.categories and not any(cat.lower() in category for cat in settings.categories):
        return False
    if settings.keywords and not any(keyword.lower() in text for keyword in settings.keywords):
        return False
    if settings.blacklist_words and any(word.lower() in text for word in settings.blacklist_words):
        return False
    return True
