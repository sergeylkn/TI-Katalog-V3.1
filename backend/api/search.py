"""
Search v5.2 — розуміє технічні параметри: bar, DN, °C, mm.
"""
import logging, os, re, json
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_, and_, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.models import Product, Document

logger = logging.getLogger(__name__)
router = APIRouter()

PL_MAP = {
    "wąż":"шланг hose", "węże":"шланги hoses", "przewód":"шланг труба",
    "złącze":"з'єднання фітинг", "zawór":"клапан кран", "armatura":"арматура",
    "hydrauliczny":"гідравлічний", "pneumatyczny":"пневматичний",
    "spożywczy":"харчовий food", "chemiczny":"хімічний",
    "gumowy":"гумовий rubber", "silikonowy":"силіконовий silicone",
    "ciśnienie":"тиск pressure bar", "temperatura":"температура temperature",
    "obejma":"хомут clamp", "uszczelnienie":"ущільнення seal",
}

# Ukrainian/Russian colloquial → standard terms
UA_NORMALIZE = {
    # "дн" variants → DN
    " дн ": " DN ", " дн.": " DN", "дн-": "DN-",
    # Common misspellings / short forms
    "гідравл ": "гідравлічний ", "пневмат ": "пневматичний ",
    "харч ": "харчовий ", "хім ": "хімічний ",
    # Category keywords that help narrow search
    "рукав": "шланг рукав",
}

# Category-specific search terms to BOOST correct category
CATEGORY_HINTS = {
    "шланг": ["шланг", "рукав", "hose", "wąż"],
    "шланги": ["шланг", "рукав", "hose"],
    "рукав": ["шланг", "рукав", "hose"],
    "hose": ["шланг", "рукав", "hose"],
    "кран": ["кран", "клапан", "кульовий"],
    "клапан": ["клапан", "кран", "valve"],
    "фітинг": ["фітинг", "з'єднання", "fitting"],
    "з'єднання": ["з'єднання", "фітинг", "coupling"],
    "арматура": ["арматура", "з'єднання", "fitting"],
    "манометр": ["манометр", "тиск", "pressure"],
    "хомут": ["хомут", "обойма", "clamp"],
}

def _normalize_query(q: str) -> str:
    """Normalize Ukrainian colloquial terms and expand synonyms."""
    result = q
    q_l = q.lower()
    # Fix дн/ДН → DN
    import re
    result = re.sub(r'\bдн\s*(\d+)\b', lambda m: f'DN{m.group(1)}', result, flags=re.I)
    result = re.sub(r'\bдн\b', 'DN', result, flags=re.I)
    # Apply UA normalizations
    for orig, repl in UA_NORMALIZE.items():
        result = result.replace(orig, repl)
    return result

def _expand(q: str) -> str:
    result = _normalize_query(q)
    q_l = q.lower()
    # Polish expansion
    for pl, ua in PL_MAP.items():
        if pl in q_l: result += " " + ua
    return result

def _get_category_boost(q: str) -> list:
    """Return terms that should boost matching by category."""
    q_l = q.lower()
    for kw, terms in CATEGORY_HINTS.items():
        if kw in q_l:
            return terms
    return []

def _params(q: str) -> dict:
    """
    Extract technical params from query.
    DN = номінальний діаметр = внутрішній діаметр шланга.
    Розуміє: DN65, 65мм, 65mm, 25x35, шланг 65
    """
    p = {}
    qu = q.upper()

    # SKU first (before other number patterns)
    if m := re.search(r'\b([A-Z]{2,8}[-][A-Z0-9][-A-Z0-9/\.]{2,30})\b', qu):
        p["sku"] = m.group(1)

    # Pressure bar/бар
    if m := re.search(r'(\d+[\.,]?\d*)\s*(?:bar|бар|BAR|БАР)\b', q, re.I):
        p["bar"] = m.group(1).replace(",",".")

    # Temperature °C
    if m := re.search(r'([+-]?\d+)\s*°?\s*[Cc]', q):
        p["temp"] = m.group(1)

    # DN explicitly written
    if m := re.search(r'\bDN\s*?(\d+)\b', q, re.I):
        p["dn"] = m.group(1)
        p["d_inner"] = m.group(1)   # DN = внутрішній діаметр

    # Inner x outer: 25x35mm or 25/35
    if m := re.search(r'\b(\d+)\s*[xX×/]\s*(\d+)\s*(?:mm|мм)?\b', q):
        p["d_inner"] = m.group(1)
        p["d_outer"] = m.group(2)
        if not p.get("dn"):
            p["dn"] = m.group(1)    # inner = DN

    # Standalone mm — likely inner diameter if no DN yet
    if not p.get("dn"):
        if m := re.search(r'\b(\d+)\s*(?:mm|мм)\b', q, re.I):
            val = m.group(1)
            # Reasonable hose diameter: 4-400mm
            if 4 <= int(val) <= 400:
                p["dn"] = val
                p["d_inner"] = val

    # Standalone number after key words like "шланг 65" "шланг DN 65"
    if not p.get("dn"):
        kw = ["шланг", "hose", "wąż", "труб", "pipe", "арматур", "кран", "valve"]
        for k in kw:
            if k in q.lower():
                if m := re.search(r'\b(\d{2,3})\b', q):
                    val = m.group(1)
                    if 4 <= int(val) <= 400 and val != p.get("bar","").split(".")[0]:
                        p["dn"] = val
                        p["d_inner"] = val
                        break

    return p

