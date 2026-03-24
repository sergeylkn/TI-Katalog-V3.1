"""
R2 Importer v5 — correct 2-level categories from filename.
Filename structure: {category_slug}_{section_slug}.pdf
e.g. sylova-hidravlika_hidravlichni-adaptery.pdf
  → Category: Силова гідравліка
  → Section:  Гідравлічні адаптери
"""
import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from core.database import AsyncSessionLocal
from models.models import Document, Section, Category, ImportLog, ParseLog

logger = logging.getLogger(__name__)

def _live(msg, level="info", doc="", **kw):
    try:
        from services.live_log import log as live_log
        live_log(msg, level=level, doc=doc, **kw)
    except Exception:
        pass

def _live_progress(done, total, current="", products=0):
    try:
        from services.live_log import progress as live_progress
        live_progress(done, total, current, products)
    except Exception:
        pass

R2_BASE  = "https://pub-ada201ec5fb84401a3b36b7b21e6ed0f.r2.dev"
MANIFEST = f"{R2_BASE}/manifest.txt"

# ── Transliteration dictionary (slug → Ukrainian name) ────────────────────────
CATEGORY_NAMES = {
    "sylova-hidravlika":                    ("Силова гідравліка",            "🔧"),
    "promyslova-armatura":                  ("Промислова арматура",          "⚙️"),
    "shlanhy-dlya-promyslovosti":           ("Шланги для промисловості",     "🔴"),
    "promyslova-pnevmatyka":                ("Промислова пневматика",        "💨"),
    "pretsyziyna-armatura":                 ("Прецизійна арматура",          "📏"),
    "prystroyi-ta-aksesuary":               ("Пристрої та аксесуари",        "🛠"),
    "vymiryuvalni-systemy-ta-manometry":    ("Вимірювальні системи та манометри", "🌡️"),
    "ochystka-ta-zmyvannya":               ("Очистка та змивання",          "🧹"),
    "industrial_hoses":                     ("Industrial Hoses",             "🟠"),
    "pneumatic":                            ("Pneumatic Systems",            "💡"),
}

