"""
Smart Advisor v6 — повноцінний AI-підбірник промислової продукції.

Підхід: Claude як досвідчений інженер-консультант.
1. Отримує запит клієнта
2. Аналізує та витягує технічні вимоги
3. Робить векторний + текстовий пошук по каталогу
4. Передає ПОВНІ дані товарів Claude
5. Claude аналізує і робить конкретні рекомендації з поясненням
"""
import logging
import os
import re
import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, or_, and_, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.models import Product, Section, Category

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — Claude як інженер-консультант
# ─────────────────────────────────────────────────────────────────────────────
ADVISOR_SYSTEM = """Ти — Тарас, старший інженер-консультант компанії TI-Katalog (Tubes International Україна).
Маєш 15 років досвіду підбору промислових шлангів, арматури, гідравліки та пневматики.

ТВОЯ ЗАДАЧА: підібрати клієнту КОНКРЕТНИЙ товар з каталогу, а не просто відповісти.

СТИЛЬ РОБОТИ:
- Відповідай мовою клієнта (UA/PL/EN)
- Будь конкретним: якщо є товар — назви його, поясни чому він підходить
- Якщо запит нечіткий — спочатку уточни 1-2 ключових параметри
- Порівнюй варіанти якщо їх кілька
- Попереджай про важливі обмеження (температура, хімічна стійкість, тиск)

ФОРМАТ ВІДПОВІДІ (суворо дотримуйся):

Якщо знайшов товари — використовуй цю структуру:

**[Назва товару]** `[SKU]`
→ Чому підходить: [1-2 речення]
→ Параметри: [ключові технічні дані]
→ [Переглянути в каталозі](/product/[ID])

Якщо потрібно уточнення:
Запитай ТІЛЬКИ найважливіше — 1-2 питання максимум.

Якщо товару немає:
Скажи чесно і запропонуй альтернативу або уточнення.

ТЕХНІЧНІ ЗНАННЯ:
- DN (Діаметральний Номінальний) = ВНУТРІШНІЙ діаметр шланга в мм
  Приклад: DN25 = шланг з внутрішнім діаметром 25мм
  Якщо клієнт пише "65мм" або "шланг 65" — це означає DN65
  Зовнішній діаметр завжди більший (стінка шланга ~2-20мм залежно від типу)

- Шланги: завжди уточнюй:
  1. СЕРЕДОВИЩЕ (вода, повітря, хімія, їжа, нафта, пар, гідравліка)
  2. РОБОЧИЙ ТИСК (bar) — максимальний тиск в системі
  3. ТЕМПЕРАТУРА — мінімальна і максимальна робоча температура
  4. ДІАМЕТР — DN або мм внутрішнього діаметру

- Гідравліка: тиск (bar), тип з'єднання (BSP/NPT/SAE/JIC/ORFS/DIN), матеріал
- Пневматика: робочий тиск (max 16 bar зазвичай), діаметр трубки (4/6/8/10/12мм)
- Арматура: DN, PN (тиск), матеріал (латунь/нержавіюча сталь/чавун), стандарт
- Харчова промисловість: ОБОВ'ЯЗКОВО сертифікати FDA 21 CFR або EC 1935/2004
- Хімія: уточнюй конкретну речовину — стійкість матеріалу критична

При підборі завжди перевіряй:
✓ Тиск товару ≥ тиск клієнта (бажано з запасом 1.5-2x)
✓ Температурний діапазон товару включає робочу температуру клієнта
✓ DN товару = потрібному клієнту внутрішньому діаметру
✓ Матеріал сумісний з середовищем

ВАЖЛИВО: Ти маєш доступ до реального каталогу. Товари які тобі надані — реально існують в наявності.
Посилання /product/ID є реальними сторінками товарів."""