async def _vec(q: str, n: int = 40) -> List[int]:
    key = os.getenv("OPENAI_API_KEY","")
    if not key: return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post("https://api.openai.com/v1/embeddings",
                headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                json={"model":"text-embedding-3-small","input":q[:2000]})
            if r.status_code!=200: return []
            emb = r.json()["data"][0]["embedding"]
        from core.database import engine
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT id FROM products WHERE embedding IS NOT NULL ORDER BY embedding <=> :e::vector LIMIT :l"),
                {"e":str(emb),"l":n})
            return [row[0] for row in res.fetchall()]
    except: return []

def _score(p: Product, q_lower: str, par: dict, vec_ids: List[int], cat_hints: list = None) -> int:
    s = 0
    title = (p.title or "").lower()
    sku   = (p.sku or "").lower()
    srch  = (p.search_text or "").lower()
    desc  = (p.description or "").lower()
    attrs = str(p.attributes or {}).lower()
    alltext = f"{title} {sku} {srch} {desc} {attrs}"

    # Category hint boost — if user asked for "шланг", reward products with "шланг" in title
    if cat_hints:
        cat_matches = sum(1 for hint in cat_hints if hint in title)
        if cat_matches > 0:
            s += cat_matches * 40  # strong boost for correct category
        else:
            s -= 30  # penalize wrong category (e.g. fitting when user asked for hose)

    # SKU
    q_sku = par.get("sku","").lower()
    if q_sku:
        if sku == q_sku:                s += 200
        elif sku.startswith(q_sku):     s += 150
        elif q_sku in sku:              s += 120
        elif q_sku in srch:             s += 90

    # Vector rank
    if p.id in vec_ids:
        s += max(80 - vec_ids.index(p.id)*2, 10)

    # Technical params — DN = d_вн = inner diameter
    dn = par.get("dn") or par.get("d_inner")
    if dn:
        # Check all representations
        if (f"DN{dn}" in srch or f"DN {dn}" in srch or
            f"{dn}мм" in srch or f"{dn}mm" in srch or
            f"d_вн_мм" in attrs and dn in attrs):
            s += 70
    if par.get("bar"):
        bar_int = str(int(float(par["bar"])))
        if bar_int in attrs or bar_int + " bar" in srch: s += 55
    if par.get("temp") and par["temp"] in alltext: s += 40
    if par.get("d_outer") and par["d_outer"] in alltext: s += 30

    # Title words
    words = [w for w in q_lower.split() if len(w)>=3]
    matched = sum(1 for w in words if w in title)
    s += matched * 25
    if matched == len(words) and words: s += 30

    # Full text
    for w in words:
        if w in alltext: s += 3

    return s

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
    q_exp   = _expand(q_clean)
    q_lower = q_clean.lower()
    par     = _params(q_clean + " " + q_clean.upper())

    # 1. Vector
    vec_ids = await _vec(q_exp, 40)

    all_ids: dict = {}
    all_prods: dict = {}

    # helper
    async def add(rows, bonus=0):
        for p in rows:
            if p.id not in all_ids: all_ids[p.id] = 0
            all_ids[p.id] += bonus
            all_prods[p.id] = p

    # 2. SKU
    if par.get("sku"):
        await add((await db.execute(select(Product).where(
            or_(Product.sku.ilike(f"%{par['sku']}%"),
                Product.search_text.ilike(f"%{par['sku']}%"))
        ).limit(20))).scalars().all(), 1000)

    # 3. Vector results
    if vec_ids:
        rows = (await db.execute(select(Product).where(Product.id.in_(vec_ids)))).scalars().all()
        await add(rows, 0)

    # 4. Technical params — DN/mm = inner diameter, bar, temp
    tech_filters = []
    dn = par.get("dn") or par.get("d_inner")
    if dn:
        # DN65 → matches "DN65", "DN 65", "65мм", "65mm", "d_вн_мм: 65"
        tech_filters.append(Product.search_text.ilike(f"%DN{dn}%"))
        tech_filters.append(Product.search_text.ilike(f"%DN {dn}%"))
        tech_filters.append(Product.search_text.ilike(f"%{dn}мм%"))
        tech_filters.append(Product.search_text.ilike(f"%{dn}mm%"))
        tech_filters.append(Product.search_text.ilike(f"%d_вн_мм%{dn}%"))

    if par.get("bar"):
        bar_int = str(int(float(par["bar"])))
        tech_filters.append(Product.search_text.ilike(f"%{bar_int} bar%"))
        tech_filters.append(Product.search_text.ilike(f"%{bar_int} бар%"))
        tech_filters.append(Product.search_text.ilike(f"%Тиск_бар%{bar_int}%"))

    if par.get("temp"):
        tech_filters.append(Product.search_text.ilike(f"%{par['temp']}°%"))
        tech_filters.append(Product.search_text.ilike(f"%Темп%{par['temp']}%"))

    if tech_filters:
        rows = (await db.execute(select(Product).where(or_(*tech_filters)).limit(60))).scalars().all()
        await add(rows, 80)

    # 5. AND keyword
    words = [w for w in re.split(r'\s+', q_exp.lower())
             if len(w)>=3 and w not in ('для','або','при','від','the','and','for','with')][:5]
    if words:
        conds = [or_(Product.title.ilike(f"%{w}%"), Product.search_text.ilike(f"%{w}%"),
                     Product.description.ilike(f"%{w}%")) for w in words]
        rows = (await db.execute(select(Product).where(and_(*conds)).limit(100))).scalars().all()
        await add(rows, 50)

    # 6. OR fallback
    if len(all_ids) < 5 and words:
        conds = [Product.title.ilike(f"%{w}%") for w in words[:3]]
        rows = (await db.execute(select(Product).where(or_(*conds)).limit(50))).scalars().all()
        await add(rows, 10)

    # 7. Load missing vector prods
    miss = [i for i in vec_ids if i not in all_prods]
    if miss:
        for p in (await db.execute(select(Product).where(Product.id.in_(miss)))).scalars().all():
            all_prods[p.id] = p

    # Filter by section/category
    if section_id or category_id:
        all_prods = {i:p for i,p in all_prods.items()
                     if (not section_id or p.section_id==section_id)
                     and (not category_id or p.category_id==category_id)}
        all_ids = {i:s for i,s in all_ids.items() if i in all_prods}

    # Score & sort
    cat_hints = _get_category_boost(q_clean)
    scored = sorted(
        [(all_prods[i], _score(all_prods[i], q_lower, par, vec_ids, cat_hints) + all_ids.get(i,0))
         for i in all_prods],
        key=lambda x: -x[1]
    )
    seen, unique = set(), []
    for p, sc in scored:
        if p.id not in seen: seen.add(p.id); unique.append((p, sc))

    total = len(unique)
    page_items = unique[(page-1)*page_size: page*page_size]

    results = []
    for p, sc in page_items:
        doc_obj = await db.get(Document, p.document_id)
        match = ("sku" if par.get("sku") and par["sku"].lower() in (p.sku or "").lower()
                 else "vector" if p.id in vec_ids else "text")
        results.append({
            "id":p.id, "title":p.title, "subtitle":p.subtitle or "",
            "sku":p.sku or "", "description":(p.description or "")[:300],
            "attributes":p.attributes or {}, "variants":p.variants or [],
            "image_url":f"/api/products/{p.id}/image" if p.image_bbox else "",
            "page_number":p.page_number,
            "document_id":p.document_id, "section_id":p.section_id, "category_id":p.category_id,
            "document_url":doc_obj.file_url if doc_obj else "",
            "_score":sc, "_match":match,
        })

    return {
        "query":q_clean, "total":total, "page":page, "page_size":page_size,
        "items":results, "params_detected":par,
        "vector_used":bool(vec_ids),
        "query_expanded": q_exp if q_exp != q_clean else None,
    }

@router.get("/suggest")
async def suggest(q: str = Query(..., min_length=2), db: AsyncSession = Depends(get_db)):
    t = f"%{q}%"
    rows = (await db.execute(
        select(Product.id, Product.title, Product.sku).where(
            or_(Product.title.ilike(t), Product.sku.ilike(t), Product.search_text.ilike(t))
        ).limit(8)
    )).all()
    return {"suggestions":[{"id":r[0],"title":r[1],"sku":r[2]} for r in rows]}
