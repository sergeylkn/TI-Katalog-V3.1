import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.models import Document, Section
from services.extractor import extract_products

logger = logging.getLogger("services.importer")

MANIFEST_URL = "https://pub-ada201ec5fb84401a3b36b7b21e6ed0f.r2.dev/manifest.txt"
BASE_R2_URL = "https://pub-ada201ec5fb84401a3b36b7b21e6ed0f.r2.dev/"

async def run_import_all(db: AsyncSession):
    """Основна функція імпорту всіх PDF з маніфесту."""
    logger.info("🔄 R2 import starting...")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(MANIFEST_URL)
            if response.status_code != 200:
                logger.error(f"Не вдалося завантажити маніфест: {response.status_code}")
                return {"error": "Manifest download failed"}
            
            lines = response.text.splitlines()
            pdf_filenames = [line.strip() for line in lines if line.strip().endswith('.pdf')]
            logger.info(f"Знайдено в маніфесті: {len(pdf_filenames)} PDF")

            added_count = 0
            for filename in pdf_filenames:
                # 1. Перевіряємо, чи існує документ
                stmt = select(Document).where(Document.name == filename)
                res = await db.execute(stmt)
                doc = res.scalar_one_or_none()

                if not doc:
                    # 2. Створюємо новий документ, якщо його немає
                    file_url = f"{BASE_R2_URL}{filename}"
                    doc = Document(
                        name=filename,
                        file_url=file_url,
                        status="pending"
                    )
                    db.add(doc)
                    await db.commit()
                    await db.refresh(doc)
                    added_count += 1
                
                # 3. Запускаємо парсинг (якщо статус pending)
                if doc.status == "pending":
                    try:
                        # Важливо: передаємо об'єкт doc, у якого точно є .id
                        await process_single_pdf(doc, db)
                    except Exception as e:
                        logger.error(f"Помилка парсингу {filename}: {e}")

            return {"status": "success", "added": added_count}

    except Exception as e:
        logger.error(f"Глобальна помилка імпорту: {e}")
        return {"error": str(e)}

async def process_single_pdf(doc: Document, db: AsyncSession):
    """Функція для обробки одного конкретного PDF."""
    logger.info(f"📄 Початок обробки: {doc.name}")
    
    # Тут виклик вашого екстрактора
    # Приклад: витягуємо дані через Claude і зберігаємо через нашу нову функцію
    # Замініть на вашу реальну логіку виклику Claude
    # await extract_products(db, doc, ai_data, page_num)
    pass
