"""AI Chat with RAG — pulls relevant products from DB as context."""
import logging
import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models.models import Product, Section, Category

logger = logging.getLogger(__name__)
router = APIRouter()

SYSTEM = """Ти — AI-асистент промислового каталогу TI-Katalog (Tubes International Україна).
Допомагаєш знаходити шланги, арматуру, фітинги, гідравлічні компоненти, манометри, пневматику.

ВАЖЛИВО:
- Відповідай українською мовою (якщо запит польською — відповідай польською, якщо англійською — англійською)
- Використовуй КОНТЕКСТ З КАТАЛОГУ який буде надано нижче
- Якщо знайдено конкретні товари — називай їх з артикулом (SKU)
- Будь конкретним: називай технічні параметри (DN, бар, температура, матеріал)
- Якщо товар знайдено — додай посилання: [Переглянути товар](/product/{id})

Структура каталогу:
- Силова гідравліка: шланги, адаптери, клапани, насоси, з'єднання
- Промислова арматура: кульові крани, camlock, фітинги, хомути
- Шланги для промисловості: ПВХ, поліуретан, гума, тефлон, силікон
- Промислова пневматика: FRL, клапани, з'єднання
- Прецизійна арматура: голчасті клапани, Let-Lok, манометри
- Вимірювальні системи: манометри, датчики
- Пристрої та аксесуари: преси, барабани, пістолети

Пошук підтримує: українську, польську, англійську мови."""


async def _rag_context(q: str, db: AsyncSession) -> str:
    """Find relevant products for RAG context."""
    terms = [w for w in q.lower().split() if len(w) >= 3]
    if not terms:
        return ""

    filters = []
    for term in terms[:3]:
        t = f"%{term}%"
        filters.append(or_(
            Product.title.ilike(t),
            Product.description.ilike(t),
            Product.search_text.ilike(t),
        ))

    from sqlalchemy import or_ as sql_or
    rows = (await db.execute(
        select(Product).where(sql_or(*filters)).limit(5)
    )).scalars().all()

    if not rows:
        return ""

    parts = ["=== ЗНАЙДЕНІ ТОВАРИ В КАТАЛОЗІ ==="]
    for p in rows:
        parts.append(
            f"• {p.title}"
            + (f" [{p.sku}]" if p.sku else "")
            + (f" — {p.subtitle}" if p.subtitle else "")
            + (f"\n  Атрибути: {p.attributes}" if p.attributes else "")
            + (f"\n  ID: {p.id} → /product/{p.id}")
        )
    return "\n".join(parts)


class ChatMsg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list = []


@router.post("/")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(503, "API key not configured")

    # RAG: find relevant context
    rag = await _rag_context(req.message, db)
    system = SYSTEM
    if rag:
        system += f"\n\n{rag}"

    try:
        import httpx
        messages = req.history[-6:] + [{"role": "user", "content": req.message}]
        # Convert history to proper format
        msgs = []
        for m in messages:
            if isinstance(m, dict) and "role" in m and "content" in m:
                msgs.append({"role": m["role"], "content": str(m["content"])})

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 600,
                    "system": system,
                    "messages": msgs
                },
            )
            r.raise_for_status()

        reply = r.json()["content"][0]["text"]
        return {"reply": reply, "rag_used": bool(rag)}
    except Exception as e:
        raise HTTPException(500, str(e))
