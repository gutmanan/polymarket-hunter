from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

DATABASE_URL = "postgresql+asyncpg://admin:admin@postgres:5432/hunter"
engine = create_async_engine(DATABASE_URL, echo=False)


async def get_postgres_session() -> AsyncSession:
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def delete_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
