"""
PDF Extractor v5.2
- Pure regex, $0 import cost
- Normalized technical attributes (bar, DN, temp, diameter)
- Rich search_text with all searchable values
- OpenAI embeddings after save
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

# ── Labels to search for in PDF text ──────────────────────────────────────────
SPEC_LABELS = [
    "Матеріал шлангу", "Внутрішній шар", "Зовнішній шар", "Середній шар",
    "Армування", "Робоча температура", "Робоча темп", "Температура",
    "Матеріал", "Тиск", "Робочий тиск", "Вакуум", "Застосування",
    "Стандарт", "Колір", "Довжина", "Маса", "Вага",
]

SKU_PATTERN = re.compile(r'\b([A-Z]{2,6}[-_][A-Z0-9][-A-Z0-9/]{3,30})\b')
CERT_PATTERN = re.compile(
    r'(?:1935/2004|10/2011|2023/2006|FDA\s*21|ISO\s*\d+|EN\s*\d+|DIN\s*\d+|'
    r'RoHS|REACH|WRAS|UL94|MSHA)[^\n]{0,120}',
    re.IGNORECASE
)

# ── Technical value extraction patterns ───────────────────────────────────────
# bar/pressure
_BAR_RE   = re.compile(r'(\d+[\.,]?\d*)\s*(?:bar|BAR|бар|MPa)', re.I)
# temperature ranges like "-20°C do +60°C" or "-20 +60"
_TEMP_RE  = re.compile(r'([+-]?\d+)\s*°?\s*[Cc°]\s*(?:do|до|[+~–-])\s*([+-]?\d+)\s*°?\s*[Cc°]', re.I)
_TEMP1_RE = re.compile(r'(?:до|до\s*\+?|max\.?\s*)([+-]?\d+)\s*°?\s*[Cc]', re.I)
# DN
_DN_RE    = re.compile(r'\bDN\s*(\d+)\b', re.I)
# diameter inner x outer: 25x35 or 25/35 mm
_DIAM_RE  = re.compile(r'\b(\d+[\.,]?\d*)\s*[xX×]\s*(\d+[\.,]?\d*)\s*mm', re.I)
_DIAM1_RE = re.compile(r'\bø?\s*(\d+[\.,]?\d*)\s*mm\b', re.I)


def _normalize_attrs(raw_attrs: Dict[str, str], full_text: str) -> Dict[str, str]:
    """
    Enhance raw attributes with normalized technical values extracted from full page text.
    Always adds: bar, temp_min, temp_max, dn, d_inner, d_outer where found.
    """
    attrs = dict(raw_attrs)

    # Pressure in bar
    bars = _BAR_RE.findall(full_text)
    if bars:
        # Take the most common / largest reasonable value
        bar_vals = [float(b.replace(",", ".")) for b in bars if float(b.replace(",","."))<1000]
        if bar_vals:
            attrs["Тиск_бар"] = str(max(bar_vals))

    # Temperature range
    m = _TEMP_RE.search(full_text)
    if m:
        attrs["Темп_мін"] = m.group(1)
        attrs["Темп_макс"] = m.group(2)
    else:
        m1 = _TEMP1_RE.search(full_text)
        if m1:
            attrs["Темп_макс"] = m1.group(1)

    # DN = Номінальний діаметр = внутрішній діаметр шланга
    dns = _DN_RE.findall(full_text)
    if dns:
        attrs["DN"] = dns[0]
        attrs["d_вн_мм"] = dns[0]   # DN = внутрішній діаметр

    # Explicit inner x outer diameters e.g. 25x35mm
    m = _DIAM_RE.search(full_text)
    if m:
        attrs["d_вн_мм"]  = m.group(1)   # inner = left number
        attrs["d_зовн_мм"] = m.group(2)   # outer = right number
        if not attrs.get("DN"):
            attrs["DN"] = m.group(1)       # DN ≈ inner diameter
    else:
        diams = _DIAM1_RE.findall(full_text)
        if diams and not attrs.get("d_вн_мм"):
            attrs["d_вн_мм"] = diams[0]

    return attrs


def _build_search_text(title, subtitle, sku, attrs, variants, description, full_text="") -> str:
    """
    Denormalized searchable text. Includes:
    - All title/subtitle/sku
    - All attribute values (including normalized bar/DN/temp)
    - All variant SKUs and key values
    - Key numbers extracted from description
    """
    parts = [title or ""]
    if subtitle:  parts.append(subtitle)
    if sku:       parts.append(sku)

    # All attribute values
    for k, v in (attrs or {}).items():
        parts.append(f"{k} {v}")

    # Variant SKUs — EVERY index must be searchable
    SKU_KEYS = ["_sku","Індекс","Indeks","Index","index","Article","SKU","Артикул","КОД","код","Part No","PartNo"]
    DN_KEYS  = ["DN","d вн.","d вн","Dw","ID","d_in","d вн.(мм)","Ду","di","D внутр","внутр.д"]
    
    for var in (variants or []):
        # Extract and add ALL possible SKU/index values
        for sk in SKU_KEYS:
            if sk in var and var[sk] and str(var[sk]).strip():
                vsku = str(var[sk]).strip()
                parts.append(vsku)
                # Also add without dashes for fuzzy match
                parts.append(vsku.replace("-","").replace("_",""))
        
        # Extract DN/inner diameter values
        for dk in DN_KEYS:
            if dk in var and var[dk] and str(var[dk]).strip():
                vdn = str(var[dk]).strip()
                try:
                    dn_int = int(float(vdn))
                    parts.append(f"DN{dn_int} {dn_int}мм {dn_int}mm")
                except ValueError:
                    pass
                break
        
        # Add all numeric values for technical matching
        for vk, vv in var.items():
            if vk == "_sku" or vk in SKU_KEYS: continue
            if vv and re.search(r'\d', str(vv)):
                parts.append(str(vv))

    if description: parts.append(description[:800])

    # Add key numeric patterns from full page text
    if full_text:
        # Extract all bar values
        for b in _BAR_RE.findall(full_text):
            parts.append(f"{b} bar бар")
        # DN = внутрішній діаметр — додаємо всі варіанти написання
        for d in _DN_RE.findall(full_text):
            parts.append(f"DN{d} DN {d} {d}мм {d}mm внутрішній діаметр {d}")
        # Temperature
        m = _TEMP_RE.search(full_text)
        if m:
            parts.append(f"{m.group(1)}°C {m.group(2)}°C температура")

    # Add all variant SKUs also as plain space-separated tokens at the end
    # This ensures ILIKE '%TI-A101-08-08%' always finds them
    sku_tokens = []
    SKU_KEYS_B = ["_sku","Індекс","Indeks","Index","SKU","Артикул"]
    for var in (variants or []):
        for sk in SKU_KEYS_B:
            if sk in var and var[sk] and str(var[sk]).strip():
                v = str(var[sk]).strip()
                if len(v) >= 4:
                    sku_tokens.append(v)
                    sku_tokens.append(v.replace("-","").replace("_","").replace("/",""))

    joined = " | ".join(filter(None, parts))
    if sku_tokens:
        joined += " " + " ".join(sku_tokens)
    return joined[:10000]


# ── OpenAI embedding ──────────────────────────────────────────────────────────
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


# ── PDF page helpers ──────────────────────────────────────────────────────────
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


SKIP_TITLES = {"www.", "tubes-international", "Шланги для промисловості",
               "Силова гідравліка", "Промислова арматура", "ПРОМИСЛОВА АРМАТУРА",
               "Пневматика", "ПНЕВМАТИКА", "TI-Katalog"}


def _find_model_name(spans: List[Dict]) -> Optional[str]:
    candidates = []
    for s in spans:
        t = s["text"].strip()
        if len(t) < 2 or len(t) > 100:
            continue
        if any(sk in t for sk in SKIP_TITLES):
            continue
        upper_ratio = sum(1 for c in t if c.isupper()) / max(len(t), 1)
        score = 0
        if s["size"] >= 12:  score += 3
        if s["bold"]:         score += 2
        if upper_ratio > 0.3: score += 2
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
    lines, seen = [], set()
    for s in spans:
        t = s["text"].strip()
        if len(t) < 20: continue
        if any(sk in t for sk in ["www.", "tubes-international"]): continue
        digit_ratio = sum(1 for c in t if c.isdigit()) / len(t)
        if digit_ratio > 0.4: continue
        if 7 <= s["size"] <= 12:
            key = t[:40]
            if key not in seen:
                seen.add(key); lines.append(t)
    return " ".join(lines)[:4000]


def _extract_certifications(spans: List[Dict]) -> Optional[str]:
    full = " ".join(s["text"] for s in spans)
    matches = CERT_PATTERN.findall(full)
    if not matches: return None
    return max(matches, key=len)[:600]


def _extract_variants(page) -> List[Dict]:
    variants = []
    try:
        import pandas as pd
        tabs = page.find_tables()
        for tab in tabs.tables:
            df = tab.to_pandas()
            if df is None or df.empty: continue
            first_col = df.iloc[:, 0].astype(str)
            if not first_col.str.match(r'[A-Z]{2,}[-_]').any(): continue
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

        image_bbox    = _find_product_image(page)
        subtitle      = _find_subtitle(spans, model_name)
        raw_specs     = _extract_specs(spans)
        description   = _extract_description(spans)
        certifications = _extract_certifications(spans)
        variants      = _extract_variants(page)

        # Normalize with full page text for bar/DN/temp
        attrs = _normalize_attrs(raw_specs, page_raw)

        # SKU
        sku = None
        if variants:
            sku = variants[0].get("_sku") or variants[0].get("Індекс")
        if not sku:
            m = SKU_PATTERN.search(" ".join(s["text"] for s in spans))
            sku = m.group(1) if m else None

        search_text = _build_search_text(
            model_name, subtitle, sku, attrs, variants, description, page_raw
        )

        embedding = await _get_embedding(search_text[:2000])

        prod_data = dict(
            title=model_name[:512],
            subtitle=(subtitle or "")[:512],
            sku=(sku or "")[:128],
            description=description,
            certifications=certifications,
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
                        pass

                # Build search index for all variant SKUs
                try:
                    from services.indexer import index_product
                    await index_product(prod, db)
                    await db.commit()
                except Exception as ie:
                    logger.debug(f"Index product#{prod.id}: {ie}")

                saved.append(prod)
                logger.info(
                    f"Doc#{document_id} p{pnum}: '{model_name}' "
                    f"attrs={list(attrs.keys())[:4]} "
                    f"variants={len(variants)} "
                    f"img={'✓' if image_bbox else '✗'} "
                    f"emb={'✓' if embedding else '✗'}"
                )
        except Exception as e:
            logger.error(f"Save product p{pnum}: {e}")

    doc.close()

    # Update section full_text
    if all_page_text and section_id:
        full = "\n\n".join(all_page_text)[:50000]
        try:
            async with AsyncSessionLocal() as db:
                sec = await db.get(Section, section_id)
                if sec and not sec.full_text:
                    sec.full_text = full
                    if not sec.description:
                        sec.description = "\n".join(all_page_text[:2])[:1000]
                    await db.commit()
        except Exception as e:
            logger.debug(f"Section full_text: {e}")

    return saved, page_count
