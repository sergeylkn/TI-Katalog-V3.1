"""
Парсер PDF-каталогов Tubes International без использования LLM.
Обрабатывает 3 формата таблиц, обнаруженных в реальных PDF-файлах:

  ФОРМАТ A — Матрица перекрёстных ссылок (стиль hidravlichni-adaptery)
    строки = комбинации резьбовых размеров, столбцы = типы адаптеров, ячейки = SKU
    пример: TI-A101-02-02, TI-A116-04*, ...

  ФОРМАТ B — Список товаров с несколькими материалами (стиль camlock)
    строка 0 = название категории, заголовок содержит "номенклатура (алюміній)" и т.д.
    ячейки могут содержать несколько SKU, разделённых \n
    пример: AC-A-050-A\nAC-A-050-AX

  ФОРМАТ C — Простой список товаров (пневматика/шланги)
    строка 0 = название товара, строка 1 = код серии, строка 2 = заголовки столбцов
    столбец "індекс"/"index" = SKU, остальные = атрибуты
    пример: MW-2001B01, CX-CP-03X06, PR-WTZ-08
"""

import re
import logging
from typing import List, Dict, Tuple, Any, Optional, Set

import fitz  # PyMuPDF ≥ 1.23

logger = logging.getLogger("pdf_parser")


# ---------------------------------------------------------------------------
# Извлечение описания и сертификатов со страницы
# ---------------------------------------------------------------------------

# Паттерны сертификатов и стандартов, встречающихся в каталогах Tubes International
_CERT_RE = re.compile(
    r'(?:'
    r'FDA\s+\d+\s+CFR[\s\d\.]+(?:\d{4,7})?|'           # FDA 21 CFR 175.300
    r'(?:EC|EU)\s+(?:Regulation\s+)?\d{3,}/\d{4}[^,\s]*|'  # EC 1935/2004
    r'\d{4}/\d{4}/(?:EC|EU)\b|'                          # 1935/2004/EC
    r'10/\d{4}/EU\b|'                                    # 10/2011/EU
    r'2023/\d{4}/EC\b|'
    r'ISO\s+\d{4,}(?:[:-]\d+)?|'                        # ISO 4628-2
    r'EN\s+\d{4,}(?:[:-]\d+)?|'                         # EN 14420-7
    r'DIN\s+\d{4,}|'                                    # DIN 20022
    r'NSF(?:/ANSI)?(?:\s*\d+)?|'                        # NSF/ANSI 61
    r'ATEX(?:\s+II\s+[\w\s]+)?|'                        # ATEX
    r'REACH\b|'
    r'RoHS\b|'
    r'3-A\s+\d+|'
    r'USP\s+Class\s+VI|'
    r'DNV[-\s]?GL|'
    r'Lloyd\'?s\s+Register|'
    r'WRAS\b|'
    r'KTW\b|'
    r'W-\d{3}\b|'
    r'DVGW\b|'
    r'GMP\b|'
    r'CE\b(?!\s*(?:RT|FE|ment|ramic|nter|ll|N|D))'     # CE Mark (не слова типа "center")
    r')',
    re.IGNORECASE
)

_MIN_DESCRIPTION_LEN = 40  # минимум символов для текстового блока описания


def _extract_certs_from_text(text: str) -> str:
    """Извлекает уникальные упоминания сертификатов из произвольного текста."""
    found = []
    seen: Set[str] = set()
    for m in _CERT_RE.finditer(text):
        val = re.sub(r'\s+', ' ', m.group(0).strip())
        key = val.upper()
        if key not in seen and len(key) >= 2:
            seen.add(key)
            found.append(val)
    return '; '.join(found)