SECTION_NAMES = {
    # sylova-hidravlika
    "hidravlichni-adaptery":                "Гідравлічні адаптери",
    "hidravlichni-ahrehaty":                "Гідравлічні агрегати",
    "hidravlichni-klapany-klasyfikatsiya":  "Класифікація гідравлічних клапанів",
    "hidravlichni-kulovi-krany":            "Гідравлічні кульові крани",
    "hidravlichni-nasosy":                  "Гідравлічні насоси",
    "hidravlichni-rozpodilnyky":            "Гідравлічні розподільники",
    "hidravlichni-shvydko-rozyemni-zyednannya": "Гідравлічні швидкороз'ємні з'єднання",
    "hidravlichni-truby":                   "Гідравлічні труби",
    "hidravlichni-zapobizhni-klapany-dilnyky": "Запобіжні клапани та дільники",
    "hidravlichni-zvorotni-klapany":        "Зворотні клапани",
    "hidrotsylindry":                       "Гідроциліндри",
    "humovi-hidravlichni-shlanhy":          "Гумові гідравлічні шланги",
    "inshi-hidravlichni-klapany":           "Інші гідравлічні клапани",
    "inshi-hidravlichni-komponenty":        "Інші гідравлічні компоненти",
    "khomuty-dlya-trub-din-3015":           "Хомути для труб DIN 3015",
    "klapany-ta-hidro-rozpodilnyky":        "Клапани та гідророзподільники",
    "manometri-uhp":                        "Манометри UHP",
    "obertovi-hidravlichni-mufty":          "Обертові гідравлічні муфти",
    "obladnannya-nadvysokoho-tysku-zahalna-informatsiya": "Обладнання надвисокого тиску",
    "ochyshchennya-uhp":                    "Очищення UHP",
    "rozyemy-orfs":                         "Роз'єми ORFS",
    "rukavy-waterblast-ta-fitynhy":         "Рукави Waterblast та фітинги",
    "shlanhy-spir-star-kintsevyky-ta-pryladdya": "Шланги SPIR STAR, кінцівки та приладдя",
    "shvydkorozyemni-zyednannya":           "Швидкороз'ємні з'єднання",
    "spetsialna-hidravlichni-obpresovky":   "Спеціальні гідравлічні обпресовки",
    "standartni-vtulky-typu-z":             "Стандартні втулки типу Z",
    "termoplastychni-shlanhy-ta-fitynhy-kintsevyky-uhp": "Термопластичні шланги та фітинги UHP",
    "termoplastychni-shlanhy":              "Термопластичні шланги",
    "vtulky-na-zakrutku-typ-s":             "Втулки на закрутку тип S",
    "vtulky-non-skive-typ-n":               "Втулки Non-Skive тип N",
    "zyednannya-din-2353":                  "З'єднання DIN 2353",
    "zyednannya-jic":                       "З'єднання JIC",
    "adaptery-uhp":                         "Адаптери UHP",
    "droselni-ta-zapobizhni-klapany":       "Дросельні та запобіжні клапани",
    "fitynhy-mp-hp":                        "Фітинги MP/HP",
    "fitynhy-ta-adaptery-stecko":           "Фітинги та адаптери Stecko",
    "fitynhy-ta-obtyskni-vtulky-typ-interlock-typ-il": "Фітинги та обтискні втулки Interlock",
    "flantsevi-zyednannya-dlya-hidravlichnykh-nasosiv": "Фланцеві з'єднання для насосів",
    "flantsevi-zyednannya-sae":             "Фланцеві з'єднання SAE",
    # shlanhy-dlya-promyslovosti
    "universalni-shlanhy":                  "Універсальні шланги",
    "shlanhy-dlya-vody-ta-povitrya":        "Шланги для води та повітря",
    "shlanhy-dlya-kharchovykh-rechovyn":    "Шланги для харчових речовин",
    "shlanhy-dlya-khimichnykh-rechovyn":    "Шланги для хімічних речовин",
    "shlanhy-dlya-naftoproduktiv":          "Шланги для нафтопродуктів",
    "shlanhy-dlya-vodyanoyi-pary":          "Шланги для водяної пари",
    "sylikonovi-promyslovi-shlanhy":        "Силіконові промислові шланги",
    "teflonovi-shlanhy-bez-obpletennya":    "Тефлонові шланги без обплетення",
    "teflonovi-rukavy-dlya-promyslovykh-protsesiv": "Тефлонові рукави для промислових процесів",
    "kompozytni-shlanhy":                   "Композитні шланги",
    "spiralni-stalevi-shlanhy":             "Спіральні сталеві шланги",
    "shlanhy-tygon":                        "Шланги TYGON®",
    "vytyazhni-ta-ventylyatsiyni-shlanhy":  "Витяжні та вентиляційні шланги",
    "santekhnichni-shlanhy":                "Сантехнічні шланги",
    "shlanhy-ta-liniyi-dlya-okholodzhuvalnoyi-ridyny": "Шланги для охолоджувальної рідини",
    "avtomobilni-shlanhy-ta-zyednannya":    "Автомобільні шланги та з'єднання",
    "universalni-samozatyskni-shlanhy":     "Універсальні самозатискні шланги",
    "metalorukavy-napirni-ta-yikh-armatura-fitynhy": "Металорукави напірні та їх арматура",
    # promyslova-armatura
    "kulovi-krany":                         "Кульові крани",
    "zvorotni-klapany-ta-filtry":           "Зворотні клапани та фільтри",
    "zasuvky-zapirni-klapany":              "Засувки та запірні клапани",
    "nerzhaviyuchi-hihiyenichni-klapany":   "Нержавіючі гігієнічні клапани",
    "rozyemy-camlock":                      "Роз'єми Camlock",
    "rozyemy-camlock-iz-zakhystom":         "Роз'єми Camlock із захистом",
    "zyednannya-guillemin":                 "З'єднання Guillemin",
    "zyednannya-storz":                     "З'єднання Storz",
    "zyednannya-bauer":                     "З'єднання Bauer",
    "vazhilni-zyednannya-bauer":            "Важільні з'єднання Bauer",
    "vazhilni-zyednannya-anfor":            "Важільні з'єднання Anfor",
    "vazhilni-zyednannya-ferrari":          "Важільні з'єднання Ferrari",
    "vazhilni-zyednannya-perrot":           "Важільні з'єднання Perrot",
    "vazhilni-zyednannya-laux-42":          "Важільні з'єднання Laux 42",
    "latunni-rizbovi-fitynhy":              "Латунні різьбові фітинги",
    "plastykovi-kintsevyky-ta-zyednuvachi": "Пластикові кінцівки та з'єднувачі",
    "promyslovi-rizbovi-zyednannya":        "Промислові різьбові з'єднання",
    "promyslovi-rizbovi-adaptery":          "Промислові різьбові адаптери",
    "khomuty-dlya-fiksatsiyi-ta-montuvannya-kintsevykiv": "Хомути для фіксації та монтажу",
    "khomuty-p-clip":                       "Хомути P-Clip",
    "inshi-oboymy-khomuty-dlya-trub":       "Інші обойми та хомути для труб",
    "kintsevyky-ta-zyednannya-typu-ec":     "Кінцівки та з'єднання типу EC",
    "kintsevyky-typu-cn":                   "Кінцівки типу CN",
    "klykovi-zyednannya-40-mm":             "Клинові з'єднання 40 мм",
    # promyslova-pnevmatyka
    "frl-pidhotuvannya-povitrya":           "FRL — підготування повітря",
    "aksesuary-dlya-frl":                   "Аксесуари для FRL",
    "pnevmatychni-klapany-ta-aksesuary-do-nykh": "Пневматичні клапани та аксесуари",
    "rizbovi-latunni-zyednannya":           "Різьбові латунні з'єднання",
    "rizbovi-zyednannya-zi-stali-marky-316": "Різьбові з'єднання зі сталі 316",
    "tsanhovi-funktsionalni-rozyemy":       "Цангові функціональні роз'єми",
    "zyednannya-banjo":                     "З'єднання Banjo",
    "zyednannya-na-vrizne-kolechko":        "З'єднання на врізне кільце",
    "zyednannya-na-zatysknu-hayku":         "З'єднання на затискну гайку",
    # pretsyziyna-armatura
    "bloky-komplekty-klapaniv":             "Блоки та комплекти клапанів",
    "inshi-klapany-ta-filtry":              "Інші клапани та фільтри",
    "inshi-zyednuvachi":                    "Інші з'єднувачі",
    "manometry-ta-aksesuary":               "Манометри та аксесуари",
    "pretsyziyna-armatura-zahalna-informatsiya": "Прецизійна арматура — загальна інформація",
    "pretsyziyni-holchasti-klapany":        "Прецизійні голчасті клапани",
    "pretsyziyni-kulovi-krany-klapany":     "Прецизійні кульові крани та клапани",
    "pretsyziyni-rizbovi-zyednuvachi":      "Прецизійні різьбові з'єднувачі",
    "pretsyziyni-shvydko-rozyemni-zyednuvachi": "Прецизійні швидкороз'ємні з'єднувачі",
    "pretsyziyni-truby":                    "Прецизійні труби",
    "pretsyziyni-zyednuvachi-let-lok":      "Прецизійні з'єднувачі Let-Lok",
    # vymiryuvalni-systemy-ta-manometry
    "inshi-vymiryuvalni-prylady":           "Інші вимірювальні прилади",
    "manometry-reduktsiyni-adaptery-ta-manometrychni-kranyky": "Манометри, редукційні адаптери",
    "vymiryuvalni-systemy":                 "Вимірювальні системи",
    "vymiryuvalni-zyednannya-vymiryuvalni-shlanhy-ta-kintsevyky": "Вимірювальні з'єднання та шланги",
    # ochystka-ta-zmyvannya
    "aksesuary-dlya-zmashchuvannya":        "Аксесуари для змащування",
    "nyzkonapirni-vodyani-pistolety":       "Низьконапірні водяні пістолети",
    "obpresovky-dlya-shlanhiv-ta-myyky":    "Обпресовки для шлангів та мийки",
    "shlanhy-ta-tavotnytsi-maslonky-dlya-zmashchuvannya": "Шланги та таватниці для змащування",
    # prystroyi-ta-aksesuary
    "barabany-ta-kotushky-oznayomcha-informatsiya": "Барабани та котушки",
    "ruchni-hidravlichni-elektrychni-pnevmatychni-barabany": "Ручні, гідравлічні та пневматичні барабани",
    "pruzhynno-zmotuval-ni-barabany":       "Пружинно-змотувальні барабани",
    "aksesuary-dlya-barabaniv":             "Аксесуари для барабанів",
    "zatyskni-presy":                       "Затискні преси",
    "pistolety-ta-obladnannya-dlya-pidkachky-kolis": "Пістолети для підкачки коліс",
    "povitryani-pistolety":                 "Повітряні пістолети",
    "pnevmatychni-pistolety-spetsialni":    "Пневматичні пістолети спеціальні",
    "promyslova-khimiya":                   "Промислова хімія",
    "stiyky-dlya-shlanhiv":                 "Стійки для шлангів",
    "zakhyst":                              "Захист",
    "zakhysty":                             "Захисти",
    "vysokotemperaturnyy-zakhyst":          "Високотемпературний захист",
    # industrial_hoses
    "compensators":                         "Компенсатори",
    "floating_hoses_and_equipment":         "Плавучі шланги та обладнання",
    "heated_hoses":                         "Підігрівні шланги",
    "hoses_for_braking_systems":            "Шланги для гальмівних систем",
    "technical_gas":                        "Технічні гази",
    # pneumatic
    "fittings":                             "Пневматичні фітинги",
    "hoses":                                "Пневматичні шланги",
    "speedfit_system":                      "Система Speedfit",
    # ── Додаткові розділи (повний список з manifest) ─────────────────────────
    # promyslova-armatura
    "chavunni-zatyskni-oboymy-dlya-obtyskannya-fitynhiv": "Чавунні затискні обойми для обтискання фітингів",
    "fitynhy-dlya-vnutrishnoho-obtyskannya":    "Фітинги для внутрішнього обтискання",
    "hammer-lug-zyednannya-ta-armatura":        "З'єднання Hammer Lug та арматура",
    "inshi-zyednuvalni-elementy-dlya-vydobutku-nafty-ta-hazu": "З'єднувальні елементи для видобутку нафти та газу",
    "oboymy-dlya-remontu-ta-zyednannya-trub":   "Обойми для ремонту та з'єднання труб",
    "oboymy-shkaralupchasti-dlya-montuvannya-kintsevykiv": "Обойми шкаралупчасті для монтування кінцівок",
    "palyvni-zyednannya-na-skrutku":            "Паливні з'єднання на скрутку",
    "palyvni-zyednannya":                       "Паливні з'єднання",
    "peredavalni-transportuvalni-zyednannya-zahalna-informatsiya": "Передавальні/транспортувальні з'єднання",
    "perevantazhuvalni-ohlyadovi-lyuky":        "Перевантажувальні оглядові люки",
    "perevantazhuvalni-sharnirno-rukhomi-plechi": "Перевантажувальні шарнірно-рухомі плечі",
    "rizbovi-armatury-z-chavunu-ta-stali":      "Різьбова арматура з чавуну та сталі",
    "rozyemy-ibc":                              "Роз'єми IBC",
    "strichkova-zatyskna-systema":              "Стрічкова затискна система",
    "sukho-rozyemni-zyednannya":                "Сухо роз'ємні з'єднання",
    "ushchilnennya-ta-kripylni-bolty-dlya-flantsevykh-zyednan": "Ущільнення та кріпильні болти для фланцевих з'єднань",
    "vazhilne-zyednannya-klaudia":              "Важільне з'єднання Klaudia",
    "vsmoktuvalni-filtry":                      "Всмоктувальні фільтри",
    "zaliznychni-zyednuvachi":                  "Залізничні з'єднувачі",
    "zalyvalni-zapravni-pistolety":             "Заливальні/заправні пістолети",
    "zapravna-nalyvna-armatura-insha":          "Заправна/наливна арматура (інша)",
    "zasuvky-zapirni-klapany":                  "Засувки та запірні клапани",
    "zvarni-truby-ta-fasonni-chastyny-pid-pryvarku": "Зварні труби та фасонні частини під приварку",
    "zyednannya-dlya-nyzkoho-tysku-zahalnoho-pryznachennya": "З'єднання для низького тиску загального призначення",
    "zyednannya-dlya-shtukaturky":              "З'єднання для штукатурки",
    "zyednannya-gost":                          "З'єднання ГОСТ",
    "zyednannya-klykove-sms":                   "З'єднання клинове SMS",
    "zyednannya-nor":                           "З'єднання NOR",
    "zyednannya-rotta":                         "З'єднання Rotta",
    "zyednannya-storz":                         "З'єднання Storz",
    "zyednannya-guillemin":                     "З'єднання Guillemin",
    "zyednannya-ta-lpglng-ta-kriohazy":         "З'єднання LPG/LNG та кріогази",
    "zyednannya-tw":                            "З'єднання TW",
    "zyednuvachi-avariynoho-vidyednannya-avariyni-rozyemy": "Аварійні роз'єми від'єднання",
    "zyednuvachi-dlya-piskostrumynnoyi-obrobky": "З'єднувачі для піскоструминної обробки",
    "zyednuvachi-z-zatysknym-kiltsem":          "З'єднувачі з затискним кільцем",
    "shvydko-rozyemni-zyednannya-dlya-pres-form": "Швидкороз'ємні з'єднання для прес-форм",
    "shvydko-rozyemni-zyednannya-plastykovi-promyslovi": "Швидкороз'ємні з'єднання пластикові промислові",
    "shvydko-rozyemy-nerzhaviyuchi-dlya-vody":  "Швидкороз'єми нержавіючі для води",
    "shvydkorozyemni-zyednannya-dlya-kharchovoyi-promyslovosti": "Швидкороз'ємні з'єднання для харчової промисловості",
    # shlanhy-dlya-promyslovosti
    "aksesuary-dlya-vodyanoyi-pary":            "Аксесуари для водяної пари",
    "fitynhy-dlya-systemy-kondytsionuvannya-povitrya": "Фітинги для системи кондиціонування повітря",
    "halmivni-fitynhy":                         "Гальмівні фітинги",
    "kintsevyky-fitynhy-dlya-vodyanoyi-pary":   "Кінцівки та фітинги для водяної пари",
    "kompozytni-zyednannya-dlya-shlanhiv":      "Композитні з'єднання для шлангів",
    "montazh-fitynhiv-dlya-kondytsioneriv":     "Монтаж фітингів для кондиціонерів",
    "shlanhy-dlya-perekachuvannya-sypuchykh-rechovyn": "Шланги для перекачування сипучих речовин",
    "shlanhy-dlya-system-kondytsionuvannya-povitrya": "Шланги для систем кондиціонування повітря",
    "shlanhy-v-teflonovomu-obpletenni-ta-fitynhy-dlya-nykh": "Шланги в тефлоновому обплетенні та фітинги",
    "teflonovi-shlanhy-zahalnainformatsiya":     "Тефлонові шланги — загальна інформація",
    "zyednuvachi-dlya-vytyazhnykh-shlanhiv":    "З'єднувачі для витяжних шлангів",
    # prystroyi-ta-aksesuary
    "bahatofunktsionalne-obladnannya-dlya-obrobky-trub": "Багатофункціональне обладнання для обробки труб",
    "inshe-obladnannya":                        "Інше обладнання",
    "inshi-barabany":                           "Інші барабани",
    "obladnannya-dlya-montuvannya-kiletsta-rozvaltsyuvannya": "Обладнання для монтажу кілець та розвальцювання",
    "obladnannya-dlya-ochyshchennya-shlanhiv-i-trubok": "Обладнання для очищення шлангів і трубок",
    "pnevmo-aksesuary":                         "Пневмо-аксесуари",
    "prystriy-dlya-hnuttya-trub":               "Пристрій для гнуття труб",
    "prystroyi-dlya-markuvannya":               "Пристрої для маркування",
    "prystroyi-dlya-rizannya-shlanhiv":         "Пристрої для різання шлангів",
    "prystroyi-dlya-znimannya-vnutrishnoho":    "Пристрої для зняття внутрішнього шару",
    "znaryaddya-ta-instrumenty-dlya-vydalennya-zadyrok-na-trubakh": "Знаряддя для видалення задирок на трубах",
    # industrial_hoses (english slugs)
    "hoses_compensators":                       "Компенсатори",
    "hoses_floating_hoses_and_equipment":       "Плавучі шланги та обладнання",
    "hoses_heated_hoses":                       "Підігрівні шланги",
    "hoses_hoses_for_braking_systems":          "Шланги для гальмівних систем",
    "hoses_technical_gas":                      "Технічні гази",
}


