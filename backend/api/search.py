"""
Smart Search v6 — AI-powered search with recommendations.
- дн/ДН → DN normalization
- Category-aware scoring
- AI recommendations panel (separate endpoint)
- Inline AI suggestions in search bar
"""
import logging, os, re, json
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_, and_, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.models import Product, Document, Category, Section, ProductIndex

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])

# ── Polish → Ukrainian/English ────────────────────────────────────────────────
# ── Russian → Ukrainian/English keyword mapping ───────────────────────────────
RU_MAP = {
    # Шланги
    "шланг":             "шланг hose",
    "шлангов":           "шланг hose",
    "рукав":             "рукав шланг hose",
    "рукава":            "рукав шланг hose",
    "трубопровод":       "шланг трубопровід pipe",
    "труба":             "труба трубопровід pipe",
    "трубка":            "трубка tube",
    # Матеріали
    "резиновый":         "гумовий rubber",
    "резиновая":         "гумова rubber",
    "силиконовый":       "силіконовий silicone",
    "силиконовая":       "силіконова silicone",
    "пищевой":           "харчовий food",
    "пищевая":           "харчова food",
    "химический":        "хімічний chemical",
    "химическая":        "хімічна chemical",
    "нержавейка":        "нержавіюча stainless",
    "нержавеющий":       "нержавіюча stainless",
    "латунный":          "латунний brass",
    "латунная":          "латунна brass",
    "стальной":          "сталевий steel",
    "стальная":          "сталева steel",
    "чугунный":          "чавунний cast iron",
    "пластиковый":       "пластиковий plastic",
    # Гідравліка
    "гидравлический":    "гідравлічний hydraulic",
    "гидравлическая":    "гідравлічна hydraulic",
    "гидравлика":        "гідравліка hydraulic",
    "насос":             "насос pump",
    "цилиндр":           "циліндр cylinder",
    "гидроцилиндр":      "гідроциліндр hydraulic cylinder",
    # Пневматика
    "пневматический":    "пневматичний pneumatic",
    "пневматическая":    "пневматична pneumatic",
    "пневматика":        "пневматика pneumatic",
    "воздушный":         "повітряний air",
    # Арматура / з'єднання
    "соединение":        "з'єднання fitting connection",
    "соединения":        "з'єднання fitting connection",
    "фитинг":            "фітинг fitting",
    "фитинги":           "фітинги fittings",
    "адаптер":           "адаптер adapter",
    "переходник":        "перехідник adapter",
    "муфта":             "муфта coupling",
    "кран":              "кран valve",
    "шаровый кран":      "кульовий кран ball valve",
    "шаровой кран":      "кульовий кран ball valve",
    "клапан":            "клапан valve",
    "обратный клапан":   "зворотний клапан check valve",
    "манометр":          "манометр gauge pressure",
    "хомут":             "хомут clamp",
    "хомуты":            "хомути clamps",
    "обойма":            "обойма clamp",
    "фланец":            "фланець flange",
    "фланцевый":         "фланцевий flange",
    "штуцер":            "штуцер fitting",
    "ниппель":           "ніпель nipple",
    "угольник":          "кутник elbow",
    "тройник":           "трійник tee",
    "заглушка":          "заглушка plug cap",
    "уплотнение":        "ущільнення seal",
    "прокладка":         "прокладка gasket",
    "быстросъемное":     "швидкороз'ємне quick connect",
    "быстроразъемное":   "швидкороз'ємне quick disconnect",
    "камлок":            "camlock",
    "камелок":           "camlock",
    # Технічні параметри (включно з розмітками ДН → DN)
    "давление":          "тиск pressure",
    "диаметр":           "діаметр diameter",
    "внутренний":        "внутрішній inner",
    "наружный":          "зовнішній outer",
    "наружний":          "зовнішній outer",
    "рабочее давление":  "робочий тиск working pressure",
    "температура":       "температура temperature",
    "рабочая температура": "робоча температура working temperature",
    # Застосування
    "нефть":             "нафта oil petroleum",
    "нефтепродукты":     "нафтопродукти petroleum",
    "масло":             "масло oil",
    "вода":              "вода water",
    "воздух":            "повітря air",
    "пар":               "пара steam",
    "газ":               "газ gas",
    "топливо":           "паливо fuel",
    "пескоструй":        "піскоструминний sandblast",
    "пескоструйный":     "піскоструминний sandblast",
    "пищевая промышленность": "харчова промисловість food industry",
    "промышленность":    "промисловість industry",
    "сельское хозяйство": "сільське господарство agriculture",
    # Одиниці виміру
    "бар":               "bar",
    "атм":               "bar",
    "кгс":               "bar",
}


