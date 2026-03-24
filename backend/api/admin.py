from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
import os
import logging

from core.database import get_db
from models.models import Product, Document, ParseLog, ImportLog, ProductIndex
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
    if credentials.username != DEFAULT_ADMIN["username"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(credentials.password, DEFAULT_ADMIN["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(admin_id=credentials.username)
    return TokenResponse(access_token=token)


@router.get("/whoami")
async def whoami(admin: str = Depends(get_current_admin)):
    return {"admin": admin, "authenticated": True}


@router.get("/env-status")
async def get_env_status():
    """Перевірка налаштувань середовища — повертає {active, preview} для кожного ключа."""
    def key_info(val: str | None, preview_len: int = 14):
        if not val:
            return {"active": False, "preview": ""}
        return {"active": True, "preview": val[:preview_len] + "…"}

    return {
        "ANTHROPIC_API_KEY": key_info(os.getenv("ANTHROPIC_API_KEY")),
        "DATABASE_URL":      key_info(os.getenv("DATABASE_URL")),
        "R2_BUCKET_URL":     key_info(os.getenv("R2_BUCKET_URL")),
    }


@router.get("/import-status")
async def get_import_status(db: AsyncSession = Depends(get_db)):
    """Статус імпорту PDF-документів та кількість товарів у базі."""
    try:
        total      = await db.scalar(select(func.count(Document.id))) or 0
        pending    = await db.scalar(select(func.count(Document.id)).where(Document.status == "pending")) or 0
        processing = await db.scalar(select(func.count(Document.id)).where(Document.status == "processing")) or 0
        completed  = await db.scalar(select(func.count(Document.id)).where(Document.status == "completed")) or 0
        failed     = await db.scalar(select(func.count(Document.id)).where(Document.status == "failed")) or 0
        products   = await db.scalar(select(func.count(Product.id))) or 0

        return {
            "total":    total,
            "done":     completed,
            "error":    failed,
            "parsing":  processing,
            "pending":  pending,
            "products": products,
            "running":  processing > 0 or pending > 0,
        }
    except Exception as e:
        logger.error(f"import-status error: {e}")
        return {"total": 0, "done": 0, "error": 0, "parsing": 0, "pending": 0, "products": 0, "running": False}


@router.get("/index-stats")
async def get_index_stats(db: AsyncSession = Depends(get_db)):
    """Розширена статистика: товари, описи, сертифікати, індекси артикулів."""
    try:
        total_products = await db.scalar(select(func.count(Product.id))) or 0

        with_desc = await db.scalar(
            select(func.count(Product.id)).where(
                Product.description.isnot(None),
                Product.description != ''
            )
        ) or 0

        with_certs = await db.scalar(
            select(func.count(Product.id)).where(
                Product.certifications.isnot(None),
                Product.certifications != ''
            )
        ) or 0

        try:
            total_indexes = await db.scalar(select(func.count(ProductIndex.id))) or 0
        except Exception:
            total_indexes = 0

        return {
            "total_products":  total_products,
            "total_indexes":   total_indexes,
            "with_description": with_desc,
            "with_certs":      with_certs,
        }
    except Exception as e:
        logger.error(f"index-stats error: {e}")
        return {"total_products": 0, "total_indexes": 0, "with_description": 0, "with_certs": 0}


@router.get("/import-logs")
async def get_import_logs(limit: int = Query(150, le=500), db: AsyncSession = Depends(get_db)):
    """Історія оброблених документів (Document table)."""
    try:
        stmt = select(Document).order_by(Document.parsed_at.desc().nullslast(), Document.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        docs = result.scalars().all()

        # Підраховуємо кількість товарів на документ через subquery
        prod_counts: dict[int, int] = {}
        if docs:
            sq = select(Product.document_id, func.count(Product.id).label("cnt")).group_by(Product.document_id)
            rows = (await db.execute(sq)).all()
            prod_counts = {r.document_id: r.cnt for r in rows}

        return {
            "logs": [
                {
                    "at":       d.parsed_at.isoformat() if d.parsed_at else (d.created_at.isoformat() if d.created_at else None),
                    "status":   d.status,
                    "doc":      d.name or str(d.id),
                    "pages":    d.page_count,
                    "products": prod_counts.get(d.id, 0),
                    "error":    d.error_msg,
                }
                for d in docs
            ]
        }
    except Exception as e:
        logger.error(f"import-logs error: {e}")
        return {"logs": [], "error": str(e)}


@router.get("/parse-logs")
async def get_parse_logs(limit: int = Query(150, le=500), db: AsyncSession = Depends(get_db)):
    """Сирі записи ParseLog."""
    try:
        stmt = select(ParseLog).order_by(ParseLog.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        logs = result.scalars().all()
        return {
            "logs": [
                {
                    "at":      log.created_at.isoformat() if log.created_at else None,
                    "level":   log.level,
                    "message": log.message,
                }
                for log in logs
            ]
        }
    except Exception as e:
        return {"logs": [], "error": str(e)}


@router.post("/import-all-pdfs")
async def import_all_pdfs(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Запуск повного імпорту всіх PDF з R2."""
    background_tasks.add_task(run_import_all, db)
    return {"status": "started"}


@router.get("/live-log")
async def get_live_log_sse():
    """SSE-стрім живих логів парсингу."""
    async def event_generator():
        async for event in bus.stream():
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/rebuild-search-text")
async def rebuild_search_text(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Переіндексація пошукового тексту для всіх товарів."""
    async def _task():
        try:
            bus.push({"type": "log", "level": "info", "msg": "🔄 Починаємо переіндексацію пошукового тексту..."})
            stmt = select(Product)
            result = await db.execute(stmt)
            products = result.scalars().all()
            updated = 0
            for product in products:
                attr_values = [str(v) for v in (product.attributes or {}).values() if v]
                certs = product.certifications or ""
                new_text = f"{product.title} {product.sku} {product.description or ''} {' '.join(attr_values)} {certs}".lower()
                if product.search_text != new_text:
                    product.search_text = new_text
                    updated += 1
                if updated % 100 == 0 and updated > 0:
                    bus.push({"type": "log", "level": "info", "msg": f"  ↻ Оновлено {updated} товарів..."})
            await db.commit()
            bus.push({"type": "log", "level": "done", "msg": f"✅ Пошук переіндексовано: {updated} товарів оновлено"})
        except Exception as e:
            bus.push({"type": "log", "level": "error", "msg": f"❌ Помилка переіндексації: {str(e)[:200]}"})

    background_tasks.add_task(_task)
    return {"status": "started"}


@router.post("/rebuild-indexes")
async def rebuild_indexes(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Перебудова таблиці product_indexes."""
    async def _task():
        try:
            from services.indexer import rebuild_all_indexes
            bus.push({"type": "log", "level": "info", "msg": "🗂 Перебудовуємо індекси артикулів..."})
            count = await rebuild_all_indexes(db)
            bus.push({"type": "log", "level": "done", "msg": f"✅ Індекси перебудовано: {count} записів"})
        except Exception as e:
            bus.push({"type": "log", "level": "error", "msg": f"❌ Помилка перебудови індексів: {str(e)[:200]}"})

    background_tasks.add_task(_task)
    return {"status": "started"}


@router.post("/clear-database")
async def clear_database(db: AsyncSession = Depends(get_db)):
    """Повне очищення бази даних."""
    try:
        await db.execute(text("DELETE FROM product_indexes"))
        await db.execute(text("DELETE FROM products"))
        await db.execute(text("DELETE FROM parse_logs"))
        await db.execute(text("DELETE FROM import_logs"))
        await db.execute(text("DELETE FROM documents"))
        for seq in ["products_id_seq", "documents_id_seq", "parse_logs_id_seq", "import_logs_id_seq"]:
            try:
                await db.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
            except Exception:
                pass
        await db.commit()
        return {"status": "success"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        from services.monitoring import monitor
        health = await monitor.get_full_health(db)
        return JSONResponse(content=health, status_code=200 if health["status"] == "healthy" else 503)
    except Exception as e:
        return JSONResponse(content={"status": "unhealthy", "error": str(e)}, status_code=503)
