from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
import os
import logging

# Імпорти з вашого проекту
from core.database import get_db
from models.models import Product, Document, ParseLog, ImportLog
from services.importer import run_import_all
from services.live_log import bus
from services.auth import (
    create_access_token, 
    verify_password, 
    DEFAULT_ADMIN,
    get_current_admin
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger("admin_api")

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    """Вхід в адмін-панель."""
    if credentials.username != DEFAULT_ADMIN["username"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(credentials.password, DEFAULT_ADMIN["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(admin_id=credentials.username)
    logger.info(f"Admin login successful: {credentials.username}")
    return TokenResponse(access_token=token)

@router.get("/whoami")
async def whoami(admin: str = Depends(get_current_admin)):
    """Інформація про поточного адміністратора."""
    return {"admin": admin, "authenticated": True}

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
async def get_live_log_sse():
    """Live event stream (SSE) для логів парсингу."""
    async def event_generator():
        async for event in bus.stream():
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

@router.get("/parse-logs")
async def get_parse_logs(db: AsyncSession = Depends(get_db)):
    """Останні події парсингу (JSON)."""
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

@router.post("/rebuild-search-text")
async def rebuild_search_text(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Переіндексація пошукового текста для всіх товарів."""
    async def rebuild_task():
        try:
            from models.models import Product
            from sqlalchemy.orm import selectinload

            logger.info("🔄 Starting search text rebuild...")
            bus.push({
                "type": "log",
                "level": "info",
                "msg": "🔄 Starting search text rebuild..."
            })

            # Оновлюємо search_text для кожного товару
            stmt = select(Product)
            result = await db.execute(stmt)
            products = result.scalars().all()

            updated = 0
            for product in products:
                # Реконструюємо пошуковий текст
                attr_values = [str(v) for v in (product.attributes or {}).values() if v]
                certs = product.certifications or ""
                search_text = f"{product.title} {product.sku} {' '.join(attr_values)} {certs}".lower()

                if product.search_text != search_text:
                    product.search_text = search_text
                    updated += 1

                if updated % 50 == 0:
                    logger.info(f"Updated {updated} products...")

            await db.commit()
            logger.info(f"✅ Search rebuild complete: {updated} products updated")
            bus.push({
                "type": "log",
                "level": "done",
                "msg": f"✅ Search rebuild complete: {updated} products updated"
            })
        except Exception as e:
            logger.error(f"Error rebuilding search text: {e}")
            bus.push({
                "type": "log",
                "level": "error",
                "msg": f"❌ Search rebuild failed: {str(e)[:200]}"
            })

    background_tasks.add_task(rebuild_task)
    return {"status": "started", "message": "Search rebuild process initiated"}

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Перевірка здоров'я API та БД."""
    try:
        from services.monitoring import monitor
        health = await monitor.get_full_health(db)

        # Determine HTTP status code
        http_status = 200 if health["status"] == "healthy" else 503
        return health, http_status

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}, 503
