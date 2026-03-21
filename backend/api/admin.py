"""Admin API — import, status, logs, cache, clear."""
import asyncio
import logging
import os
from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
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




@router.get("/live-log")
async def live_log_stream():
    """SSE stream of live import/parse events."""
    from services.live_log import bus
    return StreamingResponse(
        bus.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )

@router.get("/env-status")
async def env_status():
    """Check status of all required environment variables."""
    def _check(key: str):
        val = os.getenv(key, "")
        return {
            "active": bool(val),
            "source": "railway" if val else "missing",
            "preview": f"{val[:4]}…{val[-4:]}" if len(val) > 10 else ("✓" if val else ""),
        }
    return {
        "ANTHROPIC_API_KEY": _check("ANTHROPIC_API_KEY"),
        "OPENAI_API_KEY":    _check("OPENAI_API_KEY"),
        "DATABASE_URL":      _check("DATABASE_URL"),
        "PORT":              _check("PORT"),
    }


@router.post("/rebuild-indexes")
async def rebuild_indexes(bg: BackgroundTasks):
    """
    Rebuild product_indexes table from existing products.variants JSON.
    No PDF re-download — reads from DB only. Run this once after deployment.
    """
    async def _do():
        from core.database import AsyncSessionLocal
        from services.indexer import rebuild_all_indexes
        async with AsyncSessionLocal() as db:
            count = await rebuild_all_indexes(db)
            logger.info(f"rebuild-indexes done: {count} indexes")

    bg.add_task(_do)
    return {"status": "started", "message": "Rebuilding indexes in background..."}


@router.get("/index-stats")
async def index_stats(db: AsyncSession = Depends(get_db)):
    """Show stats about product_indexes table."""
    from models.models import ProductIndex
    from sqlalchemy import func
    total = (await db.execute(select(func.count(ProductIndex.id)))).scalar_one()
    by_type = (await db.execute(
        select(ProductIndex.index_type, func.count(ProductIndex.id))
        .group_by(ProductIndex.index_type)
    )).all()
    return {
        "total_indexes": total,
        "by_type": {row[0]: row[1] for row in by_type},
    }


@router.post("/rebuild-search-text")
async def rebuild_search_text(bg: BackgroundTasks):
    """
    Rebuild search_text for all products from their variants JSON.
    Fixes SKU search without full PDF reimport.
    """
    async def _do():
        import logging, re
        logger = logging.getLogger(__name__)
        from core.database import AsyncSessionLocal
        from models.models import Product, ProductIndex
        from sqlalchemy import delete

        SKU_KEYS = ["_sku","Індекс","Indeks","Index","index","SKU","Артикул","КОД","Part No"]

        async with AsyncSessionLocal() as db:
            offset = 0
            updated = 0
            errors = 0
            while True:
                rows = (await db.execute(
                    select(Product).offset(offset).limit(200)
                )).scalars().all()
                if not rows:
                    break

                for p in rows:
                    try:
                        # Collect all variant SKUs
                        sku_tokens = []
                        for var in (p.variants or []):
                            for sk in SKU_KEYS:
                                if sk in var and var[sk]:
                                    v = str(var[sk]).strip()
                                    if len(v) >= 4:
                                        sku_tokens.append(v)
                                        sku_tokens.append(v.replace("-","").replace("_","").replace("/",""))

                        if not sku_tokens:
                            continue

                        # Append SKU tokens to existing search_text
                        existing = p.search_text or ""
                        new_tokens = " ".join(sku_tokens)
                        
                        # Only update if tokens are missing
                        missing = [t for t in sku_tokens[:5] if t not in existing]
                        if missing:
                            p.search_text = (existing + " " + new_tokens)[:10000]
                            updated += 1

                        # Also rebuild ProductIndex for this product
                        await db.execute(
                            delete(ProductIndex).where(ProductIndex.product_id == p.id)
                        )
                        for token in set(sku_tokens):
                            if re.match(r'[A-Z0-9]{2,}[-_/]', token.upper()):
                                db.add(ProductIndex(
                                    product_id=p.id,
                                    index_value=token.upper().strip(),
                                    index_type="variant",
                                    variant_row=None,
                                ))

                    except Exception as e:
                        errors += 1
                        logger.error(f"rebuild search_text product#{p.id}: {e}")

                await db.commit()
                offset += 200
                logger.info(f"rebuild-search-text: {offset} processed, {updated} updated")

            logger.info(f"Done: {updated} updated, {errors} errors")

    bg.add_task(_do)
    return {"status": "started", "message": "Rebuilding search_text + indexes in background..."}
