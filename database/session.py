from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from config.settings import Settings
from database.base import Base


def create_engine_and_factory(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, session_factory


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
