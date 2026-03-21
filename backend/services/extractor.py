import logging
import json
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

# ВАЖНО: Мы не импортируем Product и Document на уровне модуля, 
# чтобы избежать ошибки "partially initialized module" (circular import).
# Импорт происходит внутри функции extract_products.

logger = logging.getLogger("extractor")

def safe_list_to_str(value: Any, separator: str = "; ") -> str:
    """Безопасно преобразует список или любое значение в строку для БД."""
    if value is None:
        return ""
    if isinstance(value, list):
        return separator.join([str(i).strip() for i in value if i is not None])
    return str(value).strip()

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