def _is_russian(q: str) -> bool:
    """Detect if query contains Russian (not Ukrainian) text."""
    ua_specific_chars = {"і", "ї", "є", "ґ"}
    # Common Ukrainian words that share chars with Russian
    ua_words = {"шланг", "харчовий", "харчова", "кран", "клапан", "тиск",
                "рукав", "фітинг", "з'єднання", "нержавіюча", "гідравлічний",
                "пневматичний", "хомут", "манометр", "насос"}
    # Russian-specific words (not used in Ukrainian)
    ru_words = {"гидравлический", "гидравлическ", "пневматический", "пневматическ",
                "соединение", "давление", "рукава", "шлангов", "нержавейка",
                "пищевых", "пищевой", "пищевая", "химический", "химическ",
                "диаметр", "резиновый", "резинов", "латунный", "стальной",
                "фитинг", "угольник", "тройник", "заглушка", "уплотнение",
                "продуктов", "промышленн", "сельского", "воздушный", "воздушн",
                "нефтепродукт", "топливный", "быстросъем", "быстроразъем",
                "температурн", "рабочего", "рабочей", "рабочий"}
    q_l = q.lower()
    cyrillic = [c for c in q_l if "\u0400" <= c <= "\u04FF"]
    if not cyrillic:
        return False
    if set(cyrillic) & ua_specific_chars:
        return False  # has Ukrainian-specific letters
    # Check Russian-specific words first (they override ambiguous shared words)
    has_ru_words = any(w in q_l for w in ru_words)
    has_ua_words = any(w in q_l for w in ua_words)
    if has_ru_words and not has_ua_words:
        return True   # purely Russian terms
    if has_ru_words and has_ua_words:
        return True   # mixed but has Russian - still translate (adds UA equivalents)
    if has_ua_words:
        return False  # Ukrainian words without Russian
    # Default: ambiguous, treat as Ukrainian (safer)
    return False


def _ru_to_ua(q: str) -> str:
    """Translate Russian query terms to Ukrainian/English equivalents."""
    if not _is_russian(q):
        return q
    result = q
    q_l = q.lower()
    # Apply longer phrases first (more specific)
    for ru, ua_en in sorted(RU_MAP.items(), key=lambda x: -len(x[0])):
        if ru in q_l:
            result += " " + ua_en
    # Russian ДН → DN (same as Ukrainian дн)
    result = re.sub(r"\bДН\s*(\d+)\b", lambda m: f"DN{m.group(1)}", result, flags=re.I)
    result = re.sub(r"\bДН\b", "DN", result, flags=re.I)
    return result


PL_MAP = {
    "wąż":"шланг hose", "węże":"шланги hoses", "przewód":"шланг труба",
    "złącze":"з'єднання фітинг", "zawór":"клапан кран", "armatura":"арматура",
    "hydrauliczny":"гідравлічний hydraulic", "pneumatyczny":"пневматичний pneumatic",
    "spożywczy":"харчовий food", "chemiczny":"хімічний chemical",
    "gumowy":"гумовий rubber", "silikonowy":"силіконовий silicone",
    "ciśnienie":"тиск pressure bar", "temperatura":"температура temperature",
    "obejma":"хомут clamp", "uszczelnienie":"ущільнення seal",
    "zawór kulowy":"кульовий кран ball valve",
    "szybkozłącze":"швидкороз'ємне з'єднання quick coupling",
    "wąż hydrauliczny":"гідравлічний шланг hydraulic hose",
    "wąż spożywczy":"харчовий шланг food hose",
}

