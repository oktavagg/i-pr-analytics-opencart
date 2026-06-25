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
    top_products,
    validate_order_xml,
    validate_product_xml,
)


LOGO_PATH = Path(__file__).with_name("ipr.jpeg")
DATA_DIR = Path(__file__).with_name("uploaded_data")
ORDERS_XML_PATH = DATA_DIR / "orders.xml"
PRODUCTS_XML_PATH = DATA_DIR / "products.xml"
UPLOAD_META_PATH = DATA_DIR / "metadata.json"

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


@st.cache_data(show_spinner=False)
def parse_xml_cached(xml_bytes: bytes):
    return parse_xml(xml_bytes)


@st.cache_data(show_spinner=False)
def validate_order_xml_cached(xml_bytes: bytes):
    return validate_order_xml(xml_bytes)


@st.cache_data(show_spinner=False)
def validate_product_xml_cached(xml_bytes: bytes):
    return validate_product_xml(xml_bytes)


def stored_import_exists() -> bool:
    paths = (ORDERS_XML_PATH, PRODUCTS_XML_PATH)
    return all(path.is_file() and path.stat().st_size > 0 for path in paths)


def save_uploaded_files(orders_file, products_file) -> None:
    orders_bytes = orders_file.getvalue()
    products_bytes = products_file.getvalue()

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
            "orders_name": orders_file.name,
            "products_name": products_file.name,
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


