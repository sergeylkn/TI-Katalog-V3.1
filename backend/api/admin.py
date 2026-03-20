"""Admin API — import, status, logs, cache, clear."""
import asyncio
import logging
import os
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.models import Document, Product, Section, ImportLog, ParseLog

logger = logging.getLogger(__name__)
router = APIRouter()

_import_running = False
_api_key_store: dict = {}


@router.post("/set-api-key")
async def set_api_key(payload: dict):
    key = payload.get("api_key", "").strip()
    os.environ["ANTHROPIC_API_KEY"] = key
    _api_key_store["key"] = key
    return {"status": "saved"}


@router.get("/get-api-key")
async def get_api_key():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return {"has_key": bool(key), "preview": f"{key[:8]}…" if key else ""}


@router.post("/import-all-pdfs")
async def import_all(bg: BackgroundTasks):
    global _import_running
    if _import_running:
        return {"status": "already_running"}
    _import_running = True
    async def _run():
        global _import_running
        try:
            from services.importer import run_import_all
            await run_import_all()
        finally:
            _import_running = False
    bg.add_task(_run)
    return {"status": "started"}


@router.get("/import-status")
async def import_status(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(Document))).scalar_one()
    done  = (await db.execute(select(func.count()).select_from(Document).where(Document.status == "done"))).scalar_one()
    err   = (await db.execute(select(func.count()).select_from(Document).where(Document.status == "error"))).scalar_one()
    pars  = (await db.execute(select(func.count()).select_from(Document).where(Document.status == "parsing"))).scalar_one()
    prods = (await db.execute(select(func.count()).select_from(Product))).scalar_one()
    return {"total": total, "done": done, "error": err, "parsing": pars,
            "products": prods, "running": _import_running}


@router.get("/import-logs")
async def import_logs(limit: int = 100, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(ImportLog).order_by(ImportLog.created_at.desc()).limit(limit))
    logs = r.scalars().all()
    return {"logs": [{"id": l.id, "doc": l.document_name, "status": l.status,
                      "msg": l.message, "at": l.created_at.isoformat()} for l in logs]}


@router.get("/parse-logs")
async def parse_logs(limit: int = 100, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(ParseLog).order_by(ParseLog.created_at.desc()).limit(limit))
    logs = r.scalars().all()
    return {"logs": [{"id": l.id, "doc_id": l.document_id, "level": l.level,
                      "msg": l.message, "at": l.created_at.isoformat()} for l in logs]}


@router.post("/reparse/{doc_id}")
async def reparse(doc_id: int, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(404, "Document not found")
    doc.status = "pending"
    await db.commit()
    async def _run():
        from services.importer import parse_one
        await parse_one(doc_id)
    bg.add_task(_run)
    return {"status": "queued", "doc_id": doc_id}


@router.delete("/document/{doc_id}")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if doc:
        await db.delete(doc)
        await db.commit()
    return {"deleted": doc_id}


@router.post("/clear-database")
async def clear_database(db: AsyncSession = Depends(get_db)):
    await db.execute(text(
        "TRUNCATE TABLE parse_logs, import_logs, products, documents RESTART IDENTITY CASCADE"
    ))
    await db.commit()
    return {"status": "cleared"}


@router.get("/cache-stats")
async def cache_stats():
    return {"cache": "disabled", "note": "lightweight mode"}
