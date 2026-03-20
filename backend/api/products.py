"""Products API + /product-image/{id} endpoint."""
import io
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.models import Product, Document, Section, Category

router = APIRouter()
logger = logging.getLogger(__name__)

# Simple in-memory PDF cache (doc_id → bytes)
_pdf_cache: dict = {}
_pdf_cache_max = 20


def _prod(p: Product, doc: Document = None) -> dict:
    return {
        "id": p.id, "title": p.title, "subtitle": p.subtitle or "",
        "sku": p.sku or "", "description": p.description or "",
        "certifications": p.certifications or "",
        "attributes": p.attributes or {}, "variants": p.variants or [],
        "image_bbox": p.image_bbox, "page_number": p.page_number,
        "document_id": p.document_id, "section_id": p.section_id,
        "category_id": p.category_id,
        "document_url": doc.file_url if doc else "",
        "image_url": f"/api/products/{p.id}/image" if p.image_bbox else "",
    }


@router.get("/{product_id}/image")
async def product_image(product_id: int, db: AsyncSession = Depends(get_db)):
    """Render product image from PDF using stored bbox coordinates."""
    prod = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if not prod:
        raise HTTPException(404)

    doc = await db.get(Document, prod.document_id)
    if not doc:
        raise HTTPException(404)

    bbox = prod.image_bbox
    pnum = (prod.page_number or 1) - 1  # 0-indexed

    try:
        import fitz, httpx

        # Get PDF bytes (cached)
        pdf_bytes = _pdf_cache.get(doc.id)
        if pdf_bytes is None:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(doc.file_url)
                r.raise_for_status()
                pdf_bytes = r.content
            if len(_pdf_cache) >= _pdf_cache_max:
                _pdf_cache.pop(next(iter(_pdf_cache)))
            _pdf_cache[doc.id] = pdf_bytes

        pdfdoc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = pdfdoc[min(pnum, len(pdfdoc) - 1)]

        if bbox:
            # Render specific bbox region
            clip = fitz.Rect(
                bbox["x0"] - 4, bbox["y0"] - 4,
                bbox["x1"] + 4, bbox["y1"] + 4
            )
        else:
            # Render top-left quadrant of page as fallback
            r = page.rect
            clip = fitz.Rect(0, r.height * 0.1, r.width * 0.5, r.height * 0.6)

        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, clip=clip)
        img_bytes = pix.tobytes("png")
        pdfdoc.close()

        return Response(
            content=img_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"}
        )
    except Exception as e:
        logger.warning(f"product_image {product_id}: {e}")
        raise HTTPException(500, "Image render failed")


@router.get("/")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    section_id: int = Query(None),
    category_id: int = Query(None),
    db: AsyncSession = Depends(get_db)
):
    q = select(Product)
    if section_id:
        q = q.where(Product.section_id == section_id)
    if category_id:
        q = q.where(Product.category_id == category_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(desc(Product.created_at)).offset((page-1)*page_size).limit(page_size)
    )).scalars().all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_prod(p) for p in rows]}


@router.get("/section/{ref}")
async def products_by_section(
    ref: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    section = None
    if ref.isdigit():
        section = (await db.execute(select(Section).where(Section.id == int(ref)))).scalar_one_or_none()
    if not section:
        section = (await db.execute(select(Section).where(Section.slug == ref))).scalar_one_or_none()
    if not section:
        raise HTTPException(404, f"Section '{ref}' not found")
    q = select(Product).where(Product.section_id == section.id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(Product.title).offset((page-1)*page_size).limit(page_size)
    )).scalars().all()
    return {"total": total, "page": page, "page_size": page_size,
            "section": {"id": section.id, "name": section.name, "slug": section.slug},
            "items": [_prod(p) for p in rows]}


@router.get("/{product_id}/recommendations")
async def recommendations(product_id: int, db: AsyncSession = Depends(get_db)):
    prod = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if not prod:
        raise HTTPException(404)
    recs = (await db.execute(
        select(Product).where(
            Product.section_id == prod.section_id, Product.id != product_id
        ).limit(6)
    )).scalars().all()
    return {"recommendations": [_prod(r) for r in recs]}


@router.get("/{product_id}")
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    prod = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if not prod:
        raise HTTPException(404)
    doc = await db.get(Document, prod.document_id)
    return _prod(prod, doc)