def delete_uploaded_files() -> None:
    for path in (ORDERS_XML_PATH, PRODUCTS_XML_PATH, UPLOAD_META_PATH):
        path.unlink(missing_ok=True)

    parse_xml_cached.clear()
    validate_order_xml_cached.clear()
    validate_product_xml_cached.clear()

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
            <div class="import-step">ПЕРВЫЙ ШАГ</div>
            <h2>Загрузите данные магазина</h2>
            <p>Для запуска системы нужны два XML-файла: заказы и полный каталог товаров.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    orders_column, products_column = st.columns(2, gap="large")
    with orders_column:
        st.markdown("### 01. Заказы")
        st.caption("XML с заказами и товарами внутри каждого заказа")
        orders_file = st.file_uploader(
            "Файл заказов",
            type=["xml"],
            key="initial_orders_xml",
            label_visibility="collapsed",
        )

    with products_column:
        st.markdown("### 02. Товары")
        st.caption("XML со всеми товарами интернет-магазина")
        products_file = st.file_uploader(
            "Файл товаров",
            type=["xml"],
            key="initial_products_xml",
            label_visibility="collapsed",
        )

    files_ready = orders_file is not None and products_file is not None
    if not files_ready:
        st.caption("Продолжение откроется после загрузки обоих файлов.")
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
            background: #ffffff !important;
            color: #111111 !important;
        }

        body, p, span, label, div, h1, h2, h3, h4, h5, h6 {
            color: #111111;
        }

        [data-testid="stHeader"] {
            background: rgba(255, 255, 255, 0.98) !important;
        }

        [data-testid="stSidebar"] {
            background: #FFFEEE !important;
            border-right: 1px solid #D9D267;
        }

        [data-testid="stSidebar"] * {
            color: #111111 !important;
        }

        [data-testid="stSidebar"] hr {
            border-color: #D9D267 !important;
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
            width: 2.45rem !important;
            height: 2.45rem !important;
            align-items: center !important;
            justify-content: center !important;
            background: #FBF560 !important;
            border: 1px solid #111111 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
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

        [data-testid="stSidebar"] [role="radiogroup"] {
            gap: 6px;
            margin-bottom: 14px;
        }

        [data-testid="stSidebar"] [role="radio"] {
            padding: 9px 10px;
            background: #FFFFFF;
            border: 1px solid #D9D267;
        }

        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] {
            background: #FBF560;
            border-color: #111111;
            font-weight: 800;
        }

        .sidebar-product-title {
            margin: 0 0 10px;
            padding: 12px 14px;
            background: #111111;
            color: #FFFFFF !important;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .sidebar-product-title * {
            color: #FFFFFF !important;
        }

        .nav-group-heading {
            margin: 24px 0 7px;
            padding: 0 5px;
            color: #111111 !important;
            font-size: 1rem;
            font-weight: 800;
            line-height: 1.25;
        }

        [data-testid="stSidebar"] .stButton {
            margin: 0 0 2px;
        }

        [data-testid="stSidebar"] .stButton > button {
            min-height: 2.15rem;
            padding: 0.38rem 0.7rem 0.38rem 1.05rem;
            justify-content: flex-start;
            text-align: left;
            background: transparent !important;
            border: 0 !important;
            border-left: 3px solid transparent !important;
            font-size: 0.88rem;
            font-weight: 600 !important;
            line-height: 1.2;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: #FFF9B5 !important;
            border-left-color: #D8D142 !important;
        }

        [data-testid="stSidebar"] button[kind="primary"],
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
            background: #FBF560 !important;
            border-left: 3px solid #111111 !important;
            font-weight: 800 !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {
            background: #FBF560 !important;
            border: 1px solid #111111 !important;
            padding-left: 0.75rem;
            justify-content: center;
        }

        .page-heading {
            margin: 4px 0 22px;
            padding-bottom: 14px;
            border-bottom: 1px solid #D9D267;
        }

        .page-heading h2 {
            margin: 0 0 5px;
            font-size: 1.75rem;
            line-height: 1.2;
        }

        .page-heading p {
            margin: 0;
            color: #4B4B4B !important;
        }

        .module-placeholder {
            min-height: 310px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: flex-start;
            padding: 38px;
            background: #FFFEEE;
            border: 1px solid #D9D267;
            border-left: 6px solid #FBF560;
        }

        .module-placeholder .module-status {
            display: inline-block;
            margin-bottom: 14px;
            padding: 5px 9px;
            background: #FBF560;
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
            color: #4B4B4B !important;
            line-height: 1.55;
        }


        .period-control-box {
            margin: 0 0 18px;
            padding: 18px 20px;
            background: #FFFEEE;
            border: 1px solid #D9D267;
            border-left: 5px solid #FBF560;
        }

        .period-control-box h3 {
            margin: 0 0 5px;
            font-size: 1.05rem;
        }

        .period-control-box p {
            margin: 0;
            color: #4B4B4B !important;
            font-size: 0.9rem;
        }

        .period-comparison-title {
            margin: 8px 0 14px;
            padding: 17px 20px;
            background: #FBF560;
            color: #111111 !important;
            border: 1px solid #111111;
            font-size: 1.2rem;
            font-weight: 800;
            text-align: center;
        }

        .period-comparison-title * {
            color: #111111 !important;
        }

        .comparison-table-wrap {
            width: 100%;
            overflow-x: auto;
            margin-bottom: 14px;
            border: 1px solid #D9D267;
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
            background: #FBF560;
            color: #111111 !important;
            border-right: 1px solid #A49E23;
            border-bottom: 1px solid #111111;
            text-align: center;
            font-weight: 800;
        }

        .comparison-table th:first-child {
            text-align: left;
        }

        .comparison-table td {
            padding: 10px 12px;
            border-right: 1px solid #C5CCD6;
            border-bottom: 1px solid #C5CCD6;
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
            background: #E8F3E4;
        }

        .comparison-table tr.negative td {
            background: #FCE8DE;
        }

        .comparison-table tr.neutral td {
            background: #F4F4F4;
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
            color: #4B4B4B !important;
            font-weight: 700;
        }

        .comparison-footnote {
            margin: 8px 0 22px;
            color: #5B5B5B !important;
            font-size: 0.86rem;
            font-style: italic;
        }

        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 3rem;
            max-width: 1480px;
        }

        .brand-header {
            position: relative;
            display: flex;
            align-items: center;
            gap: 28px;
            min-height: 104px;
            padding: 22px 28px;
            border: 1px solid #D9D267;
            border-top: 4px solid #FBF560;
            border-radius: 0;
            background: linear-gradient(120deg, #FFFFFF 0%, #FFFEEE 60%, #FFFCD0 100%);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.04);
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
            border-radius: 0;
            background: rgba(251, 245, 96, 0.18);
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
            border-radius: 0;
            background: #FFFFFF;
            border: 1px solid #D9D267;
        }

        .brand-logo img {
            display: block;
            width: 178px;
            max-height: 68px;
            object-fit: contain;
        }

        .brand-logo-missing {
            color: #111111;
            font-size: 0.86rem;
            text-align: center;
        }

        .brand-copy {
            position: relative;
            z-index: 1;
        }

        .brand-copy h1 {
            margin: 0 0 7px 0;
            color: #111111 !important;
            font-size: 2rem;
            line-height: 1.12;
            font-weight: 750;
        }

        .brand-copy p {
            margin: 0;
            color: #4B4B4B !important;
            font-size: 0.98rem;
        }

        [data-testid="stMetric"] {
            position: relative;
            overflow: hidden;
            background: #FFFFFF;
            border: 1px solid #D9D267;
            padding: 18px;
            border-radius: 0;
            box-shadow: none;
        }

        [data-testid="stMetric"]::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 3px;
            background: #FBF560;
        }

        [data-testid="stMetricLabel"] {
            color: #4B4B4B !important;
            font-size: 0.86rem;
        }

        [data-testid="stMetricValue"] {
            color: #111111 !important;
            font-size: 1.55rem;
            font-weight: 720;
        }

        [data-testid="stMetricDelta"] svg {
            fill: currentColor;
        }

        div[data-testid="stPlotlyChart"],
        div[data-testid="stDataFrame"] {
            background: #FFFFFF;
            border: 1px solid #D9D267;
            border-radius: 0;
            padding: 8px;
            box-shadow: none;
        }

        .summary-box {
            background: linear-gradient(120deg, #FFFEEE 0%, #FFFCD0 100%);
            border: 1px solid #D9D267;
            border-left: 4px solid #FBF560;
            border-radius: 0;
            padding: 18px 20px;
            margin: 12px 0 18px 0;
            color: #111111 !important;
            line-height: 1.55;
        }

        .summary-box * {
            color: #111111 !important;
        }

        .recommendation-card {
            height: 100%;
            background: #FFFFFF;
            border: 1px solid #D9D267;
            border-left: 4px solid #FBF560;
            border-radius: 0;
            padding: 17px 18px;
            box-shadow: none;
        }

        .recommendation-card.high {
            border-left-color: #111111;
            background: #FFFEEE;
        }

        .recommendation-card.medium {
            border-left-color: #D8D142;
            background: #FFFEEE;
        }

        .recommendation-card.positive {
            border-left-color: #FBF560;
            background: #FFFCD0;
        }

        .recommendation-card h4 {
            margin: 0 0 7px 0;
            color: #111111 !important;
            font-size: 1rem;
        }

        .recommendation-card p {
            margin: 0;
            color: #4B4B4B !important;
            line-height: 1.45;
            font-size: 0.91rem;
        }

        .small-muted,
        [data-testid="stCaptionContainer"] {
            color: #4B4B4B !important;
            font-size: 0.9rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            border-bottom: 1px solid #D9D267;
        }

        .stTabs [data-baseweb="tab"] {
            background: #FFFEEE;
            border: 1px solid #D9D267;
            border-bottom: 0;
            border-radius: 0;
            padding: 8px 14px;
            color: #111111 !important;
        }

        .stTabs [aria-selected="true"] {
            background: #FBF560 !important;
            color: #111111 !important;
            font-weight: 700;
        }

        .stButton > button,
        .stDownloadButton > button {
            background: #FBF560 !important;
            color: #111111 !important;
            border: 1px solid #111111 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            font-weight: 700 !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            background: #FFF89A !important;
            border-color: #111111 !important;
        }

        [data-baseweb="select"] > div,
        [data-testid="stDateInput"] input,
        [data-testid="stDateInput"] > div,
        [data-baseweb="tag"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            border-color: #D9D267 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
        }

        [data-baseweb="tag"] {
            background: #FBF560 !important;
            color: #111111 !important;
            border: 1px solid #111111 !important;
        }

        [data-baseweb="tag"] span,
        [data-baseweb="tag"] svg {
            color: #111111 !important;
            fill: #111111 !important;
        }

        [data-testid="stFileUploaderDropzone"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D9D267 !important;
            border-radius: 0 !important;
        }

        [data-testid="stFileUploaderDropzone"] button {
            background: #FBF560 !important;
            color: #111111 !important;
            border: 1px solid #111111 !important;
            border-radius: 0 !important;
        }

        [data-testid="stFileUploader"] section {
            background: #FFFFFF !important;
            border-radius: 0 !important;
        }

        [data-testid="stFileUploaderFile"] {
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #111111 !important;
            border-radius: 0 !important;
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
            background: #FBF560 !important;
            color: #111111 !important;
            border: 1px solid #111111 !important;
            border-radius: 0 !important;
        }

        [data-testid="stFileUploaderFileDeleteBtn"] * {
            color: #111111 !important;
            fill: #111111 !important;
        }

        .stAlert {
            background: #FFFCD0 !important;
            color: #111111 !important;
            border: 1px solid #D9D267 !important;
            border-radius: 0 !important;
        }


        .import-intro {
            padding: 30px 32px;
            margin: 8px 0 24px;
            background: #FFFEEE;
            border: 1px solid #D9D267;
            border-left: 6px solid #FBF560;
        }

        .import-intro h2 {
            margin: 7px 0 8px;
            font-size: 1.75rem;
        }

        .import-intro p {
            margin: 0;
            color: #4B4B4B !important;
        }

        .import-step {
            display: inline-block;
            padding: 4px 8px;
            background: #FBF560;
            border: 1px solid #111111;
            font-size: 0.75rem;
            font-weight: 800;
            letter-spacing: 0.08em;
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
                font-size: 1.55rem;
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
        priority = "high" if waiting_share >= 8 else "medium"
        recommendations.append(
            {
                "priority": priority,
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
                "priority": "high" if repeat_share < 15 else "medium",
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
                "priority": "positive",
                "title": "Повторные клиенты дают заметную долю",
                "text": (
                    f"На повторных клиентов приходится {repeat_share:.1f}% суммы. "
                    "Сохраните этот сегмент и выделите для него отдельные предложения."
                ),
            }
        )

    single_item_share = float(metrics["single_item_share"])
    if single_item_share >= 45:
        recommendations.append(
            {
                "priority": "medium",
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
                "priority": "medium",
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
                "priority": "high",
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
                "priority": "positive",
                "title": "Продажи ускоряются",
                "text": (
                    f"Средняя дневная сумма выросла на {trend:.1f}% во второй половине периода. "
                    "Проверьте запас популярных товаров и масштабируйте источники, которые дали рост."
                ),
            }
        )

    top5_share = float(metrics["top5_share"])
    if top5_share >= 40:
        recommendations.append(
            {
                "priority": "high" if top5_share >= 60 else "medium",
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
                "priority": "positive",
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
                    "priority": "positive",
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
                "priority": "medium",
                "title": "Проверить слабые товары",
                "text": (
                    f"Найдено {low_movers_count} товаров с низкими продажами и длительным перерывом. "
                    "Проверьте цену, карточку товара, наличие и целесообразность закупки."
                ),
            }
        )

    recommendations.append(
        {
            "priority": "positive",
            "title": f"Лучший день для активности: {metrics['best_weekday']}",
            "text": (
                "В этот день средняя дневная сумма выше остальных. "
                "Планируйте рассылки, публикации и обновление рекламных кампаний перед этим днем."
            ),
        }
    )

    priority_order = {"high": 0, "medium": 1, "positive": 2}
    return sorted(recommendations, key=lambda item: priority_order[item["priority"]])[:8]





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
            if st.button(
                page_title,
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
    selected_dates,
    selected_statuses: list[str],
) -> dict[str, object] | None:
    all_orders = parsed.orders.copy()
    all_items = parsed.items.copy()
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
        "all_orders": all_orders,
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
    render_page_heading(page_key)

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
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if parsed.orders.empty:
        st.warning("В XML нет заказов с разрешенными статусами.")
        st.stop()

    all_orders = parsed.orders.copy()
    min_date = all_orders["order_date"].min().date()
    max_date = all_orders["order_date"].max().date()

    with st.sidebar:
        active_module = st.radio(
            "Основной раздел",
            options=["01 Аналитика продаж", "02 CRO аудит"],
            key="main_module",
            label_visibility="collapsed",
        )

        if active_module == "01 Аналитика продаж":
            selected_page = render_analytics_navigation()
        else:
            selected_page = "cro"

        with st.expander("Фильтры", expanded=False):
            if selected_page == "period_changes":
                selected_dates = (min_date, max_date)
                st.caption(
                    "Диапазон для страницы «Изменения за период» "
                    "выбирается в верхней части самой страницы."
                )
            else:
                selected_dates = st.date_input(
                    "Период",
                    value=(min_date, max_date),
                    min_value=min_date,
                    max_value=max_date,
                    key="analytics_period",
                )
            selected_statuses = st.multiselect(
                "Статусы",
                options=list(ALLOWED_STATUSES),
                default=list(ALLOWED_STATUSES),
                key="analytics_statuses",
            )

        with st.expander("Загруженные файлы", expanded=False):
            render_loaded_files_sidebar()

    if active_module == "02 CRO аудит":
        cro_module.render_cro_page(LOGO_PATH)
        return

    render_header()

    context = prepare_analytics_context(parsed, selected_dates, selected_statuses)
    if context is None:
        render_page_heading(selected_page)
        st.warning("По выбранным фильтрам нет заказов.")
        return

    render_selected_analytics_page(selected_page, context)

    st.caption(
        f"В XML найдено {parsed.total_xml_orders} заказов. "
        f"Исключено по статусу: {parsed.skipped_by_status}. "
        f"В текущем фильтре: {int(context['order_count'])}."
    )


if __name__ == "__main__":
    main()
