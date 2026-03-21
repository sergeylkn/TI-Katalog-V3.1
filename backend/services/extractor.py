import logging
from typing import Any, Dict, List

# МИ НЕ ІМПОРТУЄМО Document ТУТ, щоб уникнути Circular Import
# Ми імпортуємо Product всередині функції або використовуємо загальний об'єкт

logger = logging.getLogger("extractor")

def safe_list_to_str(value: Any, separator: str = "; ") -> str:
    if value is None: return ""
    if isinstance(value, list):
        return separator.join([str(i).strip() for i in value if i is not None])
    return str(value).strip()

async def extract_products(db, doc, products_data: Any, page_num: int) -> int:
    """
    Зберігає товари. Ми імпортуємо Product локально, 
    щоб не було циклічної залежності.
    """
    from models.models import Product  # ЛОКАЛЬНИЙ ІМПОРТ
    
    added_count = 0
    items = []
    
    if isinstance(products_data, dict):
        items = products_data.get("products", [])
    elif isinstance(products_data, list):
        items = products_data
    else:
        logger.error(f"Doc#{doc.id} p{page_num}: Invalid format")
        return 0

    for p_data in items:
        try:
            if not isinstance(p_data, dict): continue

            title = p_data.get("title") or p_data.get("name") or "Без назви"
            sku = p_data.get("sku") or p_data.get("article") or ""
            
            # Виправлення для PostgreSQL (список у рядок)
            certs = safe_list_to_str(p_data.get("certifications", ""))
            
            # Безпечне отримання JSON полів
            attributes = p_data.get("attributes", {})
            if not isinstance(attributes, dict): attributes = {"raw": str(attributes)}
            
            variants = p_data.get("variants", [])
            if not isinstance(variants, list): variants = []

            # Пошуковий індекс
            search_text = f"{title} {sku} {certs}".lower()

            new_product = Product(
                document_id=doc.id,
                section_id=doc.section_id,
                title=str(title)[:255],
                sku=str(sku)[:100],
                description=str(p_data.get("description", "")),
                certifications=certs,
                attributes=attributes,
                variants=variants,
                page_number=page_num,
                search_text=search_text
            )
            db.add(new_product)
            added_count += 1
            
        except Exception as e:
            logger.error(f"Error processing item: {e}")
            continue

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"DB Commit failed: {e}")
        return 0
        
    return added_count