# ─────────────────────────────────────────────────────────────────────────────
# Витяг технічних параметрів з запиту
# ─────────────────────────────────────────────────────────────────────────────
PL_KEYWORDS = {
    "wąż": "шланг", "węże": "шланги", "przewód": "шланг труба",
    "złącze": "з'єднання фітинг", "złącza": "з'єднання фітинги",
    "zawór": "клапан кран", "armatura": "арматура",
    "hydrauliczny": "гідравлічний", "pneumatyczny": "пневматичний",
    "spożywczy": "харчовий food", "chemiczny": "хімічний",
    "gumowy": "гумовий", "silikonowy": "силіконовий",
    "ciśnienie": "тиск pressure", "temperatura": "температура",
    "obejma": "хомут", "uszczelnienie": "ущільнення",
}

def _expand_query(q: str) -> str:
    """Translate PL terms, normalize."""
    expanded = q
    for pl, ua in PL_KEYWORDS.items():
        if pl in q.lower():
            expanded += " " + ua
    return expanded


def _extract_tech_params(q: str) -> dict:
    """
    DN = номінальний діаметр = ВНУТРІШНІЙ діаметр шланга.
    Розуміє: DN65, 65мм, 65mm, 25x35, "шланг 65мм"
    """
    params = {}
    qu = q.upper()

    # SKU
    if m := re.search(r'\b([A-Z]{2,8}[-][A-Z0-9][-A-Z0-9/\.]{3,30})\b', qu):
        params["sku"] = m.group(1)

    # Pressure
    if m := re.search(r'(\d+[\.,]?\d*)\s*(?:bar|бар)\b', q, re.I):
        params["bar"] = float(m.group(1).replace(",", "."))

    # Temperature
    if m := re.search(r'([+-]?\d+)\s*°?\s*[Cc]', q):
        params["temp_c"] = int(m.group(1))

    # Normalize дн/ДН → DN first
    q = re.sub(r'\bдн\s*(\d+)\b', lambda m: f'DN{m.group(1)}', q, flags=re.I)
    q = re.sub(r'\bдн\b', 'DN', q, flags=re.I)

    # DN (after normalization)
    if m := re.search(r'\bDN\s*?(\d+)\b', q, re.I):
        params["dn"] = int(m.group(1))
        params["d_inner"] = int(m.group(1))

    # Inner x outer: 25x35mm
    if m := re.search(r'\b(\d+)\s*[xX×]\s*(\d+)\s*(?:mm|мм)?\b', q):
        params["d_inner"] = int(m.group(1))
        params["d_outer"] = int(m.group(2))
        if not params.get("dn"):
            params["dn"] = int(m.group(1))

    # Standalone mm = inner diameter if no DN yet
    if not params.get("dn"):
        if m := re.search(r'\b(\d+)\s*(?:mm|мм)\b', q, re.I):
            val = int(m.group(1))
            if 4 <= val <= 400:
                params["dn"] = val
                params["d_inner"] = val

    return params


# ─────────────────────────────────────────────────────────────────────────────
# Пошук по каталогу
# ─────────────────────────────────────────────────────────────────────────────
async def _vector_search(q: str, limit: int = 15) -> List[int]:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "text-embedding-3-small", "input": q[:3000]}
            )
            if r.status_code != 200:
                return []
            emb = r.json()["data"][0]["embedding"]
        from core.database import engine
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT id FROM products WHERE embedding IS NOT NULL ORDER BY embedding <=> :e::vector LIMIT :l"),
                {"e": str(emb), "l": limit}
            )
            return [row[0] for row in res.fetchall()]
    except Exception as e:
        logger.debug(f"Vector: {e}")
        return []