def _parse_filename(fname: str):
    """
    Parse filename into (category_slug, section_slug).
    e.g. sylova-hidravlika_hidravlichni-adaptery.pdf
      → ('sylova-hidravlika', 'hidravlichni-adaptery')
    Special case: pneumatic_fittings.pdf → ('pneumatic', 'fittings')
    """
    name = fname.replace(".pdf", "")
    # Find the first underscore that separates category from section
    # Category slugs use hyphens internally, sections also use hyphens
    # So split on first underscore
    idx = name.find("_")
    if idx == -1:
        return name, name
    cat_slug = name[:idx]
    sec_slug = name[idx+1:]
    return cat_slug, sec_slug


def _slug_to_name(slug: str, lookup: dict, fallback_fn=None) -> str:
    if slug in lookup:
        return lookup[slug]
    # Try replacing underscores with hyphens
    slug2 = slug.replace("_", "-")
    if slug2 in lookup:
        return lookup[slug2]
    # Fallback: capitalize and replace dashes
    if fallback_fn:
        return fallback_fn(slug)
    return slug.replace("-", " ").replace("_", " ").title()


def _humanize(slug: str) -> str:
    """Convert slug to human-readable Ukrainian/English text."""
    return slug.replace("-", " ").replace("_", " ").capitalize()


