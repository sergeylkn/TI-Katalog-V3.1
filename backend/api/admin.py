from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
import os
import logging

# Імпорти з вашого проекту
# Використовуємо відносні/пакетні імпорти
from core.database import get_db
from models.models import Product, Document, ParseLog, ImportLog
from services.importer import run_import_all

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger("admin_api")

@router.get("/env-status")
async def get_env_status():
    """Перевірка налаштувань середовища."""
    return {
        "anthropic_api_key": "set" if os.getenv("ANTHROPIC_API_KEY") else "missing",
        "database_url": "set" if os.getenv("DATABASE_URL") else "missing",
        "r2_bucket": "set" if os.getenv("R2_BUCKET_URL") else "missing"
    }

@router.get("/import-status")
async def get_import_status(db: AsyncSession = Depends(get_db)):
    """Отримати статистику завантаження документів."""
    try:
        total = await db.scalar(select(func.count(Document.id)))
        pending = await db.scalar(select(func.count(Document.id)).where(Document.status == "pending"))
        processing = await db.scalar(select(func.count(Document.id)).where(Document.status == "processing"))
        completed = await db.scalar(select(func.count(Document.id)).where(Document.status == "completed"))
        failed = await db.scalar(select(func.count(Document.id)).where(Document.status == "failed"))
        
        return {
            "total": total or 0,
            "pending": pending or 0,
            "processing": processing or 0,
            "completed": completed or 0,
            "failed": failed or 0
        }
    except Exception as e:
        logger.error(f"Error getting import status: {e}")
        return {"error": str(e)}

@router.get("/index-stats")
async def get_index_stats(db: AsyncSession = Depends(get_db)):
    """Статистика товарів у базі."""
    try:
        total_products = await db.scalar(select(func.count(Product.id)))
        return {"total_products": total_products or 0}
    except Exception as e:
        return {"error": str(e)}

@router.post("/clear-database")
async def clear_database(db: AsyncSession = Depends(get_db)):
    """
    Безпечне очищення бази даних через DELETE.
    Це запобігає Deadlock, який виникає при TRUNCATE.
    """
    try:
        # Видаляємо дані в каскадному порядку
        await db.execute(text("DELETE FROM products"))
        await db.execute(text("DELETE FROM parse_logs"))
        await db.execute(text("DELETE FROM import_logs"))
        await db.execute(text("DELETE FROM documents"))
        
        # Скидаємо лічильники ID для PostgreSQL
        sequences = [
            "products_id_seq", 
            "documents_id_seq", 
            "parse_logs_id_seq", 
            "import_logs_id_seq"
        ]
        for seq in sequences:
            try:
                await db.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
            except Exception as seq_e:
                logger.warning(f"Could not reset sequence {seq}: {seq_e}")
        
        await db.commit()
        return {"status": "success", "message": "Database cleared successfully"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to clear database: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/import-all-pdfs")
async def import_all_pdfs(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Запуск повного імпорту з R2 у фоновому режимі."""
    background_tasks.add_task(run_import_all, db)
    return {"status": "started", "message": "Background import process initiated"}

@router.get("/live-log")
async def get_live_log(db: AsyncSession = Depends(get_db)):
    """Останні події парсингу."""
    try:
        stmt = select(ParseLog).order_by(ParseLog.created_at.desc()).limit(50)
        result = await db.execute(stmt)
        logs = result.scalars().all()
        return [
            {
                "time": log.created_at.isoformat() if log.created_at else None,
                "level": log.level,
                "message": log.message
            } for log in logs
        ]
    except Exception as e:
        return {"error": str(e)}
