"""
Rule-based PDF parser for Tubes International product catalogs.
Handles 3 real table formats found in the catalog PDFs:

  FORMAT A — Cross-reference matrix (hidravlichni-adaptery style)
    rows = thread-dimension combos, cols = adapter types, cells = SKU
    e.g. TI-A101-02-02, TI-A116-04*, ...

  FORMAT B — Multi-material product list (camlock style)
    row 0 = category title, header row has "номенклатура (алюміній)" etc.
    cells may contain multiple SKUs separated by \n
    e.g. AC-A-050-A\nAC-A-050-AX

  FORMAT C — Simple product list (pneumatic/hose style)
    row 0 = product title, row 1 maybe series code, row 2 = col headers
    col "індекс"/"index" = SKU, rest = attributes
    e.g. MW-2001B01, CX-CP-03X06, PR-WTZ-08
"""

import re
import logging
from typing import List, Dict, Tuple, Any, Optional

import fitz  # PyMuPDF ≥ 1.23

logger = logging.getLogger("pdf_parser")


# ---------------------------------------------------------------------------
# SKU pattern — covers all article formats observed in the PDFs
# ---------------------------------------------------------------------------
_SKU_RE = re.compile(
    r'^(?:'
    r'[A-Z]{1,5}(?:[\-\/\.][A-Z0-9]+){1,6}'           # TI-A101-02-02, AC-A-050-SS, MW-2001B01
    r'|[A-Z]{1,4}[\-][A-Z]{1,4}[\-][A-Z0-9]{2,}'      # CX-CP-03X06, PR-WTZ-08 (letter-letter-mixed)
    r'|[A-Z0-9]{2,}[\-][A-Z0-9][\-A-Z0-9\.\/]{2,}'    # generic with at least one dash
    r')\*?$',
    re.IGNORECASE,
)

_SKIP_VALUES = {'-', '–', '—', '', 'none', 'nan', '-\n-', '–\n–'}

def _is_sku(val: str) -> bool:
    v = val.strip().rstrip('*')
    # Must start with a letter — rules out CAS numbers (e.g. "64-17-5") and REACH IDs
    return 3 <= len(v) <= 45 and v[0].isalpha() and bool(_SKU_RE.match(v))

def _clean_sku(val: str) -> str:
    """Remove trailing * and whitespace."""
    return val.strip().rstrip('*').strip()


# ---------------------------------------------------------------------------
# Header / title detection helpers
# ---------------------------------------------------------------------------
_INDEX_KW = {'індекс', 'indeks', 'index', 'артикул', 'article', 'sku',
             'код', 'code', 'ref', 'part', 'номенклатура'}
_SKIP_COL_KW = {'вага', 'weight', 'kg', 'кг', 'ціна', 'price'}
_DIM_KW = {'dn', 'd', 'dd', 'dw', 'l', 'mm', 'мм', 'діаметр', 'diameter',
           'тиск', 'pressure', 'бар', 'bar', 'pn', 'різьба', 'thread',
           'розмір', 'size', 'довжина', 'length', 'товщина', 'wall',
           'радіус', 'radius', 'зовнішній', 'внутрішній', 'з\'єднання'}
_MATERIAL_KW = {'алюміній', 'aluminium', 'aluminum', 'латунь', 'brass',
                'сталь', 'steel', 'aisi', 'поліпропілен', 'polypropylene',
                'пластик', 'plastic', 'нержавіюч'}
_NOMENKLATURA_KW = {'номенклатура', 'nomenclature', 'нрменклатура'}


def _row_text(row: List[str]) -> str:
    return ' '.join(row).lower()

def _has_skus_in_row(row: List[str]) -> bool:
    return any(_is_sku(c) for c in row if c.strip() not in _SKIP_VALUES)

def _count_skus(row: List[str]) -> int:
    return sum(1 for c in row if c.strip() not in _SKIP_VALUES and _is_sku(c))

def _is_dimension_header_row(row: List[str]) -> bool:
    txt = _row_text(row)
    return any(kw in txt for kw in _DIM_KW)

