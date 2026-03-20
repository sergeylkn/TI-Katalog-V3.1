"""FastAPI main — TI-Katalog v5."""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.database import engine
    from models.models import Base
    import asyncio

    # Wait for PostgreSQL (Railway may need a moment after restart)
    for attempt in range(30):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            break
        except Exception as e:
            logger.info(f"⏳ DB not ready ({attempt+1}/30) — retry in 3s… ({e})")
            await asyncio.sleep(3)

    async with engine.begin() as conn:
        # Enable pgvector extension (ignore if not available)
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            logger.info("✅ pgvector extension enabled")
        except Exception as e:
            logger.warning(f"pgvector not available: {e}")

        # Create tables
        await conn.run_sync(Base.metadata.create_all)

        # Add embedding column if pgvector is available
        try:
            await conn.execute(text(
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS embedding vector(1536)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_products_embedding "
                "ON products USING hnsw (embedding vector_cosine_ops)"
            ))
            logger.info("✅ pgvector embedding column ready")
        except Exception as e:
            logger.info(f"Embedding column: {e}")

    logger.info("✅ All DB tables ready")
    yield
    await engine.dispose()


app = FastAPI(title="TI-Katalog API v5", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api import admin, documents, products, search, chat

app.include_router(admin.router,     prefix="/api/admin")
app.include_router(documents.router, prefix="/api/documents")
app.include_router(products.router,  prefix="/api/products")
app.include_router(search.router,    prefix="/api/search")
app.include_router(chat.router,      prefix="/api/chat")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "5"}


@app.get("/")
async def root():
    return {"name": "TI-Katalog API", "version": "5", "docs": "/docs"}
