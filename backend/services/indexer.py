"""
Product Indexer — будує таблицю product_indexes з усіх артикулів.
Викликається:
1. Після імпорту кожного товару
2. Через /api/admin/rebuild-indexes (без реімпорту PDF)
"""
import logging
import re
from typing import List, Dict

from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Product, ProductIndex

logger = logging.getLogger(__name__)

# Всі можливі ключі з варіантів де може бути артикул
SKU_KEYS = [
    "_sku", "Індекс", "Indeks", "Index", "index",
    "Article", "SKU", "Артикул", "КОД", "код",
    "Part No", "PartNo", "Part number", "Ref",
    "Номенклатура", "Каталожний номер",
]

# Патерн для визначення що значення є артикулом (не просто числом)
_SKU_PAT = re.compile(r'^[A-Z0-9]{2,}[-_/][A-Z0-9][-A-Z0-9/_\.]{2,}$', re.I)


def _looks_like_sku(val: str) -> bool:
    val = val.strip()
    return bool(_SKU_PAT.match(val)) and len(val) >= 5


def _normalize_index(val: str) -> str:
    """Uppercase, strip spaces."""
    return val.strip().upper()


def _extract_indexes(product: Product) -> List[Dict]:
    """
    Return list of {index_value, index_type, variant_row}
    for every unique identifier of this product.
    """
    results = []
    seen = set()

    def add(val: str, itype: str, row=None):
        norm = _normalize_index(val)
        if norm and norm not in seen and len(norm) >= 3:
            seen.add(norm)
            results.append({
                "index_value": norm,
                "index_type": itype,
                "variant_row": row,
            })

    # 1. Own SKU
    if product.sku:
        add(product.sku, "sku")

    # 2. Every variant row
    for var in (product.variants or []):
        for sk in SKU_KEYS:
            if sk in var:
                val = str(var[sk]).strip()
                if val and val.lower() not in ("nan", "none", "") and _looks_like_sku(val):
                    add(val, "variant", var)
                    # Also add version without dashes for prefix search
                    # e.g. FTCRISTALLOEX08X12
                    clean = val.replace("-", "").replace("_", "").replace("/", "")
                    if clean != val:
                        add(clean, "alt", var)

    return results


async def index_product(product: Product, db: AsyncSession):
    """Index one product — call after save/update."""
    # Delete old indexes for this product
    await db.execute(delete(ProductIndex).where(ProductIndex.product_id == product.id))

    indexes = _extract_indexes(product)
    for idx in indexes:
        db.add(ProductIndex(
            product_id  = product.id,
            index_value = idx["index_value"],
            index_type  = idx["index_type"],
            variant_row = idx["variant_row"],
        ))

    if indexes:
        logger.debug(f"Product#{product.id}: indexed {len(indexes)} identifiers")


async def rebuild_all_indexes(db: AsyncSession) -> int:
    """
    Rebuild entire product_indexes table from products.variants JSON.
    No PDF re-download needed — reads from DB only.
    """
    # Clear all
    await db.execute(delete(ProductIndex))
    await db.commit()

    # Process in batches
    batch_size = 200
    offset = 0
    total_indexed = 0
    total_products = 0

    while True:
        rows = (await db.execute(
            select(Product).offset(offset).limit(batch_size)
        )).scalars().all()
        if not rows:
            break

        for product in rows:
            indexes = _extract_indexes(product)
            for idx in indexes:
                db.add(ProductIndex(
                    product_id  = product.id,
                    index_value = idx["index_value"],
                    index_type  = idx["index_type"],
                    variant_row = idx["variant_row"],
                ))
            total_indexed += len(indexes)
            total_products += 1

        await db.commit()
        offset += batch_size
        logger.info(f"Indexer: {total_products} products, {total_indexed} indexes so far...")

    logger.info(f"Rebuild complete: {total_products} products, {total_indexed} indexes")
    return total_indexed