def _get_page_text_and_certs(page: Any, tables) -> Tuple[str, str]:
    """
    Извлекает описательный текст и сертификаты со страницы.

    Алгоритм:
    1. Определяет Y-координату начала первой таблицы С данными (SKU-ячейки).
    2. Собирает текстовые блоки в диапазоне y ∈ [65, first_data_y0).
    3. Из НЕ-данных таблиц (sku=0) — тоже собирает текст для поиска сертификатов.
    4. Возвращает (description, certifications).
    """
    page_h = page.rect.height

    # Определяем Y начала первой data-таблицы
    data_table_y0 = page_h
    for tbl in tables:
        rows = tbl.extract()
        if not rows:
            continue
        rows_s = [[str(c or '').strip() for c in row] for row in rows]
        if any(_is_sku(c) for row in rows_s for c in row if c):
            data_table_y0 = min(data_table_y0, tbl.bbox[1])
            break

    # Сбор текстовых блоков страницы
    description_parts = []
    cert_text_parts = []

    for b in page.get_text('blocks'):
        if b[6] != 0:  # не текстовый блок
            continue
        bx0, by0, bx1, by1, btext = b[0], b[1], b[2], b[3], b[4]
        btext = btext.strip()
        if not btext:
            continue
        # Пропускаем шапку (лого, колонтитулы) и подвал
        if by0 < _LOGO_MAX_Y0 or by0 > page_h * _FOOTER_Y_RATIO:
            continue

        cert_text_parts.append(btext)

        # Описание — только ДО первой data-таблицы, длинные блоки
        if by0 < data_table_y0 and len(btext) >= _MIN_DESCRIPTION_LEN:
            description_parts.append(btext.replace('\n', ' ').strip())

    # Также берём текст из описательных таблиц (без SKU) для поиска сертификатов
    for tbl in tables:
        rows = tbl.extract()
        if not rows:
            continue
        rows_s = [[str(c or '').strip() for c in row] for row in rows]
        if not any(_is_sku(c) for row in rows_s for c in row if c):
            tbl_text = ' '.join(c for row in rows_s for c in row if c)
            if len(tbl_text) >= 20:
                cert_text_parts.append(tbl_text)

    description = ' | '.join(description_parts)[:1500]
    certifications = _extract_certs_from_text(' '.join(cert_text_parts))

    return description, certifications


# ---------------------------------------------------------------------------
# Регулярное выражение для артикулов — охватывает все форматы из PDF
# ---------------------------------------------------------------------------
_SKU_RE = re.compile(
    r'^(?:'
    r'[A-Z]{1,5}(?:[\-\/\.][A-Z0-9]+){1,6}'           # TI-A101-02-02, AC-A-050-SS, MW-2001B01
    r'|[A-Z]{1,4}[\-][A-Z]{1,4}[\-][A-Z0-9]{2,}'      # CX-CP-03X06, PR-WTZ-08 (буква-буква-смесь)
    r'|[A-Z0-9]{2,}[\-][A-Z0-9][\-A-Z0-9\.\/]{2,}'    # общий формат с хотя бы одним дефисом
    r')\*?$',
    re.IGNORECASE,
)

# Значения ячеек, которые нужно игнорировать
_SKIP_VALUES = {'-', '–', '—', '', 'none', 'nan', '-\n-', '–\n–'}

def _is_sku(val: str) -> bool:
    v = val.strip().rstrip('*')
    # Должен начинаться с буквы — исключает номера CAS (например, "64-17-5") и REACH ID
    return 3 <= len(v) <= 45 and v[0].isalpha() and bool(_SKU_RE.match(v))

def _clean_sku(val: str) -> str:
    """Убирает завершающий * и пробелы."""
    return val.strip().rstrip('*').strip()


# ---------------------------------------------------------------------------
# Вспомогательные функции для определения заголовков и названий
# ---------------------------------------------------------------------------

# Ключевые слова для столбца с артикулом
_INDEX_KW = {'індекс', 'indeks', 'index', 'артикул', 'article', 'sku',
             'код', 'code', 'ref', 'part', 'номенклатура',
             'art', 'order', 'poz', 'numer', 'catalog no', 'cat.no', 'nr kat',
             'item', 'type no', 'type-no', 'ordering'}
# Столбцы, которые пропускаем (вес, цена)
_SKIP_COL_KW = {'вага', 'weight', 'kg', 'кг', 'ціна', 'price'}
# Ключевые слова размерных параметров
_DIM_KW = {'dn', 'd', 'dd', 'dw', 'l', 'mm', 'мм', 'діаметр', 'diameter',
           'тиск', 'pressure', 'бар', 'bar', 'pn', 'різьба', 'thread',
           'розмір', 'size', 'довжина', 'length', 'товщина', 'wall',
           'радіус', 'radius', 'зовнішній', 'внутрішній', 'з\'єднання'}
