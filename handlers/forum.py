from __future__ import annotations

from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.repositories import StatsRepository
from services.ai_service import AIService

router = Router(name="forum")


def _thread_key(chat_id: int, thread_id: int) -> str:
    return f"{chat_id}:{thread_id}"


def _ollama_thread_metric(chat_id: int) -> str:
    return f"ollama_thread_id:{chat_id}"


async def _get_saved_ollama_thread_id(session_factory: async_sessionmaker, chat_id: int) -> int | None:
    async with session_factory() as session:
        return await StatsRepository(session).get_metric(_ollama_thread_metric(chat_id))


async def _save_ollama_thread_id(session_factory: async_sessionmaker, chat_id: int, thread_id: int) -> None:
    async with session_factory() as session:
        repo = StatsRepository(session)
        await repo.set_metric(_ollama_thread_metric(chat_id), thread_id)
        await session.commit()


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


@router.message(Command("bind_ollama"), F.message_thread_id)
async def bind_ollama_topic(message: Message, session_factory: async_sessionmaker) -> None:
    if not message.chat or not message.message_thread_id:
        await message.answer("Команду нужно отправить внутри темы.")
        return
    await _save_ollama_thread_id(session_factory, message.chat.id, message.message_thread_id)
    await message.answer("Текущая тема привязана как Ollama-тема. Теперь бот будет отвечать здесь после перезапуска тоже.")


@router.message(F.message_thread_id)
async def ollama_forum_message(
    message: Message,
    bot: Bot,
    ai_service: AIService,
    session_factory: async_sessionmaker,
    ollama_thread_id: int | None = None,
) -> None:
    if not message.chat or not message.message_thread_id:
        return

    saved_thread_id = await _get_saved_ollama_thread_id(session_factory, message.chat.id)
    target_thread_id = saved_thread_id or ollama_thread_id
    if target_thread_id is None or message.message_thread_id != target_thread_id:
        return

    if (message.text or "").strip() == "/clear":
        ai_service.clear_thread_history(_thread_key(message.chat.id, target_thread_id))
        await message.answer("Контекст этой темы очищен.")
        return

    if message.text and not message.text.startswith("/"):
        await message.answer("⏳ Генерирую ответ...")
        result = await ai_service.generate_free_text(
            message.text,
            thread_key=_thread_key(message.chat.id, target_thread_id),
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
