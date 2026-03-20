"""
PDF Extractor v5 — Pure regex, $0 import cost.
- Extracts products with image_bbox, variants, full attributes
- Builds search_text for hybrid search
- Optional: OpenAI embeddings after save
- Updates section.full_text as RAG knowledge base
"""
import asyncio
import logging
import os
import re
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    import fitz
    _FITZ = True
except ImportError:
    _FITZ = False

# ── Spec key-value labels ─────────────────────────────────────────────────────
SPEC_LABELS = [
    "Матеріал шлангу", "Внутрішній шар", "Зовнішній шар",
    "Армування", "Робоча темп", "Робоча температура",
    "Температура", "Матеріал", "Середній шар",
    "Тиск", "Робочий тиск", "Вакуум",
]

SKU_PATTERN = re.compile(r'\b([A-Z]{2,6}[-_][A-Z0-9][-A-Z0-9/]{3,30})\b')
CERT_PATTERN = re.compile(
    r'(?:1935/2004|10/2011|2023/2006|FDA\s*21|ISO\s*\d+|EN\s*\d+|DIN\s*\d+|'
    r'RoHS|REACH|WRAS|UL94|MSHA)[^\n]{0,120}',
    re.IGNORECASE
)


# ── OpenAI embedding (optional) ───────────────────────────────────────────────

async def _get_embedding(text: str) -> Optional[List[float]]:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or not text:
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "text-embedding-3-small", "input": text[:8000]}
            )
            if r.status_code == 200:
                return r.json()["data"][0]["embedding"]
    except Exception as e:
        logger.debug(f"Embedding error: {e}")
    return None


# ── PDF helpers ───────────────────────────────────────────────────────────────

def _get_spans(page) -> List[Dict]:
    spans = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                t = span["text"].strip()
                if t:
                    spans.append({
                        "text": t, "size": span["size"],
                        "bold": "Bold" in span.get("font", ""),
                        "bbox": span["bbox"], "color": span["color"],
                    })
    return spans


def _find_product_image(page) -> Optional[Dict]:
    """Find largest product photo (left half, medium size)."""
    best, best_area = None, 0
    for img in page.get_images(full=True):
        try:
            bbox = page.get_image_bbox(img)
            w, h = bbox.x1 - bbox.x0, bbox.y1 - bbox.y0
            if w < 80 or h < 60 or w > 350 or bbox.x0 > 310:
                continue
            area = w * h
            if area > best_area:
                best_area = area
                best = {"page": page.number + 1,
                        "x0": round(bbox.x0, 1), "y0": round(bbox.y0, 1),
                        "x1": round(bbox.x1, 1), "y1": round(bbox.y1, 1)}
        except Exception:
            continue
    return best


def _find_model_name(spans: List[Dict]) -> Optional[str]:
    skip = {"www.", "tubes-international", "Шланги для промисловості",
            "Шланги промислові", "Шланги універсальні", "Силова гідравліка",
            "Промислова арматура", "Пневматика"}
    candidates = []
    for s in spans:
        t = s["text"].strip()
        if len(t) < 2 or len(t) > 80:
            continue
        if any(sk in t for sk in skip):
            continue
        upper_ratio = sum(1 for c in t if c.isupper()) / max(len(t), 1)
        score = 0
        if s["size"] >= 12: score += 3
        if s["bold"]:        score += 2
        if upper_ratio > 0.4: score += 2
        if re.search(r'[A-Z]{3}', t): score += 1
        if score >= 4:
            candidates.append((score, s["bbox"][1], t))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


def _find_subtitle(spans: List[Dict], model: str) -> Optional[str]:
    found = False
    for s in spans:
        t = s["text"].strip()
        if model and model.upper() in t.upper():
            found = True
            continue
        if found and len(t) > 10:
            if s["color"] != 0 or s["bold"]:
                return t[:300]
            if not any(lbl in t for lbl in SPEC_LABELS):
                return t[:300]
    return None


def _extract_specs(spans: List[Dict]) -> Dict[str, str]:
    specs = {}
    full_text = "\n".join(s["text"] for s in spans)
    for label in SPEC_LABELS:
        m = re.search(
            rf'{re.escape(label)}\s*[:\s]\s*(.{{3,120}}?)(?=\n|$)',
            full_text, re.IGNORECASE | re.MULTILINE
        )
        if m:
            val = m.group(1).strip().rstrip(".,")
            if val:
                specs[label.split()[0]] = val[:200]
    return specs


def _extract_description(spans: List[Dict]) -> str:
    lines = []
    seen = set()
    for s in spans:
        t = s["text"].strip()
        if len(t) < 20:
            continue
        if any(sk in t for sk in ["www.", "tubes-international"]):
            continue
        digit_ratio = sum(1 for c in t if c.isdigit()) / len(t)
        if digit_ratio > 0.4:
            continue
        if 7 <= s["size"] <= 12:
            key = t[:40]
            if key not in seen:
                seen.add(key)
                lines.append(t)
    return " ".join(lines)[:4000]


