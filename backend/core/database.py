"""Async SQLAlchemy engine — asyncpg driver."""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

_url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://").replace("postgres://", "postgresql+asyncpg://")

engine = create_async_engine(_url, pool_size=3, max_overflow=2, pool_pre_ping=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize database schema (create tables).

    This will run SQLAlchemy's Base.metadata.create_all using an async
    engine via run_sync. It's safe to call multiple times.
    """
    try:
        # Import here to avoid circular import at module load
        from models.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        # Let caller handle/log the exception
        raise