def _is_index_header_row(row: List[str]) -> bool:
    txt = _row_text(row)
    return any(kw in txt for kw in _INDEX_KW)


# ---------------------------------------------------------------------------
# Table format detection
# ---------------------------------------------------------------------------

def _detect_format(rows: List[List[str]]) -> str:
    """
    Returns 'A' (cross-matrix), 'B' (multi-material), 'C' (simple list),
    or 'SKIP' if the table has no useful product data.
    """
    if not rows or len(rows) < 3:
        return 'SKIP'

    flat = ' '.join(' '.join(r) for r in rows[:8]).lower()
    n_cols = max(len(r) for r in rows)

    # Check for 'номенклатура' keyword → Format B or A
    nomen_count = flat.count('номенклатур')
    if nomen_count >= 2:
        # Format A: cross-reference matrix — thread dimension rows
        # Identified by: multiple SKU columns AND dimension-like row headers
        sku_rows = sum(1 for r in rows[4:12] if _count_skus(r) >= 2)
        if sku_rows >= 2 and n_cols >= 8:
            return 'A'
        return 'B'

    # Format C: simple list with index column
    for r in rows[:5]:
        if _is_index_header_row(r):
            return 'C'

    # If rows contain SKUs → treat as C
    for r in rows[1:5]:
        if _has_skus_in_row(r):
            return 'C'

    return 'SKIP'


# ---------------------------------------------------------------------------
# Utility: extract page-level title from text above the table
# ---------------------------------------------------------------------------

def _get_page_title(page: Any) -> str:
    """Extract the largest/first text block as section title."""
    blocks = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']
    candidates = []
    for b in blocks:
        if b.get('type') != 0:
            continue
        for line in b.get('lines', []):
            for span in line.get('spans', []):
                txt = span.get('text', '').strip()
                size = span.get('size', 0)
                if txt and size >= 9:
                    candidates.append((size, txt))
    if not candidates:
        return ''
    # Return the largest-font text (likely page title)
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1][:200]


# ---------------------------------------------------------------------------
# FORMAT A parser — cross-reference matrix
# e.g. hidravlichni-adaptery: rows = thread dims, cols = adapter types
# ---------------------------------------------------------------------------

def _parse_format_a(rows: List[List[str]], page_title: str, page_num: int) -> List[Dict]:
    """
    Find all cells that are valid SKUs; attach thread-dimension attributes
    from the row's first two columns and product-type from the column group header.
    """
    products = []
    n_cols = len(rows[0]) if rows else 0

    # Find column group headers (appear in rows 0-5)
    # Each 'номенклатура' header spans a group of columns.
    # Row 0 often has the real category name; row 1 may have just 'номенклатура' —
    # use setdefault so the first (real) name wins over the generic keyword.
    col_type_names: Dict[int, str] = {}
    for ri, row in enumerate(rows[:8]):
        for ci, cell in enumerate(row):
            if cell and any(kw in cell.lower() for kw in _NOMENKLATURA_KW):
                col_type_names.setdefault(ci, cell.replace('\n', ' ').strip())
            elif cell and not any(c in cell for c in ['[', '"', '°', '/']):
                # Could be adapter type name (e.g., "GZ BSP (конус 60°)")
                if len(cell) > 8 and ci > 1:
                    col_type_names.setdefault(ci, cell.replace('\n', ' ').strip())

    # Find data rows (contain real SKUs in non-first columns)
    data_start = 0
    for ri, row in enumerate(rows):
        if _count_skus(row) >= 1 and ri >= 3:
            data_start = ri
            break

    seen = set()
    for row in rows[data_start:]:
        dim1 = row[0].strip() if len(row) > 0 else ''
        dim2 = row[1].strip() if len(row) > 1 else ''
        attrs_base = {}
        if dim1:
            attrs_base['Розмірність 1'] = dim1
        if dim2 and dim2 != dim1:
            attrs_base['Розмірність 2'] = dim2

        for ci in range(2, len(row)):
            cell = row[ci].strip()
            if not cell or cell in _SKIP_VALUES:
                continue
            # Cells may contain multiple SKUs separated by newline
            for raw_sku in cell.split('\n'):
                raw_sku = raw_sku.strip()
                if not raw_sku or raw_sku in _SKIP_VALUES:
                    continue
                if not _is_sku(raw_sku):
                    continue
                sku = _clean_sku(raw_sku)
                if sku in seen:
                    continue
                seen.add(sku)

                col_type = col_type_names.get(ci, '')
                # If col_type is just the generic keyword, strip it
                if col_type and all(kw in col_type.lower() for kw in ['номенклатур']):
                    # Keep only non-keyword suffix (e.g. "номенклатура (AISI 316)" → "AISI 316")
                    suffix = re.sub(r'номенклатур[а-яА-Я]*\s*', '', col_type, flags=re.I).strip('() ')
                    col_type = suffix

                title = col_type or page_title or 'Артикул'
                if dim1 and dim2:
                    title = f"{title} {dim1}×{dim2}".strip()

                products.append({
                    'title': title[:512],
                    'sku': sku[:128],
                    'description': '',
                    'attributes': {**attrs_base, 'Тип': col_type} if col_type else attrs_base,
                    'variants': [],
                    'page_number': page_num,
                })

    return products


