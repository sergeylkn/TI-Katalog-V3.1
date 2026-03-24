"""
Smart Advisor v7 — AI-підбір промислової продукції на базі Claude Sonnet.

Логіка:
1. Витягуємо технічні вимоги з запиту (DN, bar, температура, матеріал, середовище)
2. Виконуємо мульти-стратегічний пошук: ProductIndex (SKU) + вектор + ключові слова + параметри
3. Фільтруємо та ранжуємо кандидатів за відповідністю параметрів
4. Claude Sonnet аналізує ПОВНІ дані товарів і підбирає оптимальний варіант
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
from models.models import Product, Section, Category, ProductIndex

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — спеціаліст з підбору промислової продукції TI
# ─────────────────────────────────────────────────────────────────────────────
ADVISOR_SYSTEM = """Ти — Тарас, старший інженер-консультант TI-Katalog (Tubes International Україна).
15 років підбираєш промислові шланги, арматуру, гідравліку та пневматику.
Говориш мовою клієнта (UA/PL/EN/RU).

═══════════════════════════════════════════════════════
АЛГОРИТМ ПІДБОРУ (ВИКОНУЙ СТРОГО)
═══════════════════════════════════════════════════════

КРОК 1 — АНАЛІЗ ВИМОГ
Визнач з запиту:
• Тип продукту (шланг / арматура / гідравліка / пневматика / клапан / з'єднання)
• Середовище/застосування (вода, масло, повітря, пар, хімія, їжа, нафта, газ)
• DN (внутрішній діаметр, мм) — "65мм" = DN65, "ДН25" = DN25
• Робочий тиск (bar) — завжди потрібен запас × 1.5–2
• Температурний діапазон (°C)
• Матеріал (гума, силікон, ПТФЕ, нержавійка, латунь, поліпропілен)
• Спеціальні вимоги (харчова промисловість, ATEX, хімстійкість, зовнішнє застосування)
• Конкретний SKU/артикул (якщо клієнт знає)

КРОК 2 — ВИБІР З КАТАЛОГУ
Із наданих товарів (розділ ЗНАЙДЕНО В КАТАЛОЗІ) обери найкращий варіант.

КРИТЕРІЇ ВІДПОВІДНОСТІ (перевіряй кожен):
✓ DN товару = запитуваному (або найближчий стандартний)
✓ Робочий тиск товару ≥ потрібний × 1.5 (запас міцності)
✓ Температурний діапазон ВКЛЮЧАЄ робочу температуру клієнта
✓ Матеріал СУМІСНИЙ із середовищем
✓ Наявні сертифікати (FDA/EC для їжі, ATEX для вибухонебезпечних зон)
✓ Конструкція підходить для умов монтажу

КРОК 3 — ФОРМАТ ВІДПОВІДІ

Якщо знайшов підходящий товар:

**[Назва товару]** `[SKU]`
→ **Відповідність**: [% або коротко: "DN ✓, тиск ✓, матеріал ✓"]
→ **Чому підходить**: [1–2 речення з технічним обґрунтуванням]
→ **Параметри**: [DN, тиск, температура, матеріал]
→ [Переглянути в каталозі](/product/[ID])

Якщо є 2–3 варіанти — покажи всі, поясни різницю.

Якщо параметри товару краще за потрібні — поясни запас.

⚠ ПОПЕРЕДЖЕННЯ (якщо є обмеження):
[Критичне обмеження або несумісність]

Якщо товарів у каталозі немає або жоден не підходить:
→ Скажи чесно. Уточни 1–2 параметри для кращого пошуку.

Якщо запит нечіткий:
→ Задай ТІЛЬКИ 1–2 найважливіших уточнювальних питання.

═══════════════════════════════════════════════════════
ТЕХНІЧНІ ЗНАННЯ
═══════════════════════════════════════════════════════

DN (Номінальний діаметр) = ВНУТРІШНІЙ діаметр шланга/труби:
• "шланг 65мм", "ДН65", "DN65" — всі означають DN65
• Зовнішній діаметр завжди більший (стінка 2–20мм)
• Стандартний ряд: DN6, 10, 12, 16, 19, 25, 32, 38, 50, 63, 76, 100, 125, 150, 200

ТИСК:
• Робочий тиск (PN/WP) — максимальний постійний тиск
• Тиск розриву (BP) — зазвичай 3–4× робочий
• Рекомендація: вибирай WP ≥ потрібний × 1.5
• Гідравліка: 70–700 bar; Пневматика: до 16 bar; Промисловість: 6–25 bar

МАТЕРІАЛИ ТА СЕРЕДОВИЩА:
• ПТФЕ (тефлон) — харчова промисловість, агресивна хімія, пар до 230°C
• EPDM — вода, пар до 150°C, НЕ для масел/нафти
• NBR/нітрил — масло, паливо, гідравліка; НЕ для кетонів
• Silicone — їжа, фарма, температури -60°C до +200°C
• Polyurethane — пневматика, абразиви
• Нержавійка 316L — агресивна хімія, харчова промисловість, море
• Латунь — вода, повітря, нейтральні середовища до 120°C

СЕРТИФІКАТИ:
• FDA 21 CFR / EC 1935/2004 — обов'язково для харчових продуктів
• ATEX — вибухонебезпечні зони (пил, горючі гази)
• NSF/ANSI 61 — питна вода
• CE / REACH / RoHS — загальна відповідність ЄС

ВАЖЛИВО: Всі товари в розділі ЗНАЙДЕНО В КАТАЛОЗІ — реальні, наявні позиції.
Посилання /product/ID — реальні сторінки каталогу."""


# ─────────────────────────────────────────────────────────────────────────────
# Розширення запиту та витяг параметрів
# ─────────────────────────────────────────────────────────────────────────────
PL_KEYWORDS = {
    "wąż": "шланг hose", "węże": "шланги hoses", "przewód": "шланг труба",
    "złącze": "з'єднання фітинг", "złącza": "з'єднання фітинги",
    "zawór": "клапан кран", "armatura": "арматура",
    "hydrauliczny": "гідравлічний hydraulic", "pneumatyczny": "пневматичний pneumatic",
    "spożywczy": "харчовий food", "chemiczny": "хімічний chemical",
    "gumowy": "гумовий rubber", "silikonowy": "силіконовий silicone",
    "ciśnienie": "тиск pressure", "temperatura": "температура",
    "obejma": "хомут", "uszczelnienie": "ущільнення",
}

RU_KEYWORDS = {
    "шланг": "шланг hose", "рукав": "рукав шланг hose",
    "соединение": "з'єднання fitting", "фитинг": "фітинг fitting",
    "клапан": "клапан valve", "кран": "кран valve",
    "гидравлика": "гідравліка hydraulic", "пневматика": "пневматика pneumatic",
    "нержавейка": "нержавіюча stainless", "латунь": "латунь brass",
    "пищевой": "харчовий food", "химический": "хімічний chemical",
    "давление": "тиск pressure", "диаметр": "діаметр diameter",
    "температура": "температура temperature", "масло": "масло oil",
    "вода": "вода water", "воздух": "повітря air", "пар": "пара steam",
    "хомут": "хомут clamp", "манометр": "манометр gauge",
    "адаптер": "адаптер adapter", "муфта": "муфта coupling",
    "быстросъемное": "швидкороз'ємне quick connect",
    "камлок": "camlock", "обратный клапан": "зворотний клапан check valve",
    "шаровой кран": "кульовий кран ball valve",
}


def _expand_query(q: str) -> str:
    """Розширює запит: перекладає PL/RU терміни + нормалізує ДН→DN."""
    expanded = q
    q_l = q.lower()
    for kw, ua in {**PL_KEYWORDS, **RU_KEYWORDS}.items():
        if kw in q_l:
            expanded += " " + ua
    # ДН/дн → DN
    expanded = re.sub(r'\bдн\s*(\d+)\b', lambda m: f'DN{m.group(1)}', expanded, flags=re.I)
    expanded = re.sub(r'\bбар\b', 'bar', expanded, flags=re.I)
    return expanded


def _extract_tech_params(q: str) -> dict:
    """Витягує технічні параметри: DN, bar, temp, SKU, medium."""
    params = {}
    qu = q.upper()
    q_norm = re.sub(r'\bдн\s*(\d+)\b', lambda m: f'DN{m.group(1)}', q, flags=re.I)

    # SKU (артикул)
    if m := re.search(r'\b([A-Z]{1,8}[-][A-Z0-9][-A-Z0-9/\.]{2,25})\b', qu):
        params["sku"] = m.group(1)

    # Тиск
    if m := re.search(r'(\d+[\.,]?\d*)\s*(?:bar|бар|атм)\b', q, re.I):
        params["bar"] = float(m.group(1).replace(",", "."))

    # Температура
    if m := re.search(r'([+-]?\d+)\s*°?\s*[Cc]', q):
        params["temp_c"] = int(m.group(1))

    # DN (після нормалізації)
    if m := re.search(r'\bDN\s*?(\d+)\b', q_norm, re.I):
        params["dn"] = int(m.group(1))

    # d_inner × d_outer
    if m := re.search(r'\b(\d+)\s*[xX×]\s*(\d+)\s*(?:mm|мм)?\b', q):
        params["d_inner"] = int(m.group(1))
        params["d_outer"] = int(m.group(2))
        if not params.get("dn"):
            params["dn"] = int(m.group(1))

    # Просто мм → внутрішній діаметр
    if not params.get("dn"):
        if m := re.search(r'\b(\d+)\s*(?:mm|мм)\b', q, re.I):
            val = int(m.group(1))
            if 4 <= val <= 400:
                params["dn"] = val
                params["d_inner"] = val

    # Середовище
    media_map = {
        "вода": "water", "water": "water", "woda": "water",
        "масло": "oil", "oil": "oil", "olej": "oil",
        "повітря": "air", "воздух": "air", "air": "air", "powietrze": "air",
        "пар": "steam", "пара": "steam", "steam": "steam", "para": "steam",
        "їжа": "food", "харчов": "food", "food": "food", "spożyw": "food",
        "хімі": "chemical", "химич": "chemical", "chemical": "chemical",
        "нафта": "petroleum", "нефт": "petroleum", "petroleum": "petroleum",
        "газ": "gas", "gas": "gas",
    }
    q_l = q.lower()
    for kw, medium in media_map.items():
        if kw in q_l:
            params["medium"] = medium
            break

    return params


# ─────────────────────────────────────────────────────────────────────────────
# Пошук по каталогу — багатостратегічний
# ─────────────────────────────────────────────────────────────────────────────
async def _vector_search(q: str, limit: int = 20) -> List[int]:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "text-embedding-3-small", "input": q[:3000]},
            )
            if r.status_code != 200:
                return []
            emb = r.json()["data"][0]["embedding"]
        from core.database import engine
        async with engine.connect() as conn:
            res = await conn.execute(
                text(
                    f"SELECT id FROM products WHERE embedding IS NOT NULL "
                    f"ORDER BY embedding <=> '{str(emb)}'::vector LIMIT {limit}"
                )
            )
            return [row[0] for row in res.fetchall()]
    except Exception as e:
        logger.debug(f"Vector: {e}")
        return []


async def _catalog_search(
    q: str, params: dict, db: AsyncSession, limit: int = 15
) -> List[Product]:
    """
    Мульти-стратегічний пошук:
    1. ProductIndex — точний пошук SKU (включно з варіантами)
    2. Vector semantic search
    3. SKU prefix/contains
    4. AND-keyword (всі слова)
    5. OR-keyword (хоча б одне слово)
    6. Технічні параметри (DN, bar, temp)
    7. Ранжування з урахуванням всіх параметрів
    """
    q_exp = _expand_query(q)
    found_ids: dict = {}   # id → score
    all_products: dict = {}

    def _add(prods, bonus=0):
        for p in prods:
            found_ids[p.id] = found_ids.get(p.id, 0) + bonus
            all_products[p.id] = p

    # 1. ProductIndex — найточніший пошук SKU та варіантів
    if params.get("sku"):
        sku_q = params["sku"].upper()
        sku_nodash = re.sub(r'[-_]', '', sku_q)
        filters = [
            ProductIndex.index_value == sku_q,
            ProductIndex.index_value.ilike(f"{sku_q}%"),
        ]
        if sku_nodash != sku_q:
            filters.append(ProductIndex.index_value.ilike(f"{sku_nodash}%"))
        idx_rows = (await db.execute(
            select(ProductIndex).where(or_(*filters)).limit(10)
        )).scalars().all()
        if idx_rows:
            pids = list({r.product_id for r in idx_rows})
            prods = (await db.execute(select(Product).where(Product.id.in_(pids)))).scalars().all()
            _add(prods, 3000)

    # 2. Vector search (семантична відповідність)
    vec_ids = await _vector_search(q_exp, limit=20)
    for rank, pid in enumerate(vec_ids):
        found_ids[pid] = found_ids.get(pid, 0) + (20 - rank) * 5

    # 3. Пошук по SKU в полі products.sku
    q_up = q.upper().strip()
    if len(q_up) >= 4:
        rows = (await db.execute(
            select(Product).where(or_(
                Product.sku.ilike(f"{q_up}%"),
                Product.sku.ilike(f"%{q_up}%"),
                Product.search_text.ilike(f"%{q_up}%"),
            )).limit(20)
        )).scalars().all()
        _add(rows, 1500)

    # 4. AND-keyword пошук (всі значущі слова)
    words = [w for w in re.split(r'\s+', q_exp.lower())
             if len(w) >= 3 and w not in ('для', 'або', 'при', 'від', 'the', 'and', 'for', 'with', 'do')][:5]
    if words:
        and_conds = [or_(
            Product.title.ilike(f"%{w}%"),
            Product.search_text.ilike(f"%{w}%"),
            Product.description.ilike(f"%{w}%"),
        ) for w in words]
        rows = (await db.execute(
            select(Product).where(and_(*and_conds)).limit(50)
        )).scalars().all()
        _add(rows, 50)

    # 5. OR-fallback (хоча б одне слово)
    if len(found_ids) < 5 and words:
        or_conds = [Product.title.ilike(f"%{w}%") for w in words[:3]]
        rows = (await db.execute(
            select(Product).where(or_(*or_conds)).limit(30)
        )).scalars().all()
        _add(rows, 10)

    # 6. Технічні параметри — завантажуємо vector prods
    missing = [pid for pid in vec_ids if pid not in all_products]
    if missing:
        rows = (await db.execute(select(Product).where(Product.id.in_(missing)))).scalars().all()
        for p in rows:
            all_products[p.id] = p

    # 7. Буст за параметрами
    dn = params.get("dn")
    bar = params.get("bar")
    temp = params.get("temp_c")
    medium = params.get("medium", "")

    for pid, p in all_products.items():
        srch = (p.search_text or "").lower()
        desc = (p.description or "").lower()
        attrs_str = json.dumps(p.attributes or {}).lower()
        combined = srch + " " + desc + " " + attrs_str

        if dn:
            dn_s = str(dn)
            if f"dn{dn_s}" in combined or f"dn {dn_s}" in combined or f" {dn_s}мм" in combined or f" {dn_s}mm" in combined:
                found_ids[pid] = found_ids.get(pid, 0) + 120
            elif dn_s in combined:
                found_ids[pid] = found_ids.get(pid, 0) + 50

        if bar:
            bar_s = str(int(bar))
            if f"{bar_s} bar" in combined or f"{bar_s} бар" in combined or f"{bar_s}bar" in combined:
                found_ids[pid] = found_ids.get(pid, 0) + 80

        if temp:
            temp_s = str(temp)
            if temp_s in combined:
                found_ids[pid] = found_ids.get(pid, 0) + 50

        if medium and medium in combined:
            found_ids[pid] = found_ids.get(pid, 0) + 60

    # Сортування за сукупним балом
    sorted_ids = sorted(found_ids.keys(), key=lambda pid: found_ids[pid], reverse=True)
    result = []
    for pid in sorted_ids[:limit]:
        if pid in all_products:
            result.append(all_products[pid])
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Форматування товару для AI контексту — максимально детально
# ─────────────────────────────────────────────────────────────────────────────
def _find_attr(attrs: dict, *patterns: str) -> Optional[str]:
    for key, val in attrs.items():
        if any(p.lower() in key.lower() for p in patterns):
            return str(val)
    return None


def _format_product_for_ai(p: Product, rank: int) -> str:
    lines = [f"\n{'─'*50}", f"[ТОВАР #{rank} | ID:{p.id}]"]
    lines.append(f"Назва: {p.title}")
    if p.subtitle:
        lines.append(f"Підзаголовок: {p.subtitle}")
    if p.sku:
        lines.append(f"SKU/Артикул: {p.sku}")

    if p.attributes:
        lines.append("Технічні характеристики:")
        attrs = p.attributes

        # Пріоритетні параметри — виносимо окремо
        dn = _find_attr(attrs, "dn", "d_вн", "внутр", "inner", "nominal", "розмірн", "діаметр")
        if dn:
            lines.append(f"  • DN / внутрішній діаметр: {dn} мм")
        d_out = _find_attr(attrs, "зовн", "outer", "d_out")
        if d_out:
            lines.append(f"  • Зовнішній діаметр: {d_out} мм")
        bar = _find_attr(attrs, "тиск", "pressure", "bar", "pn", "робочий", "wp", "dn/pn")
        if bar:
            lines.append(f"  • Робочий тиск: {bar}")
        temp = _find_attr(attrs, "темп", "temperature", "температур")
        if temp:
            lines.append(f"  • Температура: {temp}")
        mat = _find_attr(attrs, "матер", "material", "матеріал")
        if mat:
            lines.append(f"  • Матеріал: {mat}")
        medium = _find_attr(attrs, "середовищ", "medium", "застосув", "application")
        if medium:
            lines.append(f"  • Середовище/застосування: {medium}")

        # Решта атрибутів
        shown_kw = {"dn","d_вн","внутр","inner","nominal","розмірн","діаметр",
                    "зовн","outer","тиск","pressure","bar","pn","робочий","wp",
                    "темп","temperature","матер","material","середовищ","medium",
                    "застосув","application"}
        for k, v in attrs.items():
            if not any(s in k.lower() for s in shown_kw):
                lines.append(f"  • {k}: {v}")

    if p.certifications:
        lines.append(f"Сертифікати: {p.certifications}")

    if p.description and len(p.description) > 20:
        lines.append(f"Опис: {p.description[:800]}")

    # Варіанти (розміри) — показуємо всі, вони важливі для підбору
    if p.variants and len(p.variants) > 0:
        lines.append(f"Доступні варіанти ({len(p.variants)} розмірів):")
        for v in p.variants[:8]:
            v_parts = []
            for k, val in v.items():
                if k not in ("_sku",) and val:
                    v_parts.append(f"{k}:{val}")
            vline = ", ".join(v_parts)[:100]
            v_sku = v.get("_sku", "")
            if vline:
                lines.append(f"  [{v_sku}] {vline}" if v_sku else f"  {vline}")
        if len(p.variants) > 8:
            lines.append(f"  ... і ще {len(p.variants) - 8} варіантів")

    lines.append(f"Посилання в каталозі: /product/{p.id}")
    return "\n".join(lines)


async def _get_catalog_overview(db: AsyncSession) -> str:
    cats = (await db.execute(select(Category).order_by(Category.name))).scalars().all()
    if not cats:
        return ""
    lines = ["Структура каталогу TI:"]
    for cat in cats:
        count = (await db.execute(
            select(func.count(Product.id)).where(Product.category_id == cat.id)
        )).scalar_one()
        if count > 0:
            lines.append(f"  • {cat.name}: {count} товарів")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# API endpoint
# ─────────────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    history: list = []
    search_query: Optional[str] = None


@router.post("/")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(503, "ANTHROPIC_API_KEY не налаштовано")

    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Повідомлення порожнє")

    # Витягуємо технічні параметри
    params = _extract_tech_params(message)

    # Пошук по каталогу
    products = await _catalog_search(message, params, db, limit=12)

    # Будуємо системний промпт
    system = ADVISOR_SYSTEM

    # Огляд каталогу — тільки в першому повідомленні
    if len(req.history) == 0:
        overview = await _get_catalog_overview(db)
        if overview:
            system += f"\n\n{overview}"

    # Знайдені товари
    if products:
        system += f"\n\n{'═'*50}\nЗНАЙДЕНО В КАТАЛОЗІ ({len(products)} товарів):\n{'═'*50}"
        for i, p in enumerate(products, 1):
            system += _format_product_for_ai(p, i)
        system += f"\n{'═'*50}"
        system += "\n\nВикористовуй ТІЛЬКИ ці товари. Посилання /product/ID — реальні."
    else:
        system += "\n\n[Каталог: товарів за цим запитом не знайдено. Запропонуй уточнити параметри.]"

    if params:
        params_str = json.dumps(params, ensure_ascii=False)
        system += f"\n\nВитягнуті параметри: {params_str}"

    # Формуємо повідомлення з історією
    try:
        import httpx
        msgs = []
        for m in req.history[-12:]:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                msgs.append({"role": m["role"], "content": str(m["content"])[:3000]})
        msgs.append({"role": "user", "content": message})

        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 3000,
                    "system": system,
                    "messages": msgs,
                },
            )
            r.raise_for_status()

        reply = r.json()["content"][0]["text"]

        # Формуємо search_results для фронтенду
        search_results = []
        for p in products[:6]:
            search_results.append({
                "id":         p.id,
                "title":      p.title,
                "sku":        p.sku or "",
                "subtitle":   (p.subtitle or "")[:120],
                "image_url":  f"/api/products/{p.id}/image" if p.image_bbox else "",
                "attributes": dict(list((p.attributes or {}).items())[:5]),
                "certifications": p.certifications or "",
                "page_number": p.page_number,
            })

        return {
            "reply":           reply,
            "rag_used":        bool(products),
            "search_results":  search_results,
            "product_count":   len(products),
            "params_detected": params,
        }

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(500, str(e))