# Category hint words → what to boost
CATEGORY_HINTS = {
    "шланг": ["шланг","рукав","hose","wąż","sleeve"],
    "шланги": ["шланг","рукав","hose"],
    "рукав": ["шланг","рукав","hose"],
    "hose": ["шланг","рукав","hose"],
    "кран": ["кран","valve","клапан"],
    "клапан": ["клапан","valve","кран"],
    "фітинг": ["фітинг","з'єднання","fitting","złącze"],
    "fitting": ["фітинг","з'єднання","fitting"],
    "з'єднання": ["з'єднання","фітинг","coupling","złącze"],
    "арматура": ["арматура","з'єднання","fitting","armatura"],
    "манометр": ["манометр","тиск","pressure","gauge"],
    "хомут": ["хомут","обойма","clamp","obejma"],
    "насос": ["насос","pump","агрегат"],
    "адаптер": ["адаптер","adapter","перехідник"],
    "camlock": ["camlock","роз'єм"],
    "bauer": ["bauer","важільне"],
    "guillemin": ["guillemin"],
    "storz": ["storz"],
    # Russian keywords
    "рукав": ["шланг","рукав","hose"],
    "соединение": ["з'єднання","фітинг","fitting"],
    "фитинг": ["фітинг","з'єднання","fitting"],
}


def _normalize_q(q: str) -> str:
    """дн→DN, ДН→DN, colloquial fixes."""
    r = re.sub(r'\bдн\s*(\d+)\b', lambda m: f'DN{m.group(1)}', q, flags=re.I)
    r = re.sub(r'\bдн\b', 'DN', r, flags=re.I)
    r = re.sub(r'\bбар\b', 'bar', r, flags=re.I)
    return r


def _expand_q(q: str) -> str:
    """Translate RU→UA, add Polish/English equivalents."""
    r = _normalize_q(q)
    # Russian translation (adds UA/EN equivalents)
    r = _ru_to_ua(r)
    q_l = r.lower()
    # Polish expansion
    for pl, ua in PL_MAP.items():
        if pl in q_l:
            r += " " + ua
    return r


def _extract_params(q: str) -> dict:
    q2 = _normalize_q(q)
    p = {}
    # Try SKU match on uppercase version (handles "ti-a101-08-08" → "TI-A101-08-08")
    if m := re.search(r'\b([A-Z0-9]{2,8}[-_/][A-Z0-9][-A-Z0-9/_\.]{2,30})\b', q2.upper()):
        p['sku'] = m.group(1)
    # Also check if entire query looks like a SKU (no spaces, has dashes)
    elif re.match(r'^[a-zA-Z0-9]{2,}[-_/][a-zA-Z0-9][-a-zA-Z0-9/_\.]{2,}$', q2.strip()):
        p['sku'] = q2.strip().upper()
    if m := re.search(r'(\d+[\.,]?\d*)\s*(?:bar|бар)\b', q2, re.I):
        p['bar'] = m.group(1).replace(',', '.')
    if m := re.search(r'([+-]?\d+)\s*°?\s*[Cc]\b', q2):
        p['temp'] = m.group(1)
    if m := re.search(r'\bDN\s*?(\d+)\b', q2, re.I):
        p['dn'] = m.group(1); p['d_inner'] = m.group(1)
    if not p.get('dn'):
        if m := re.search(r'\b(\d+)\s*[xX×]\s*(\d+)\s*(?:mm|мм)?\b', q2):
            p['d_inner'] = m.group(1); p['d_outer'] = m.group(2); p['dn'] = m.group(1)
    if not p.get('dn'):
        if m := re.search(r'\b(\d+)\s*(?:mm|мм)\b', q2, re.I):
            v = m.group(1)
            if 4 <= int(v) <= 400: p['dn'] = v; p['d_inner'] = v
    return p


def _cat_hints(q: str) -> list:
    q_l = q.lower()
    seen, result = set(), []
    for kw, hints in CATEGORY_HINTS.items():
        if kw in q_l:
            for h in hints:
                if h not in seen:
                    seen.add(h)
                    result.append(h)
    return result


async def _vec(q: str, n: int = 40) -> List[int]:
    key = os.getenv('OPENAI_API_KEY', '')
    if not key: return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post('https://api.openai.com/v1/embeddings',
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json={'model': 'text-embedding-3-small', 'input': q[:2000]})
            if r.status_code != 200: return []
            emb = r.json()['data'][0]['embedding']
        from core.database import engine
        async with engine.connect() as conn:
            res = await conn.execute(
                text(f'SELECT id FROM products WHERE embedding IS NOT NULL ORDER BY embedding <=> \'{str(emb)}\'::vector LIMIT {n}'))
            return [row[0] for row in res.fetchall()]
    except Exception as e:
        logger.debug(f'vec: {e}'); return []