async def _catalog_search(q: str, params: dict, db: AsyncSession, limit: int = 12) -> List[Product]:
    """Multi-strategy search: vector + keyword + technical params."""
    q_exp = _expand_query(q)
    found_ids: dict = {}  # id → score
    all_products: dict = {}  # id → Product

    # 1. Vector search (best semantic match)
    vec_ids = await _vector_search(q_exp, limit=15)
    for rank, pid in enumerate(vec_ids):
        found_ids[pid] = found_ids.get(pid, 0) + (15 - rank) * 5

    # 2. SKU exact match (highest priority)
    if params.get("sku"):
        rows = (await db.execute(
            select(Product).where(or_(
                Product.sku.ilike(f"%{params['sku']}%"),
                Product.search_text.ilike(f"%{params['sku']}%"),
            )).limit(5)
        )).scalars().all()
        for p in rows:
            found_ids[p.id] = found_ids.get(p.id, 0) + 1000
            all_products[p.id] = p

    # 3. AND keyword search (all meaningful words must match)
    words = [w for w in re.split(r'\s+', q_exp.lower()) if len(w) >= 3 and w not in
             ('для', 'або', 'при', 'від', 'the', 'and', 'for', 'with', 'do', 'ze')][:5]
    if words:
        and_conds = [or_(
            Product.title.ilike(f"%{w}%"),
            Product.search_text.ilike(f"%{w}%"),
            Product.description.ilike(f"%{w}%"),
            Product.subtitle.ilike(f"%{w}%"),
        ) for w in words]
        rows = (await db.execute(
            select(Product).where(and_(*and_conds)).limit(20)
        )).scalars().all()
        for p in rows:
            found_ids[p.id] = found_ids.get(p.id, 0) + 50
            all_products[p.id] = p

    # 4. OR fallback for partial matches
    if len(found_ids) < 5 and words:
        or_conds = [Product.title.ilike(f"%{w}%") for w in words[:3]]
        rows = (await db.execute(
            select(Product).where(or_(*or_conds)).limit(20)
        )).scalars().all()
        for p in rows:
            found_ids[p.id] = found_ids.get(p.id, 0) + 10
            all_products[p.id] = p

    # 5. Load vector results not yet loaded
    missing = [pid for pid in vec_ids if pid not in all_products]
    if missing:
        rows = (await db.execute(select(Product).where(Product.id.in_(missing)))).scalars().all()
        for p in rows:
            all_products[p.id] = p

    # 6. Technical param boost
    for pid, p in all_products.items():
        attrs = str(p.attributes or {}).lower()
        variants = str(p.variants or []).lower()
        combined = attrs + variants + (p.description or "").lower()
        if params.get("dn") and str(params["dn"]) in combined:
            found_ids[pid] = found_ids.get(pid, 0) + 80
        if params.get("bar") and str(int(params["bar"])) in attrs:
            found_ids[pid] = found_ids.get(pid, 0) + 60
        if params.get("d_inner") and str(params["d_inner"]) in combined:
            found_ids[pid] = found_ids.get(pid, 0) + 70

    # Sort by score and return top results
    sorted_ids = sorted(found_ids.keys(), key=lambda pid: found_ids[pid], reverse=True)
    result = []
    for pid in sorted_ids[:limit]:
        if pid in all_products:
            result.append(all_products[pid])
    return result


