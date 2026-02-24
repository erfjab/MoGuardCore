from typing import AsyncIterator
from contextlib import asynccontextmanager
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.config import SQLALCHEMY_DATABASE_URL

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=500,
    max_overflow=300,
    pool_recycle=300,
    pool_pre_ping=True,
    echo=False,
    connect_args={"server_settings": {"statement_timeout": "120000"}},  ### 120s
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


@asynccontextmanager
async def GetDB() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                yield session
        finally:
            try:
                await session.close()
            except:  # noqa: E722
                pass