# Ключевые слова материалов
_MATERIAL_KW = {'алюміній', 'aluminium', 'aluminum', 'латунь', 'brass',
                'сталь', 'steel', 'aisi', 'поліпропілен', 'polypropylene',
                'пластик', 'plastic', 'нержавіюч'}
# Вариации слова "номенклатура"
_NOMENKLATURA_KW = {'номенклатура', 'nomenclature', 'нрменклатура'}


def _row_text(row: List[str]) -> str:
    """Склеивает ячейки строки в одну строку нижнего регистра."""
    return ' '.join(row).lower()

def _has_skus_in_row(row: List[str]) -> bool:
    """Возвращает True, если в строке есть хотя бы один валидный артикул."""
    return any(_is_sku(c) for c in row if c.strip() not in _SKIP_VALUES)

def _count_skus(row: List[str]) -> int:
    """Считает количество валидных артикулов в строке."""
    return sum(1 for c in row if c.strip() not in _SKIP_VALUES and _is_sku(c))

def _is_dimension_header_row(row: List[str]) -> bool:
    """Проверяет, является ли строка заголовком размерных параметров."""
    txt = _row_text(row)
    return any(kw in txt for kw in _DIM_KW)

def _is_index_header_row(row: List[str]) -> bool:
    """Проверяет, содержит ли строка заголовок столбца с артикулами."""
    txt = _row_text(row)
    return any(kw in txt for kw in _INDEX_KW)


# ---------------------------------------------------------------------------
# Определение формата таблицы
# ---------------------------------------------------------------------------

def _detect_format(rows: List[List[str]]) -> str:
    """
    Возвращает 'A' (матрица), 'B' (мультиматериал), 'C' (простой список),
    или 'SKIP', если таблица не содержит полезных данных о товарах.
    """
    if not rows or len(rows) < 3:
        return 'SKIP'

    flat = ' '.join(' '.join(r) for r in rows[:8]).lower()
    n_cols = max(len(r) for r in rows)

    # Проверяем ключевое слово 'номенклатура' → Формат B или A
    nomen_count = flat.count('номенклатур')
    if nomen_count >= 2:
        # Формат A: матрица перекрёстных ссылок — строки с размерами резьбы
        # Признак: несколько столбцов SKU И заголовки с размерными параметрами
        sku_rows = sum(1 for r in rows[4:12] if _count_skus(r) >= 2)
        if sku_rows >= 2 and n_cols >= 8:
            return 'A'
        return 'B'

    # Формат A без 'номенклатура': матрица, где много строк с ≥2 SKU в столбцах
    sku_rows_matrix = sum(1 for r in rows[1:] if _count_skus(r) >= 2)
    if sku_rows_matrix >= 2 and n_cols >= 3:
        return 'A'

    # Формат C: простой список с столбцом-индексом
    for r in rows[:8]:
        if _is_index_header_row(r):
            return 'C'

    # Если строки содержат артикулы → считаем Форматом C (расширен диапазон проверки)
    for r in rows[1:10]:
        if _has_skus_in_row(r):
            return 'C'

    return 'SKIP'


# ---------------------------------------------------------------------------
# Утилита: извлечение заголовка страницы из текста над таблицей
# ---------------------------------------------------------------------------

def _get_page_title(page: Any) -> str:
    """Возвращает текст с наибольшим шрифтом на странице (обычно заголовок раздела)."""
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
    # Возвращаем текст с наибольшим размером шрифта (скорее всего заголовок)
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1][:200]


# ---------------------------------------------------------------------------
# Парсер ФОРМАТА A — матрица перекрёстных ссылок
# Пример: hidravlichni-adaptery: строки = размеры резьбы, столбцы = типы адаптеров
# ---------------------------------------------------------------------------

