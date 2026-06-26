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

import conclusions
import cro_module
import customers as customers_module
import orders as orders_module
import products as products_module

from analytics_ui import format_money, format_number, safe_percent
from xml_parser import (
    ALLOWED_STATUSES,
    parse_xml,
    parse_product_catalog,
    top_products,
    validate_order_xml,
    validate_product_xml,
)


LOGO_PATH = Path(__file__).with_name("ipr.jpeg")
DATA_DIR = Path(__file__).with_name("uploaded_data")
ORDERS_XML_PATH = DATA_DIR / "orders.xml"
PRODUCTS_XML_PATH = DATA_DIR / "products.xml"
UPLOAD_META_PATH = DATA_DIR / "metadata.json"
DEMO_DATA_DIR = Path(__file__).with_name("files_test")
DEMO_ORDERS_PATH = DEMO_DATA_DIR / "order (24).xml"
DEMO_PRODUCTS_PATH = DEMO_DATA_DIR / "product (2).xml"

BRAND_BLACK = "#111111"
BRAND_YELLOW = "#FBF560"
BRAND_GOLD = "#D8D142"
BRAND_DARK_GOLD = "#A49E23"
BRAND_PALE = "#FFFCD0"
BRAND_CREAM = "#FFFEEE"
BRAND_BORDER = "#D9D267"
BRAND_MUTED = "#4B4B4B"
CHART_COLORS = [
    "#FBF560",
    "#D8D142",
    "#111111",
    "#F6F29E",
    "#A49E23",
    "#FFF9B5",
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
    conclusions,
    orders_module,
    customers_module,
    products_module,
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
    "period_changes": "monitoring",
    "recommendations": "tips_and_updates",
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
    "top_customers_revenue": "military_tech",
    "top_customers_orders": "emoji_events",
    "products_no_sales": "inventory",
    "top_products_revenue": "sell",
    "top_products_units": "bar_chart",
    "products_together": "device_hub",
}


