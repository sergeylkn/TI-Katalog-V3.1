"""
Smart PDF Extractor v6 — Claude Haiku + PyMuPDF.

Стратегія:
1. PyMuPDF витягує текст + таблиці (безкоштовно, швидко)
2. Claude Haiku (~$0.0001/стор) аналізує текст → структуровані дані
3. Fallback regex якщо Haiku недоступний

Результат: точні назви, DN/bar/temp/матеріал, всі SKU варіантів.
"""
import asyncio
import json
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

# ── Patterns ──────────────────────────────────────────────────────────────────
_SKU_PAT  = re.compile(r'\b([A-Z]{2,8}[-_][A-Z0-9][-A-Z0-9/_\.]{2,30})\b')
_DN_RE    = re.compile(r'\bDN\s*(\d+)\b', re.I)
_BAR_RE   = re.compile(r'(\d+[\.,]?\d*)\s*(?:bar|BAR|бар)\b')
_TEMP_RE  = re.compile(r'([+-]?\d+)\s*°?\s*[Cc°]\s*(?:do|до|[~–-])\s*([+-]?\d+)\s*°?\s*[Cc°]', re.I)
_TEMP1_RE = re.compile(r'(?:від|від\s*\+?|від\s*)([+-]?\d+)', re.I)
_DIAM_RE  = re.compile(r'\b(\d+[\.,]?\d*)\s*[xX×]\s*(\d+[\.,]?\d*)\s*mm', re.I)
_CERT_PAT = re.compile(
    r'(?:1935/2004|10/2011|FDA\s*21|ISO\s*\d+|EN\s*\d+|DIN\s*\d+|'
    r'RoHS|REACH|WRAS|UL\s*94|MSHA|NSF)[^\n]{0,120}',
    re.IGNORECASE
)

SKIP_WORDS = {
    "www.", "tubes-international", "Tel:", "Fax:", "e-mail:",
    "TI-Katalog", "KATALOG", "Сторінка", "Page", "©",
}

# ── Claude Haiku extractor ────────────────────────────────────────────────────
HAIKU_SYSTEM = """Ти — парсер промислового PDF каталогу.
Витягуй дані про продукт і повертай JSON. ТІЛЬКИ JSON, без пояснень.

Правила:
- title: назва продукту/моделі (не категорія і не назва компанії)
- subtitle: короткий опис призначення (1 рядок)
- material: матеріал (гума/ПВХ/силікон/нержавіюча сталь/латунь/поліуретан тощо)
- dn_mm: внутрішній діаметр в мм (число або null)
- bar_max: максимальний робочий тиск в bar (число або null)  
- temp_min: мінімальна температура °C (число або null)
- temp_max: максимальна температура °C (число або null)
- application: застосування (харчова/хімічна/нафтова/повітря/вода/гідравліка/пара тощо)
- certifications: список сертифікатів або null
- sku: головний артикул/індекс або null
- description: опис продукту 1-3 речення

Якщо дані не знайдено — null, не вигадуй."""

HAIKU_EXTRACT_PROMPT = """Текст зі сторінки PDF каталогу промислових шлангів/арматури:

{page_text}

Таблиця варіантів (якщо є):
{table_text}

Витягни дані продукту і поверни JSON з полями:
title, subtitle, material, dn_mm, bar_max, temp_min, temp_max, application, certifications, sku, description"""


