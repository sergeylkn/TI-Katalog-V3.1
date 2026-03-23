"""
Rule-based PDF parser for industrial product catalogs.
Uses PyMuPDF table detection + text heuristics. No LLM required.
"""
import re
import logging
from typing import List, Dict, Tuple, Any

import fitz  # PyMuPDF

logger = logging.getLogger("pdf_parser")

# --- SKU detection -----------------------------------------------------------

_SKU_RE = re.compile(
    r'^(?:'
    r'[A-Z]{1,5}[\-\/]?\d{2,}[\-\.\/]?[A-Z0-9\-\.\/]{0,25}'   # ABC-1234-XX
    r'|\d{5,12}'                                                   # 1234567
    r'|[A-Z0-9]{2,}[\-\/][A-Z0-9][\-A-Z0-9\/\.]{2,}'            # AB/123-X
    r')$',
    re.IGNORECASE,
)

def _is_sku(val: str) -> bool:
    v = val.strip()
    return 3 <= len(v) <= 40 and bool(_SKU_RE.match(v))


# --- Header detection --------------------------------------------------------

_HEADER_KW = {
    # UA
    'артикул', 'індекс', 'назва', 'опис', 'розмір', 'тип', 'dn', 'pn', 'мм',
    # RU
    'артикул', 'индекс', 'наименование', 'описание', 'размер',
    # EN
    'article', 'index', 'sku', 'code', 'ref', 'name', 'description',
    'type', 'size', 'mm', 'part', 'series', 'model',
}

def _is_header_row(cells: List[str]) -> bool:
    joined = ' '.join(cells).lower()
    return sum(1 for kw in _HEADER_KW if kw in joined) >= 2


# --- Column role detection ---------------------------------------------------

_SKU_COL_KW   = {'артикул', 'article', 'sku', 'код', 'code', 'індекс', 'indeks',
                  'index', 'ref', 'part', 'арт', 'art'}
_TITLE_COL_KW = {'назва', 'name', 'description', 'опис', 'найменування',
                  'тип', 'type', 'номенклатура', 'серія', 'series', 'model', 'модель'}

def _find_col(headers: List[str], keywords: set, default: int) -> int:
    for i, h in enumerate(headers):
        if any(kw in h.lower() for kw in keywords):
            return i
    return min(default, len(headers) - 1)


# --- Table parser ------------------------------------------------------------

def _parse_table(table: Any, page_num: int) -> List[Dict]:
    """Convert one PyMuPDF Table object into a list of product dicts."""
    rows = table.extract()
    if not rows or len(rows) < 2:
        return []

    headers = [str(c or '').strip() for c in rows[0]]
    sku_col   = _find_col(headers, _SKU_COL_KW,   0)
    title_col = _find_col(headers, _TITLE_COL_KW, 1)

    products = []
    for row in rows[1:]:
        cells = [str(c or '').strip() for c in row]
        if not any(cells):
            continue
        if _is_header_row(cells):          # repeated header mid-table
            headers = cells
            sku_col   = _find_col(headers, _SKU_COL_KW,   0)
            title_col = _find_col(headers, _TITLE_COL_KW, 1)
            continue

        sku   = cells[sku_col]   if sku_col   < len(cells) else ''
        title = cells[title_col] if title_col < len(cells) else ''

        if not title:
            title = sku
        if not title:
            title = next((c for c in cells if c), '')
        if not title:
            continue

        attrs = {
            headers[i]: cells[i]
            for i in range(len(headers))
            if i not in (sku_col, title_col) and i < len(cells) and headers[i] and cells[i]
        }

        products.append({
            'title':       title[:512],
            'sku':         sku[:128],
            'description': '',
            'attributes':  attrs,
            'variants':    [],
            'page_number': page_num,
        })

    return products


# --- Text-block fallback -----------------------------------------------------

def _parse_text(page: Any, page_num: int) -> List[Dict]:
    """
    Heuristic fallback when no tables found.
    Groups text blocks: SKU line → title line → attribute lines.
    """
    products: List[Dict] = []
    blocks = page.get_text('blocks')  # (x0,y0,x1,y1,text,block_no,block_type)

    cur_sku   = ''
    cur_title = ''
    cur_attrs: Dict[str, str] = {}

    def _flush():
        nonlocal cur_sku, cur_title, cur_attrs
        if cur_title or cur_sku:
            products.append({
                'title':       (cur_title or cur_sku)[:512],
                'sku':         cur_sku[:128],
                'description': '',
                'attributes':  cur_attrs,
                'variants':    [],
                'page_number': page_num,
            })
        cur_sku, cur_title, cur_attrs = '', '', {}

    for block in blocks:
        raw: str = block[4] if len(block) > 4 else ''
        for line in (l.strip() for l in raw.split('\n') if l.strip()):
            if _is_sku(line):
                _flush()
                cur_sku = line
            elif cur_sku and not cur_title:
                cur_title = line
            elif cur_sku:
                if ':' in line:
                    k, _, v = line.partition(':')
                    cur_attrs[k.strip()[:64]] = v.strip()[:256]

    _flush()
    return products


# --- Main entry point --------------------------------------------------------

def parse_pdf(
    pdf_bytes: bytes,
    doc_id: int,
    section_id: int,
    category_id: int,
) -> Tuple[List[Dict], int]:
    """
    Parse product catalog PDF without any LLM.
    Returns (products_list, page_count).
    Each product dict contains: title, sku, description,
    attributes, variants, page_number, section_id, category_id.
    """
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype='pdf')
        page_count = len(pdf)
        all_products: List[Dict] = []

        for page_num, page in enumerate(pdf, start=1):
            try:
                page_products: List[Dict] = []

                tabs = page.find_tables()
                if tabs.tables:
                    for tbl in tabs.tables:
                        page_products.extend(_parse_table(tbl, page_num))

                # If tables gave nothing, use text fallback
                if not page_products:
                    page_products = _parse_text(page, page_num)

                for p in page_products:
                    p['section_id']  = section_id
                    p['category_id'] = category_id

                all_products.extend(page_products)

                if page_products:
                    logger.debug(
                        f"Doc#{doc_id} p{page_num}: "
                        f"{'table' if tabs.tables else 'text'} → {len(page_products)} products"
                    )

            except Exception as exc:
                logger.warning(f"Doc#{doc_id} p{page_num}: {exc}")
                continue

        pdf.close()
        logger.info(f"Doc#{doc_id}: {len(all_products)} products from {page_count} pages")
        return all_products, page_count

    except Exception as exc:
        logger.error(f"Doc#{doc_id}: PDF parse error: {exc}")
        return [], 0