def _parse_format_a(rows: List[List[str]], page_title: str, page_num: int) -> List[Dict]:
    """
    Находит все ячейки с валидными артикулами; прикрепляет атрибуты резьбовых размеров
    из первых двух столбцов строки и тип товара из заголовка группы столбцов.
    """
    products = []
    n_cols = len(rows[0]) if rows else 0

    # Ищем заголовки групп столбцов (обычно в строках 0–5).
    # Строка 0 часто содержит реальное название категории; строка 1 может содержать
    # просто 'номенклатура' — используем setdefault, чтобы первое (реальное) название
    # не перезаписывалось общим ключевым словом.
    col_type_names: Dict[int, str] = {}
    for ri, row in enumerate(rows[:8]):
        for ci, cell in enumerate(row):
            if cell and any(kw in cell.lower() for kw in _NOMENKLATURA_KW):
                col_type_names.setdefault(ci, cell.replace('\n', ' ').strip())
            elif cell and not any(c in cell for c in ['[', '"', '°', '/']):
                # Возможно название типа адаптера (например, "GZ BSP (конус 60°)")
                if len(cell) > 8 and ci > 1:
                    col_type_names.setdefault(ci, cell.replace('\n', ' ').strip())

    # Находим начало строк с данными (содержат реальные артикулы не в первых столбцах)
    # ri >= 1 чтобы пропустить строку заголовков, но захватить матрицы без 'номенклатура'
    data_start = 1
    for ri, row in enumerate(rows):
        if _count_skus(row) >= 1 and ri >= 1:
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
            # Ячейка может содержать несколько артикулов, разделённых переносом строки
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
                # Если col_type содержит только ключевое слово — убираем его,
                # оставляя только суффикс (например, "номенклатура (AISI 316)" → "AISI 316")
                if col_type and all(kw in col_type.lower() for kw in ['номенклатур']):
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
# Парсер ФОРМАТА B — список товаров с несколькими материалами
# Пример: camlock: столбцы (DN, з'єднання, d, різьба, SKU_алюм, SKU_латунь, ...)
# ---------------------------------------------------------------------------

def _parse_format_b(rows: List[List[str]], page_title: str, page_num: int) -> List[Dict]:
    products = []

    # Ищем название категории (первая непустая строка с одним значением)
    category = page_title
    for row in rows[:3]:
        non_empty = [c for c in row if c.strip()]
        if len(non_empty) == 1 and len(non_empty[0]) > 6:
            category = non_empty[0].replace('\n', ' ').strip()
            break

    # Ищем строку заголовка: содержит "DN", "різьба", "номенклатура", размерные ключевые слова
    header_row_idx = None
    for ri, row in enumerate(rows[:8]):
        txt = _row_text(row)
        if ('номенклатур' in txt or 'індекс' in txt or 'index' in txt) and (
            'dn' in txt or 'різьба' in txt or 'thread' in txt or 'діаметр' in txt or 'мм' in txt
        ):
            header_row_idx = ri
            break

    if header_row_idx is None:
        # Резервный способ: ищем по наличию артикулов
        for ri, row in enumerate(rows[1:6], 1):
            if _has_skus_in_row(row):
                header_row_idx = ri - 1
                break

    if header_row_idx is None:
        return []

    # Объединяем многострочные заголовки (иногда разбиты на 2–3 строки)
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

    # Классифицируем столбцы: размерные vs артикульные
    dim_cols: List[Tuple[int, str]] = []   # (индекс_столбца, название_столбца)
    sku_cols: List[Tuple[int, str]] = []   # (индекс_столбца, название_материала)
    for ci, h in enumerate(headers):
        h_lo = h.lower()
        if any(kw in h_lo for kw in _NOMENKLATURA_KW):
            # Извлекаем материал из заголовка, например "номенклатура (алюміній)"
            mat = re.sub(r'номенклатур[а-я]*\s*', '', h, flags=re.I).strip('() ')
            sku_cols.append((ci, mat or 'SKU'))
        elif any(kw in h_lo for kw in _INDEX_KW):
            sku_cols.append((ci, 'SKU'))
        elif h and not any(kw in h_lo for kw in _SKIP_COL_KW):
            dim_cols.append((ci, h))

    data_start = header_row_idx + 1
    # Пропускаем строки с единицами измерения (например, "[мм]", "[дюйми]")
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

        # Формируем базовые атрибуты из размерных столбцов
        attrs_base = {}
        for ci, col_name in dim_cols:
            if ci < len(row) and row[ci].strip():
                attrs_base[col_name] = row[ci].strip()

        # Извлекаем артикулы из столбцов SKU
        for ci, material in sku_cols:
            if ci >= len(row):
                continue
            cell = row[ci].strip()
            if not cell or cell in _SKIP_VALUES:
                continue

            # Ячейка может содержать несколько артикулов, разделённых переносом строки
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

                # Формируем название из категории + размеры
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
# Парсер ФОРМАТА C — простой список товаров
# Пример: пневматика, шланги: строка0=название, строка1=серия, строка2=заголовки, строки3+=данные
# ---------------------------------------------------------------------------

