"""
Hybrid Search v5 — SKU exact + pgvector semantic + PostgreSQL FTS + ILIKE.
No AI calls per query → $0/month.
Supports Ukrainian, Polish, English queries.
"""
import logging
import os
import re
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.models import Product, Document

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Technical parameter regex ─────────────────────────────────────────────────
_DN_RE    = re.compile(r'\bDN\s*(\d+)\b', re.I)
_BAR_RE   = re.compile(r'(\d+[\.,]?\d*)\s*bar\b', re.I)
_TEMP_RE  = re.compile(r'([+-]?\d+)\s*°?\s*[CcС]', re.I)
_DIAM_RE  = re.compile(r'\b(\d+[\.,]?\d*)\s*mm\b', re.I)
_SKU_RE   = re.compile(r'\b([A-Z]{2,6}[-_][A-Z0-9][-A-Z0-9/]{3,30})\b')


def _parse_params(q: str) -> dict:
    params = {}
    if m := _DN_RE.search(q):    params["dn"] = m.group(1)
    if m := _BAR_RE.search(q):   params["bar"] = m.group(1).replace(",", ".")
    if m := _TEMP_RE.search(q):  params["temp"] = m.group(1)
    if m := _DIAM_RE.search(q):  params["mm"] = m.group(1).replace(",", ".")
    if m := _SKU_RE.search(q.upper()): params["sku"] = m.group(1)
    return params


async def _vector_search(q: str, limit: int = 20) -> List[int]:
    """Return product IDs via pgvector cosine similarity."""
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "text-embedding-3-small", "input": q[:2000]}
            )
            if r.status_code != 200:
                return []
            emb = r.json()["data"][0]["embedding"]

        from core.database import engine
        async with engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT id FROM products
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> :emb::vector
                    LIMIT :lim
                """),
                {"emb": str(emb), "lim": limit}
            )
            return [row[0] for row in result.fetchall()]
    except Exception as e:
        logger.debug(f"Vector search: {e}")
        return []


def _score_product(p: Product, q_lower: str, params: dict, vector_ids: List[int]) -> int:
    score = 0
    title = (p.title or "").lower()
    sku = (p.sku or "").lower()
    desc = (p.description or "").lower()
    search = (p.search_text or "").lower()

    q_sku = params.get("sku", "").lower()

    # Exact SKU match — highest priority
    if q_sku and sku == q_sku:
        score += 100
    elif q_sku and q_sku in sku:
        score += 80
    elif q_sku and q_sku in search:
        score += 70

    # Vector similarity
    if p.id in vector_ids:
        idx = vector_ids.index(p.id)
        score += max(60 - idx * 2, 20)  # closer to top = higher score

    # Title exact match
    if q_lower in title:
        score += 50
    elif any(w in title for w in q_lower.split() if len(w) > 3):
        score += 30

    # Technical params
    attrs_str = str(p.attributes or {}).lower()
    variants_str = str(p.variants or []).lower()
    if params.get("dn") and params["dn"] in attrs_str + variants_str:
        score += 25
    if params.get("bar") and params["bar"] in attrs_str:
        score += 20
    if params.get("temp") and params["temp"] in attrs_str:
        score += 15

    # Description
    if q_lower in desc:
        score += 15
    elif any(w in desc for w in q_lower.split() if len(w) > 3):
        score += 8

    # search_text (contains variant SKUs)
    if q_lower in search:
        score += 10

    return score


@router.get("/")
async def search(
    q: str = Query(..., min_length=1),
    section_id: Optional[int] = None,
    category_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    q_clean = q.strip()
    q_lower = q_clean.lower()
    params = _parse_params(q_clean.upper() + " " + q_clean)

    # 1. Vector search (async, returns IDs sorted by similarity)
    vector_ids = await _vector_search(q_clean, limit=30)

    # 2. Build SQL filter — broad net
    terms = [w for w in re.split(r'\s+', q_lower) if len(w) >= 2]
    filters = []

    # Always include vector results
    if vector_ids:
        filters.append(Product.id.in_(vector_ids[:30]))

    # SKU search
    if params.get("sku"):
        sku_t = f"%{params['sku']}%"
        filters.append(or_(
            Product.sku.ilike(sku_t),
            Product.search_text.ilike(sku_t)
        ))

    # Technical params
    if params.get("dn"):
        filters.append(or_(
            Product.attributes.cast(__import__('sqlalchemy').Text).ilike(f"%DN{params['dn']}%"),
            Product.attributes.cast(__import__('sqlalchemy').Text).ilike(f"%{params['dn']}%"),
            Product.variants.cast(__import__('sqlalchemy').Text).ilike(f"%{params['dn']}%"),
        ))

    # Text search on multiple fields
    for term in terms[:4]:
        t = f"%{term}%"
        filters.append(or_(
            Product.title.ilike(t),
            Product.sku.ilike(t),
            Product.description.ilike(t),
            Product.search_text.ilike(t),
        ))

    if not filters:
        return {"query": q_clean, "total": 0, "items": [], "params": params}

    from sqlalchemy import or_ as sql_or
    base_q = select(Product).where(sql_or(*filters))
    if section_id:
        base_q = base_q.where(Product.section_id == section_id)
    if category_id:
        base_q = base_q.where(Product.category_id == category_id)

    rows = (await db.execute(base_q.limit(200))).scalars().all()

    # Score and sort
    scored = [(p, _score_product(p, q_lower, params, vector_ids)) for p in rows]
    scored.sort(key=lambda x: -x[1])

    # Remove duplicates
    seen, unique = set(), []
    for p, score in scored:
        if p.id not in seen:
            seen.add(p.id)
            unique.append((p, score))

    # Paginate
    total = len(unique)
    page_items = unique[(page-1)*page_size: page*page_size]

    results = []
    for p, score in page_items:
        doc = await db.get(Document, p.document_id)
        d = {
            "id": p.id, "title": p.title, "subtitle": p.subtitle or "",
            "sku": p.sku or "", "description": (p.description or "")[:300],
            "attributes": p.attributes or {}, "variants": p.variants or [],
            "image_url": f"/api/products/{p.id}/image" if p.image_bbox else "",
            "page_number": p.page_number, "document_id": p.document_id,
            "section_id": p.section_id, "category_id": p.category_id,
            "document_url": doc.file_url if doc else "",
            "_score": score,
            "_match": "sku" if params.get("sku") else ("vector" if p.id in vector_ids else "text"),
        }
        results.append(d)

    return {
        "query": q_clean, "total": total, "page": page,
        "page_size": page_size, "items": results,
        "params_detected": params,
        "vector_used": len(vector_ids) > 0,
    }


@router.get("/suggest")
async def suggest(q: str = Query(..., min_length=2), db: AsyncSession = Depends(get_db)):
    t = f"%{q}%"
    rows = (await db.execute(
        select(Product.id, Product.title, Product.sku).where(
            or_(Product.title.ilike(t), Product.sku.ilike(t),
                Product.search_text.ilike(t))
        ).limit(8)
    )).all()
    return {"suggestions": [{"id": r[0], "title": r[1], "sku": r[2]} for r in rows]}