def _format_product_for_ai(p: Product, rank: int) -> str:
    """Детальний формат товару для AI контексту."""
    lines = [f"\n[ТОВАР #{rank} | ID:{p.id}]"]
    lines.append(f"Назва: {p.title}")
    if p.subtitle:
        lines.append(f"Підзаголовок: {p.subtitle}")
    if p.sku:
        lines.append(f"SKU/Артикул: {p.sku}")
    if p.attributes:
        lines.append("Технічні характеристики:")
        attrs = p.attributes
        # Show DN/diameter prominently
        dn = attrs.get("DN") or attrs.get("d_вн_мм")
        if dn:
            lines.append(f"  • DN (внутрішній діаметр): {dn} мм")
        d_out = attrs.get("d_зовн_мм")
        if d_out:
            lines.append(f"  • Зовнішній діаметр: {d_out} мм")
        bar = attrs.get("Тиск_бар") or attrs.get("Тиск") or attrs.get("Робочий")
        if bar:
            lines.append(f"  • Робочий тиск: {bar} bar")
        t_min = attrs.get("Темп_мін")
        t_max = attrs.get("Темп_макс") or attrs.get("Температура") or attrs.get("Робоча")
        if t_min and t_max:
            lines.append(f"  • Температура: від {t_min}°C до {t_max}°C")
        elif t_max:
            lines.append(f"  • Температура: до {t_max}°C")
        # All other attributes
        skip = {"DN","d_вн_мм","d_зовн_мм","Тиск_бар","Темп_мін","Темп_макс"}
        for k, v in attrs.items():
            if k not in skip:
                lines.append(f"  • {k}: {v}")
    if p.certifications:
        lines.append(f"Сертифікати: {p.certifications}")
    if p.description and len(p.description) > 30:
        lines.append(f"Опис: {p.description[:600]}")
    if p.variants and len(p.variants) > 0:
        lines.append(f"Доступних розмірів/варіантів: {len(p.variants)}")
        # Show first 3 variants
        for v in p.variants[:3]:
            vline = ", ".join(f"{k}:{val}" for k,val in v.items() if k != "_sku" and val)[:80]
            if vline:
                lines.append(f"  - {vline}")
        if len(p.variants) > 3:
            lines.append(f"  ... і ще {len(p.variants)-3} варіантів")
    lines.append(f"Посилання: /product/{p.id}")
    return "\n".join(lines)


async def _get_category_context(db: AsyncSession) -> str:
    """Get catalog structure overview."""
    cats = (await db.execute(select(Category).order_by(Category.name))).scalars().all()
    if not cats:
        return ""
    lines = ["Структура каталогу:"]
    for cat in cats:
        count = (await db.execute(
            select(func.count(Product.id)).where(Product.category_id == cat.id)
        )).scalar_one()
        lines.append(f"  • {cat.name}: {count} товарів")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# API endpoint
# ─────────────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    history: list = []
    # Optional: if user asks to search, pass query directly
    search_query: Optional[str] = None


@router.post("/")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(503, "API key not configured")

    message = req.message.strip()

    # Extract technical params from message
    params = _extract_tech_params(message)

    # Search catalog
    products = await _catalog_search(message, params, db, limit=10)

    # Build AI context
    system = ADVISOR_SYSTEM

    # Add catalog structure on first message
    if len(req.history) == 0:
        cat_ctx = await _get_category_context(db)
        if cat_ctx:
            system += f"\n\n{cat_ctx}"

    # Add found products
    if products:
        system += f"\n\n{'='*50}\nЗНАЙДЕНО В КАТАЛОЗІ ({len(products)} товарів):\n{'='*50}"
        for i, p in enumerate(products, 1):
            system += _format_product_for_ai(p, i)
        system += f"\n{'='*50}\nВикористовуй ТІЛЬКИ ці товари у відповіді. Посилання /product/ID є реальними."
    else:
        system += "\n\n[В каталозі товарів за цим запитом не знайдено. Запропонуй клієнту уточнити параметри.]"

    if params:
        system += f"\n\nВитягнуті технічні параметри з запиту: {json.dumps(params, ensure_ascii=False)}"

    # Build message history
    try:
        import httpx
        msgs = []
        for m in req.history[-10:]:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                msgs.append({"role": m["role"], "content": str(m["content"])[:2000]})
        msgs.append({"role": "user", "content": message})

        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1200,
                    "system": system,
                    "messages": msgs
                },
            )
            r.raise_for_status()

        reply = r.json()["content"][0]["text"]

        # Build search_results for frontend
        search_results = []
        for p in products[:5]:
            search_results.append({
                "id": p.id,
                "title": p.title,
                "sku": p.sku or "",
                "subtitle": (p.subtitle or "")[:100],
                "image_url": f"/api/products/{p.id}/image" if p.image_bbox else "",
                "attributes": dict(list((p.attributes or {}).items())[:4]),
                "page_number": p.page_number,
            })

        return {
            "reply": reply,
            "rag_used": bool(products),
            "search_results": search_results,
            "product_count": len(products),
            "params_detected": params,
        }

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(500, str(e))
