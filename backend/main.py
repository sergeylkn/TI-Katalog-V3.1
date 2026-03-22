import sys
import os
import logging

# Додаємо шлях до поточної папки в sys.path, щоб Python бачив папки 'api', 'database' тощо.
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Тепер ці імпорти мають працювати коректно
from core.database import init_db
from api import admin, documents, products, search, chat

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Виконується при старті
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
    yield
    # Виконується при зупинці

app = FastAPI(
    title="TI-Katalog API",
    version="2.0",
    lifespan=lifespan
)

# Налаштування CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Підключення роутерів
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(products.router)
app.include_router(search.router)
app.include_router(chat.router)

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "TI-Katalog Backend",
        "docs": "/docs"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
