from __future__ import annotations

import base64
import json
import os
from collections import Counter
from datetime import date, timedelta
from html import escape
from itertools import combinations
from pathlib import Path

import pandas as pd
import streamlit as st

import overview_module
import conclusions
import cro_module
import customers as customers_module
import orders as orders_module
import products as products_module

from analytics_ui import format_money, format_number, safe_percent
from lead_mailer import LeadMailError, send_lead_email
from xml_parser import (
    ALLOWED_STATUSES,
    parse_xml,
    parse_product_catalog,
    top_products,
    validate_order_xml,
    validate_product_xml,
)


UHT_LOGO_PATH = Path(__file__).with_name("UHT-24-Blue.png")
IPR_LOGO_PATH = Path(__file__).with_name("ipr.jpeg")
LOGO_PATH = UHT_LOGO_PATH if UHT_LOGO_PATH.exists() else IPR_LOGO_PATH
DATA_DIR = Path(__file__).with_name("uploaded_data")
ORDERS_XML_PATH = DATA_DIR / "orders.xml"
PRODUCTS_XML_PATH = DATA_DIR / "products.xml"
UPLOAD_META_PATH = DATA_DIR / "metadata.json"
DEMO_DATA_DIR = Path(__file__).with_name("files_test")
DEMO_ORDERS_PATH = DEMO_DATA_DIR / "order.xml"
DEMO_PRODUCTS_PATH = DEMO_DATA_DIR / "product.xml"
LEGACY_DEMO_ORDERS_PATH = DEMO_DATA_DIR / "order (24).xml"
LEGACY_DEMO_PRODUCTS_PATH = DEMO_DATA_DIR / "product (2).xml"

BRAND_BLACK = "#111111"
BRAND_YELLOW = "#007FC5"
BRAND_GOLD = "#007FC5"
BRAND_DARK_GOLD = "#005F95"
BRAND_PALE = "#E5F5FC"
BRAND_CREAM = "#F4FBFF"
BRAND_BORDER = "#B8DFF2"
BRAND_MUTED = "#4B4B4B"
CHART_COLORS = [
    "#007FC5",
    "#007FC5",
    "#111111",
    "#AEE3FF",
    "#005F95",
    "#E5F5FC",
]
WEEKDAY_NAMES = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}
WEEKDAY_ORDER = list(WEEKDAY_NAMES.values())


CATEGORY_MODULES = (
    overview_module,
    orders_module,
    customers_module,
    products_module,
    conclusions,
)

ANALYTICS_NAVIGATION = [
    (category_module.CATEGORY_TITLE, category_module.PAGES)
    for category_module in CATEGORY_MODULES
]

PAGE_TITLES = {
    page_key: page_title
    for _, pages in ANALYTICS_NAVIGATION
    for page_key, page_title in pages
}

PAGE_DESCRIPTIONS = {
    page_key: description
    for category_module in CATEGORY_MODULES
    for page_key, description in category_module.PAGE_DESCRIPTIONS.items()
}

PAGE_ICONS = {
    "overview": "dashboard",
    "period_changes": "monitoring",
    "revenue": "payments",
    "revenue_segments": "pie_chart",
    "orders_count": "shopping_bag",
    "orders_segments": "grouped_bar_chart",
    "average_check": "receipt_long",
    "check_segments": "balance",
    "items_per_order": "inventory_2",
    "order_statuses": "checklist",
    "order_frequency": "schedule",
    "shipping_rating": "local_shipping",
    "customers_count": "groups",
    "repeat_share": "autorenew",
    "orders_per_customer": "person_search",
    "sleeping_customers": "bedtime",
    "top_customers": "military_tech",
    "top_customers_revenue": "military_tech",
    "top_customers_orders": "emoji_events",
    "active_products_stock": "inventory_2",
    "products_no_sales": "inventory",
    "products_no_views": "visibility_off",
    "product_conversion": "percent",
    "top_products": "sell",
    "top_products_revenue": "sell",
    "top_products_units": "bar_chart",
    "products_together": "device_hub",
}


PERIOD_PRESETS = (
    "День",
    "Неделя",
    "Месяц",
    "Всё время",
    "Кастомный",
)


@st.cache_data(show_spinner=False)
def parse_xml_cached(xml_bytes: bytes):
    return parse_xml(xml_bytes)




@st.cache_data(show_spinner=False)
def parse_product_catalog_cached(xml_bytes: bytes):
    return parse_product_catalog(xml_bytes)


@st.cache_data(show_spinner=False)
def validate_order_xml_cached(xml_bytes: bytes):
    return validate_order_xml(xml_bytes)


@st.cache_data(show_spinner=False)
def validate_product_xml_cached(xml_bytes: bytes):
    return validate_product_xml(xml_bytes)


def stored_import_exists() -> bool:
    paths = (ORDERS_XML_PATH, PRODUCTS_XML_PATH)
    return all(path.is_file() and path.stat().st_size > 0 for path in paths)


def save_xml_bytes(
    orders_bytes: bytes,
    products_bytes: bytes,
    orders_name: str,
    products_name: str,
) -> None:
    # Validate both files again immediately before writing them to disk.
    validate_order_xml_cached(orders_bytes)
    validate_product_xml_cached(products_bytes)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    files = (
        (ORDERS_XML_PATH, orders_bytes),
        (PRODUCTS_XML_PATH, products_bytes),
    )
    temporary_paths: list[Path] = []

    try:
        for destination, content in files:
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            temporary.write_bytes(content)
            temporary_paths.append(temporary)

        for temporary, (destination, _) in zip(temporary_paths, files):
            os.replace(temporary, destination)

        metadata = {
            "orders_name": orders_name,
            "products_name": products_name,
            "orders_size": len(orders_bytes),
            "products_size": len(products_bytes),
        }
        metadata_temporary = UPLOAD_META_PATH.with_suffix(".json.tmp")
        metadata_temporary.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(metadata_temporary, UPLOAD_META_PATH)
    except OSError as exc:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Не удалось сохранить XML-файлы: {exc}") from exc


def save_uploaded_files(orders_file, products_file) -> None:
    save_xml_bytes(
        orders_bytes=orders_file.getvalue(),
        products_bytes=products_file.getvalue(),
        orders_name=orders_file.name,
        products_name=products_file.name,
    )


def load_demo_files() -> None:
    orders_bytes, products_bytes, orders_path, products_path = read_demo_files()
    save_xml_bytes(
        orders_bytes=orders_bytes,
        products_bytes=products_bytes,
        orders_name=orders_path.name,
        products_name=products_path.name,
    )


def delete_uploaded_files() -> None:
    for path in (ORDERS_XML_PATH, PRODUCTS_XML_PATH, UPLOAD_META_PATH):
        path.unlink(missing_ok=True)

    parse_xml_cached.clear()
    validate_order_xml_cached.clear()
    validate_product_xml_cached.clear()
    parse_product_catalog_cached.clear()

    for key in ("initial_orders_xml", "initial_products_xml"):
        st.session_state.pop(key, None)


def load_upload_metadata() -> dict[str, object]:
    if not UPLOAD_META_PATH.exists():
        return {}
    try:
        return json.loads(UPLOAD_META_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def format_file_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} МБ"
    return f"{size / 1024:.0f} КБ"


def get_demo_file_paths() -> tuple[Path, Path]:
    orders_path = DEMO_ORDERS_PATH if DEMO_ORDERS_PATH.exists() else LEGACY_DEMO_ORDERS_PATH
    products_path = DEMO_PRODUCTS_PATH if DEMO_PRODUCTS_PATH.exists() else LEGACY_DEMO_PRODUCTS_PATH
    return orders_path, products_path


