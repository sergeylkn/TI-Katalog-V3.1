from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from database.db import get_db
from models.models import Product, Document, ParseLog, ImportLog
from services.importer import run_import_all
import os

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/env-status")
async def get_env_status():
    """Проверка наличия ключей API."""
    return {
        "anthropic_api_key": "set" if os.getenv("ANTHROPIC_API_KEY") else "missing",
        "database_url": "set" if os.getenv("DATABASE_URL") else "missing"
    }

@router.get("/import-status")
async def get_import_status(db: AsyncSession = Depends(get_db)):
    """Статистика по документам и их статусам."""
    try:
        total_docs = await db.scalar(select(func.count(Document.id)))
        pending_docs = await db.scalar(select(func.count(Document.id)).where(Document.status == "pending"))
        processing_docs = await db.scalar(select(func.count(Document.id)).where(Document.status == "processing"))
        completed_docs = await db.scalar(select(func.count(Document.id)).where(Document.status == "completed"))
        failed_docs = await db.scalar(select(func.count(Document.id)).where(Document.status == "failed"))
        
        return {
            "total": total_docs or 0,
            "pending": pending_docs or 0,
            "processing": processing_docs or 0,
            "completed": completed_docs or 0,
            "failed": failed_docs or 0
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/index-stats")
async def get_index_stats(db: AsyncSession = Depends(get_db)):
    """Статистика по количеству товаров в базе."""
    try:
        total_products = await db.scalar(select(func.count(Product.id)))
        return {"total_products": total_products or 0}
    except Exception as e:
        return {"error": str(e)}

@router.post("/clear-database")
async def clear_database(db: AsyncSession = Depends(get_db)):
    """
    Безопасная очистка базы данных. 
    Используем DELETE вместо TRUNCATE для предотвращения Deadlock.
    """
    try:
        # Удаляем данные в правильном порядке (сначала зависимые)
        await db.execute(text("DELETE FROM products"))
        await db.execute(text("DELETE FROM parse_logs"))
        await db.execute(text("DELETE FROM import_logs"))
        await db.execute(text("DELETE FROM documents"))
        
        # Сбрасываем счетчики ID (автоинкремент)
        await db.execute(text("ALTER SEQUENCE products_id_seq RESTART WITH 1"))
        await db.execute(text("ALTER SEQUENCE documents_id_seq RESTART WITH 1"))
        await db.execute(text("ALTER SEQUENCE parse_logs_id_seq RESTART WITH 1"))
        await db.execute(text("ALTER SEQUENCE import_logs_id_seq RESTART WITH 1"))
        
        await db.commit()
        return {"status": "success", "message": "Database cleared and sequences reset"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Очистка не удалась: {str(e)}")

@router.post("/import-all-pdfs")
async def import_all_pdfs(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Запуск полного импорта в фоновом режиме."""
    background_tasks.add_task(run_import_all, db)
    return {"status": "started", "message": "Import process queued in background"}

@router.get("/live-log")
async def get_live_log(db: AsyncSession = Depends(get_db)):
    """Последние 50 логов парсинга."""
    try:
        stmt = select(ParseLog).order_by(ParseLog.created_at.desc()).limit(50)
        result = await db.execute(stmt)
        logs = result.scalars().all()
        return [{"time": l.created_at, "level": l.level, "msg": l.message} for l in logs]
    except Exception as e:
        return {"error": str(e)}