def _score(p: Product, q_lower: str, par: dict, vec_ids: List[int], hints: list) -> int:
    s = 0
    title   = (p.title or '').lower()
    sku_val = (p.sku or '').lower()
    srch    = (p.search_text or '').lower()
    desc    = (p.description or '').lower()
    attrs   = str(p.attributes or {}).lower()
    all_t   = f'{title} {sku_val} {srch} {desc} {attrs}'

    # SKU exact
    q_sku = par.get('sku', '').lower()
    if q_sku:
        if sku_val == q_sku:              s += 200
        elif sku_val.startswith(q_sku):   s += 150
        elif q_sku in sku_val:            s += 120
        elif q_sku in srch:               s += 80

    # Vector rank
    if p.id in vec_ids:
        s += max(80 - vec_ids.index(p.id) * 2, 10)

    # Category hint — boost correct type, penalize wrong
    if hints:
        cat_match = sum(1 for h in hints if h in title)
        s += cat_match * 50
        if cat_match == 0:
            s -= 25  # penalize wrong category

    # DN match (inner diameter)
    dn = par.get('dn') or par.get('d_inner')
    if dn:
        if f'dn{dn}' in srch or f'dn {dn}' in srch or f'{dn}мм' in srch or f'{dn}mm' in srch:
            s += 70
        elif dn in srch:
            s += 40

    # Pressure
    if par.get('bar'):
        bar_i = str(int(float(par['bar'])))
        if f'{bar_i} bar' in srch or f'{bar_i} бар' in srch or f'тиск_бар' in attrs and bar_i in attrs:
            s += 55

    # Temperature
    if par.get('temp') and par['temp'] in all_t:
        s += 35

    # Title word matches
    words = [w for w in q_lower.split() if len(w) >= 3]
    matched = sum(1 for w in words if w in title)
    s += matched * 20
    if matched == len(words) and words: s += 40

    # Full text
    for w in words:
        if w in all_t: s += 3

    return s


async def _load_products(ids: list, db) -> dict:
    if not ids: return {}
    rows = (await db.execute(select(Product).where(Product.id.in_(ids)))).scalars().all()
    return {p.id: p for p in rows}