async def _haiku_extract(page_text: str, table_text: str) -> Optional[dict]:
    """Use Claude Haiku to extract structured product data from page text."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return None

    # Trim text to fit context
    page_trimmed = page_text[:3000]
    table_trimmed = table_text[:1000] if table_text else "немає"

    prompt = HAIKU_EXTRACT_PROMPT.format(
        page_text=page_trimmed,
        table_text=table_trimmed,
    )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 600,
                    "system": HAIKU_SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            if r.status_code != 200:
                logger.debug(f"Haiku API error: {r.status_code}")
                return None

        text = r.json()["content"][0]["text"].strip()

        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        return json.loads(text)

    except json.JSONDecodeError as e:
        logger.debug(f"Haiku JSON parse error: {e}")
        return None
    except Exception as e:
        logger.debug(f"Haiku extract error: {e}")
        return None


# ── Embedding ─────────────────────────────────────────────────────────────────
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
                json={"model": "text-embedding-3-small", "input": text[:8000]},
            )
            if r.status_code == 200:
                return r.json()["data"][0]["embedding"]
    except Exception as e:
        logger.debug(f"Embedding error: {e}")
    return None


# ── PyMuPDF helpers ───────────────────────────────────────────────────────────
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
                        "text": t,
                        "size": round(span["size"], 1),
                        "bold": "Bold" in span.get("font", ""),
                        "bbox": span["bbox"],
                        "color": span["color"],
                    })
    return spans


def _extract_tables_text(page) -> Tuple[List[Dict], str]:
    """Extract table data as both structured variants and plain text."""
    variants = []
    table_lines = []

    try:
        import pandas as pd
        tabs = page.find_tables()
        for tab in tabs.tables:
            df = tab.to_pandas()
            if df is None or df.empty:
                continue

            # Table as plain text for Claude
            table_lines.append(df.to_string(index=False, max_rows=30))

            # Check if this looks like a product variants table
            first_col = df.iloc[:, 0].astype(str)
            has_sku_col = first_col.str.match(r'[A-Z]{2,}[-_]', na=False).any()

            if not has_sku_col:
                # Maybe column header contains SKU info
                for col in df.columns:
                    if re.match(r'[A-Z]{2,}[-_]', str(col)):
                        has_sku_col = True
                        break

            if has_sku_col or len(df) > 2:
                headers = [str(c).strip()[:50] for c in df.columns]
                for _, row in df.iterrows():
                    variant = {}
                    for col, val in zip(headers, row):
                        v = str(val).strip()
                        if v and v not in ("nan", "None", "", "-"):
                            variant[col] = v[:100]
                    if len(variant) >= 2:
                        # Try to find SKU in row
                        for k, v in variant.items():
                            if re.match(r'[A-Z]{2,}[-_][A-Z0-9]', v):
                                variant["_sku"] = v
                                break
                        variants.append(variant)

    except Exception as e:
        logger.debug(f"Table extract: {e}")

    table_text = "\n---\n".join(table_lines)[:2000]
    return variants[:200], table_text


def _find_image(page) -> Optional[Dict]:
    """Find best product image bbox on page."""
    best, best_area = None, 0
    for img in page.get_images(full=True):
        try:
            bbox = page.get_image_bbox(img)
            w = bbox.x1 - bbox.x0
            h = bbox.y1 - bbox.y0
            if w < 60 or h < 50 or w > 400:
                continue
            area = w * h
            if area > best_area:
                best_area = area
                best = {
                    "page": page.number + 1,
                    "x0": round(bbox.x0, 1), "y0": round(bbox.y0, 1),
                    "x1": round(bbox.x1, 1), "y1": round(bbox.y1, 1),
                }
        except Exception:
            continue
    return best


def _extract_certifications(text: str) -> Optional[str]:
    matches = _CERT_PAT.findall(text)
    if not matches:
        return None
    return "; ".join(sorted(set(m.strip()[:100] for m in matches)))[:600]


def _extract_all_skus(text: str, variants: List[Dict]) -> List[str]:
    """Collect every SKU mention from page text and variant tables."""
    skus = set()
    for m in _SKU_PAT.finditer(text.upper()):
        skus.add(m.group(1))
    sku_keys = ["_sku", "Індекс", "Indeks", "Index", "SKU", "Артикул"]
    for var in variants:
        for k in sku_keys:
            if k in var and var[k]:
                v = str(var[k]).strip().upper()
                if re.match(r'[A-Z]{2,}[-_]', v):
                    skus.add(v)
    return list(skus)


# ── Regex fallback (when Haiku unavailable) ───────────────────────────────────
def _regex_extract(spans: List[Dict], full_text: str) -> dict:
    """Pure regex extraction — fast but less accurate than Haiku."""

    # Find title: largest/boldest text, not a category name
    SKIP = {"www.", "tubes-international", "TI-Katalog", "Tel:", "KATALOG"}
    candidates = []
    for s in spans:
        t = s["text"].strip()
        if len(t) < 3 or len(t) > 120 or any(sk in t for sk in SKIP):
            continue
        score = 0
        if s["size"] >= 12:
            score += int(s["size"])
        if s["bold"]:
            score += 5
        if re.search(r'[A-Z]{3}', t):
            score += 3
        if score >= 10:
            candidates.append((score, s["bbox"][1], t))

    title = None
    if candidates:
        candidates.sort(key=lambda x: (-x[0], x[1]))
        title = candidates[0][2]

    # Subtitle: text right after title
    subtitle = None
    if title:
        found = False
        for s in spans:
            t = s["text"].strip()
            if title.upper() in t.upper():
                found = True
                continue
            if found and len(t) > 15 and not any(sk in t for sk in SKIP):
                subtitle = t[:200]
                break

    # Technical params
    dn_mm = None
    m = _DN_RE.search(full_text)
    if m:
        dn_mm = int(m.group(1))

    bar_max = None
    bars = [float(b.replace(",", ".")) for b in _BAR_RE.findall(full_text) if float(b.replace(",", ".")) < 1000]
    if bars:
        bar_max = max(bars)

    temp_min, temp_max = None, None
    m = _TEMP_RE.search(full_text)
    if m:
        temp_min = int(m.group(1))
        temp_max = int(m.group(2))

    # Inner x outer diameter
    m = _DIAM_RE.search(full_text)
    if m and not dn_mm:
        dn_mm = float(m.group(1).replace(",", "."))

    # Material detection
    MATERIALS = {
        "силікон": "силіконовий", "silicone": "силіконовий",
        "ПВХ": "ПВХ", "PVC": "ПВХ",
        "поліуретан": "поліуретановий", "polyurethane": "поліуретановий",
        "тефлон": "тефлоновий (PTFE)", "PTFE": "тефлоновий (PTFE)",
        "гума": "гумовий", "rubber": "гумовий",
        "нержавіюч": "нержавіюча сталь", "stainless": "нержавіюча сталь",
        "латунь": "латунь", "brass": "латунь",
        "сталь": "сталь", "steel": "сталь",
        "поліамід": "поліамід", "nylon": "поліамід",
    }
    material = None
    ft_lower = full_text.lower()
    for kw, mat in MATERIALS.items():
        if kw.lower() in ft_lower:
            material = mat
            break

    # Description: medium-sized text, not too many digits
    desc_lines, seen = [], set()
    for s in spans:
        t = s["text"].strip()
        if len(t) < 25 or any(sk in t for sk in SKIP):
            continue
        digit_ratio = sum(1 for c in t if c.isdigit()) / len(t)
        if digit_ratio > 0.35:
            continue
        if 7 <= s["size"] <= 13:
            key = t[:40]
            if key not in seen:
                seen.add(key)
                desc_lines.append(t)
    description = " ".join(desc_lines)[:2000]

    return {
        "title": title,
        "subtitle": subtitle,
        "material": material,
        "dn_mm": dn_mm,
        "bar_max": bar_max,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "application": None,
        "certifications": None,
        "sku": None,
        "description": description,
    }


# ── Normalize and build attrs ─────────────────────────────────────────────────
def _build_attrs(extracted: dict, full_text: str) -> dict:
    """Build normalized attributes dict from extracted data."""
    attrs = {}

    if extracted.get("material"):
        attrs["Матеріал"] = str(extracted["material"])[:100]

    if extracted.get("dn_mm") is not None:
        dn = extracted["dn_mm"]
        attrs["DN"] = str(int(float(dn))) if float(dn) == int(float(dn)) else str(dn)
        attrs["d_вн_мм"] = attrs["DN"]

    if extracted.get("bar_max") is not None:
        attrs["Тиск_бар"] = str(extracted["bar_max"])

    if extracted.get("temp_min") is not None:
        attrs["Темп_мін"] = str(extracted["temp_min"])

    if extracted.get("temp_max") is not None:
        attrs["Темп_макс"] = str(extracted["temp_max"])

    if extracted.get("application"):
        attrs["Застосування"] = str(extracted["application"])[:100]

    if extracted.get("certifications"):
        cert_str = extracted["certifications"]
        if isinstance(cert_str, list):
            cert_str = "; ".join(cert_str)
        attrs["Сертифікати"] = str(cert_str)[:200]

    # Also extract from raw text as backup
    if "DN" not in attrs:
        m = _DN_RE.search(full_text)
        if m:
            attrs["DN"] = m.group(1)
            attrs["d_вн_мм"] = m.group(1)

    if "Тиск_бар" not in attrs:
        bars = [float(b.replace(",", ".")) for b in _BAR_RE.findall(full_text)
                if float(b.replace(",", ".")) < 1000]
        if bars:
            attrs["Тиск_бар"] = str(max(bars))

    if "Темп_мін" not in attrs or "Темп_макс" not in attrs:
        m = _TEMP_RE.search(full_text)
        if m:
            attrs.setdefault("Темп_мін", m.group(1))
            attrs.setdefault("Темп_макс", m.group(2))

    return attrs


def _build_search_text(
    title: str, subtitle: str, sku: str,
    attrs: dict, variants: List[Dict],
    description: str, all_skus: List[str],
    full_text: str = ""
) -> str:
    """Rich searchable text with all identifiers and technical values."""
    parts = [title or ""]
    if subtitle:
        parts.append(subtitle)
    if sku:
        parts.append(sku)
        parts.append(sku.replace("-", "").replace("_", ""))

    # Attributes
    for k, v in attrs.items():
        parts.append(f"{k} {v}")

    # DN searchable variants
    if attrs.get("DN"):
        d = attrs["DN"]
        parts.append(f"DN{d} DN {d} {d}мм {d}mm діаметр {d}")

    # Bar searchable variants
    if attrs.get("Тиск_бар"):
        b = attrs["Тиск_бар"]
        try:
            bi = str(int(float(b)))
            parts.append(f"{bi} bar {bi} бар {b} bar")
        except ValueError:
            pass

    # Temp
    if attrs.get("Темп_мін") and attrs.get("Темп_макс"):
        parts.append(f"{attrs['Темп_мін']}°C {attrs['Темп_макс']}°C температура")

    # ALL variant SKUs — plain text for ILIKE search
    sku_tokens = set()
    sku_keys = ["_sku", "Індекс", "Indeks", "Index", "SKU", "Артикул"]
    for var in variants:
        for k in sku_keys:
            if k in var and var[k]:
                v = str(var[k]).strip()
                if len(v) >= 4:
                    sku_tokens.add(v)
                    sku_tokens.add(v.replace("-", "").replace("_", "").replace("/", ""))
                    # Add individual parts for partial search
                    parts_of = v.split("-")
                    if len(parts_of) >= 3:
                        sku_tokens.add("-".join(parts_of[:2]))  # prefix

    # All SKUs from text
    for s in all_skus:
        sku_tokens.add(s)
        sku_tokens.add(s.replace("-", "").replace("_", ""))

    # Description
    if description:
        parts.append(description[:1000])

    # Certifications
    if attrs.get("Сертифікати"):
        parts.append(attrs["Сертифікати"])

    # Build final text
    joined = " | ".join(filter(None, parts))
    # Append all SKU tokens as plain space-separated text
    if sku_tokens:
        joined += " " + " ".join(sorted(sku_tokens))

    return joined[:12000]


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
    from sqlalchemy import text as sa_text

    use_haiku = bool(os.getenv("ANTHROPIC_API_KEY"))
    haiku_cost_estimate = 0  # in USD cents

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    saved = []
    all_page_texts = []

    for page_idx in range(page_count):
        page = doc[page_idx]
        pnum = page_idx + 1
        full_text = page.get_text("text").strip()

        if not full_text or len(full_text) < 30:
            continue

        all_page_texts.append(full_text)
        spans = _get_spans(page)
        variants, table_text = _extract_tables_text(page)
        image_bbox = _find_image(page)
        all_skus = _extract_all_skus(full_text, variants)
        certs = _extract_certifications(full_text)

        # ── Extract with Claude Haiku (primary) or regex (fallback) ──
        extracted = None
        if use_haiku:
            extracted = await _haiku_extract(full_text, table_text)
            if extracted:
                haiku_cost_estimate += 1  # ~$0.01 per 100 pages

        if not extracted:
            extracted = _regex_extract(spans, full_text)

        # Skip pages without a recognizable product title
        title = extracted.get("title") or ""
        if not title or len(title) < 2:
            continue

        # Override certifications with regex if Haiku missed them
        if not extracted.get("certifications") and certs:
            extracted["certifications"] = certs

        # Build normalized attributes
        attrs = _build_attrs(extracted, full_text)

        # SKU: from Haiku, then variants, then text scan
        sku = extracted.get("sku")
        if not sku and variants:
            for var in variants:
                for k in ["_sku", "Індекс", "Indeks", "SKU"]:
                    if k in var and var[k]:
                        sku = var[k]
                        break
                if sku:
                    break
        if not sku and all_skus:
            sku = all_skus[0]

        subtitle = extracted.get("subtitle") or ""
        description = extracted.get("description") or ""

        # Build rich search_text
        search_text = _build_search_text(
            title, subtitle, sku or "",
            attrs, variants, description,
            all_skus, full_text,
        )

        # Get embedding
        embedding = await _get_embedding(search_text[:3000])

        prod_data = dict(
            title=title[:512],
            subtitle=subtitle[:512],
            sku=(sku or "")[:128],
            description=description[:4000],
            certifications=extracted.get("certifications", "") or "",
            attributes=attrs,
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

                # Save embedding
                if embedding:
                    await db.execute(
                        sa_text("UPDATE products SET embedding = :emb WHERE id = :id"),
                        {"emb": str(embedding), "id": prod.id}
                    )
                    await db.commit()

                # Build ProductIndex for all SKUs
                try:
                    from services.indexer import index_product
                    await index_product(prod, db)
                    await db.commit()
                except Exception as ie:
                    logger.debug(f"Index product#{prod.id}: {ie}")

                saved.append(prod)
                method = "🤖 Haiku" if extracted and use_haiku else "📐 regex"
                logger.info(
                    f"Doc#{document_id} p{pnum} [{method}]: '{title[:40]}' "
                    f"DN={attrs.get('DN','?')} bar={attrs.get('Тиск_бар','?')} "
                    f"variants={len(variants)} skus={len(all_skus)} "
                    f"emb={'✓' if embedding else '✗'}"
                )

        except Exception as e:
            logger.error(f"Save product p{pnum}: {e}")

    doc.close()

    # Update section full_text
    if all_page_texts and section_id:
        full = "\n\n".join(all_page_texts)[:50000]
        try:
            async with AsyncSessionLocal() as db:
                sec = await db.get(Section, section_id)
                if sec:
                    if not sec.full_text:
                        sec.full_text = full
                    if not sec.description:
                        sec.description = all_page_texts[0][:500]
                    await db.commit()
        except Exception as e:
            logger.debug(f"Section full_text: {e}")

    if haiku_cost_estimate > 0:
        logger.info(f"Doc#{document_id}: ~{haiku_cost_estimate} Haiku calls (~${haiku_cost_estimate/10000:.4f})")

    return saved, page_count