def read_demo_files() -> tuple[bytes, bytes, Path, Path]:
    orders_path, products_path = get_demo_file_paths()
    missing = [
        str(path.relative_to(Path(__file__).parent))
        for path in (orders_path, products_path)
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError("У папці files_test відсутні файли: " + ", ".join(missing))
    return orders_path.read_bytes(), products_path.read_bytes(), orders_path, products_path


def render_import_screen() -> None:
    _, center_column, _ = st.columns([1.15, 6, 1.15], gap="large")
    with center_column:
        render_import_logo()
        st.markdown(
            """
            <div class="import-intro">
                <h2>Завантажте дані магазину</h2>
                <p>Для запуску системи потрібні два XML-файли: замовлення і повний каталог товарів.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        orders_column, products_column = st.columns(2, gap="large")
        with orders_column:
            with st.container(key="orders_upload_card"):
                st.markdown("### 01. Замовлення")
                st.caption("XML із замовленнями та товарами всередині кожного замовлення")
                orders_file = st.file_uploader(
                    "Файл замовлень",
                    type=["xml"],
                    key="initial_orders_xml",
                    label_visibility="collapsed",
                )

        with products_column:
            with st.container(key="products_upload_card"):
                st.markdown("### 02. Товари")
                st.caption("XML з усіма товарами інтернет-магазину")
                products_file = st.file_uploader(
                    "Файл товарів",
                    type=["xml"],
                    key="initial_products_xml",
                    label_visibility="collapsed",
                )

        st.markdown("### 03. Демо-дані")
        st.caption("Швидкий запуск системи без завантаження власних файлів")

        with st.container(key="demo_import_block"):
            demo_copy, demo_action = st.columns([1.8, 1], vertical_alignment="center")
            with demo_copy:
                st.markdown(
                    """
                    <div class="demo-import-copy">
                        <h3>Подивитися систему на готовому прикладі</h3>
                        <p>Будуть завантажені тестові замовлення і каталог з папки <b>files_test</b>.</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with demo_action:
                if st.button(
                    "Використати демо-дані",
                    key="use_demo_data",
                    type="secondary",
                    width="stretch",
                ):
                    try:
                        load_demo_files()
                    except (OSError, ValueError, RuntimeError) as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()

        files_ready = orders_file is not None and products_file is not None
        if not files_ready:
            st.caption("Продовження відкриється після завантаження обох файлів або вибору демо-даних.")
            return

    try:
        orders_bytes = orders_file.getvalue()
        products_bytes = products_file.getvalue()
        order_summary = validate_order_xml_cached(orders_bytes)
        product_summary = validate_product_xml_cached(products_bytes)
    except ValueError as exc:
        st.error(str(exc))
        return

    if order_summary.supported_orders == 0:
        st.error(
            "В XML замовлень нет замовлень с поддерживаемыми статусами: "
            + ", ".join(ALLOWED_STATUSES)
            + "."
        )
        return

    st.success(
        f"Файли перевірено: {order_summary.total_orders} замовлень и "
        f"{product_summary.total_products} товарів."
    )

    if st.button("Зберегти файли і відкрити систему", width="stretch"):
        try:
            save_uploaded_files(orders_file, products_file)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
            return
        st.rerun()

def render_loaded_files_sidebar() -> None:
    try:
        _, _, orders_path, products_path = read_demo_files()
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    st.header("Дані презентації")
    st.caption(f"Замовлення: {orders_path.name}, {format_file_size(orders_path.stat().st_size)}")
    st.caption(f"Товари: {products_path.name}, {format_file_size(products_path.stat().st_size)}")
    st.caption("Дані автоматично завантажуються з папки files_test.")





def apply_theme() -> None:
    st.markdown(

        """
        <style>
        :root {
            color-scheme: light;
            --ipr-black: #111111;
            --ipr-yellow: #007FC5;
            --ipr-gold: #007FC5;
            --ipr-pale: #E5F5FC;
            --ipr-cream: #F4FBFF;
            --ipr-border: #B8DFF2;
        }

        html, body, [data-testid="stAppViewContainer"],
        [data-testid="stMain"], .stApp {
            background: #F6F7FB !important;
            color: #111827 !important;
        }

        body, p, span, label, div, h1, h2, h3, h4, h5, h6 {
            color: #111827;
        }

        [data-testid="stHeader"] {
            background: rgba(246, 247, 251, 0.92) !important; border-bottom: 1px solid #ECEFF5;
        }

        [data-testid="stToolbar"],
        [data-testid="stToolbarActions"],
        [data-testid="stToolbarActionButton"],
        [data-testid="stMainMenu"],
        #MainMenu,
        footer,
        ._terminalButton_rix23_138,
        button[data-testid="manage-app-button"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }

        [data-testid="stSidebar"] {
            background: #171B22 !important;
            border-right: 1px solid #232A35;
            min-width: 330px !important;
            max-width: 330px !important;
        }

        [data-testid="stSidebar"] > div:first-child {
            padding-top: 0.9rem;
        }

        [data-testid="stSidebar"] * {
            color: #E7EDF6;
        }

        [data-testid="stSidebar"] hr {
            border-color: #2B3340 !important;
        }

        [data-testid="stSidebar"] ::-webkit-scrollbar {
            width: 6px;
        }

        [data-testid="stSidebar"] ::-webkit-scrollbar-track {
            background: transparent;
        }

        [data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
            background: #434C5E;
            border-radius: 999px;
        }

        @media (min-width: 901px) {
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="stSidebarCollapseButton"] {
                display: none !important;
                visibility: hidden !important;
                opacity: 0 !important;
                pointer-events: none !important;
            }
        }

        @media (max-width: 900px) {
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="stSidebarCollapseButton"] {
                display: flex !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
        }

        .sidebar-brand {
            position: relative;
            margin: 0 0 14px;
            padding: 15px;
            overflow: hidden;
            background: linear-gradient(180deg, #202631 0%, #1B212B 100%);
            border: 1px solid #2B3340;
            border-radius: 18px;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
        }

        .sidebar-brand::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, #007FC5 0%, #3AA7E0 100%);
        }

        .sidebar-brand-logo {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 54px;
            margin-bottom: 12px;
            padding: 8px 10px;
            background: #FFFFFF;
            border: 1px solid #2F3746;
            border-radius: 12px;
        }

        .sidebar-brand-logo img {
            display: block;
            width: 138px;
            max-height: 52px;
            object-fit: contain;
        }

        .sidebar-brand-fallback {
            font-size: 1.25rem;
            font-weight: 900;
            letter-spacing: 0.04em;
        }

        .sidebar-brand h2 {
            margin: 0 0 5px;
            color: #FFFFFF !important;
            font-size: 1rem;
            line-height: 1.25;
        }

        .sidebar-brand p {
            margin: 0;
            color: #AAB4C3 !important;
            font-size: 0.76rem;
            line-height: 1.45;
        }

        .sidebar-brand--compact {
            padding: 14px;
        }

        .sidebar-brand--compact .sidebar-brand-logo {
            margin-bottom: 0;
        }

        .sidebar-mode-label {
            margin: 2px 2px 7px;
            color: #93A0B3 !important;
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }

        [data-testid="stSidebar"] [role="radiogroup"] {
            display: grid !important;
            grid-template-columns: 1fr 1fr;
            gap: 5px;
            margin: 0 0 18px;
            padding: 5px;
            background: #11161D;
            border: 1px solid #2B3340;
            border-radius: 14px;
        }

        [data-testid="stSidebar"] [role="radio"] {
            position: relative;
            min-width: 0;
            min-height: 46px;
            padding: 8px 7px !important;
            justify-content: center;
            text-align: center;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 9px;
            transition: background 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
        }

        [data-testid="stSidebar"] [role="radio"] > div:first-child {
            display: none !important;
        }

        [data-testid="stSidebar"] [role="radio"] p {
            margin: 0;
            color: #AAB4C3 !important;
            font-size: 0.82rem !important;
            font-weight: 700 !important;
            line-height: 1.15 !important;
        }

        [data-testid="stSidebar"] [role="radio"]:hover {
            background: rgba(255, 255, 255, 0.06);
        }

        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] {
            background: #171717;
            border-color: #E7EDF6;
            box-shadow: 0 6px 16px rgba(17, 17, 17, 0.16);
            transform: translateY(-1px);
        }

        [data-testid="stSidebar"] [role="radio"][aria-checked="true"]::after {
            content: "";
            position: absolute;
            top: 7px;
            right: 7px;
            width: 6px;
            height: 6px;
            background: linear-gradient(90deg, #007FC5 0%, #3AA7E0 100%);
            border-radius: 50%;
        }

        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] p,
        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] * {
            color: #FFFFFF !important;
        }

        .nav-group-heading {
            display: flex;
            align-items: center;
            gap: 9px;
            margin: 24px 4px 9px;
            color: #98A3B5 !important;
            font-size: 0.73rem;
            font-weight: 850;
            letter-spacing: 0.085em;
            line-height: 1.2;
            text-transform: uppercase;
        }

        .nav-group-heading::after {
            content: "";
            flex: 1;
            height: 1px;
            background: #313949;
        }

        .st-key-nav_overview button {
            border-color: rgba(244, 196, 48, 0.42) !important;
            background: rgba(244, 196, 48, 0.08) !important;
            color: #FFFFFF !important;
            font-weight: 800 !important;
        }

        .st-key-nav_overview button:hover {
            background: rgba(244, 196, 48, 0.15) !important;
            border-color: rgba(244, 196, 48, 0.58) !important;
        }

        [data-testid="stSidebar"] .stButton {
            margin: 0 0 5px;
        }

        [data-testid="stSidebar"] .stButton > button {
            position: relative;
            min-height: 3rem;
            padding: 0.48rem 0.72rem 0.48rem 0.86rem;
            justify-content: flex-start;
            text-align: left;
            background: transparent !important;
            border: 1px solid transparent !important;
            border-radius: 9px !important;
            box-shadow: none !important;
            font-size: 0.98rem;
            font-weight: 600 !important;
            line-height: 1.2;
            transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease !important;
        }

        [data-testid="stSidebar"] .stButton > button > div {
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 0.52rem;
            text-align: left;
        }

        [data-testid="stSidebar"] .stButton > button p,
        [data-testid="stSidebar"] .stButton > button span,
        [data-testid="stSidebar"] .stButton > button label {
            color: #DDE6F2 !important;
            text-align: left !important;
        }

        [data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] p {
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 0.52rem;
            margin: 0;
            width: 100%;
            text-align: left !important;
        }

        [data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] .material-symbols-rounded {
            font-size: 1.1rem !important;
            line-height: 1;
            flex: 0 0 auto;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: rgba(255, 255, 255, 0.06) !important;
            border-color: #374152 !important;
            box-shadow: 0 10px 22px rgba(0, 0, 0, 0.16) !important;
            transform: translateX(2px);
        }

        [data-testid="stSidebar"] button[kind="primary"],
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
            padding-left: 1.15rem;
            background: #171717 !important;
            border-color: #303A4B !important;
            box-shadow: 0 7px 18px rgba(17, 17, 17, 0.14) !important;
            font-weight: 760 !important;
        }

        [data-testid="stSidebar"] button[kind="primary"]::before,
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"]::before {
            content: "";
            position: absolute;
            left: 7px;
            top: 50%;
            width: 4px;
            height: 18px;
            background: linear-gradient(90deg, #007FC5 0%, #3AA7E0 100%);
            border-radius: 999px;
            transform: translateY(-50%);
        }

        [data-testid="stSidebar"] button[kind="primary"] p,
        [data-testid="stSidebar"] button[kind="primary"] span,
        [data-testid="stSidebar"] button[kind="primary"] label,
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p,
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] span,
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] label {
            color: #FFFFFF !important;
        }

        [data-testid="stSidebar"] button[kind="primary"]:hover,
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
            background: #2B3544 !important;
            border-color: #39465A !important;
            transform: translateX(2px);
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] {
            margin-top: 18px;
            border: 1px solid #2B3340;
            border-radius: 14px;
            overflow: hidden;
            background: rgba(255, 255, 255, 0.03);
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            min-height: 2.6rem;
            padding: 0 0.75rem;
            font-size: 0.84rem;
            font-weight: 750;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {
            background: rgba(255, 255, 255, 0.06) !important;
            border: 1px solid #36404F !important;
            border-radius: 14px !important;
            padding-left: 0.75rem;
            justify-content: center;
        }

        .page-heading {
            margin: 2px 0 18px;
            padding-bottom: 0;
            border-bottom: none;
        }

        .page-heading h2 {
            margin: 0 0 5px;
            font-size: 1.95rem;
            line-height: 1.2;
        }

        .page-heading p {
            margin: 0;
            color: #6B7280 !important;
        }

        .module-placeholder {
            min-height: 280px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: flex-start;
            padding: 38px;
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-left: 5px solid #007FC5;
        }

        .module-placeholder .module-status {
            display: inline-block;
            margin-bottom: 14px;
            padding: 5px 9px;
            background: linear-gradient(90deg, #007FC5 0%, #3AA7E0 100%);
            border: 1px solid #111111;
            font-size: 0.75rem;
            font-weight: 800;
            letter-spacing: 0.05em;
        }

        .module-placeholder h3 {
            margin: 0 0 9px;
            font-size: 1.45rem;
        }

        .module-placeholder p {
            max-width: 680px;
            margin: 0;
            color: #6B7280 !important;
            line-height: 1.55;
        }


        .period-control-box {
            margin: 0 0 18px;
            padding: 18px 20px;
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-left: 4px solid #007FC5;
        }

        .period-control-box h3 {
            margin: 0 0 5px;
            font-size: 1.05rem;
        }

        .period-control-box p {
            margin: 0;
            color: #6B7280 !important;
            font-size: 0.9rem;
        }

        .period-comparison-title {
            margin: 8px 0 14px;
            padding: 16px 18px;
            background: #FFFFFF;
            color: #111827 !important;
            border: 1px solid #E7EAF0;
            border-radius: 16px;
            font-size: 1.14rem;
            font-weight: 800;
            text-align: center;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }

        .period-comparison-title * {
            color: #111111 !important;
        }

        .comparison-table-wrap {
            width: 100%;
            overflow-x: auto;
            margin-bottom: 14px;
            border: 1px solid #E7EAF0;
        }

        .comparison-table {
            width: 100%;
            min-width: 920px;
            border-collapse: collapse;
            background: #FFFFFF;
            font-size: 0.91rem;
        }

        .comparison-table th {
            padding: 11px 12px;
            background: #F8FAFC;
            color: #6B7280 !important;
            border-right: 1px solid #EEF2F7;
            border-bottom: 1px solid #EEF2F7;
            text-align: center;
            font-weight: 800;
        }

        .comparison-table th:first-child {
            text-align: left;
        }

        .comparison-table td {
            padding: 10px 12px;
            border-right: 1px solid #EEF2F7;
            border-bottom: 1px solid #EEF2F7;
            color: #111111 !important;
            vertical-align: middle;
        }

        .comparison-table td:first-child {
            width: 31%;
            font-weight: 750;
        }

        .comparison-table td:nth-child(2),
        .comparison-table td:nth-child(3),
        .comparison-table td:nth-child(4) {
            text-align: center;
            white-space: nowrap;
        }

        .comparison-table td:nth-child(3) {
            font-weight: 800;
        }

        .comparison-table td:last-child {
            width: 25%;
            white-space: nowrap;
        }

        .comparison-table tr.positive td {
            background: #F3F9F4;
        }

        .comparison-table tr.negative td {
            background: #FFF4F1;
        }

        .comparison-table tr.neutral td {
            background: #F8FAFC;
        }

        .comparison-table .change-positive,
        .comparison-table .conclusion-positive {
            color: #1A6A2A !important;
            font-weight: 800;
        }

        .comparison-table .change-negative,
        .comparison-table .conclusion-negative {
            color: #C40018 !important;
            font-weight: 800;
        }

        .comparison-table .change-neutral,
        .comparison-table .conclusion-neutral {
            color: #6B7280 !important;
            font-weight: 700;
        }

        .comparison-footnote {
            margin: 8px 0 22px;
            color: #5B5B5B !important;
            font-size: 0.86rem;
            font-style: normal;
        }

        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 2.4rem;
            padding-left: 1.35rem;
            padding-right: 1.35rem;
            max-width: none;
        }

        .brand-header {
            position: relative;
            display: flex;
            align-items: center;
            gap: 28px;
            min-height: 104px;
            padding: 22px 28px;
            border: 1px solid #E7EAF0;
            border-top: 1px solid #E7EAF0;
            border-radius: 20px;
            background: linear-gradient(135deg, #FFFFFF 0%, #FCFCFD 70%, #EAF7FD 100%);
            box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
            margin-bottom: 22px;
            overflow: hidden;
        }

        .brand-header::after {
            content: "";
            position: absolute;
            right: -44px;
            top: -80px;
            width: 230px;
            height: 230px;
            border-radius: 28px;
            background: rgba(244, 196, 48, 0.12);
            transform: rotate(12deg);
        }

        .brand-logo {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 205px;
            min-height: 72px;
            padding: 8px 14px;
            border-radius: 14px;
            background: #FFFFFF;
            border: 1px solid #ECEFF5;
        }

        .brand-logo img {
            display: block;
            width: 178px;
            max-height: 68px;
            object-fit: contain;
        }

        .brand-logo-missing {
            color: #111827;
            font-size: 0.86rem;
            text-align: center;
        }

        .brand-copy {
            position: relative;
            z-index: 1;
        }

        .brand-copy h1 {
            margin: 0 0 7px 0;
            color: #111827 !important;
            font-size: 2.05rem;
            line-height: 1.12;
            font-weight: 750;
        }

        .brand-copy p {
            margin: 0;
            color: #6B7280 !important;
            font-size: 0.98rem;
        }

        [data-testid="stMetric"] {
            position: relative;
            overflow: hidden;
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            padding: 18px;
            border-radius: 18px;
            box-shadow: 0 10px 26px rgba(15, 23, 42, 0.05);
        }

        [data-testid="stMetric"]::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, #007FC5 0%, #3AA7E0 100%);
        }

        [data-testid="stMetricLabel"] {
            color: #6B7280 !important;
            font-size: 0.86rem;
        }

        [data-testid="stMetricValue"] {
            color: #111111 !important;
            font-size: 1.7rem;
            font-weight: 720;
        }

        [data-testid="stMetricDelta"] svg {
            fill: currentColor;
        }

        div[data-testid="stPlotlyChart"],
        div[data-testid="stDataFrame"],
        .element-container:has(> div[data-testid="stDataFrame"]) {
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-radius: 18px;
            padding: 10px 12px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
        }

        .summary-box {
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-left: 4px solid #007FC5;
            border-radius: 16px;
            padding: 18px 20px;
            margin: 12px 0 18px 0;
            color: #111111 !important;
            line-height: 1.55;
        }

        .summary-box * {
            color: #111111 !important;
        }

        .monthly-table-wrap {
            width: 100%;
            overflow-x: auto;
            border: 1px solid #E7EAF0;
            background: #FFFFFF;
        }

        .monthly-report-table {
            width: 100%;
            min-width: 520px;
            border-collapse: collapse;
            font-size: 0.88rem;
        }

        .monthly-report-table th {
            padding: 11px 10px;
            background: #F8FAFC;
            color: #6B7280 !important;
            border-right: 1px solid #EEF2F7;
            border-bottom: 1px solid #EEF2F7;
            text-align: center;
            font-weight: 800;
            white-space: nowrap;
        }

        .monthly-report-table td {
            padding: 10px;
            color: #111111 !important;
            border-right: 1px solid #EEF2F7;
            border-bottom: 1px solid #EEF2F7;
            text-align: right;
            white-space: nowrap;
        }

        .monthly-report-table td:first-child,
        .monthly-report-table th:first-child {
            text-align: left;
            font-weight: 750;
        }

        .monthly-report-table tbody tr:nth-child(even) td {
            background: #FBFCFE;
        }

        .monthly-report-table tfoot td {
            background: #F8FAFC;
            border-top: 2px solid #111111;
            font-weight: 850;
        }

        .recommendation-card {
            height: 100%;
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-left: 5px solid #CBD5E1;
            border-radius: 18px;
            padding: 18px 18px;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }

        .recommendation-card.critical {
            border-left-color: #C40018;
            background: #FFF4F2;
        }

        .recommendation-card.important {
            border-left-color: #D86A00;
            background: #F4FBFF;
        }

        .recommendation-card.recommendation {
            border-left-color: #005F95;
            background: #F4FBFF;
        }

        .recommendation-card.idea {
            border-left-color: #111827;
            background: #F8FAFC;
        }

        .recommendation-priority {
            display: inline-block;
            margin: 0 0 10px;
            padding: 4px 8px;
            border: 1px solid #111111;
            background: linear-gradient(90deg, #007FC5 0%, #3AA7E0 100%);
            color: #111111 !important;
            font-size: 0.72rem;
            font-weight: 850;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .recommendation-card.critical .recommendation-priority {
            background: #C40018;
            color: #FFFFFF !important;
            border-color: #C40018;
        }

        .recommendation-card.important .recommendation-priority {
            background: #D86A00;
            color: #FFFFFF !important;
            border-color: #D86A00;
        }

        .recommendation-card.idea .recommendation-priority {
            background: #1F2937;
            color: #FFFFFF !important;
        }

        .recommendation-card h4 {
            margin: 0 0 7px 0;
            color: #111111 !important;
            font-size: 1rem;
        }

        .recommendation-card p {
            margin: 0;
            color: #6B7280 !important;
            line-height: 1.45;
            font-size: 0.91rem;
        }

        .small-muted,
        [data-testid="stCaptionContainer"] {
            color: #6B7280 !important;
            font-size: 0.9rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            border-bottom: 1px solid #E7EAF0;
        }

        .stTabs [data-baseweb="tab"] {
            background: #FBFCFE;
            border: 1px solid #E7EAF0;
            border-bottom: 0;
            border-radius: 12px 12px 0 0;
            padding: 8px 14px;
            color: #111111 !important;
        }

        .stTabs [aria-selected="true"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            font-weight: 700;
        }

        .stButton > button,
        .stDownloadButton > button {
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D7DCE5 !important;
            border-radius: 12px !important;
            box-shadow: none !important;
            font-weight: 700 !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            background: #F8FAFC !important;
            border-color: #C8D0DB !important;
        }

        [data-baseweb="select"] > div,
        [data-testid="stDateInput"] input,
        [data-testid="stDateInput"] > div,
        [data-baseweb="tag"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            border-color: #D8DEE8 !important;
            border-radius: 12px !important;
            box-shadow: none !important;
        }

        [data-baseweb="tag"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D7DCE5 !important;
        }

        [data-baseweb="tag"] span,
        [data-baseweb="tag"] svg {
            color: #111111 !important;
            fill: #111111 !important;
        }

        [data-testid="stFileUploaderDropzone"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px dashed #D6DCE7 !important;
            border-radius: 14px !important;
        }

        [data-testid="stFileUploaderDropzone"] button {
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D7DCE5 !important;
            border-radius: 12px !important;
        }

        [data-testid="stFileUploader"] section {
            background: #FFFFFF !important;
            border-radius: 14px !important;
        }

        [data-testid="stFileUploaderFile"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D8D8D8 !important;
            border-radius: 12px !important;
            box-shadow: none !important;
        }

        [data-testid="stFileUploaderFile"] * {
            color: #111111 !important;
            fill: #111111 !important;
        }

        [data-testid="stFileUploaderFileName"] {
            color: #111111 !important;
        }

        [data-testid="stFileUploaderFileDeleteBtn"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D7DCE5 !important;
            border-radius: 7px !important;
        }

        [data-testid="stFileUploaderFileDeleteBtn"] * {
            color: #111111 !important;
            fill: #111111 !important;
        }

        .stAlert {
            background: #E5F5FC !important;
            color: #111111 !important;
            border: 1px solid #B8DFF2 !important;
            border-radius: 12px !important;
        }


        .import-intro {
            padding: 28px 30px;
            margin: 8px 0 24px;
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-left: 4px solid #007FC5;
            border-radius: 18px;
            box-shadow: 0 14px 32px rgba(15, 23, 42, 0.05);
            transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
        }

        .import-intro:hover {
            transform: translateY(-1px);
            border-color: #D6D09A;
            box-shadow: 0 12px 30px rgba(17, 17, 17, 0.055);
        }

        .st-key-orders_upload_card,
        .st-key-products_upload_card {
            height: 100%;
            padding: 20px 20px 18px;
            background: #FFFFFF;
            border: 1px solid #E5E5E5;
            border-radius: 12px;
            box-shadow: 0 8px 22px rgba(17, 17, 17, 0.03);
            transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
        }

        .st-key-orders_upload_card:hover,
        .st-key-products_upload_card:hover {
            transform: translateY(-1px);
            border-color: #D7D18C;
            box-shadow: 0 12px 28px rgba(17, 17, 17, 0.05);
        }

        .st-key-orders_upload_card h3,
        .st-key-products_upload_card h3 {
            margin-top: 0;
        }

        .st-key-demo_import_block {
            margin: 0 0 20px;
            padding: 18px 20px;
            background: #F6FBF6;
            border: 1px solid #D7E8D7;
            border-left: 4px solid #85B87B;
            border-radius: 18px;
            box-shadow: 0 14px 32px rgba(70, 112, 61, 0.05);
            transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
        }

        .st-key-demo_import_block:hover {
            transform: translateY(-1px);
            border-color: #8DB985;
            box-shadow: 0 12px 28px rgba(70, 112, 61, 0.08);
        }

        .demo-import-copy h3 {
            margin: 5px 0 6px;
            font-size: 1.16rem;
        }

        .demo-import-copy p {
            margin: 0;
            color: #3F4F3B !important;
            font-size: 0.9rem;
        }

        .st-key-demo_import_block .stButton > button {
            min-height: 3rem;
            background: #ECF7E8 !important;
            color: #111111 !important;
            border: 1px solid #7FAA76 !important;
            border-radius: 9px !important;
            transition: transform 150ms ease, background 150ms ease, border-color 150ms ease;
        }

        .st-key-demo_import_block .stButton > button *,
        .st-key-demo_import_block .stButton > button p,
        .st-key-demo_import_block .stButton > button span {
            color: #111111 !important;
            fill: #111111 !important;
        }

        .st-key-demo_import_block .stButton > button:hover {
            transform: translateY(-1px);
            background: #DDF0D8 !important;
            color: #111111 !important;
            border-color: #4F7D47 !important;
        }

        .import-divider {
            position: relative;
            margin: 2px 0 22px;
            text-align: center;
        }

        .import-divider::before {
            content: "";
            position: absolute;
            top: 50%;
            left: 0;
            right: 0;
            height: 1px;
            background: #E7EAF0;
        }

        .import-divider span {
            position: relative;
            display: inline-block;
            padding: 0 12px;
            background: #FFFFFF;
            color: #6B7280 !important;
            font-size: 0.98rem;
        }

        [data-testid="stFileUploaderDropzone"] {
            transition: transform 150ms ease, border-color 150ms ease, background 150ms ease;
        }

        [data-testid="stFileUploaderDropzone"]:hover {
            transform: translateY(-1px);
            border-color: #C8D0DB !important;
            background: #F4FBFF !important;
        }

        .import-intro h2 {
            margin: 0 0 8px;
            font-size: 1.95rem;
        }

        .import-intro p {
            margin: 0;
            color: #6B7280 !important;
        }

        [data-testid="stMainBlockContainer"] {
            max-width: none !important;
        }

        .element-container {
            margin-bottom: 0.65rem;
        }

        [data-testid="stMetric"]:hover,
        div[data-testid="stPlotlyChart"]:hover,
        div[data-testid="stDataFrame"]:hover,
        .monthly-table-wrap:hover,
        .comparison-table-wrap:hover,
        .summary-box:hover {
            box-shadow: 0 16px 34px rgba(15, 23, 42, 0.07);
            border-color: #D7DDE7;
        }

        [data-testid="stMetricLabel"] p {
            text-transform: uppercase;
            letter-spacing: 0.03em;
            font-size: 0.76rem;
            color: #8A94A6 !important;
        }

        [data-testid="stMetricDelta"] {
            font-size: 0.82rem !important;
        }

        [data-testid="stSidebar"] .stRadio label {
            cursor: pointer;
        }

        .page-heading p {
            max-width: 760px;
            font-size: 0.96rem;
        }

        .st-key-page_period_filter {
            margin: 0 0 22px;
            padding: 16px 18px 15px;
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-radius: 18px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.045);
        }

        .date-filter-label {
            color: #8A94A6 !important;
            font-size: 0.96rem;
            font-weight: 750;
            white-space: nowrap;
        }

        .date-filter-arrow {
            color: #B3BBC8 !important;
            font-size: 1.4rem;
            text-align: center;
        }

        .date-filter-current {
            display: inline-flex;
            align-items: center;
            justify-content: flex-end;
            gap: 12px;
            width: 100%;
            color: #8A8F98 !important;
            font-size: 0.95rem;
            text-align: right;
            white-space: nowrap;
        }

        .date-filter-current span {
            color: #8A8F98 !important;
        }

        .date-filter-current strong {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 74px;
            padding: 8px 12px;
            border-radius: 999px;
            background: #FFF2B8;
            border: 1px solid #007FC5;
            color: #111827 !important;
            font-size: 0.92rem;
            font-weight: 850;
            line-height: 1.2;
            box-shadow: 0 6px 14px rgba(244, 196, 48, 0.18);
        }

        .st-key-page_period_filter [data-testid="stDateInput"] {
            width: 100%;
        }

        .st-key-page_period_filter [data-testid="stDateInput"] > div,
        .st-key-page_period_filter [data-testid="stDateInput"] input,
        .st-key-page_period_filter [data-baseweb="input"],
        .st-key-page_period_filter [data-baseweb="input"] > div {
            background: #FFFFFF !important;
            box-shadow: none !important;
            border-color: #DCE3EE !important;
            border-radius: 12px !important;
        }

        .st-key-page_period_filter [data-testid="stDateInput"] input {
            min-height: 2.6rem;
            padding-left: 0.9rem !important;
            padding-right: 0.55rem !important;
            font-weight: 700;
            font-size: 0.96rem;
            letter-spacing: 0;
        }

        .st-key-page_period_filter .stButton > button[kind="primary"],
        .st-key-page_period_filter .stButton > button {
            min-height: 2.6rem;
            min-width: 128px;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            white-space: nowrap !important;
            word-break: normal !important;
            overflow-wrap: normal !important;
            line-height: 1.1 !important;
        }

        .st-key-page_period_filter .stButton > button p,
        .st-key-page_period_filter .stButton > button span,
        .st-key-page_period_filter .stButton > button div {
            white-space: nowrap !important;
            word-break: normal !important;
            overflow-wrap: normal !important;
        }

        .period-filter-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 13px;
        }

        .period-filter-icon {
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 40px;
            width: 40px;
            height: 40px;
            border-radius: 12px;
            background: #EAF7FD;
            color: #006CA8 !important;
        }

        .period-filter-icon svg {
            width: 21px;
            height: 21px;
            display: block;
            color: #006CA8 !important;
        }

        .period-filter-title {
            color: #111827 !important;
            font-size: 0.96rem;
            font-weight: 800;
            line-height: 1.2;
        }

        .period-filter-description {
            margin-top: 3px;
            color: #7A8494 !important;
            font-size: 0.82rem;
            line-height: 1.35;
        }

        .st-key-page_period_filter [data-testid="stSegmentedControl"],
        .st-key-page_period_filter [data-baseweb="button-group"] {
            width: 100%;
            padding: 4px;
            background: #F3F5F8;
            border: 1px solid #E8EBF0;
            border-radius: 13px;
        }

        .st-key-page_period_filter [data-testid="stSegmentedControl"] button,
        .st-key-page_period_filter [data-baseweb="button-group"] button {
            min-height: 2.35rem;
            border: 0 !important;
            border-radius: 10px !important;
            background: transparent !important;
            color: #667085 !important;
            box-shadow: none !important;
            font-size: 0.82rem !important;
            font-weight: 700 !important;
        }

        .st-key-page_period_filter [data-testid="stSegmentedControl"] button[aria-pressed="true"],
        .st-key-page_period_filter [data-baseweb="button-group"] button[aria-pressed="true"],
        .st-key-page_period_filter [data-testid="stSegmentedControl"] button[data-active="true"],
        .st-key-page_period_filter [data-baseweb="button-group"] button[data-active="true"] {
            background: #EAF7FD !important;
            color: #111827 !important;
            border: 1px solid #007FC5 !important;
            box-shadow: 0 6px 14px rgba(244, 196, 48, 0.22) !important;
        }

        .st-key-page_period_filter [data-testid="stSegmentedControl"] button:hover,
        .st-key-page_period_filter [data-baseweb="button-group"] button:hover {
            background: rgba(255, 255, 255, 0.82) !important;
        }

        .st-key-page_period_filter [data-testid="stDateInput"] {
            margin-top: 12px;
        }

        .period-filter-result {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #EEF1F5;
            color: #667085 !important;
            font-size: 0.84rem;
        }

        .period-filter-result-copy {
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 0;
        }

        .period-filter-result span,
        .period-filter-result small {
            color: #7A8494 !important;
        }

        .period-filter-result strong {
            color: #111827 !important;
            font-size: 0.9rem;
        }

        .period-filter-result small {
            margin-left: auto;
            padding: 4px 8px;
            border-radius: 999px;
            background: #F3F5F8;
            font-size: 0.76rem;
        }

        .comparison-table, .monthly-report-table {
            border-radius: 16px;
            overflow: hidden;
        }

        .comparison-table th, .monthly-report-table th {
            font-size: 0.78rem;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }

        .brand-copy p {
            color: #667085 !important;
        }


        .import-logo-wrap {
            display: flex;
            justify-content: center;
            margin: 2rem 0 1.1rem;
        }

        .import-logo {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 220px;
            padding: 16px 22px;
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-radius: 18px;
            box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
        }

        .import-logo img {
            display: block;
            width: 176px;
            max-height: 62px;
            object-fit: contain;
        }

        .import-intro {
            text-align: center;
            margin-bottom: 1.35rem;
        }

        .import-intro p {
            max-width: 620px;
            margin: 0.55rem auto 0;
        }

        @media (max-width: 800px) {
            .brand-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 16px;
                padding: 22px;
            }

            .brand-logo {
                flex-basis: auto;
            }

            .brand-copy h1 {
                font-size: 1.7rem;
            }
        }


        @media (max-width: 1180px) {
            [data-testid="stSidebar"] {
                min-width: 300px !important;
                max-width: 300px !important;
            }

            .st-key-page_period_filter .stButton > button[kind="primary"],
            .st-key-page_period_filter .stButton > button {
                min-width: 112px;
                font-size: 0.88rem !important;
            }
        }

        @media (max-width: 900px) {
            [data-testid="stMainBlockContainer"] {
                padding-left: 0.9rem !important;
                padding-right: 0.9rem !important;
                padding-top: 1rem !important;
            }

            h1, .page-heading h1 {
                font-size: 1.9rem !important;
                line-height: 1.15 !important;
            }

            .st-key-page_period_filter {
                padding: 14px !important;
                border-radius: 16px !important;
            }

            .st-key-page_period_filter [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 0.55rem !important;
            }

            .st-key-page_period_filter [data-testid="column"] {
                min-width: 145px !important;
                width: auto !important;
                flex: 1 1 145px !important;
            }

            .st-key-page_period_filter [data-testid="column"]:first-child {
                min-width: 100% !important;
                flex-basis: 100% !important;
            }

            .date-filter-label,
            .date-filter-current {
                text-align: left !important;
                justify-content: flex-start !important;
            }

            .date-filter-current {
                margin-top: 0.35rem;
                width: 100%;
                flex-wrap: wrap;
                gap: 8px;
            }

            .date-filter-arrow {
                display: none !important;
            }

            [data-testid="stMetric"] {
                padding: 14px 16px !important;
                border-radius: 16px !important;
            }

            div[data-testid="stPlotlyChart"],
            div[data-testid="stDataFrame"],
            .summary-box,
            .monthly-table-wrap,
            .comparison-table-wrap {
                border-radius: 16px !important;
                overflow-x: auto !important;
            }

            [data-testid="stDataFrame"] {
                max-width: 100% !important;
                overflow-x: auto !important;
            }
        }

        @media (max-width: 640px) {
            [data-testid="stMainBlockContainer"] {
                padding-left: 0.7rem !important;
                padding-right: 0.7rem !important;
            }

            .st-key-page_period_filter [data-testid="column"] {
                min-width: 100% !important;
                flex-basis: 100% !important;
            }

            .st-key-page_period_filter .stButton > button,
            .st-key-page_period_filter [data-testid="stDateInput"] input {
                width: 100% !important;
            }

            .date-filter-current strong {
                width: 100%;
            }
        }

        </style>
        """
,
        unsafe_allow_html=True,
    )





def render_header() -> None:
    if LOGO_PATH.exists():
        logo_base64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        logo_html = (
            f'<img src="data:image/jpeg;base64,{logo_base64}" '
            'alt="IPR ecommerce agency">'
        )
    else:
        logo_html = (
            '<div class="brand-logo-missing">'
            'Добавьте файл <b>ipr.jpeg</b><br>в корень проекта'
            '</div>'
        )

    st.markdown(
        f"""
        <div class="brand-header">
            <div class="brand-logo">{logo_html}</div>
            <div class="brand-copy">
                <h1>Аналитика интернет-магазина</h1>
                <p>Продажи, товары, клиенты и автоматические бизнес-рекомендации</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_import_logo() -> None:
    if LOGO_PATH.exists():
        logo_base64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        logo_html = (
            f'<img src="data:image/jpeg;base64,{logo_base64}" '
            'alt="IPR ecommerce agency">'
        )
    else:
        logo_html = '<div class="brand-logo-missing">I-PR</div>'

    st.markdown(
        f"""
        <div class="import-logo-wrap">
            <div class="import-logo">{logo_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    if LOGO_PATH.exists():
        logo_base64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        logo_html = (
            f'<img src="data:image/jpeg;base64,{logo_base64}" '
            'alt="IPR ecommerce agency">'
        )
    else:
        logo_html = '<div class="sidebar-brand-fallback">I-PR</div>'

    st.markdown(
        f"""
        <div class="sidebar-brand sidebar-brand--compact">
            <div class="sidebar-brand-logo">{logo_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def product_analytics(items: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    if items.empty:
        return pd.DataFrame()

    products = top_products(items).copy()
    last_sales = (
        items.groupby(["product_id", "product_name", "sku"], as_index=False)
        .agg(last_sale=("order_date", "max"), average_price=("unit_price", "mean"))
    )
    products = products.merge(
        last_sales,
        on=["product_id", "product_name", "sku"],
        how="left",
    )

    period_days = max((end_date - start_date).days + 1, 1)
    first_days = max(period_days // 2, 1)
    second_days = max(period_days - first_days, 1)
    split_date = start_date + timedelta(days=first_days)

    first_items = items[items["order_date"].dt.date < split_date]
    second_items = items[items["order_date"].dt.date >= split_date]

    first_quantity = first_items.groupby("product_id")["quantity"].sum()
    second_quantity = second_items.groupby("product_id")["quantity"].sum()

    products["first_units"] = products["product_id"].map(first_quantity).fillna(0)
    products["second_units"] = products["product_id"].map(second_quantity).fillna(0)
    products["first_daily_rate"] = products["first_units"] / first_days
    products["second_daily_rate"] = products["second_units"] / second_days

    def growth(row: pd.Series) -> float | None:
        if row["first_daily_rate"] == 0:
            return 100.0 if row["second_daily_rate"] > 0 else 0.0
        return (
            (row["second_daily_rate"] - row["first_daily_rate"])
            / row["first_daily_rate"]
            * 100
        )

    products["growth_percent"] = products.apply(growth, axis=1)
    products["days_since_last_sale"] = (
        pd.Timestamp(end_date) - products["last_sale"].dt.normalize()
    ).dt.days.clip(lower=0)

    return products


def product_pairs(items: pd.DataFrame) -> pd.DataFrame:
    if items.empty:
        return pd.DataFrame(columns=["Товар 1", "Товар 2", "Совместных замовлень"])

    names = (
        items.drop_duplicates("product_id")
        .set_index("product_id")["product_name"]
        .to_dict()
    )
    counter: Counter[tuple[str, str]] = Counter()

    for _, group in items.groupby("order_id"):
        product_ids = sorted(set(group["product_id"].astype(str)))
        for pair in combinations(product_ids, 2):
            counter[pair] += 1

    rows = [
        {
            "Товар 1": names.get(first, first),
            "Товар 2": names.get(second, second),
            "Совместных замовлень": count,
        }
        for (first, second), count in counter.most_common(10)
    ]
    return pd.DataFrame(rows)


def calculate_business_metrics(
    orders: pd.DataFrame,
    items: pd.DataFrame,
    products: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    revenue = float(orders["order_total"].sum())
    order_count = int(orders["order_id"].nunique())
    customer_summary = (
        orders.groupby("customer_key", as_index=False)
        .agg(orders=("order_id", "nunique"), revenue=("order_total", "sum"))
    )
    repeat_keys = set(customer_summary.loc[customer_summary["orders"] >= 2, "customer_key"])
    repeat_revenue = float(orders.loc[orders["customer_key"].isin(repeat_keys), "order_total"].sum())

    top5_revenue = float(products.nlargest(5, "revenue")["revenue"].sum()) if not products.empty else 0.0
    waiting_orders = orders[orders["status"] == "Очікування"]
    liqpay_orders = orders[
        (orders["status"] == "Успішна оплата LiqPay")
        | orders["payment_method"].str.contains("LiqPay", case=False, na=False)
    ]

    single_item_orders = int((orders["item_quantity"] <= 1).sum())
    average_items = float(orders["item_quantity"].mean()) if order_count else 0.0

    daily = (
        orders.assign(day=orders["order_date"].dt.floor("D"))
        .groupby("day", as_index=False)
        .agg(revenue=("order_total", "sum"), orders=("order_id", "nunique"))
    )

    period_days = max((end_date - start_date).days + 1, 1)
    split_index = max(period_days // 2, 1)
    split_date = pd.Timestamp(start_date + timedelta(days=split_index))
    first_days = max(split_index, 1)
    second_days = max(period_days - split_index, 1)
    first_revenue = float(daily.loc[daily["day"] < split_date, "revenue"].sum())
    second_revenue = float(daily.loc[daily["day"] >= split_date, "revenue"].sum())
    first_daily = first_revenue / first_days
    second_daily = second_revenue / second_days
    period_trend = ((second_daily - first_daily) / first_daily * 100) if first_daily else 0.0

    weekday_daily = daily.copy()
    weekday_daily["weekday_num"] = weekday_daily["day"].dt.weekday
    weekday_summary = (
        weekday_daily.groupby("weekday_num", as_index=False)
        .agg(average_daily_revenue=("revenue", "mean"), total_orders=("orders", "sum"))
    )
    best_weekday_num = int(weekday_summary.nlargest(1, "average_daily_revenue")["weekday_num"].iloc[0])

    threshold_days = min(21, max(7, period_days // 3))
    low_movers = products[
        (products["sold_units"] <= 2)
        & (products["days_since_last_sale"] >= threshold_days)
    ] if not products.empty else pd.DataFrame()

    pairs = product_pairs(items)

    return {
        "revenue": revenue,
        "order_count": order_count,
        "median_check": float(orders["order_total"].median()),
        "average_items": average_items,
        "repeat_revenue_share": safe_percent(repeat_revenue, revenue),
        "top5_share": safe_percent(top5_revenue, revenue),
        "waiting_revenue": float(waiting_orders["order_total"].sum()),
        "waiting_count": int(waiting_orders["order_id"].nunique()),
        "waiting_share": safe_percent(float(waiting_orders["order_total"].sum()), revenue),
        "liqpay_share": safe_percent(int(liqpay_orders["order_id"].nunique()), order_count),
        "single_item_share": safe_percent(single_item_orders, order_count),
        "period_trend": period_trend,
        "best_weekday": WEEKDAY_NAMES[best_weekday_num],
        "low_movers_count": int(len(low_movers)),
        "low_movers": low_movers,
        "pairs": pairs,
    }


def build_recommendations(
    metrics: dict[str, object],
    products: pd.DataFrame,
) -> list[dict[str, object]]:
    recommendations: list[dict[str, object]] = []

    waiting_share = float(metrics["waiting_share"])
    waiting_count = int(metrics["waiting_count"])
    waiting_revenue = float(metrics["waiting_revenue"])
    if waiting_count > 0:
        recommendations.append(
            {
                "priority": "critical" if waiting_share >= 8 else "important",
                "title": "Снизить количество замовлень в ожидании",
                "text": (
                    f"В статусе «Очікування» находится {waiting_count} замовлень на "
                    f"{format_money(waiting_revenue)}, это {waiting_share:.1f}% суммы. "
                    "Часть клиентов может теряться на оплате или после оформления заказа."
                ),
                "actions": [
                    "Добавить понятный экран успешного оформления с дальнейшими шагами.",
                    "Показывать статус оплаты и кнопку повторной оплаты в кабинете и письме.",
                    "Добавить автоматическое напоминание о незавершённой оплате.",
                    "Проверить ошибки оплаты на мобильных устройствах.",
                ],
            }
        )

    repeat_share = float(metrics["repeat_revenue_share"])
    if repeat_share < 25:
        recommendations.append(
            {
                "priority": "critical" if repeat_share < 15 else "important",
                "title": "Увеличить повторные покупки",
                "text": (
                    f"Повторные клиенты формируют {repeat_share:.1f}% оборота. "
                    "Сайт почти не возвращает покупателя после первой покупки."
                ),
                "actions": [
                    "Добавить кнопку «Повторить заказ» в личном кабинете.",
                    "Показывать персональные рекомендации на основе прошлой покупки.",
                    "Добавить блок повторной покупки расходных товарів с ориентировочным сроком.",
                    "Запустить email или push-цепочку после заказа.",
                ],
            }
        )
    else:
        recommendations.append(
            {
                "priority": "recommendation",
                "title": "Развивать персонализацию для постоянных клиентов",
                "text": (
                    f"Повторные клиенты формируют {repeat_share:.1f}% оборота. "
                    "Этот сегмент уже приносит заметную часть продаж."
                ),
                "actions": [
                    "Добавить персональную подборку товарів в кабинете клиента.",
                    "Показывать историю замовлень и быстрое повторение покупки.",
                    "Вывести индивидуальные предложения и бонусы для постоянных клиентов.",
                ],
            }
        )

    single_item_share = float(metrics["single_item_share"])
    if single_item_share >= 45:
        recommendations.append(
            {
                "priority": "important",
                "title": "Увеличить количество товарів в заказе",
                "text": (
                    f"{single_item_share:.1f}% замовлень содержат только один товар. "
                    "Сайт слабо помогает клиенту подобрать дополнения."
                ),
                "actions": [
                    "Добавить блок «С этим товаром покупают» в карточке товара.",
                    "Показывать допродажи в корзине без перехода на отдельную страницу.",
                    "Создать готовые комплекты с понятной выгодой.",
                    "Показывать прогресс до бесплатной доставки.",
                ],
            }
        )

    liqpay_share = float(metrics["liqpay_share"])
    if liqpay_share < 30:
        recommendations.append(
            {
                "priority": "recommendation",
                "title": "Упростить выбор онлайн-оплаты",
                "text": (
                    f"Онлайн-оплата используется примерно в {liqpay_share:.1f}% замовлень. "
                    "Причиной может быть слабая заметность или недостаток доверия."
                ),
                "actions": [
                    "Сделать онлайн-оплату первым и визуально заметным вариантом.",
                    "Кратко объяснить безопасность оплаты рядом с выбором способа.",
                    "Не скрывать итоговую сумму и условия возврата до оплаты.",
                    "Проверить удобство платежного сценария на смартфонах.",
                ],
            }
        )

    trend = float(metrics["period_trend"])
    if trend <= -12:
        recommendations.append(
            {
                "priority": "critical",
                "title": "Усилить главную страницу и категории",
                "text": (
                    f"Средняя дневная сумма во второй половине периода снизилась на {abs(trend):.1f}%. "
                    "Стоит проверить, насколько быстро пользователь находит актуальные товары и предложения."
                ),
                "actions": [
                    "Вывести на главной странице товары-лидеры и актуальные предложения.",
                    "Проверить сортировку категорий, чтобы слабые товары не стояли первыми.",
                    "Улучшить поиск, подсказки и фильтры по ключевым характеристикам.",
                    "Проверить мобильную скорость и стабильность основных страниц.",
                ],
            }
        )
    elif trend >= 12:
        recommendations.append(
            {
                "priority": "recommendation",
                "title": "Закрепить рост через витрину сайта",
                "text": (
                    f"Средняя дневная сумма выросла на {trend:.1f}%. "
                    "Нужно закрепить товары и сценарии, которые дали рост."
                ),
                "actions": [
                    "Вывести растущие товары в заметные блоки главной страницы.",
                    "Добавить на карточках товара связанные альтернативы.",
                    "Сохранить удачные баннеры и порядок блоков на период роста.",
                ],
            }
        )

    top5_share = float(metrics["top5_share"])
    if top5_share >= 40:
        recommendations.append(
            {
                "priority": "critical" if top5_share >= 60 else "important",
                "title": "Снизить зависимость от нескольких товарів",
                "text": (
                    f"Топ-5 товарів формируют {top5_share:.1f}% оборота. "
                    "Если один из лидеров выпадет из наличия, продажи заметно просядут."
                ),
                "actions": [
                    "Добавить блок аналогов и замен на карточках лидеров.",
                    "Показывать альтернативы при отсутствии товара.",
                    "Улучшить перелинковку между товарами одной задачи или категории.",
                    "Вывести похожие товары в поиске и категориях.",
                ],
            }
        )
    elif not products.empty:
        top_product = products.nlargest(1, "revenue").iloc[0]
        recommendations.append(
            {
                "priority": "recommendation",
                "title": "Усилить карточку товара-лидера",
                "text": (
                    f"Лидер по обороту: «{top_product['product_name']}». "
                    "Карточка этого товара влияет на заметную часть результата."
                ),
                "actions": [
                    "Проверить первый экран карточки, цену, наличие и главную кнопку.",
                    "Добавить ответы на частые вопросы и условия доставки.",
                    "Добавить отзывы, характеристики и понятные преимущества.",
                    "Показать совместимые товары и более дорогие альтернативы.",
                ],
            }
        )

    pairs = metrics["pairs"]
    if isinstance(pairs, pd.DataFrame) and not pairs.empty:
        top_pair = pairs.iloc[0]
        if int(top_pair["Совместных замовлень"]) >= 3:
            recommendations.append(
                {
                    "priority": "idea",
                    "title": "Оформить популярную связку как комплект",
                    "text": (
                        f"«{top_pair['Товар 1']}» и «{top_pair['Товар 2']}» покупали вместе "
                        f"в {int(top_pair['Совместных замовлень'])} заказах."
                    ),
                    "actions": [
                        "Создать отдельный комплект с общей ценой и выгодой.",
                        "Добавить взаимные рекомендации в карточках обоих товарів.",
                        "Показать комплект в корзине при добавлении одного из товарів.",
                    ],
                }
            )

    low_movers_count = int(metrics["low_movers_count"])
    if low_movers_count:
        recommendations.append(
            {
                "priority": "important",
                "title": "Переработать карточки слабых товарів",
                "text": (
                    f"Найдено {low_movers_count} товарів с низкими продажами и длительным перерывом. "
                    "Проблема может быть в видимости, цене или качестве карточек."
                ),
                "actions": [
                    "Проверить фото, заголовок, характеристики и описание.",
                    "Добавить товар в подходящие категории и фильтры.",
                    "Проверить индексацию и мета-данные карточки.",
                    "Скрыть или перенести товары, которые больше неактуальны.",
                ],
            }
        )

    recommendations.append(
        {
            "priority": "idea",
            "title": "Улучшить мобильный сценарий покупки",
            "text": (
                "Основная часть покупателей интернет-магазинов использует смартфоны. "
                "Даже небольшие проблемы в карточке или корзине снижают конверсию."
            ),
            "actions": [
                "Добавить фиксированную кнопку покупки на мобильной карточке товара.",
                "Сократить высоту первого экрана и быстрее показывать цену и наличие.",
                "Упростить поля оформления и использовать правильные типы клавиатуры.",
                "Проверить размеры кнопок, отступы и читаемость текста.",
            ],
        }
    )

    recommendations.extend(
        [
            {
                "priority": "recommendation",
                "title": "Улучшить поиск и фильтры каталога",
                "text": (
                    "Часть покупателей знает, какой товар им нужен, но теряется при длинном каталоге. "
                    "Быстрый поиск и понятные фильтры сокращают путь до покупки."
                ),
                "actions": [
                    "Добавить подсказки и исправление опечаток в поиске.",
                    "Вывести популярные фильтры первыми и показывать количество товарів.",
                    "Сохранять выбранные фильтры при возврате из карточки товара.",
                    "Добавить понятное пустое состояние с альтернативами.",
                ],
            },
            {
                "priority": "important",
                "title": "Упростить корзину и оформление заказа",
                "text": (
                    "Чем больше лишних полей и шагов в оформлении, тем выше риск потери клиента перед заказом."
                ),
                "actions": [
                    "Оставить только обязательные поля и объединить шаги оформления.",
                    "Показывать итоговую стоимость, доставку и скидку без скрытых условий.",
                    "Добавить оформление без обязательной регистрации.",
                    "Сохранять корзину и введённые данные после ошибки.",
                ],
            },
            {
                "priority": "recommendation",
                "title": "Повысить доверие на ключевых страницах",
                "text": (
                    "Покупателю нужны быстрые ответы о доставке, оплате, возврате и надёжности магазина."
                ),
                "actions": [
                    "Разместить условия доставки и возврата рядом с кнопкой покупки.",
                    "Добавить реальные отзывы, контакты и юридическую информацию.",
                    "Показывать наличие и актуальный срок отправки.",
                    "Убрать неподтверждённые обещания и устаревшие элементы.",
                ],
            },
            {
                "priority": "idea",
                "title": "Настроить точное отслеживание воронки",
                "text": (
                    "Заказы показывают итог, но не объясняют, на каком шаге сайт теряет пользователей."
                ),
                "actions": [
                    "Настроить события просмотра товара, корзины, оформления и оплаты.",
                    "Отдельно отслеживать ошибки формы и платежа.",
                    "Передавать товар, категорию, стоимость и источник заказа.",
                    "Собрать отдельный отчёт по конверсии каждого шага.",
                ],
            },
        ]
    )

    priority_order = {
        "critical": 0,
        "important": 1,
        "recommendation": 2,
        "idea": 3,
    }
    return sorted(
        recommendations,
        key=lambda item: priority_order.get(str(item["priority"]), 9),
    )[:12]



def _recommendation_priority_label(priority: str) -> str:
    return {
        "critical": "Критично",
        "important": "Важно",
        "recommendation": "Рекомендация",
        "idea": "Идея",
    }.get(priority, "Рекомендация")


def _render_direct_recommendation_form(
    recommendation: dict[str, object],
    context: dict[str, object],
    form_key: str,
) -> None:
    title = str(recommendation.get("title", "Доработка сайта"))
    text_value = str(recommendation.get("text", ""))
    actions = recommendation.get("actions", [])
    actions_list = [str(item) for item in actions] if isinstance(actions, list) else []

    st.markdown(
        f"""
        <div style="margin:0 0 16px;padding:18px 20px;border:1px solid #E7EAF0;border-left:5px solid #007FC5;border-radius:18px;background:#FFFFFF;">
            <div style="font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;color:#8A94A6;">Вы выбрали рекомендацию</div>
            <div style="margin-top:5px;font-size:18px;font-weight:850;color:#111827;">{escape(title)}</div>
            <div style="margin-top:6px;color:#667085;line-height:1.5;">{escape(text_value)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form(form_key, clear_on_submit=False):
        first, second = st.columns(2, gap="large")
        with first:
            project = st.text_input(
                "Проект или адрес сайта",
                placeholder="https://example.com",
            )
            name = st.text_input(
                "Ваше имя",
                placeholder="Как к вам обращаться",
            )
        with second:
            contact = st.text_input(
                "Телефон, email или Telegram",
                placeholder="Контакт для обратной связи",
            )
            comment = st.text_area(
                "Комментарий",
                placeholder="Что нужно учесть или уточнить",
                height=104,
            )

        consent = st.checkbox(
            "Согласен на обработку данных для связи по заявке",
            value=False,
        )
        submitted = st.form_submit_button(
            "Отправить заявку",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return
    if not project.strip():
        st.error("Укажите проект или адрес сайта.")
        return
    if not contact.strip():
        st.error("Укажите контакт для обратной связи.")
        return
    if not consent:
        st.error("Подтвердите согласие на обработку данных.")
        return

    payload = {
        "priority": str(recommendation.get("priority", "recommendation")),
        "priority_label": _recommendation_priority_label(
            str(recommendation.get("priority", "recommendation"))
        ),
        "title": title,
        "text": text_value,
        "actions": actions_list,
    }

    try:
        send_lead_email(
            recommendation=payload,
            project=project.strip(),
            name=name.strip(),
            contact=contact.strip(),
            comment=comment.strip(),
            context={
                "start_date": context.get("start_date"),
                "end_date": context.get("end_date"),
                "revenue": format_money(float(context.get("revenue", 0.0))),
                "order_count": format_number(int(context.get("order_count", 0))),
            },
        )
    except LeadMailError as exc:
        st.error(str(exc))
    else:
        st.success(
            "Заявка отправлена. В письмо переданы название, полный текст рекомендации и список доработок."
        )


def render_recommendations_page_direct(context: dict[str, object]) -> None:
    recommendations = list(context.get("recommendations", []))[:12]
    if not recommendations:
        st.info("За выбранный период рекомендации не сформированы.")
        return

    st.markdown(
        """
        <style>
        [class*="st-key-direct_rec_card_"] {
            height: 100%;
            padding: 18px !important;
            border: 1px solid #E7EAF0 !important;
            border-radius: 18px !important;
            background: #FFFFFF !important;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }
        [class*="st-key-direct_rec_card_"] ul {
            margin: 5px 0 14px;
            padding-left: 20px;
        }
        [class*="st-key-direct_rec_card_"] li {
            margin-bottom: 5px;
            color: #4B5563 !important;
            line-height: 1.45;
        }
        [class*="st-key-direct_rec_button_"] button,
        .st-key-direct_general_cta button {
            min-height: 44px !important;
            background: #007FC5 !important;
            color: #111827 !important;
            border: 1px solid #D6A900 !important;
            font-weight: 850 !important;
            box-shadow: 0 7px 16px rgba(244, 196, 48, 0.22) !important;
        }
        [class*="st-key-direct_rec_button_"] button:hover,
        .st-key-direct_general_cta button:hover {
            background: #007FC5 !important;
            border-color: #005F95 !important;
        }
        .direct-rec-badge {
            display:inline-flex;
            padding:5px 9px;
            border-radius:999px;
            font-size:11px;
            line-height:1;
            font-weight:850;
            text-transform:uppercase;
            letter-spacing:.04em;
        }
        .direct-rec-badge.critical { background:#FEECEC; color:#B42318 !important; }
        .direct-rec-badge.important { background:#EAF7FD; color:#006CA8 !important; }
        .direct-rec-badge.recommendation { background:#EAF2FF; color:#245FA8 !important; }
        .direct-rec-badge.idea { background:#F1ECFF; color:#6842A8 !important; }
        .direct-rec-title { margin:10px 0 7px;font-size:16px;font-weight:850;color:#111827 !important; }
        .direct-rec-text { margin-bottom:12px;color:#4B5563 !important;line-height:1.5; }
        .direct-rec-actions-title { margin:8px 0 5px;font-size:13px;font-weight:850;color:#111827 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    intro_left, intro_right = st.columns([3, 1], vertical_alignment="center")
    with intro_left:
        st.markdown(
            f"""
            <div style="padding:18px 20px;border:1px solid #E7EAF0;border-left:5px solid #007FC5;border-radius:18px;background:#FFFFFF;">
                <div style="font-size:18px;font-weight:850;color:#111827;">{len(recommendations)} рекомендаций по доработке сайта</div>
                <div style="margin-top:5px;color:#667085;">Под каждой рекомендацией есть кнопка «Меня интересует». Выбранный текст полностью попадёт в заявку.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with intro_right:
        if st.button(
            "Обсудить сайт",
            key="direct_general_cta",
            type="primary",
            use_container_width=True,
        ):
            st.session_state["direct_selected_recommendation"] = "general"
            st.rerun()

    selected = st.session_state.get("direct_selected_recommendation")
    if selected == "general":
        _render_direct_recommendation_form(
            {
                "priority": "recommendation",
                "title": "Комплексная доработка интернет-магазина",
                "text": "Нужна консультация и план улучшения сайта на основе данных дашборда.",
                "actions": [
                    "Провести разбор сайта и ключевых сценариев.",
                    "Сформировать приоритетный список доработок.",
                    "Оценить сроки и бюджет реализации.",
                ],
            },
            context,
            "direct_general_lead_form",
        )
    elif isinstance(selected, int) and 0 <= selected < len(recommendations):
        _render_direct_recommendation_form(
            recommendations[selected],
            context,
            f"direct_recommendation_lead_form_{selected}",
        )

    for start in range(0, len(recommendations), 2):
        columns = st.columns(2, gap="large")
        for offset, recommendation in enumerate(recommendations[start:start + 2]):
            index = start + offset
            priority = str(recommendation.get("priority", "recommendation"))
            label = _recommendation_priority_label(priority)
            title = str(recommendation.get("title", "Рекомендация"))
            text_value = str(recommendation.get("text", ""))
            actions = recommendation.get("actions", [])
            actions_list = [str(item) for item in actions] if isinstance(actions, list) else []

            with columns[offset]:
                with st.container(key=f"direct_rec_card_{index}", border=True):
                    st.markdown(
                        f'<span class="direct-rec-badge {escape(priority)}">{escape(label)}</span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="direct-rec-title">{escape(title)}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="direct-rec-text">{escape(text_value)}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        '<div class="direct-rec-actions-title">Что доработать на сайте</div>',
                        unsafe_allow_html=True,
                    )
                    if actions_list:
                        for action in actions_list:
                            st.markdown(f"- {action}")
                    else:
                        st.markdown("- Провести аудит страницы и подготовить план изменений.")

                    if st.button(
                        "Меня интересует",
                        key=f"direct_rec_button_{index}",
                        type="primary",
                        use_container_width=True,
                    ):
                        st.session_state["direct_selected_recommendation"] = index
                        st.rerun()



def render_page_heading(page_key: str) -> None:
    title = PAGE_TITLES.get(page_key, "Аналітика")
    description = PAGE_DESCRIPTIONS.get(
        page_key,
        "Розділ підключено до навігації.",
    )
    st.markdown(
        f"""
        <div class="page-heading">
            <h2>{escape(title)}</h2>
            <p>{escape(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _format_report_period(start_date: date, end_date: date) -> str:
    if start_date == end_date:
        return start_date.strftime("%d.%m.%Y")
    return f"{start_date:%d.%m.%Y} → {end_date:%d.%m.%Y}"


def _normalise_date_range(value, min_date: date, max_date: date) -> tuple[date, date]:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        start_date, end_date = value
    elif isinstance(value, (tuple, list)) and len(value) == 1:
        start_date = value[0]
        end_date = value[0]
    elif isinstance(value, date):
        start_date = value
        end_date = value
    else:
        start_date = min_date
        end_date = max_date

    start_date = max(min_date, min(start_date, max_date))
    end_date = max(min_date, min(end_date, max_date))
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


VIEW_PAGES = {
    "revenue",
    "revenue_segments",
    "orders_count",
    "orders_segments",
    "average_check",
    "check_segments",
    "items_per_order",
    "orders_per_customer",
}

NO_FILTER_PAGES = set()


def render_page_period_filter(
    page_key: str,
    min_date: date,
    max_date: date,
) -> tuple[date, date, str]:
    start_key = f"period_start_{page_key}"
    end_key = f"period_end_{page_key}"
    temp_start_key = f"period_temp_start_{page_key}"
    temp_end_key = f"period_temp_end_{page_key}"
    view_key = f"view_granularity_{page_key}"

    for key, default in ((start_key, min_date), (end_key, max_date), (temp_start_key, min_date), (temp_end_key, max_date)):
        if key not in st.session_state or not isinstance(st.session_state.get(key), date):
            st.session_state[key] = default
        st.session_state[key] = max(min_date, min(st.session_state[key], max_date))

    if st.session_state[start_key] > st.session_state[end_key]:
        st.session_state[start_key], st.session_state[end_key] = st.session_state[end_key], st.session_state[start_key]
    if st.session_state[temp_start_key] > st.session_state[temp_end_key]:
        st.session_state[temp_start_key], st.session_state[temp_end_key] = st.session_state[temp_end_key], st.session_state[temp_start_key]

    if st.session_state.get(view_key) not in ("day", "week", "month"):
        st.session_state[view_key] = "month"

    with st.container(key="page_period_filter"):
        row = st.columns([0.82, 1.08, 0.08, 1.08, 0.9, 0.78, 3.7], vertical_alignment="center")
        row[0].markdown('<div class="date-filter-label">Діапазон дат:</div>', unsafe_allow_html=True)
        with row[1]:
            st.date_input(
                "Початкова дата",
                min_value=min_date,
                max_value=max_date,
                key=temp_start_key,
                format="DD.MM.YYYY",
                label_visibility="collapsed",
            )
        row[2].markdown('<div class="date-filter-arrow">—</div>', unsafe_allow_html=True)
        with row[3]:
            st.date_input(
                "Кінцева дата",
                min_value=min_date,
                max_value=max_date,
                key=temp_end_key,
                format="DD.MM.YYYY",
                label_visibility="collapsed",
            )
        with row[4]:
            if st.button("Застосувати", key=f"period_apply_{page_key}", type="primary", width="stretch"):
                start_date, end_date = _normalise_date_range(
                    (st.session_state[temp_start_key], st.session_state[temp_end_key]),
                    min_date,
                    max_date,
                )
                st.session_state[start_key] = start_date
                st.session_state[end_key] = end_date
                st.rerun()
        with row[5]:
            if st.button("Скинути", key=f"period_reset_{page_key}", width="stretch"):
                st.session_state[start_key] = min_date
                st.session_state[end_key] = max_date
                st.session_state[temp_start_key] = min_date
                st.session_state[temp_end_key] = max_date
                st.session_state[view_key] = "month"
                st.session_state[f"view_selector_{page_key}"] = "За місяць"
                st.rerun()
        applied_days = (st.session_state[end_key] - st.session_state[start_key]).days + 1
        row[6].markdown(
            f'<div class="date-filter-current"><span>Період: {st.session_state[start_key]:%Y-%m-%d} → {st.session_state[end_key]:%Y-%m-%d}</span><strong>{applied_days} днів</strong></div>',
            unsafe_allow_html=True,
        )

        if page_key in VIEW_PAGES:
            view_row = st.columns([0.78, 2.1, 5.46], vertical_alignment="center")
            view_row[0].markdown('<div class="date-filter-label">Представлення:</div>', unsafe_allow_html=True)
            with view_row[1]:
                view_labels = {"day": "За день", "week": "За тиждень", "month": "За місяць"}
                widget_key = f"view_selector_{page_key}"
                if st.session_state.get(widget_key) not in view_labels.values():
                    st.session_state[widget_key] = view_labels[st.session_state[view_key]]
                selected_label = st.segmented_control(
                    "Представлення",
                    list(view_labels.values()),
                    key=widget_key,
                    label_visibility="collapsed",
                    width="stretch",
                )
                reverse = {value: key for key, value in view_labels.items()}
                st.session_state[view_key] = reverse.get(selected_label, "month")

    start_date = st.session_state[start_key]
    end_date = st.session_state[end_key]
    view = st.session_state[view_key]
    st.session_state["current_view_granularity"] = view
    return start_date, end_date, view


def render_placeholder(page_key: str) -> None:
    title = PAGE_TITLES.get(page_key, "Новый раздел")
    st.markdown(
        f"""
        <div class="module-placeholder">
            <div class="module-status">МОДУЛЬ ПОДГОТОВЛЕН</div>
            <h3>{escape(title)}</h3>
            <p>
                Пункт уже добавлен в структуру системы. Расчеты, таблицы и графики
                для него подключим отдельным модулем, не затрагивая остальные разделы.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_analytics_navigation() -> str:
    navigation_version = "ua_rework_v32"
    if st.session_state.get("analytics_navigation_version") != navigation_version:
        st.session_state["analytics_navigation_version"] = navigation_version
        st.session_state["analytics_page"] = "overview"

    selected_page = st.session_state.get("analytics_page", "overview")
    if selected_page not in PAGE_TITLES:
        selected_page = "overview"
        st.session_state["analytics_page"] = selected_page

    for group_title, pages in ANALYTICS_NAVIGATION:
        st.markdown(
            f'<div class="nav-group-heading">{escape(group_title)}</div>',
            unsafe_allow_html=True,
        )
        for page_key, page_title in pages:
            button_label = f":material/{PAGE_ICONS.get(page_key, 'chevron_right')}: {page_title}"
            if st.button(
                button_label,
                key=f"nav_{page_key}",
                width="stretch",
                type="primary" if page_key == selected_page else "secondary",
            ):
                st.session_state["analytics_page"] = page_key
                st.rerun()

    return selected_page


def add_customer_segments(
    period_orders: pd.DataFrame,
    all_orders: pd.DataFrame,
) -> pd.DataFrame:
    segmented = period_orders.copy()
    first_order_dates = all_orders.groupby("customer_key")["order_date"].min()
    segmented["first_order_date"] = segmented["customer_key"].map(first_order_dates)
    segmented["customer_segment"] = "Повторные"
    first_order_mask = (
        segmented["order_date"].dt.normalize()
        == segmented["first_order_date"].dt.normalize()
    )
    segmented.loc[first_order_mask, "customer_segment"] = "Новые"
    return segmented


def prepare_analytics_context(
    parsed,
    product_catalog: pd.DataFrame,
    selected_dates,
    selected_statuses: list[str],
) -> dict[str, object] | None:
    all_orders = parsed.orders.copy()
    all_items = parsed.items.copy()
    all_status_history = getattr(parsed, "all_orders", all_orders).copy()
    min_date = all_orders["order_date"].min().date()
    max_date = all_orders["order_date"].max().date()

    if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        selected_date = selected_dates if isinstance(selected_dates, date) else min_date
        start_date = selected_date
        end_date = selected_date

    orders = all_orders[
        all_orders["order_date"].dt.date.between(start_date, end_date)
        & all_orders["status"].isin(selected_statuses)
    ].copy()
    items = all_items[all_items["order_id"].isin(orders["order_id"])].copy()
    all_status_orders = all_status_history[
        all_status_history["order_date"].dt.date.between(start_date, end_date)
    ].copy()

    if orders.empty:
        return None

    filtered_all_orders = all_orders[all_orders["status"].isin(selected_statuses)].copy()
    segmented_orders = add_customer_segments(orders, filtered_all_orders)

    period_days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    previous_orders = filtered_all_orders[
        filtered_all_orders["order_date"].dt.date.between(previous_start, previous_end)
    ].copy()

    revenue = float(orders["order_total"].sum())
    order_count = int(orders["order_id"].nunique())
    average_check = revenue / order_count if order_count else 0.0
    sold_units = int(items["quantity"].sum()) if not items.empty else 0
    unique_customers = int(orders["customer_key"].nunique())
    customer_orders = orders.groupby("customer_key")["order_id"].nunique()
    repeat_customers = int((customer_orders >= 2).sum())
    repeat_rate = safe_percent(repeat_customers, unique_customers)

    previous_revenue = float(previous_orders["order_total"].sum())
    previous_count = int(previous_orders["order_id"].nunique())
    previous_average = previous_revenue / previous_count if previous_count else 0.0

    products = product_analytics(items, start_date, end_date)
    business = calculate_business_metrics(orders, items, products, start_date, end_date)
    recommendations = build_recommendations(business, products)

    daily = (
        orders.assign(day=orders["order_date"].dt.floor("D"))
        .groupby("day", as_index=False)
        .agg(
            revenue=("order_total", "sum"),
            orders=("order_id", "nunique"),
            average_check=("order_total", "mean"),
        )
    )

    customer_summary = (
        orders.groupby("customer_key", as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            revenue=("order_total", "sum"),
            last_order=("order_date", "max"),
        )
    )
    customer_summary["segment"] = customer_summary["orders"].apply(
        lambda count: "Повторные" if count >= 2 else "Одна покупка"
    )

    return {
        "parsed": parsed,
        "product_catalog": product_catalog,
        "all_items_history": all_items,
        "all_orders": all_orders,
        "all_status_history": all_status_history,
        "all_status_orders": all_status_orders,
        "orders": orders,
        "items": items,
        "segmented_orders": segmented_orders,
        "previous_orders": previous_orders,
        "products": products,
        "business": business,
        "recommendations": recommendations,
        "daily": daily,
        "customer_summary": customer_summary,
        "start_date": start_date,
        "end_date": end_date,
        "revenue": revenue,
        "order_count": order_count,
        "average_check": average_check,
        "sold_units": sold_units,
        "unique_customers": unique_customers,
        "repeat_customers": repeat_customers,
        "repeat_rate": repeat_rate,
        "previous_revenue": previous_revenue,
        "previous_count": previous_count,
        "previous_average": previous_average,
        "selected_statuses": list(selected_statuses),
    }





def render_selected_analytics_page(page_key: str, context: dict[str, object]) -> None:
    if page_key == "recommendations":
        render_recommendations_page_direct(context)
        return

    for category_module in CATEGORY_MODULES:
        if category_module.render(page_key, context):
            return

    render_placeholder(page_key)


def main() -> None:
    st.set_page_config(
        page_title="I-PR Аналітика магазину",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    apply_theme()

    try:
        stored_orders_bytes, stored_products_bytes, _, _ = read_demo_files()
        validate_order_xml_cached(stored_orders_bytes)
        validate_product_xml_cached(stored_products_bytes)
    except (OSError, ValueError, FileNotFoundError) as exc:
        st.error(f"Не вдалося завантажити дані з папки files_test: {exc}")
        st.stop()

    try:
        parsed = parse_xml_cached(stored_orders_bytes)
        catalog_data = parse_product_catalog_cached(stored_products_bytes)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if parsed.orders.empty:
        st.warning("В XML нет замовлень с разрешенными статусами.")
        st.stop()

    all_orders = parsed.orders.copy()
    min_date = all_orders["order_date"].min().date()
    max_date = all_orders["order_date"].max().date()

    selected_statuses = list(ALLOWED_STATUSES)

    with st.sidebar:
        render_sidebar_brand()
        selected_page = render_analytics_navigation()

        with st.expander("Завантажені файли", expanded=False):
            render_loaded_files_sidebar()

    render_page_heading(selected_page)
    selected_start, selected_end, selected_view = render_page_period_filter(
        selected_page,
        min_date,
        max_date,
    )

    context = prepare_analytics_context(
        parsed,
        catalog_data.products,
        (selected_start, selected_end),
        selected_statuses,
    )
    if context is None:
        st.warning("За вибраний період немає замовлень з робочими статусами.")
        return

    context["view_granularity"] = selected_view
    render_selected_analytics_page(selected_page, context)

    st.caption(
        f"В XML знайдено {parsed.total_xml_orders} замовлень. "
        f"Виключено за статусом: {parsed.skipped_by_status}. "
        f"В аналітиці враховано: {int(context['order_count'])}."
    )


if __name__ == "__main__":
    main()