def _parse_format_c(rows: List[List[str]], page_title: str, page_num: int) -> List[Dict]:
    products = []

    # Извлекаем название категории (первая непустая строка с одним значением)
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

    # Ищем строку заголовка — столбец с индексом имеет приоритет над размерными ключевыми словами
    header_row_idx = None
    # Приоритет 1: строка явно содержит 'індекс'/'index'/'артикул' и т.д.
    for ri, row in enumerate(rows[:10]):
        if _is_index_header_row(row):
            header_row_idx = ri
            break
    # Приоритет 2: любая строка с размерными ключевыми словами (для многострочных заголовков)
    if header_row_idx is None:
        for ri, row in enumerate(rows[:6]):
            if _is_dimension_header_row(row):
                header_row_idx = ri
                break
    # Запасной вариант: первая строка, после которой идут артикулы
    if header_row_idx is None:
        for ri in range(len(rows) - 1):
            if _has_skus_in_row(rows[ri + 1]):
                header_row_idx = ri
                break

    if header_row_idx is None:
        return []

    # Формируем заголовки (могут занимать несколько строк)
    raw_headers = list(rows[header_row_idx])
    for ri in range(header_row_idx + 1, min(header_row_idx + 3, len(rows))):
        next_row = rows[ri]
        if _has_skus_in_row(next_row):
            break
        all_units = all(
            not c.strip() or re.match(r'^\[', c.strip()) for c in next_row if c.strip()
        )
        if all_units:
            # Объединяем строку с единицами измерения в заголовки
            for ci, cell in enumerate(next_row):
                if ci < len(raw_headers) and cell.strip():
                    raw_headers[ci] += ' ' + cell.strip()
            header_row_idx += 1

    headers = [h.replace('\n', ' ').strip() for h in raw_headers]

    # Находим столбец с артикулом
    sku_col = -1
    for ci, h in enumerate(headers):
        if any(kw in h.lower() for kw in _INDEX_KW):
            sku_col = ci
            break
    if sku_col == -1:
        # Угадываем: первый столбец, в котором данные похожи на артикулы
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

    # Столбцы атрибутов (всё, кроме артикула, веса и цены)
    attr_cols: List[Tuple[int, str]] = [
        (ci, h) for ci, h in enumerate(headers)
        if ci != sku_col and h and not any(kw in h.lower() for kw in _SKIP_COL_KW)
    ]

    seen = set()
    for row in rows[header_row_idx + 1:]:
        if sku_col >= len(row):
            continue
        cell = row[sku_col].strip()
        # Некоторые ячейки содержат несколько артикулов (например, "MW-2001B01\nMW-2001A01")
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

            # Формируем название из категории + первые 2 атрибута
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
# Определение bbox основного изображения товара на странице
# ---------------------------------------------------------------------------

# Лого Tubes International: bbox ≈ [42.6, 30.5, 147.6, 57.0], всегда в шапке y0 < 65
_LOGO_MAX_Y0 = 65        # изображения выше этой точки — лого в шапке
_MIN_IMG_AREA = 500      # минимальная площадь чтобы отсечь крошечные иконки
_FOOTER_Y_RATIO = 0.88   # изображения ниже 88% высоты страницы — footer/декор