# ── Main search endpoint ──────────────────────────────────────────────────────
@router.get('/')
async def search(
    q: str = Query(..., min_length=1),
    section_id: Optional[int] = None,
    category_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    q_clean = q.strip()
    q_exp   = _expand_q(q_clean)
    q_lower = _normalize_q(q_clean).lower()
    par     = _extract_params(q_clean + ' ' + q_clean.upper())
    hints   = _cat_hints(q_clean)

    # 1. Vector
    vec_ids = await _vec(q_exp, 40)

    all_ids: dict = {}
    all_prods: dict = {}

    async def add(rows, bonus=0):
        for p in rows:
            all_ids[p.id] = all_ids.get(p.id, 0) + bonus
            all_prods[p.id] = p

    # 2. SKU / Index search — multiple strategies
    q_up = _normalize_q(q_clean).upper().strip()
    q_up_nodash = re.sub(r'[-_/]', '', q_up)  # "TIA10108-08" for fuzzy match

    # 2a. ProductIndex table (fast, catches all variant SKUs)
    idx_filters = [
        ProductIndex.index_value == q_up,
        ProductIndex.index_value.ilike(f"{q_up}%"),
    ]
    # Also try without dashes
    if q_up_nodash != q_up and len(q_up_nodash) >= 4:
        idx_filters.append(ProductIndex.index_value.ilike(f"{q_up_nodash}%"))
    
    idx_rows = (await db.execute(
        select(ProductIndex).where(or_(*idx_filters)).limit(20)
    )).scalars().all()
    if idx_rows:
        pids = list({r.product_id for r in idx_rows})
        idx_prods = (await db.execute(select(Product).where(Product.id.in_(pids)))).scalars().all()
        await add(idx_prods, 2000)

    # 2b. Direct SKU field match (own SKU, not variants)
    sku_q = par.get('sku') or q_up
    if sku_q and len(sku_q) >= 4:
        rows = (await db.execute(select(Product).where(
            or_(
                Product.sku.ilike(f"{sku_q}%"),      # starts with
                Product.sku.ilike(f"%{sku_q}%"),      # contains
            )
        ).limit(20))).scalars().all()
        await add(rows, 1500)

    # 2c. search_text contains the index (catches variant SKUs even without ProductIndex)
    if sku_q and len(sku_q) >= 4:
        rows = (await db.execute(select(Product).where(
            or_(
                Product.search_text.ilike(f"%{sku_q}%"),
                Product.search_text.ilike(f"%{q_up_nodash}%") if q_up_nodash != q_up else Product.search_text.ilike(f"%{sku_q}%"),
            )
        ).limit(30))).scalars().all()
        await add(rows, 1000)

    # 3. Vector results
    if vec_ids:
        await add((await db.execute(select(Product).where(Product.id.in_(vec_ids)))).scalars().all())

    # 4. Technical params
    tech = []
    dn = par.get('dn') or par.get('d_inner')
    if dn:
        tech += [Product.search_text.ilike(f'%DN{dn}%'),
                 Product.search_text.ilike(f'%{dn}мм%'),
                 Product.search_text.ilike(f'%{dn}mm%')]
    if par.get('bar'):
        bi = str(int(float(par['bar'])))
        tech += [Product.search_text.ilike(f'%{bi} bar%'),
                 Product.search_text.ilike(f'%{bi} бар%')]
    if par.get('temp'):
        tech.append(Product.search_text.ilike(f"%{par['temp']}%"))
    if tech:
        await add((await db.execute(select(Product).where(or_(*tech)).limit(60))).scalars().all(), 80)

    # 5. AND keyword search
    words = [w for w in re.split(r'\s+', q_exp.lower())
             if len(w) >= 3 and w not in ('для','або','при','від','the','and','for','with')][:5]
    if words:
        conds = [or_(Product.title.ilike(f'%{w}%'),
                     Product.search_text.ilike(f'%{w}%'),
                     Product.description.ilike(f'%{w}%')) for w in words]
        await add((await db.execute(select(Product).where(and_(*conds)).limit(100))).scalars().all(), 50)

    # 6. OR fallback
    if len(all_ids) < 5 and words:
        conds = [Product.title.ilike(f'%{w}%') for w in words[:3]]
        await add((await db.execute(select(Product).where(or_(*conds)).limit(50))).scalars().all(), 10)

    # Load missing vector prods
    miss = [i for i in vec_ids if i not in all_prods]
    if miss:
        for p in (await db.execute(select(Product).where(Product.id.in_(miss)))).scalars().all():
            all_prods[p.id] = p

    # Filter
    if section_id or category_id:
        all_prods = {i: p for i, p in all_prods.items()
                     if (not section_id or p.section_id == section_id)
                     and (not category_id or p.category_id == category_id)}
        all_ids = {i: s for i, s in all_ids.items() if i in all_prods}

    # Score + sort
    scored = sorted(
        [(all_prods[i], _score(all_prods[i], q_lower, par, vec_ids, hints) + all_ids.get(i, 0))
         for i in all_prods],
        key=lambda x: -x[1]
    )
    seen, unique = set(), []
    for p, sc in scored:
        if p.id not in seen: seen.add(p.id); unique.append((p, sc))

    total = len(unique)
    page_items = unique[(page - 1) * page_size: page * page_size]

    results = []
    for p, sc in page_items:
        doc = await db.get(Document, p.document_id)
        match = ('sku' if par.get('sku') and par['sku'].lower() in (p.sku or '').lower()
                 else 'vector' if p.id in vec_ids else 'text')
        results.append({
            'id': p.id, 'title': p.title, 'subtitle': p.subtitle or '',
            'sku': p.sku or '', 'description': (p.description or '')[:300],
            'attributes': p.attributes or {}, 'variants': p.variants or [],
            'image_url': f'/api/products/{p.id}/image' if (p.image_bbox or p.page_number) else '',
            'page_number': p.page_number,
            'document_id': p.document_id, 'section_id': p.section_id, 'category_id': p.category_id,
            'document_url': doc.file_url if doc else '',
            '_score': sc, '_match': match,
        })

    return {
        'query': q_clean, 'total': total, 'page': page, 'page_size': page_size,
        'items': results, 'params_detected': par,
        'vector_used': bool(vec_ids),
        'query_expanded': q_exp if q_exp != q_clean else None,
    }


# ── AI Recommendations endpoint ───────────────────────────────────────────────
@router.get('/ai-recommend')
async def ai_recommend(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns AI recommendation text + top products for inline search panel.
    Called when user types in search box — shows smart suggestions.
    """
    anthro_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not anthro_key:
        return {'advice': '', 'products': [], 'clarify': []}

    par = _extract_params(q + ' ' + q.upper())
    q_exp = _expand_q(q)

    # Find top products
    vec_ids = await _vec(q_exp, 10)
    words = [w for w in re.split(r'\s+', q_exp.lower()) if len(w) >= 3][:4]

    products = []
    seen_ids = set()

    if vec_ids:
        rows = (await db.execute(select(Product).where(Product.id.in_(vec_ids[:8])))).scalars().all()
        id_order = {pid: i for i, pid in enumerate(vec_ids)}
        rows = sorted(rows, key=lambda p: id_order.get(p.id, 99))
        for p in rows:
            if p.id not in seen_ids:
                seen_ids.add(p.id); products.append(p)

    if len(products) < 5 and words:
        conds = [or_(Product.title.ilike(f'%{w}%'), Product.search_text.ilike(f'%{w}%')) for w in words[:3]]
        extra = (await db.execute(select(Product).where(and_(*conds)).limit(8))).scalars().all()
        for p in extra:
            if p.id not in seen_ids and len(products) < 8:
                seen_ids.add(p.id); products.append(p)

    # Score and pick top 5
    hints = _cat_hints(q)
    scored = sorted(products, key=lambda p: _score(p, q.lower(), par, vec_ids, hints), reverse=True)
    top5 = scored[:5]

    # Build AI advice
    def _pick(attrs: dict, *kws) -> str:
        for k, v in attrs.items():
            if any(kw in k.lower() for kw in kws):
                return str(v)[:30]
        return ''

    prod_ctx = '\n'.join(
        f'- {p.title}' + (f' [{p.sku}]' if p.sku else '') +
        (f' | DN:{_pick(p.attributes or {}, "dn","d_вн","inner","nominal")}' if _pick(p.attributes or {}, "dn","d_вн","inner","nominal") else '') +
        (f' | {_pick(p.attributes or {}, "тиск","pressure","bar","pn")} bar' if _pick(p.attributes or {}, "тиск","pressure","bar","pn") else '') +
        (f' | {_pick(p.attributes or {}, "матер","material")}' if _pick(p.attributes or {}, "матер","material") else '')
        for p in top5
    ) or 'Товарів не знайдено'

    params_str = json.dumps(par, ensure_ascii=False) if par else 'не виявлено'

    system = """Ти — технічний консультант промислового каталогу TI-Katalog.
Відповідай мовою запиту (UA/PL/EN). Будь дуже коротким — 1-3 речення максимум.

Твоя задача:
1. Якщо запит зрозумілий — скажи що саме знайдено і чому це підходить
2. Якщо запит нечіткий — задай 1 уточнююче питання
3. Якщо є технічні параметри (DN, bar, °C) — підтверди що врахував їх

НЕ перераховуй товари (вони вже показані). Коментуй підбір."""

    user_msg = f"""Запит клієнта: "{q}"
Виявлені параметри: {params_str}
Знайдені товари:
{prod_ctx}

Дай коротку консультацію."""

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                'https://api.anthropic.com/v1/messages',
                headers={'x-api-key': anthro_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                json={'model': 'claude-haiku-4-5-20251001', 'max_tokens': 200,
                      'system': system,
                      'messages': [{'role': 'user', 'content': user_msg}]}
            )
            r.raise_for_status()
        advice = r.json()['content'][0]['text'].strip()
    except Exception as e:
        logger.debug(f'ai-recommend: {e}')
        advice = ''

    return {
        'advice': advice,
        'params': par,
        'products': [
            {'id': p.id, 'title': p.title, 'sku': p.sku or '',
             'image_url': f'/api/products/{p.id}/image' if (p.image_bbox or p.page_number) else '',
             'attributes': dict(list((p.attributes or {}).items())[:4])}
            for p in top5
        ],
        'clarify': [],
    }


@router.get("/suggest")
async def suggest(q: str = Query(..., min_length=2), db: AsyncSession = Depends(get_db)):
    results = []
    seen_ids = set()
    q_up = q.upper().strip()
    t = f"%{q}%"

    # 1. ProductIndex — finds any variant SKU instantly
    idx_rows = (await db.execute(
        select(ProductIndex).where(
            ProductIndex.index_value.ilike(f"{q_up}%")
        ).order_by(ProductIndex.index_value).limit(6)
    )).scalars().all()

    if idx_rows:
        pids = list({r.product_id for r in idx_rows})
        prods = {p.id: p for p in
                 (await db.execute(select(Product).where(Product.id.in_(pids)))).scalars().all()}
        for ir in idx_rows:
            p = prods.get(ir.product_id)
            if p and p.id not in seen_ids:
                seen_ids.add(p.id)
                results.append({
                    "id": p.id,
                    "title": p.title,
                    "sku": ir.index_value,         # show the matched index
                    "match_type": ir.index_type,   # "sku" | "variant"
                })

    # 2. Direct SKU field search
    if len(results) < 8:
        sku_rows = (await db.execute(
            select(Product.id, Product.title, Product.sku).where(
                Product.sku.ilike(f"{q_up}%")
            ).limit(6)
        )).all()
        for pid, title, sku in sku_rows:
            if pid not in seen_ids and len(results) < 8:
                seen_ids.add(pid)
                results.append({"id": pid, "title": title, "sku": sku or "", "match_type": "sku"})

    # 3. search_text contains (catches variant SKUs)
    if len(results) < 8:
        srch_rows = (await db.execute(
            select(Product.id, Product.title, Product.sku).where(
                Product.search_text.ilike(f"%{q_up}%")
            ).limit(8)
        )).all()
        for pid, title, sku in srch_rows:
            if pid not in seen_ids and len(results) < 8:
                seen_ids.add(pid)
                results.append({"id": pid, "title": title, "sku": q_up, "match_type": "index"})

    # 4. Title search
    if len(results) < 8:
        title_rows = (await db.execute(
            select(Product.id, Product.title, Product.sku).where(
                Product.title.ilike(f"%{q}%")
            ).limit(8)
        )).all()
        for pid, title, sku in title_rows:
            if pid not in seen_ids and len(results) < 8:
                seen_ids.add(pid)
                results.append({"id": pid, "title": title, "sku": sku or "", "match_type": "title"})

    return {"suggestions": results[:8]}


@router.get("/by-index")
async def by_index(index: str = Query(..., min_length=3), db: AsyncSession = Depends(get_db)):
    """Find product by exact variant index/SKU and highlight the variant."""
    from fastapi import HTTPException
    from models.models import Document as Doc
    index_up = index.upper().strip()
    # 1. Own SKU
    row = (await db.execute(select(Product).where(Product.sku.ilike(index_up)))).scalar_one_or_none()
    # 2. Search_text (contains all variant SKUs)
    if not row:
        row = (await db.execute(
            select(Product).where(Product.search_text.ilike(f"%{index_up}%")).limit(1)
        )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"Index {index} not found")
    # Find the specific variant
    matched_variant = None
    sku_keys = ["_sku","Індекс","Indeks","Index","SKU","Артикул"]
    for var in (row.variants or []):
        for sk in sku_keys:
            if sk in var and index_up in str(var[sk]).upper():
                matched_variant = var
                break
        if matched_variant: break
    doc = await db.get(Doc, row.document_id)
    return {
        "id": row.id, "title": row.title, "sku": row.sku or "",
        "matched_index": index, "matched_variant": matched_variant,
        "image_url": f"/api/products/{row.id}/image" if (row.image_bbox or row.page_number) else "",
        "document_url": doc.file_url if doc else "",
        "page_number": row.page_number,
        "attributes": row.attributes or {}, "variants": row.variants or [],
    }
