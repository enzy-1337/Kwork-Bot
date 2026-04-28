from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin


class ParsedOrder(Base, TimestampMixin):
    __tablename__ = "parsed_orders"
    __table_args__ = (UniqueConstraint("external_id", name="uq_parsed_orders_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(120), default="unknown")
    min_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    is_urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSettings(Base, TimestampMixin):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    min_budget: Mapped[int] = mapped_column(Integer, default=0)
    max_budget: Mapped[int] = mapped_column(Integer, default=1_000_000)
    categories: Mapped[list[str]] = mapped_column(JSONB, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    blacklist_words: Mapped[list[str]] = mapped_column(JSONB, default=list)
    only_urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class GenerationHistory(Base, TimestampMixin):
    __tablename__ = "generation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("parsed_orders.id", ondelete="CASCADE"))
    style: Mapped[str] = mapped_column(String(32), default="business")
    generated_text: Mapped[str] = mapped_column(Text)
    recommended_price: Mapped[int] = mapped_column(Integer)
    recommended_eta_days: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)

    order: Mapped[ParsedOrder] = relationship(backref="generations")


class BotStats(Base, TimestampMixin):
    __tablename__ = "bot_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric: Mapped[str] = mapped_column(String(120), unique=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
