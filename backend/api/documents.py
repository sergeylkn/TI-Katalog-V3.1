"""Documents + Categories API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.models import Document, Section, Category, Product

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    cats = (await db.execute(select(Category).order_by(Category.name))).scalars().all()
    result = []
    for cat in cats:
        # Count products in this category
        count = (await db.execute(
            select(func.count(Product.id)).where(Product.category_id == cat.id)
        )).scalar_one()
        # Count sections
        sec_count = (await db.execute(
            select(func.count(Section.id)).where(Section.category_id == cat.id)
        )).scalar_one()
        result.append({
            "id": cat.id, "name": cat.name, "slug": cat.slug,
            "icon": cat.icon or "📦", "description": cat.description or "",
            "product_count": count, "section_count": sec_count,
        })
    return result


@router.get("/categories/{slug}")
async def get_category(slug: str, db: AsyncSession = Depends(get_db)):
    cat = (await db.execute(
        select(Category).where(Category.slug == slug)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(404)
    sections = (await db.execute(
        select(Section).where(Section.category_id == cat.id).order_by(Section.name)
    )).scalars().all()
    secs = []
    for sec in sections:
        count = (await db.execute(
            select(func.count(Product.id)).where(Product.section_id == sec.id)
        )).scalar_one()
        secs.append({
            "id": sec.id, "name": sec.name, "slug": sec.slug,
            "description": sec.description or "", "product_count": count,
        })
    return {
        "id": cat.id, "name": cat.name, "slug": cat.slug,
        "icon": cat.icon or "📦", "sections": secs
    }


@router.get("/sections")
async def list_sections(db: AsyncSession = Depends(get_db)):
    secs = (await db.execute(select(Section).order_by(Section.name))).scalars().all()
    return [{"id": s.id, "name": s.name, "slug": s.slug,
             "category_id": s.category_id} for s in secs]


@router.get("/")
async def list_documents(db: AsyncSession = Depends(get_db)):
    docs = (await db.execute(select(Document).order_by(Document.name))).scalars().all()
    return [{"id": d.id, "name": d.name, "status": d.status,
             "page_count": d.page_count} for d in docs]


@router.get("/{doc_id}")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404)
    return {"id": doc.id, "name": doc.name, "file_url": doc.file_url,
            "status": doc.status, "page_count": doc.page_count}
