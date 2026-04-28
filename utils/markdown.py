def escape_markdown_v2(text: str) -> str:
    # Telegram MarkdownV2 reserved characters.
    reserved = r"_*[]()~`>#+-=|{}.!"
    escaped = []
    for ch in text:
        if ch in reserved:
            escaped.append("\\" + ch)
        else:
            escaped.append(ch)
    return "".join(escaped)
