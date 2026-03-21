import logging
import json
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.models import Product, Document, Section

logger = logging.getLogger("extractor")

def safe_list_to_str(value: Any, separator: str = "; ") -> str:
    """Безопасно преобразует список или любое значение в строку для БД."""
    if value is None:
        return ""
    if isinstance(value, list):
        return separator.join([str(i).strip() for i in value if i is not None])
    return str(value).strip()

async def save_extracted_products(
    db: AsyncSession, 
    doc: Document, 
    products_data: Any, 
    page_num: int
) -> int:
    """
    Сохраняет извлеченные товары в базу данных.
    Исправляет ошибки типов данных и структуры JSON.
    """
    added_count = 0
    
    # 1. Защита от 'list' object has no attribute 'get'
    # Если пришел список вместо словаря с ключом "products"
    items = []
    if isinstance(products_data, dict):
        items = products_data.get("products", [])
    elif isinstance(products_data, list):
        items = products_data
    else:
        logger.error(f"Doc#{doc.id} p{page_num}: Неверный формат данных от ИИ")
        return 0

    for p_data in items:
        try:
            # Пропускаем, если элемент не является словарем
            if not isinstance(p_data, dict):
                continue

            # 2. Очистка и нормализация данных
            title = p_data.get("title") or p_data.get("name") or "Без назви"
            sku = p_data.get("sku") or p_data.get("article") or ""
            description = p_data.get("description", "")
            
            # Исправление DataError: преобразуем список сертификатов в строку
            certifications = safe_list_to_str(p_data.get("certifications", ""))
            
            # Обработка атрибутов и вариантов (должны быть dict/list для JSON поля)
            attributes = p_data.get("attributes", {})
            if not isinstance(attributes, dict):
                attributes = {"raw_data": str(attributes)}
                
            variants = p_data.get("variants", [])
            if not isinstance(variants, list):
                variants = [variants]

            # 3. Создание поискового текста для Full-Text Search
            attr_str = " ".join([f"{k} {v}" for k, v in attributes.items() if isinstance(v, (str, int, float))])
            search_text = f"{title} {sku} {description} {attr_str} {certifications}".lower()

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
            logger.error(f"Doc#{doc.id} p{page_num}: Ошибка сохранения товара: {e}")
            continue

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Doc#{doc.id}: Ошибка коммита в базу: {e}")
        return 0
        
    return added_count