async def _get_or_create_category(db, slug: str) -> Category:
    r = await db.execute(select(Category).where(Category.slug == slug))
    cat = r.scalar_one_or_none()
    if not cat:
        name = _slug_to_name(slug, {k: v[0] for k, v in CATEGORY_NAMES.items()}, _humanize)
        icon = CATEGORY_NAMES.get(slug, ("", "📦"))[1]
        cat = Category(name=name, slug=slug, icon=icon)
        db.add(cat)
        await db.flush()
    return cat


async def _get_or_create_section(db, slug: str, cat_id: int) -> Section:
    r = await db.execute(
        select(Section).where(Section.slug == slug, Section.category_id == cat_id)
    )
    sec = r.scalar_one_or_none()
    if not sec:
        name = _slug_to_name(slug, SECTION_NAMES, _humanize)
        sec = Section(name=name, slug=slug, category_id=cat_id)
        db.add(sec)
        await db.flush()
    return sec


async def run_import_all(db=None):
    """Background task to import all PDFs from R2 manifest.

    Args:
        db: Optional AsyncSession (created internally if not provided).
    """
    logger.info("🔄 R2 import v5 starting…")

    # Use provided db session or create new one
    should_close_db = db is None
    if db is None:
        db = AsyncSessionLocal()

    try:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                resp = await c.get(MANIFEST)
                resp.raise_for_status()
            files = [l.strip() for l in resp.text.splitlines() if l.strip().lower().endswith(".pdf")]
            logger.info(f"Manifest: {len(files)} PDFs")
            _live(f"📋 Manifest: {len(files)} PDF файлів знайдено", "info")
        except Exception as e:
            db.add(ImportLog(document_name="manifest.txt", status="error", message=str(e)[:400]))
            await db.commit()
            return

        queue_ids = []
        retry_ids = []  # документи с ошибкой или зависшие в "parsing"

        for fname in files:
            url = f"{R2_BASE}/{fname}"
            r = await db.execute(select(Document).where(Document.file_url == url))
            existing = r.scalar_one_or_none()

            if existing:
                # Повторно обрабатываем: error-документы и зависшие в "parsing"
                if existing.status in ("error", "parsing"):
                    existing.status = "pending"
                    retry_ids.append(existing.id)
                # done/pending — пропускаем
                continue

            cat_slug, sec_slug = _parse_filename(fname)
            cat = await _get_or_create_category(db, cat_slug)
            sec = await _get_or_create_section(db, sec_slug, cat.id)

            doc = Document(
                name=fname, file_url=url, status="pending",
                section_id=sec.id, category_id=cat.id
            )
            db.add(doc)
            await db.flush()
            db.add(ImportLog(
                document_id=doc.id, document_name=fname, status="queued",
                message=f"{cat.name} → {sec.name}"
            ))
            queue_ids.append(doc.id)

        await db.commit()

        all_ids = queue_ids + retry_ids
        logger.info(f"✅ Черга: {len(queue_ids)} нових + {len(retry_ids)} повторних документів")
        _live(f"✅ Черга: {len(queue_ids)} нових + {len(retry_ids)} повторних документів", "info")

        total_docs = len(all_ids)
        if total_docs == 0:
            _live("ℹ Всі PDF вже оброблено. Для повторного імпорту очистіть БД.", "info")
        for idx, doc_id in enumerate(all_ids):
            try:
                await parse_one(doc_id)
            except Exception as e:
                logger.error(f"parse_one({doc_id}): {e}")
            _live_progress(idx + 1, total_docs)
            await asyncio.sleep(0.3)
        _live(f"🏁 Імпорт завершено: {total_docs} документів оброблено", "done")
    finally:
        if should_close_db:
            await db.close()