PERIOD_PRESETS = (
    "За всё время",
    "Последние 30 дней",
    "Последние 90 дней",
    "Свой диапазон",
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
    missing = [
        path.name
        for path in (DEMO_ORDERS_PATH, DEMO_PRODUCTS_PATH)
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(
            "В папке files_test отсутствуют демо-файлы: "
            + ", ".join(missing)
        )

    save_xml_bytes(
        orders_bytes=DEMO_ORDERS_PATH.read_bytes(),
        products_bytes=DEMO_PRODUCTS_PATH.read_bytes(),
        orders_name=DEMO_ORDERS_PATH.name,
        products_name=DEMO_PRODUCTS_PATH.name,
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


def render_import_screen() -> None:
    render_header()
    st.markdown(
        """
        <div class="import-intro">
            <h2>Загрузите данные магазина</h2>
            <p>Для запуска системы нужны два XML-файла: заказы и полный каталог товаров.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    orders_column, products_column = st.columns(2, gap="large")
    with orders_column:
        with st.container(key="orders_upload_card"):
            st.markdown("### 01. Заказы")
            st.caption("XML с заказами и товарами внутри каждого заказа")
            orders_file = st.file_uploader(
                "Файл заказов",
                type=["xml"],
                key="initial_orders_xml",
                label_visibility="collapsed",
            )

    with products_column:
        with st.container(key="products_upload_card"):
            st.markdown("### 02. Товары")
            st.caption("XML со всеми товарами интернет-магазина")
            products_file = st.file_uploader(
                "Файл товаров",
                type=["xml"],
                key="initial_products_xml",
                label_visibility="collapsed",
            )

    st.markdown("### 03. Демо-данные")
    st.caption("Быстрый запуск системы без загрузки собственных файлов")

    with st.container(key="demo_import_block"):
        demo_copy, demo_action = st.columns([2.2, 1], vertical_alignment="center")
        with demo_copy:
            st.markdown(
                """
                <div class="demo-import-copy">
                    <h3>Посмотреть систему на готовом примере</h3>
                    <p>Будут загружены тестовые заказы и каталог из папки <b>files_test</b>.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with demo_action:
            if st.button(
                "Использовать демо-данные",
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
        st.caption("Продолжение откроется после загрузки обоих файлов или выбора демо-данных.")
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
            "В XML заказов нет заказов с поддерживаемыми статусами: "
            + ", ".join(ALLOWED_STATUSES)
            + "."
        )
        return

    st.success(
        f"Файлы проверены: {order_summary.total_orders} заказов и "
        f"{product_summary.total_products} товаров."
    )

    if st.button("Сохранить файлы и открыть систему", width="stretch"):
        try:
            save_uploaded_files(orders_file, products_file)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
            return
        st.rerun()

def render_loaded_files_sidebar() -> None:
    metadata = load_upload_metadata()
    orders_name = str(metadata.get("orders_name", "orders.xml"))
    products_name = str(metadata.get("products_name", "products.xml"))
    orders_size = int(metadata.get("orders_size", ORDERS_XML_PATH.stat().st_size))
    products_size = int(metadata.get("products_size", PRODUCTS_XML_PATH.stat().st_size))

    st.header("Загруженные данные")
    st.caption(f"Заказы: {orders_name}, {format_file_size(orders_size)}")
    st.caption(f"Товары: {products_name}, {format_file_size(products_size)}")
    if st.button("Удалить загруженные файлы", width="stretch"):
        delete_uploaded_files()
        st.rerun()





def apply_theme() -> None:
    st.markdown(

        """
        <style>
        :root {
            color-scheme: light;
            --ipr-black: #111111;
            --ipr-yellow: #FBF560;
            --ipr-gold: #D8D142;
            --ipr-pale: #FFFCD0;
            --ipr-cream: #FFFEEE;
            --ipr-border: #D9D267;
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

        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarCollapseButton"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            z-index: 1000000 !important;
        }

        [data-testid="stSidebarCollapsedControl"] {
            position: fixed !important;
            top: 0.75rem !important;
            left: 0.75rem !important;
            width: 2.5rem !important;
            height: 2.5rem !important;
            align-items: center !important;
            justify-content: center !important;
            background: #FFFFFF !important;
            border: 1px solid #E7EAF0 !important;
            border-radius: 11px !important;
            box-shadow: 0 8px 24px rgba(17, 17, 17, 0.08) !important;
            transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease !important;
        }

        [data-testid="stSidebarCollapsedControl"]:hover {
            background: #F4C430 !important;
            border-color: #F4C430 !important;
            transform: translateY(-1px);
        }

        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapseButton"] button {
            color: #111111 !important;
            background: transparent !important;
        }

        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="stSidebarCollapseButton"] svg {
            color: #111111 !important;
            fill: #111111 !important;
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
            background: linear-gradient(90deg, #F4C430 0%, #F8E16A 100%);
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
            background: linear-gradient(90deg, #F4C430 0%, #F8E16A 100%);
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
            background: linear-gradient(90deg, #F4C430 0%, #F8E16A 100%);
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
            border-left: 5px solid #F4C430;
        }

        .module-placeholder .module-status {
            display: inline-block;
            margin-bottom: 14px;
            padding: 5px 9px;
            background: linear-gradient(90deg, #F4C430 0%, #F8E16A 100%);
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
            border-left: 4px solid #F4C430;
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
            background: linear-gradient(135deg, #FFFFFF 0%, #FCFCFD 70%, #FFF8D8 100%);
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
            background: linear-gradient(90deg, #F4C430 0%, #F8E16A 100%);
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
            border-left: 4px solid #F4C430;
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
            background: #FFF8EE;
        }

        .recommendation-card.recommendation {
            border-left-color: #A49E23;
            background: #FFFBEB;
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
            background: linear-gradient(90deg, #F4C430 0%, #F8E16A 100%);
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
            background: #FFFCD0 !important;
            color: #111111 !important;
            border: 1px solid #D9D267 !important;
            border-radius: 12px !important;
        }


        .import-intro {
            padding: 28px 30px;
            margin: 8px 0 24px;
            background: #FFFFFF;
            border: 1px solid #E7EAF0;
            border-left: 4px solid #F4C430;
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
            background: #FFFEEE !important;
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
            flex: 0 0 38px;
            width: 38px;
            height: 38px;
            border-radius: 12px;
            background: #FFF7D6;
            color: #9A7300 !important;
            font-size: 1.2rem !important;
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
            font-size: 0.84rem !important;
            font-weight: 700 !important;
        }

        .st-key-page_period_filter [data-testid="stSegmentedControl"] button[aria-pressed="true"],
        .st-key-page_period_filter [data-baseweb="button-group"] button[aria-pressed="true"],
        .st-key-page_period_filter [data-testid="stSegmentedControl"] button[data-active="true"] {
            background: #FFFFFF !important;
            color: #111827 !important;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08) !important;
        }

        .st-key-page_period_filter [data-testid="stDateInput"] {
            margin-top: 12px;
        }

        .period-filter-result {
            display: flex;
            align-items: center;
            gap: 9px;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #EEF1F5;
            color: #667085 !important;
            font-size: 0.84rem;
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
        <div class="sidebar-brand">
            <div class="sidebar-brand-logo">{logo_html}</div>
            <h2>Аналитика магазина</h2>
            <p>Продажи, товары, покупатели и бизнес-рекомендации</p>
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
        return pd.DataFrame(columns=["Товар 1", "Товар 2", "Совместных заказов"])

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
            "Совместных заказов": count,
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


def build_recommendations(metrics: dict[str, object], products: pd.DataFrame) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []

    waiting_share = float(metrics["waiting_share"])
    waiting_count = int(metrics["waiting_count"])
    waiting_revenue = float(metrics["waiting_revenue"])
    if waiting_count > 0:
        recommendations.append(
            {
                "priority": "critical" if waiting_share >= 8 else "important",
                "title": "Отработать заказы в ожидании",
                "text": (
                    f"В статусе «Очікування» находится {waiting_count} заказов на "
                    f"{format_money(waiting_revenue)}, это {waiting_share:.1f}% суммы. "
                    "Проверьте оплату и свяжитесь с клиентами по старым заказам."
                ),
            }
        )

    repeat_share = float(metrics["repeat_revenue_share"])
    if repeat_share < 25:
        recommendations.append(
            {
                "priority": "critical" if repeat_share < 15 else "important",
                "title": "Увеличить повторные продажи",
                "text": (
                    f"Повторные клиенты формируют {repeat_share:.1f}% суммы. "
                    "Запустите сообщение после покупки, персональный промокод и напоминание о повторном заказе."
                ),
            }
        )
    else:
        recommendations.append(
            {
                "priority": "recommendation",
                "title": "Развивать сегмент повторных клиентов",
                "text": (
                    f"На повторных клиентов приходится {repeat_share:.1f}% суммы. "
                    "Сохраните этот сегмент и подготовьте для него отдельные предложения."
                ),
            }
        )

    single_item_share = float(metrics["single_item_share"])
    if single_item_share >= 45:
        recommendations.append(
            {
                "priority": "important",
                "title": "Добавить комплекты и допродажи",
                "text": (
                    f"{single_item_share:.1f}% заказов содержат только один товар. "
                    "Добавьте блоки «С этим покупают», готовые комплекты и предложение второго товара в корзине."
                ),
            }
        )

    liqpay_share = float(metrics["liqpay_share"])
    if liqpay_share < 30:
        recommendations.append(
            {
                "priority": "recommendation",
                "title": "Повысить долю онлайн-оплаты",
                "text": (
                    f"LiqPay используется примерно в {liqpay_share:.1f}% заказов. "
                    "Проверьте заметность способа оплаты и протестируйте небольшую выгоду за оплату онлайн."
                ),
            }
        )

    trend = float(metrics["period_trend"])
    if trend <= -12:
        recommendations.append(
            {
                "priority": "critical",
                "title": "Продажи во второй половине периода снизились",
                "text": (
                    f"Средняя дневная сумма снизилась на {abs(trend):.1f}%. "
                    "Сравните наличие лидеров, рекламную активность и количество заказов по дням."
                ),
            }
        )
    elif trend >= 12:
        recommendations.append(
            {
                "priority": "recommendation",
                "title": "Закрепить рост продаж",
                "text": (
                    f"Средняя дневная сумма выросла на {trend:.1f}% во второй половине периода. "
                    "Проверьте запас популярных товаров и источники, которые дали рост."
                ),
            }
        )

    top5_share = float(metrics["top5_share"])
    if top5_share >= 40:
        recommendations.append(
            {
                "priority": "critical" if top5_share >= 60 else "important",
                "title": "Выручка зависит от нескольких товаров",
                "text": (
                    f"Топ-5 товаров формируют {top5_share:.1f}% суммы. "
                    "Контролируйте их остатки и развивайте товары-замены, чтобы снизить риск просадки."
                ),
            }
        )
    elif not products.empty:
        top_product = products.nlargest(1, "revenue").iloc[0]
        recommendations.append(
            {
                "priority": "recommendation",
                "title": "Поддерживать главный товар периода",
                "text": (
                    f"Лидер по сумме: «{top_product['product_name']}». "
                    "Проверьте остаток, рекламные объявления и видимость товара в каталоге."
                ),
            }
        )

    pairs = metrics["pairs"]
    if isinstance(pairs, pd.DataFrame) and not pairs.empty:
        top_pair = pairs.iloc[0]
        if int(top_pair["Совместных заказов"]) >= 3:
            recommendations.append(
                {
                    "priority": "idea",
                    "title": "Создать готовый комплект",
                    "text": (
                        f"«{top_pair['Товар 1']}» и «{top_pair['Товар 2']}» покупали вместе "
                        f"в {int(top_pair['Совместных заказов'])} заказах. Добавьте комплект или взаимную рекомендацию."
                    ),
                }
            )

    low_movers_count = int(metrics["low_movers_count"])
    if low_movers_count:
        recommendations.append(
            {
                "priority": "important",
                "title": "Проверить слабые товары",
                "text": (
                    f"Найдено {low_movers_count} товаров с низкими продажами и длительным перерывом. "
                    "Проверьте цену, карточку товара, наличие и целесообразность закупки."
                ),
            }
        )

    recommendations.append(
        {
            "priority": "idea",
            "title": f"Планировать активность на {metrics['best_weekday']}",
            "text": (
                "В этот день средняя дневная сумма выше остальных. "
                "Планируйте рассылки, публикации и обновление рекламных кампаний перед этим днем."
            ),
        }
    )

    priority_order = {
        "critical": 0,
        "important": 1,
        "recommendation": 2,
        "idea": 3,
    }
    return sorted(
        recommendations,
        key=lambda item: priority_order.get(item["priority"], 9),
    )[:8]



def render_page_heading(page_key: str) -> None:
    title = PAGE_TITLES.get(page_key, "Аналитика")
    description = PAGE_DESCRIPTIONS.get(
        page_key,
        "Раздел подключен к навигации. Аналитический модуль будет добавлен отдельно.",
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
    return f"{start_date:%d.%m.%Y} — {end_date:%d.%m.%Y}"


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


def render_page_period_filter(
    page_key: str,
    min_date: date,
    max_date: date,
) -> tuple[date, date]:
    preset_key = f"period_preset_{page_key}"
    custom_key = f"period_custom_{page_key}"

    if st.session_state.get(preset_key) not in PERIOD_PRESETS:
        st.session_state[preset_key] = "За всё время"

    stored_custom = st.session_state.get(custom_key, (min_date, max_date))
    custom_start, custom_end = _normalise_date_range(stored_custom, min_date, max_date)
    if stored_custom != (custom_start, custom_end):
        st.session_state[custom_key] = (custom_start, custom_end)

    with st.container(key="page_period_filter"):
        st.markdown(
            """
            <div class="period-filter-header">
                <div class="period-filter-icon material-symbols-rounded">date_range</div>
                <div>
                    <div class="period-filter-title">Период отчёта</div>
                    <div class="period-filter-description">Выберите диапазон, который будет применён только к текущему разделу.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        selected_preset = st.segmented_control(
            "Период отчёта",
            PERIOD_PRESETS,
            key=preset_key,
            label_visibility="collapsed",
            width="stretch",
        )

        if selected_preset == "Последние 30 дней":
            start_date = max(min_date, max_date - timedelta(days=29))
            end_date = max_date
        elif selected_preset == "Последние 90 дней":
            start_date = max(min_date, max_date - timedelta(days=89))
            end_date = max_date
        elif selected_preset == "Свой диапазон":
            selected_custom = st.date_input(
                "Выберите начальную и конечную дату",
                min_value=min_date,
                max_value=max_date,
                key=custom_key,
                format="DD.MM.YYYY",
            )
            start_date, end_date = _normalise_date_range(
                selected_custom,
                min_date,
                max_date,
            )
        else:
            start_date = min_date
            end_date = max_date

        period_days = (end_date - start_date).days + 1
        st.markdown(
            f"""
            <div class="period-filter-result">
                <span>Выбран период</span>
                <strong>{_format_report_period(start_date, end_date)}</strong>
                <small>{period_days} календ. дн.</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return start_date, end_date


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
    selected_page = st.session_state.get("analytics_page", "period_changes")
    if selected_page not in PAGE_TITLES:
        selected_page = "period_changes"
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
    for category_module in CATEGORY_MODULES:
        if category_module.render(page_key, context):
            return

    render_placeholder(page_key)


def main() -> None:
    st.set_page_config(
        page_title="I-PR Store Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    apply_theme()

    if not stored_import_exists():
        render_import_screen()
        st.stop()

    try:
        stored_orders_bytes = ORDERS_XML_PATH.read_bytes()
        stored_products_bytes = PRODUCTS_XML_PATH.read_bytes()
        validate_order_xml_cached(stored_orders_bytes)
        validate_product_xml_cached(stored_products_bytes)
    except (OSError, ValueError) as exc:
        render_header()
        st.error(f"Сохраненные данные повреждены: {exc}")
        if st.button("Удалить поврежденные файлы и загрузить заново"):
            delete_uploaded_files()
            st.rerun()
        st.stop()

    try:
        parsed = parse_xml_cached(stored_orders_bytes)
        catalog_data = parse_product_catalog_cached(stored_products_bytes)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if parsed.orders.empty:
        st.warning("В XML нет заказов с разрешенными статусами.")
        st.stop()

    all_orders = parsed.orders.copy()
    min_date = all_orders["order_date"].min().date()
    max_date = all_orders["order_date"].max().date()

    selected_statuses = list(ALLOWED_STATUSES)

    with st.sidebar:
        render_sidebar_brand()
        selected_page = render_analytics_navigation()

        with st.expander("Загруженные файлы", expanded=False):
            render_loaded_files_sidebar()

    render_page_heading(selected_page)
    selected_dates = render_page_period_filter(
        selected_page,
        min_date,
        max_date,
    )

    context = prepare_analytics_context(
        parsed,
        catalog_data.products,
        selected_dates,
        selected_statuses,
    )
    if context is None:
        st.warning("За выбранный период нет заказов с рабочими статусами.")
        return

    render_selected_analytics_page(selected_page, context)

    st.caption(
        f"В XML найдено {parsed.total_xml_orders} заказов. "
        f"Исключено по статусу: {parsed.skipped_by_status}. "
        f"В аналитике учтено: {int(context['order_count'])}."
    )


if __name__ == "__main__":
    main()