# ---------------------------------------------------------------------------
# FORMAT B parser — multi-material product list
# e.g. camlock: columns are (DN, з'єднання, d, різьба, SKU_alu, SKU_brass, ...)
# ---------------------------------------------------------------------------

def _parse_format_b(rows: List[List[str]], page_title: str, page_num: int) -> List[Dict]:
    products = []

    # Find category title (first non-empty row, single cell)
    category = page_title
    for row in rows[:3]:
        non_empty = [c for c in row if c.strip()]
        if len(non_empty) == 1 and len(non_empty[0]) > 6:
            category = non_empty[0].replace('\n', ' ').strip()
            break

    # Find header row: contains "DN", "різьба", "номенклатура", dimension keywords
    header_row_idx = None
    for ri, row in enumerate(rows[:8]):
        txt = _row_text(row)
        if ('номенклатур' in txt or 'індекс' in txt or 'index' in txt) and (
            'dn' in txt or 'різьба' in txt or 'thread' in txt or 'діаметр' in txt or 'мм' in txt
        ):
            header_row_idx = ri
            break

    if header_row_idx is None:
        # Try to find it by SKU presence
        for ri, row in enumerate(rows[1:6], 1):
            if _has_skus_in_row(row):
                header_row_idx = ri - 1
                break

    if header_row_idx is None:
        return []

    # Merge multi-row headers (sometimes split across 2-3 rows)
    headers = [''] * len(rows[header_row_idx])
    for ri in range(header_row_idx, min(header_row_idx + 3, len(rows))):
        row = rows[ri]
        for ci, cell in enumerate(row):
            if ci < len(headers) and cell.strip():
                if not headers[ci]:
                    headers[ci] = cell.strip()
                else:
                    headers[ci] += ' ' + cell.strip()
    headers = [h.replace('\n', ' ').strip() for h in headers]

    # Classify columns: dim cols vs sku cols
    dim_cols: List[Tuple[int, str]] = []   # (col_idx, col_name)
    sku_cols: List[Tuple[int, str]] = []   # (col_idx, material_label)
    for ci, h in enumerate(headers):
        h_lo = h.lower()
        if any(kw in h_lo for kw in _NOMENKLATURA_KW):
            # Extract material from header e.g. "номенклатура (алюміній)"
            mat = re.sub(r'номенклатур[а-я]*\s*', '', h, flags=re.I).strip('() ')
            sku_cols.append((ci, mat or 'SKU'))
        elif any(kw in h_lo for kw in _INDEX_KW):
            sku_cols.append((ci, 'SKU'))
        elif h and not any(kw in h_lo for kw in _SKIP_COL_KW):
            dim_cols.append((ci, h))

    data_start = header_row_idx + 1
    # Skip sub-header rows (e.g., "[мм]", "[дюйми]")
    while data_start < len(rows):
        row_txt = _row_text(rows[data_start])
        if any(unit in row_txt for unit in ['[мм]', '[mm]', '[дюйм', '[bar]', '[m]', '[kg']):
            data_start += 1
        else:
            break

    seen = set()
    for row in rows[data_start:]:
        if not any(c.strip() for c in row):
            continue

        # Build base attributes from dimension columns
        attrs_base = {}
        for ci, col_name in dim_cols:
            if ci < len(row) and row[ci].strip():
                attrs_base[col_name] = row[ci].strip()

        # Extract SKUs from SKU columns
        for ci, material in sku_cols:
            if ci >= len(row):
                continue
            cell = row[ci].strip()
            if not cell or cell in _SKIP_VALUES:
                continue

            # Cell may have multiple SKUs split by newline
            raw_skus = [s.strip() for s in cell.split('\n') if s.strip()]
            for raw_sku in raw_skus:
                if raw_sku in _SKIP_VALUES:
                    continue
                if not _is_sku(raw_sku):
                    continue
                sku = _clean_sku(raw_sku)
                if sku in seen:
                    continue
                seen.add(sku)

                attrs = dict(attrs_base)
                if material and material != 'SKU':
                    attrs['Матеріал'] = material

                # Build title from category + dims
                dim_str = ', '.join(f"{k}: {v}" for k, v in list(attrs_base.items())[:3])
                title = category
                if dim_str:
                    title = f"{category} ({dim_str})"

                products.append({
                    'title': title[:512],
                    'sku': sku[:128],
                    'description': '',
                    'attributes': attrs,
                    'variants': [],
                    'page_number': page_num,
                })

    return products