async def parse_one(doc_id: int):
    from services.extractor import extract_products
    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, doc_id)
        if not doc or doc.status in ("parsing", "done"):
            return
        # Зависший в "parsing" от предыдущего запуска — разрешаем повторно
        # (run_import_all уже сбросил его в "pending" перед вызовом)
        doc.status = "parsing"
        await db.commit()

        async def _log(level, msg):
            async with AsyncSessionLocal() as db2:
                db2.add(ParseLog(document_id=doc_id, level=level, message=msg[:400]))
                await db2.commit()

        try:
            await _log("info", f"📥 {doc.file_url}")
            _live(f"⬇ Завантажую: {doc.name}", "info", doc=doc.name)
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
                resp = await c.get(doc.file_url)
                resp.raise_for_status()

            from services.extractor import extract_products_from_pdf, extract_products

            products_list, page_count = await extract_products_from_pdf(
                resp.content, doc_id, doc.section_id or 0, doc.category_id or 0
            )

            products_count = 0
            if products_list:
                async with AsyncSessionLocal() as db2:
                    doc2 = await db2.get(Document, doc_id)
                    if doc2:
                        products_count = await extract_products(db2, doc2, products_list, page_count)

            async with AsyncSessionLocal() as db2:
                doc2 = await db2.get(Document, doc_id)
                if doc2:
                    doc2.status = "done"
                    doc2.page_count = page_count
                    doc2.parsed_at = datetime.now(timezone.utc)
                    await db2.commit()

            await _log("info", f"✅ {products_count} товарів, {page_count} сторінок")
            logger.info(f"✅ doc#{doc_id} ({doc.name}): {products_count} products, {page_count} pages")
            _live(f"✅ {doc.name} — {products_count} товарів", "done", doc=doc.name)

        except Exception as e:
            logger.error(f"parse error doc#{doc_id}: {e}")
            async with AsyncSessionLocal() as db2:
                doc2 = await db2.get(Document, doc_id)
                if doc2:
                    doc2.status = "error"
                    doc2.error_msg = str(e)[:400]
                    await db2.commit()
            await _log("error", str(e)[:400])
            _live(f"❌ {doc.name}: {str(e)[:120]}", "error", doc=doc.name)
