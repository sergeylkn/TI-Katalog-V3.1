"""
Локальний імпортер PDF — читає файли з локальної директорії (pdf_cache).
Використовується для повного перепарсингу без доступу до R2.
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import select
from core.database import AsyncSessionLocal
from models.models import Document, Category, Section, ImportLog, ParseLog

logger = logging.getLogger(__name__)


def _live(msg, level="info", doc=""):
    try:
        from services.live_log import log as live_log
        live_log(msg, level=level, doc=doc)
    except Exception:
        pass


def _live_progress(done, total, current="", products=0):
    try:
        from services.live_log import progress as live_progress
        live_progress(done, total, current, products)
    except Exception:
        pass


async def run_local_import(path: str, force_reparse: bool = False):
    """
    Імпортує всі PDF з локальної директорії.
    path         — абсолютний шлях до директорії з PDF
    force_reparse — True = повторно парсить навіть 'done' документи
    """
    from services.importer import (
        _parse_filename,
        _get_or_create_category,
        _get_or_create_section,
    )

    pdf_dir = Path(path)
    if not pdf_dir.exists():
        _live(f"❌ Директорія не знайдена: {path}", "error")
        return

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    _live(f"📋 Знайдено {len(pdf_files)} PDF у {pdf_dir.name}/", "info")

    if not pdf_files:
        _live("ℹ PDF файлів не знайдено в директорії", "info")
        return

    async with AsyncSessionLocal() as db:
        queue_ids = []
        retry_ids = []

        for pdf_path in pdf_files:
            fname = pdf_path.name
            local_url = f"local://{pdf_path.absolute().as_posix()}"

            r = await db.execute(select(Document).where(Document.name == fname))
            existing = r.scalar_one_or_none()

            if existing:
                if force_reparse or existing.status in ("error", "parsing"):
                    existing.status = "pending"
                    existing.file_url = local_url
                    existing.error_msg = None
                    retry_ids.append(existing.id)
                # done/pending без force_reparse — пропускаємо
                continue

            cat_slug, sec_slug = _parse_filename(fname)
            cat = await _get_or_create_category(db, cat_slug)
            sec = await _get_or_create_section(db, sec_slug, cat.id)

            doc = Document(
                name=fname,
                file_url=local_url,
                status="pending",
                section_id=sec.id,
                category_id=cat.id,
            )
            db.add(doc)
            await db.flush()
            db.add(ImportLog(
                document_id=doc.id, document_name=fname,
                status="queued", message=f"{cat.name} → {sec.name}"
            ))
            queue_ids.append(doc.id)

        await db.commit()

    all_ids = queue_ids + retry_ids
    total = len(all_ids)
    _live(
        f"✅ Черга: {len(queue_ids)} нових + {len(retry_ids)} повторних ({total} разом)",
        "info",
    )

    if not all_ids:
        if force_reparse:
            _live("ℹ Немає документів для повторного парсингу", "info")
        else:
            _live("ℹ Всі PDF вже оброблено. Використайте force_reparse для повторного парсингу.", "info")
        return

    for idx, doc_id in enumerate(all_ids):
        try:
            await _parse_one_local(doc_id)
        except Exception as e:
            logger.error(f"_parse_one_local({doc_id}): {e}")
        _live_progress(idx + 1, total)
        await asyncio.sleep(0.05)

    _live(f"🏁 Локальний імпорт завершено: {total} документів оброблено", "done")


async def _parse_one_local(doc_id: int):
    """Парсить один документ з локального файлу (file_url = 'local://...')."""
    from services.extractor import extract_products_from_pdf, extract_products

    # Отримуємо doc та встановлюємо статус "parsing"
    doc_name = ""
    doc_section_id = 0
    doc_category_id = 0
    doc_file_url = ""

    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, doc_id)
        if not doc:
            return
        if doc.status == "parsing":
            return
        doc_name = doc.name
        doc_section_id = doc.section_id or 0
        doc_category_id = doc.category_id or 0
        doc_file_url = doc.file_url or ""
        doc.status = "parsing"
        await db.commit()

    try:
        # file_url формат: "local:///absolute/path/file.pdf"
        file_path_str = doc_file_url.removeprefix("local://")
        pdf_path = Path(file_path_str)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF не знайдено: {pdf_path}")

        _live(f"🔍 Парсинг: {doc_name}", "info", doc=doc_name)
        pdf_bytes = pdf_path.read_bytes()

        products_list, page_count = await extract_products_from_pdf(
            pdf_bytes, doc_id, doc_section_id, doc_category_id
        )

        products_count = 0
        if products_list:
            async with AsyncSessionLocal() as db2:
                doc2 = await db2.get(Document, doc_id)
                if doc2:
                    products_count = await extract_products(db2, doc2, products_list, page_count)

        async with AsyncSessionLocal() as db2:
            doc2 = await db2.get(Document, doc_id)
            if doc2:
                doc2.status = "done"
                doc2.page_count = page_count
                doc2.parsed_at = datetime.now(timezone.utc)
                db2.add(ParseLog(
                    document_id=doc_id, level="info",
                    message=f"✅ {products_count} товарів, {page_count} сторінок"
                ))
                await db2.commit()

        _live(f"✅ {doc_name} — {products_count} товарів", "done", doc=doc_name)
        logger.info(f"Local doc#{doc_id} ({doc_name}): {products_count} products / {page_count} pages")

    except Exception as e:
        logger.error(f"Local parse error doc#{doc_id} ({doc_name}): {e}")
        async with AsyncSessionLocal() as db2:
            doc2 = await db2.get(Document, doc_id)
            if doc2:
                doc2.status = "error"
                doc2.error_msg = str(e)[:400]
                db2.add(ParseLog(
                    document_id=doc_id, level="error", message=str(e)[:400]
                ))
                await db2.commit()
        _live(f"❌ {doc_name}: {str(e)[:120]}", "error", doc=doc_name)