# ---------------------------------------------------------------------------
# FORMAT C parser — simple product list
# e.g. pneumatic fittings, hoses: row0=title, row1=series, row2=headers, rows3+=data
# ---------------------------------------------------------------------------

def _parse_format_c(rows: List[List[str]], page_title: str, page_num: int) -> List[Dict]:
    products = []

    # Extract category title (first non-empty single-value row)
    category = page_title
    series_code = ''
    for row in rows[:4]:
        non_empty = [c.strip() for c in row if c.strip()]
        if len(non_empty) == 1:
            txt = non_empty[0]
            if re.match(r'^R\s*\d+', txt) or re.match(r'^[A-Z]\s*\d+$', txt):
                series_code = txt
            elif len(txt) > 6:
                category = txt.replace('\n', ' ')

    if series_code and category:
        category = f"{category} ({series_code})"

    # Find header row — index column takes priority over dimension keywords
    header_row_idx = None
    # Priority 1: row explicitly containing 'індекс'/'index'/'артикул' etc.
    for ri, row in enumerate(rows[:10]):
        if _is_index_header_row(row):
            header_row_idx = ri
            break
    # Priority 2: any dimension-keyword row (e.g. multi-row header tables)
    if header_row_idx is None:
        for ri, row in enumerate(rows[:6]):
            if _is_dimension_header_row(row):
                header_row_idx = ri
                break
    # Fallback: find first row where the following row has SKUs
    if header_row_idx is None:
        for ri in range(len(rows) - 1):
            if _has_skus_in_row(rows[ri + 1]):
                header_row_idx = ri
                break

    if header_row_idx is None:
        return []

    # Build headers (may span multiple rows)
    raw_headers = list(rows[header_row_idx])
    for ri in range(header_row_idx + 1, min(header_row_idx + 3, len(rows))):
        next_row = rows[ri]
        if _has_skus_in_row(next_row):
            break
        all_units = all(
            not c.strip() or re.match(r'^\[', c.strip()) for c in next_row if c.strip()
        )
        if all_units:
            # Merge unit row into headers
            for ci, cell in enumerate(next_row):
                if ci < len(raw_headers) and cell.strip():
                    raw_headers[ci] += ' ' + cell.strip()
            header_row_idx += 1

    headers = [h.replace('\n', ' ').strip() for h in raw_headers]

    # Find SKU column
    sku_col = -1
    for ci, h in enumerate(headers):
        if any(kw in h.lower() for kw in _INDEX_KW):
            sku_col = ci
            break
    if sku_col == -1:
        # Guess: first column that has SKU-looking values in data
        for ci in range(len(headers)):
            sku_vals = sum(
                1 for row in rows[header_row_idx + 1: header_row_idx + 6]
                if ci < len(row) and _is_sku(row[ci])
            )
            if sku_vals >= 2:
                sku_col = ci
                break
    if sku_col == -1:
        return []

    # Attribute columns (everything except SKU and weight/price)
    attr_cols: List[Tuple[int, str]] = [
        (ci, h) for ci, h in enumerate(headers)
        if ci != sku_col and h and not any(kw in h.lower() for kw in _SKIP_COL_KW)
    ]

    seen = set()
    for row in rows[header_row_idx + 1:]:
        if sku_col >= len(row):
            continue
        cell = row[sku_col].strip()
        # Some cells have multiple SKUs (e.g., "MW-2001B01\nMW-2001A01")
        raw_skus = [s.strip() for s in cell.split('\n') if s.strip()]
        if not raw_skus:
            continue

        attrs = {}
        for ci, col_name in attr_cols:
            if ci < len(row) and row[ci].strip():
                attrs[col_name] = row[ci].strip().replace('\n', ' ')

        for raw_sku in raw_skus:
            if raw_sku in _SKIP_VALUES or not _is_sku(raw_sku):
                continue
            sku = _clean_sku(raw_sku)
            if sku in seen:
                continue
            seen.add(sku)

            # Build title from category + first 2 attrs
            dim_str = ', '.join(f"{k}: {v}" for k, v in list(attrs.items())[:2] if v)
            title = category
            if dim_str:
                title = f"{category} — {dim_str}"

            products.append({
                'title': title[:512],
                'sku': sku[:128],
                'description': '',
                'attributes': attrs,
                'variants': [],
                'page_number': page_num,
            })

    return products


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_pdf(
    pdf_bytes: bytes,
    doc_id: int,
    section_id: int,
    category_id: int,
) -> Tuple[List[Dict], int]:
    """
    Parse a Tubes International product catalog PDF without any LLM.
    Returns (products_list, page_count).
    """
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype='pdf')
        page_count = len(pdf)
        all_products: List[Dict] = []
        seen_skus: set = set()

        for page_num, page in enumerate(pdf, start=1):
            try:
                page_title = _get_page_title(page)
                tabs = page.find_tables()

                for tbl in tabs.tables:
                    rows = tbl.extract()
                    if not rows:
                        continue

                    # Normalise: all cells to str, strip
                    rows = [[str(c or '').strip() for c in row] for row in rows]

                    fmt = _detect_format(rows)
                    if fmt == 'SKIP':
                        continue

                    if fmt == 'A':
                        prods = _parse_format_a(rows, page_title, page_num)
                    elif fmt == 'B':
                        prods = _parse_format_b(rows, page_title, page_num)
                    else:
                        prods = _parse_format_c(rows, page_title, page_num)

                    # De-duplicate across pages
                    for p in prods:
                        if p['sku'] and p['sku'] in seen_skus:
                            continue
                        if p['sku']:
                            seen_skus.add(p['sku'])
                        p['section_id'] = section_id
                        p['category_id'] = category_id
                        all_products.append(p)

                    if prods:
                        logger.debug(
                            f"Doc#{doc_id} p{page_num} fmt={fmt}: "
                            f"{len(prods)} products from table {rows[0][0][:30]!r}"
                        )

            except Exception as exc:
                logger.warning(f"Doc#{doc_id} p{page_num}: {exc}")
                continue

        pdf.close()
        logger.info(f"Doc#{doc_id}: {len(all_products)} products / {page_count} pages")
        return all_products, page_count

    except Exception as exc:
        logger.error(f"Doc#{doc_id}: PDF parse error: {exc}")
        return [], 0
