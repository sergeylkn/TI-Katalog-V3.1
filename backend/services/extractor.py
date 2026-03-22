import logging
import json
import os
import base64
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("extractor")

def safe_list_to_str(value: Any, separator: str = "; ") -> str:
    """Безопасно преобразует список или любое значение в строку для БД."""
    if value is None:
        return ""
    if isinstance(value, list):
        return separator.join([str(i).strip() for i in value if i is not None])
    return str(value).strip()

async def extract_products_from_pdf(
    pdf_bytes: bytes, 
    doc_id: int,
    section_id: int,
    category_id: int
) -> Tuple[List[Dict], int]:
    """
    Извлекает товары из PDF используя Claude API.
    Возвращает (список товаров, количество страниц)
    """
    try:
        import httpx
        import fitz  # PyMuPDF

        # Открываем PDF
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(pdf_doc)

        all_products = []

        # Обрабатываем первые 5 страниц (для демо)
        for page_num in range(min(3, page_count)):
            try:
                page = pdf_doc[page_num]

                # Извлекаем текст
                text = page.get_text()
                if not text.strip():
                    continue

                # Сокращаем текст (Claude имеет лимит)
                text = text[:2000]

                # Вызываем Claude для анализа
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    logger.warning(f"Doc#{doc_id}: ANTHROPIC_API_KEY not set")
                    break

                prompt = f"""Analyze this product catalog page and extract all products in JSON format.
For each product, extract: title, sku, description, certifications, attributes as dict.
Return ONLY valid JSON array with field "products", no markdown, no explanation.

Page text:
{text}"""

                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json"
                        },
                        json={
                            "model": "claude-3-5-sonnet-20241022",
                            "max_tokens": 1500,
                            "messages": [{"role": "user", "content": prompt}]
                        }
                    )

                    if response.status_code == 200:
                        result = response.json()
                        content = result.get("content", [{}])[0].get("text", "{}")

                        # Парсим JSON
                        try:
                            data = json.loads(content)
                            products = data.get("products", [])

                            for p in products:
                                p["page_number"] = page_num + 1
                                p["section_id"] = section_id
                                p["category_id"] = category_id

                            all_products.extend(products)
                            logger.info(f"Doc#{doc_id} p{page_num + 1}: Extracted {len(products)} products")
                        except json.JSONDecodeError as e:
                            logger.error(f"Doc#{doc_id} p{page_num + 1}: Invalid JSON from Claude: {e}")
                    else:
                        logger.error(f"Doc#{doc_id}: Claude API error: {response.status_code}")

            except Exception as e:
                logger.error(f"Doc#{doc_id} p{page_num + 1}: {e}")
                continue

        return all_products, page_count

    except Exception as e:
        logger.error(f"Doc#{doc_id}: PDF processing error: {e}")
        return [], 0

async def extract_products(
    db: AsyncSession, 
    doc: Any, 
    products_data: Any, 
    page_num: int
) -> int:
    """
    Сохраняет извлеченные товары в базу данных.
    Локальный импорт моделей разрывает циклическую зависимость с importer.py.
    """
    from models.models import Product  # Локальный импорт

    added_count = 0

    # Определяем список товаров из полученных данных
    items = []
    if isinstance(products_data, dict):
        items = products_data.get("products", [])
    elif isinstance(products_data, list):
        items = products_data
    else:
        logger.error(f"Doc#{doc.id} p{page_num}: Неверный формат данных от Claude")
        return 0

    for p_data in items:
        try:
            if not isinstance(p_data, dict):
                continue

            # Извлечение основных полей
            title = p_data.get("title") or p_data.get("name") or "Без назви"
            sku = p_data.get("sku") or p_data.get("article") or ""
            description = p_data.get("description", "")

            # Критическое исправление: преобразуем список сертификатов в строку для PostgreSQL String column
            certifications = safe_list_to_str(p_data.get("certifications", ""))

            # Обработка JSON полей (атрибуты и варианты)
            attributes = p_data.get("attributes", {})
            if not isinstance(attributes, dict):
                attributes = {"raw_data": str(attributes)}

            variants = p_data.get("variants", [])
            if not isinstance(variants, list):
                variants = []

            # Формирование поискового индекса
            attr_values = [str(v) for v in attributes.values() if v]
            search_text = f"{title} {sku} {' '.join(attr_values)} {certifications}".lower()

            # Создание объекта модели
            new_product = Product(
                document_id=doc.id,
                section_id=doc.section_id,
                title=str(title)[:255],
                sku=str(sku)[:100],
                description=str(description),
                certifications=certifications,
                attributes=attributes,
                variants=variants,
                page_number=page_num,
                search_text=search_text,
                image_bbox=p_data.get("image_bbox", {})
            )

            db.add(new_product)
            added_count += 1

        except Exception as e:
            logger.error(f"Doc#{doc.id} p{page_num}: Ошибка обработки товара: {e}")
            continue

    try:
        # Сохраняем изменения для текущей страницы
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Doc#{doc.id}: Ошибка транзакции БД: {e}")
        return 0

    return added_count