def _get_page_main_image_bbox(page: Any) -> Optional[Dict]:
    """
    Находит bbox основного изображения товара на странице.
    Игнорирует: логотип (y0 < 65), footer (y0 > 88%) и крошечные иконки (<500 pt²).
    Возвращает bbox наибольшего подходящего изображения, или None.
    """
    page_h = page.rect.height
    best: Optional[Dict] = None
    best_area = 0.0

    for img in page.get_images(full=True):
        xref = img[0]
        try:
            for r in page.get_image_rects(xref):
                area = (r.x1 - r.x0) * (r.y1 - r.y0)
                # Исключаем крошечные иконки
                if area < _MIN_IMG_AREA:
                    continue
                # Исключаем лого в шапке (всегда y0 < 65 на этих PDF)
                if r.y0 < _LOGO_MAX_Y0:
                    continue
                # Исключаем footer-изображения
                if r.y0 > page_h * _FOOTER_Y_RATIO:
                    continue
                if area > best_area:
                    best_area = area
                    best = {
                        'x0': round(r.x0, 1),
                        'y0': round(r.y0, 1),
                        'x1': round(r.x1, 1),
                        'y1': round(r.y1, 1),
                    }
        except Exception:
            pass

    return best


# ---------------------------------------------------------------------------
# Основная точка входа
# ---------------------------------------------------------------------------

def parse_pdf(
    pdf_bytes: bytes,
    doc_id: int,
    section_id: int,
    category_id: int,
) -> Tuple[List[Dict], int]:
    """
    Парсит PDF-каталог Tubes International без использования LLM.
    Возвращает (список_товаров, количество_страниц).
    """
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype='pdf')
        page_count = len(pdf)
        all_products: List[Dict] = []
        seen_skus: set = set()

        for page_num, page in enumerate(pdf, start=1):
            try:
                page_title = _get_page_title(page)
                # Определяем главное изображение страницы один раз для всех товаров
                page_img_bbox = _get_page_main_image_bbox(page)
                tabs = page.find_tables()
                # Извлекаем описание и сертификаты со страницы
                page_description, page_certifications = _get_page_text_and_certs(page, tabs.tables)

                for tbl in tabs.tables:
                    rows = tbl.extract()
                    if not rows:
                        continue

                    # Нормализуем: все ячейки приводим к строке и убираем пробелы
                    rows = [[str(c or '').strip() for c in row] for row in rows]

                    fmt = _detect_format(rows)
                    if fmt == 'SKIP':
                        # Диагностика: показываем первые 2 строки пропущенной таблицы
                        preview = ' | '.join(
                            '[' + ', '.join(c[:15] for c in r if c)[:60] + ']'
                            for r in rows[:2]
                        )
                        logger.info(f"Doc#{doc_id} p{page_num} SKIP({len(rows)}r×{len(rows[0])}c): {preview[:120]}")
                        continue

                    if fmt == 'A':
                        prods = _parse_format_a(rows, page_title, page_num)
                    elif fmt == 'B':
                        prods = _parse_format_b(rows, page_title, page_num)
                    else:
                        prods = _parse_format_c(rows, page_title, page_num)

                    # Дедупликация между страницами + привязка bbox изображения
                    for p in prods:
                        if p['sku'] and p['sku'] in seen_skus:
                            continue
                        if p['sku']:
                            seen_skus.add(p['sku'])
                        p['section_id'] = section_id
                        p['category_id'] = category_id
                        # Сохраняем bbox изображения страницы для endpoint /image
                        p['image_bbox'] = page_img_bbox or {}
                        # Заполняем описание и сертификаты (форматные парсеры дают пустые строки)
                        if not p.get('description'):
                            p['description'] = page_description
                        p['certifications'] = page_certifications
                        all_products.append(p)

                    logger.info(
                        f"Doc#{doc_id} p{page_num} fmt={fmt}: "
                        f"{len(prods)} товаров, заголовок {rows[0][0][:40]!r}"
                    )

            except Exception as exc:
                logger.warning(f"Doc#{doc_id} p{page_num}: {exc}")
                continue

        pdf.close()
        logger.info(f"Doc#{doc_id}: {len(all_products)} товаров / {page_count} страниц")
        return all_products, page_count

    except Exception as exc:
        logger.error(f"Doc#{doc_id}: Ошибка парсинга PDF: {exc}")
        return [], 0
