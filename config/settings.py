from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    owner_telegram_id: int = Field(alias="OWNER_TELEGRAM_ID")

    database_url: str = Field(alias="DATABASE_URL")

    kwork_projects_url: str = Field(
        default="https://kwork.ru/projects",
        alias="KWORK_PROJECTS_URL",
    )
    parse_interval_seconds: int = Field(default=45, alias="PARSE_INTERVAL_SECONDS")
    request_timeout_seconds: int = Field(default=20, alias="REQUEST_TIMEOUT_SECONDS")
    telegram_forum_chat_id: int | None = Field(default=None, alias="TELEGRAM_FORUM_CHAT_ID")
    forum_auto_create_topics: bool = Field(default=True, alias="FORUM_AUTO_CREATE_TOPICS")
    forum_topic_title_max_length: int = Field(default=120, alias="FORUM_TOPIC_TITLE_MAX_LENGTH")
    ollama_topic_name: str = Field(default="Ollama", alias="OLLAMA_TOPIC_NAME")
    kwork_cookie: str | None = Field(default=None, alias="KWORK_COOKIE")
    bot_proxychains_enabled: bool = Field(default=True, alias="BOT_PROXYCHAINS_ENABLED")
    telegram_proxy_url: str | None = Field(default=None, alias="TELEGRAM_PROXY_URL")
    telegram_proxy_required: bool = Field(default=True, alias="TELEGRAM_PROXY_REQUIRED")

    ai_provider: Literal["ollama", "hf", "gemini"] = Field(default="ollama", alias="AI_PROVIDER")
    ollama_url: str = Field(default="http://ollama:11434/api/generate", alias="OLLAMA_URL")
    ollama_model: str = Field(default="qwen2.5:7b", alias="OLLAMA_MODEL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    hf_api_token: str | None = Field(default=None, alias="HF_API_TOKEN")
    hf_model: str = Field(default="HuggingFaceH4/zephyr-7b-beta", alias="HF_MODEL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
