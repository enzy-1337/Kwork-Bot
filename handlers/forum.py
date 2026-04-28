from __future__ import annotations

from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, Message

from services.ai_service import AIService

router = Router(name="forum")


def _thread_key(chat_id: int, thread_id: int) -> str:
    return f"{chat_id}:{thread_id}"


def _pick_file(message: Message) -> tuple[str, str] | None:
    if message.document:
        return message.document.file_id, message.document.file_name or "document.bin"
    if message.photo:
        largest = message.photo[-1]
        return largest.file_id, f"photo_{largest.file_unique_id}.jpg"
    if message.video:
        return message.video.file_id, message.video.file_name or f"video_{message.video.file_unique_id}.mp4"
    if message.audio:
        return message.audio.file_id, message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3"
    if message.voice:
        return message.voice.file_id, f"voice_{message.voice.file_unique_id}.ogg"
    if message.video_note:
        return message.video_note.file_id, f"video_note_{message.video_note.file_unique_id}.mp4"
    if message.animation:
        return message.animation.file_id, message.animation.file_name or f"animation_{message.animation.file_unique_id}.gif"
    if message.sticker:
        return message.sticker.file_id, f"sticker_{message.sticker.file_unique_id}.webp"
    return None


@router.message(F.message_thread_id)
async def ollama_forum_message(message: Message, bot: Bot, ai_service: AIService, ollama_thread_id: int | None = None) -> None:
    if not message.chat or ollama_thread_id is None or message.message_thread_id != ollama_thread_id:
        return

    if (message.text or "").strip() == "/clear":
        ai_service.clear_thread_history(_thread_key(message.chat.id, ollama_thread_id))
        await message.answer("Контекст этой темы очищен.")
        return

    if message.text and not message.text.startswith("/"):
        await message.answer("⏳ Генерирую ответ...")
        result = await ai_service.generate_free_text(
            message.text,
            thread_key=_thread_key(message.chat.id, ollama_thread_id),
        )
        await message.answer(result[:3900])
        return

    file_data = _pick_file(message)
    if not file_data:
        return

    file_id, filename = file_data
    telegram_file = await bot.get_file(file_id)
    output = BytesIO()
    await bot.download(telegram_file, destination=output)
    output.seek(0)

    await message.answer_document(
        document=BufferedInputFile(file=output.read(), filename=filename),
        caption="Файл получен и отправлен как документ.",
    )