def _extract_certifications(spans: List[Dict]) -> Optional[str]:
    full = " ".join(s["text"] for s in spans)
    matches = CERT_PATTERN.findall(full)
    if not matches:
        return None
    return max(matches, key=len)[:600]


def _extract_variants(page) -> List[Dict]:
    variants = []
    try:
        tabs = page.find_tables()
        for tab in tabs.tables:
            df = tab.to_pandas()
            if df is None or df.empty:
                continue
            first_col = df.iloc[:, 0].astype(str)
            if not first_col.str.match(r'[A-Z]{2,}[-_]').any():
                continue
            headers = [str(c).strip() for c in df.columns]
            for _, row in df.iterrows():
                variant = {}
                for col, val in zip(headers, row):
                    v = str(val).strip()
                    if v and v not in ("nan", "None", ""):
                        variant[str(col).strip()[:50]] = v[:80]
                if variant:
                    vals = list(variant.values())
                    if vals and re.match(r'[A-Z]{2,}[-_]', vals[0]):
                        variant["_sku"] = vals[0]
                    variants.append(variant)
    except Exception as e:
        logger.debug(f"Table extract: {e}")
    return variants[:200]


def _build_search_text(title, subtitle, sku, attrs, variants, description) -> str:
    """Denormalized text for FTS and vector search."""
    parts = [title or ""]
    if subtitle:
        parts.append(subtitle)
    if sku:
        parts.append(sku)
    for v, k in attrs.items():
        parts.append(f"{v} {k}")
    # Add all variant SKUs
    for var in (variants or []):
        vsku = var.get("_sku") or var.get("Індекс") or var.get("indeks", "")
        if vsku:
            parts.append(vsku)
    if description:
        parts.append(description[:500])
    return " | ".join(filter(None, parts))[:8000]


# ── Main extraction ───────────────────────────────────────────────────────────

async def extract_products(
    pdf_bytes: bytes,
    document_id: int,
    section_id: Optional[int],
    category_id: Optional[int] = None,
) -> Tuple[List, int]:
    if not _FITZ:
        raise RuntimeError("PyMuPDF not installed")

    from core.database import AsyncSessionLocal
    from models.models import Product, Section

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    saved = []
    all_page_text = []

    for page_idx in range(page_count):
        page = doc[page_idx]
        pnum = page_idx + 1
        spans = _get_spans(page)
        page_raw = page.get_text("text").strip()
        if page_raw:
            all_page_text.append(page_raw)

        if not spans:
            continue

        model_name = _find_model_name(spans)
        if not model_name:
            continue

        image_bbox = _find_product_image(page)
        subtitle = _find_subtitle(spans, model_name)
        specs = _extract_specs(spans)
        description = _extract_description(spans)
        certifications = _extract_certifications(spans)
        variants = _extract_variants(page)

        # SKU from first variant or text scan
        sku = None
        if variants:
            sku = variants[0].get("_sku") or variants[0].get("Індекс")
        if not sku:
            m = SKU_PATTERN.search(" ".join(s["text"] for s in spans))
            sku = m.group(1) if m else None

        search_text = _build_search_text(
            model_name, subtitle, sku, specs, variants, description
        )

        # Optional embedding
        embedding = await _get_embedding(search_text[:2000])

        prod_data = dict(
            title=model_name[:512],
            subtitle=(subtitle or "")[:512],
            sku=(sku or "")[:128],
            description=description,
            certifications=certifications,
            attributes=specs,
            variants=variants,
            search_text=search_text,
            image_bbox=image_bbox,
            page_number=pnum,
            document_id=document_id,
            section_id=section_id,
            category_id=category_id,
        )

        try:
            async with AsyncSessionLocal() as db:
                prod = Product(**prod_data)
                db.add(prod)
                await db.commit()
                await db.refresh(prod)

                # Store embedding in separate table if pgvector available
                if embedding:
                    try:
                        await db.execute(
                            __import__('sqlalchemy').text(
                                "UPDATE products SET embedding = :emb WHERE id = :id"
                            ),
                            {"emb": str(embedding), "id": prod.id}
                        )
                        await db.commit()
                    except Exception:
                        pass  # pgvector not available yet

                saved.append(prod)
                logger.info(
                    f"Doc#{document_id} p{pnum}: '{model_name}' "
                    f"{len(variants)} variants, "
                    f"img={'✓' if image_bbox else '✗'}, "
                    f"emb={'✓' if embedding else '✗'}"
                )
        except Exception as e:
            logger.error(f"Save product p{pnum}: {e}")

    doc.close()

    # Update section full_text (RAG knowledge base)
    if all_page_text and section_id:
        full = "\n\n".join(all_page_text)[:50000]
        try:
            async with AsyncSessionLocal() as db:
                sec = await db.get(Section, section_id)
                if sec and not sec.full_text:
                    sec.full_text = full
                    # Extract description from first 2 pages
                    intro = "\n".join(all_page_text[:2])[:1000]
                    if not sec.description:
                        sec.description = intro
                    await db.commit()
        except Exception as e:
            logger.debug(f"Section full_text: {e}")

    return saved, page_count
