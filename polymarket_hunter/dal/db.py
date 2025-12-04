from typing import Any, AsyncGenerator, Optional

import redis.asyncio as redis
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql.base import Executable
from sqlmodel import SQLModel

from polymarket_hunter.config.settings import settings
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

REDIS_CLIENT = redis.from_url(settings.REDIS_URL, decode_responses=True)
POSTGRES_ENGINE = create_async_engine(settings.POSTGRES_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(bind=POSTGRES_ENGINE, expire_on_commit=False)


async def get_postgres_session() -> AsyncGenerator[AsyncSession, Any]:
    async with AsyncSessionLocal() as session:
        yield session


async def delete_db_and_tables():
    async with POSTGRES_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


async def create_db_and_tables():
    async with POSTGRES_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def write_object(obj: SQLModel) -> bool:
    async for session in get_postgres_session():
        try:
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return True
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error during persistence of {obj.__tablename__}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during persistence: {e}")
            return False
    else:
        return False


async def get_object(statement: Executable) -> Optional[Any]:
    async for session in get_postgres_session():
        try:
            result = await session.execute(statement)
            obj = result.scalars().first()
            if obj:
                session.expunge(obj)
                return obj
            return None
        except Exception as e:
            logger.error(f"Unexpected error during execute: {e}")
            return None
    else:
        return None