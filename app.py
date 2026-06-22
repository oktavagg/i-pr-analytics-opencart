from __future__ import annotations

import base64
from collections import Counter
from datetime import date, timedelta
from html import escape
from itertools import combinations
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import cro_module

from parser import ALLOWED_STATUSES, parse_xml, top_products


LOGO_PATH = Path(__file__).with_name("ipr.jpeg")

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


@st.cache_data(show_spinner=False)
def parse_xml_cached(xml_bytes: bytes):
    return parse_xml(xml_bytes)


def format_money(value: float) -> str:
    return f"{value:,.2f} грн".replace(",", " ")


def format_number(value: float | int) -> str:
    return f"{value:,.0f}".replace(",", " ")


def percent_delta(current: float, previous: float) -> str | None:
    if previous == 0:
        return None
    return f"{((current - previous) / previous) * 100:+.1f}%"


def safe_percent(part: float, total: float) -> float:
    return part / total * 100 if total else 0.0


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

        .app-brandbar {
            display: flex;
            align-items: center;
            gap: 18px;
            padding: 16px 20px;
            background: #111111;
            border-bottom: 4px solid #FBF560;
        }

        .app-brandbar__logo {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 170px;
            min-width: 170px;
            height: 62px;
            background: #FFFFFF;
            border: 1px solid #FBF560;
        }

        .app-brandbar__logo img {
            width: 145px;
            max-height: 50px;
            object-fit: contain;
        }

        .app-brandbar__copy strong {
            display: block;
            color: #FFFFFF !important;
            font-size: 1.12rem;
            letter-spacing: 0.01em;
        }

        .app-brandbar__copy span {
            display: block;
            margin-top: 4px;
            color: #D8D8D8 !important;
            font-size: 0.86rem;
        }

        [data-testid="stRadio"] {
            margin: 0 0 22px 0;
        }

        [data-testid="stRadio"] [role="radiogroup"] {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            padding: 10px;
            background: #FFFEEE;
            border: 1px solid #D9D267;
            border-top: 0;
        }

        [data-testid="stRadio"] label {
            display: flex !important;
            align-items: center;
            justify-content: center;
            min-height: 58px;
            margin: 0 !important;
            padding: 10px 18px !important;
            background: #FFFFFF;
            border: 1px solid #111111;
            cursor: pointer;
            transition: background 0.15s ease, transform 0.15s ease;
        }

        [data-testid="stRadio"] label:hover {
            background: #FFFCD0;
        }

        [data-testid="stRadio"] label:has(input:checked) {
            background: #FBF560 !important;
            box-shadow: inset 0 -4px 0 #111111;
        }

        [data-testid="stRadio"] label p {
            color: #111111 !important;
            font-size: 1rem !important;
            font-weight: 750 !important;
            letter-spacing: 0.01em;
        }

        [data-testid="stRadio"] label > div:first-child {
            display: none !important;
        }

        .page-heading {
            position: relative;
            padding: 28px 30px;
            margin-bottom: 22px;
            background: #FFFFFF;
            border: 1px solid #D9D267;
            border-left: 8px solid #FBF560;
            overflow: hidden;
        }

        .page-heading::after {
            content: "";
            position: absolute;
            right: -45px;
            top: -82px;
            width: 220px;
            height: 220px;
            background: #FBF560;
            opacity: 0.28;
            transform: rotate(17deg);
        }

        .page-heading__label {
            position: relative;
            z-index: 1;
            display: inline-block;
            margin-bottom: 8px;
            padding: 4px 8px;
            background: #111111;
            color: #FFFFFF !important;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .page-heading h1 {
            position: relative;
            z-index: 1;
            margin: 0 0 7px 0;
            color: #111111 !important;
            font-size: 2rem;
            line-height: 1.12;
        }

        .page-heading p {
            position: relative;
            z-index: 1;
            margin: 0;
            color: #4B4B4B !important;
        }

        .stButton > button *,
        .stDownloadButton > button *,
        .stLinkButton > a * {
            color: #111111 !important;
        }

        .stLinkButton > a {
            display: flex !important;
            align-items: center;
            justify-content: center;
            min-height: 42px;
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #111111 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            font-weight: 750 !important;
            text-decoration: none !important;
        }

        .stLinkButton > a:hover {
            background: #FFFCD0 !important;
            color: #111111 !important;
        }

        [data-testid="stProgressBar"] [role="progressbar"] > div,
        [data-testid="stProgressBar"] div[style*="width"] {
            background-color: #FBF560 !important;
        }

        .cro-score-panel {
            min-height: 220px;
            padding: 24px;
            background: #111111;
            border-bottom: 8px solid #FBF560;
        }

        .cro-score-panel__label {
            color: #FBF560 !important;
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .cro-score-panel__value {
            margin-top: 15px;
            color: #FFFFFF !important;
            font-size: 4.3rem;
            line-height: 0.92;
            font-weight: 800;
        }

        .cro-score-panel__value span {
            color: #AFAFAF !important;
            font-size: 1.35rem;
        }

        .cro-score-panel__status {
            margin-top: 20px;
            color: #FFFFFF !important;
            font-size: 1.05rem;
            font-weight: 750;
        }

        .cro-score-panel__text {
            margin-top: 7px;
            color: #CFCFCF !important;
            line-height: 1.5;
            font-size: 0.9rem;
        }

        .cro-kpi-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            margin-bottom: 12px;
        }

        .cro-kpi {
            min-height: 128px;
            padding: 18px;
            background: #FFFFFF;
            border: 1px solid #D9D267;
            border-top: 4px solid #FBF560;
        }

        .cro-kpi__label {
            color: #4B4B4B !important;
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .cro-kpi__value {
            margin-top: 13px;
            color: #111111 !important;
            font-size: 2rem;
            font-weight: 800;
        }

        .cro-kpi__hint {
            margin-top: 5px;
            color: #676767 !important;
            font-size: 0.82rem;
        }

        .cro-backlog {
            border: 1px solid #D9D267;
            background: #FFFFFF;
        }

        .cro-backlog__head,
        .cro-backlog__row {
            display: grid;
            grid-template-columns: 56px minmax(190px, 1.5fr) 120px 120px minmax(180px, 1fr);
            align-items: center;
            gap: 12px;
        }

        .cro-backlog__head {
            padding: 12px 16px;
            background: #111111;
        }

        .cro-backlog__head span {
            color: #FFFFFF !important;
            font-size: 0.76rem;
            font-weight: 750;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .cro-backlog__row {
            padding: 14px 16px;
            border-top: 1px solid #ECE7B5;
        }

        .cro-backlog__row:hover {
            background: #FFFEEE;
        }

        .cro-backlog__rank {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            background: #FBF560;
            color: #111111 !important;
            font-weight: 800;
        }

        .cro-backlog__section {
            color: #111111 !important;
            font-weight: 750;
        }

        .cro-backlog__number {
            color: #111111 !important;
            font-weight: 700;
        }

        .cro-backlog__progress {
            display: grid;
            grid-template-columns: 1fr 52px;
            align-items: center;
            gap: 10px;
        }

        .cro-backlog__track {
            height: 9px;
            background: #E8E8E8;
            overflow: hidden;
        }

        .cro-backlog__fill {
            height: 100%;
            background: #FBF560;
            border-right: 2px solid #111111;
        }

        .cro-backlog__percent {
            color: #111111 !important;
            font-size: 0.82rem;
            font-weight: 750;
            text-align: right;
        }

        .cro-action-panel {
            padding: 20px;
            background: #FFFEEE;
            border: 1px solid #D9D267;
            border-top: 5px solid #FBF560;
            margin-bottom: 12px;
        }

        .cro-action-panel__eyebrow {
            color: #6A651F !important;
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .cro-action-panel h3 {
            margin: 9px 0 8px 0;
            color: #111111 !important;
            font-size: 1.25rem;
        }

        .cro-action-panel p {
            margin: 0;
            color: #4B4B4B !important;
            line-height: 1.5;
        }

        .cro-focus-card {
            position: relative;
            min-height: 160px;
            padding: 20px;
            background: #FFFFFF;
            border: 1px solid #D9D267;
            border-bottom: 5px solid #FBF560;
            overflow: hidden;
        }

        .cro-focus-card__rank {
            position: absolute;
            right: 13px;
            top: 7px;
            color: #EEE9A7 !important;
            font-size: 3.8rem;
            line-height: 1;
            font-weight: 900;
        }

        .cro-focus-card__section {
            position: relative;
            z-index: 1;
            color: #111111 !important;
            font-size: 1.06rem;
            font-weight: 800;
        }

        .cro-focus-card__todo {
            position: relative;
            z-index: 1;
            margin-top: 24px;
            color: #111111 !important;
            font-size: 1.8rem;
            font-weight: 800;
        }

        .cro-focus-card__todo span {
            color: #686868 !important;
            font-size: 0.9rem;
            font-weight: 600;
        }

        .cro-focus-card__text {
            position: relative;
            z-index: 1;
            margin-top: 7px;
            color: #4B4B4B !important;
            font-size: 0.86rem;
        }

        .cro-sheet-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            padding: 18px 20px;
            margin-bottom: 16px;
            background: #111111;
            border-bottom: 5px solid #FBF560;
        }

        .cro-sheet-toolbar h3 {
            margin: 0 0 4px 0;
            color: #FFFFFF !important;
        }

        .cro-sheet-toolbar p {
            margin: 0;
            color: #CFCFCF !important;
            font-size: 0.88rem;
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

            .app-brandbar {
                align-items: flex-start;
                flex-direction: column;
            }

            .app-brandbar__logo {
                width: 150px;
                min-width: 150px;
            }

            [data-testid="stRadio"] [role="radiogroup"] {
                grid-template-columns: 1fr;
            }

            .cro-kpi-grid {
                grid-template-columns: 1fr;
            }

            .cro-backlog__head {
                display: none;
            }

            .cro-backlog__row {
                grid-template-columns: 42px 1fr;
            }

            .cro-backlog__row > :nth-child(3),
            .cro-backlog__row > :nth-child(4) {
                display: none;
            }

            .cro-backlog__progress {
                grid-column: 2;
            }
        }
        </style>
        """
,
        unsafe_allow_html=True,
    )


def configure_plot(fig: go.Figure, height: int | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        colorway=CHART_COLORS,
        font=dict(
            color=BRAND_BLACK,
            family="Arial, sans-serif",
            size=13,
        ),
        title=dict(
            font=dict(color=BRAND_BLACK, size=17),
            x=0.02,
            xanchor="left",
        ),
        legend=dict(
            font=dict(color=BRAND_BLACK),
            title_font=dict(color=BRAND_BLACK),
        ),
        margin=dict(l=28, r=22, t=62, b=32),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor=BRAND_GOLD,
            font=dict(color=BRAND_BLACK),
        ),
    )

    fig.update_xaxes(
        tickfont=dict(color=BRAND_BLACK),
        title_font=dict(color=BRAND_BLACK),
        gridcolor="#F2E8BC",
        linecolor="#CDBB70",
        zerolinecolor="#CDBB70",
        showline=True,
    )
    fig.update_yaxes(
        tickfont=dict(color=BRAND_BLACK),
        title_font=dict(color=BRAND_BLACK),
        gridcolor="#F2E8BC",
        linecolor="#CDBB70",
        zerolinecolor="#CDBB70",
        showline=True,
    )

    fig.update_traces(
        textfont=dict(color=BRAND_BLACK),
        selector=dict(type="bar"),
    )

    if height:
        fig.update_layout(height=height)
    return fig



def render_global_navigation() -> str:
    if LOGO_PATH.exists():
        logo_base64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        logo_html = (
            f'<img src="data:image/jpeg;base64,{logo_base64}" '
            'alt="IPR ecommerce agency">'
        )
    else:
        logo_html = "<strong style='color:#111111'>IPR</strong>"

    st.markdown(
        f"""
        <div class="app-brandbar">
            <div class="app-brandbar__logo">{logo_html}</div>
            <div class="app-brandbar__copy">
                <strong>I-PR Business Dashboard</strong>
                <span>Аналитика продаж и контроль конверсии интернет-магазина</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected = st.radio(
        "Основной раздел",
        options=["АНАЛИТИКА ПРОДАЖ", "CRO-АУДИТ"],
        horizontal=True,
        label_visibility="collapsed",
        key="main_navigation",
    )

    return "CRO" if selected == "CRO-АУДИТ" else "Аналитика"


def render_header() -> None:
    st.markdown(
        """
        <div class="page-heading">
            <span class="page-heading__label">Sales intelligence</span>
            <h1>Аналитика интернет-магазина</h1>
            <p>Продажи, товары, клиенты и автоматические бизнес-рекомендации</p>
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


def render_recommendations(recommendations: list[dict[str, str]]) -> None:
    for start in range(0, len(recommendations), 2):
        columns = st.columns(2)
        for index, recommendation in enumerate(recommendations[start:start + 2]):
            with columns[index]:
                st.markdown(
                    f"""
                    <div class="recommendation-card {recommendation['priority']}">
                        <h4>{escape(recommendation['title'])}</h4>
                        <p>{escape(recommendation['text'])}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def main() -> None:
    st.set_page_config(
        page_title="I-PR Store Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    apply_theme()
    active_section = render_global_navigation()

    if active_section == "CRO":
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"],
            [data-testid="stSidebarCollapsedControl"] {
                display: none !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        cro_module.render_cro_page(LOGO_PATH)
        return

    render_header()

    with st.sidebar:
        st.header("Загрузка данных")
        uploaded_file = st.file_uploader("XML с заказами", type=["xml"])
        st.caption("Файл обрабатывается в памяти и не сохраняется приложением.")

    if uploaded_file is None:
        st.info("Загрузите XML-файл с заказами, чтобы построить дашборд.")
        st.stop()

    try:
        parsed = parse_xml_cached(uploaded_file.getvalue())
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if parsed.orders.empty:
        st.warning("В XML нет заказов с разрешенными статусами.")
        st.stop()

    all_orders = parsed.orders.copy()
    all_items = parsed.items.copy()
    min_date = all_orders["order_date"].min().date()
    max_date = all_orders["order_date"].max().date()

    with st.sidebar:
        st.divider()
        st.header("Фильтры")
        selected_dates = st.date_input(
            "Период",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        selected_statuses = st.multiselect(
            "Статусы",
            options=list(ALLOWED_STATUSES),
            default=list(ALLOWED_STATUSES),
        )

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
        st.warning("По выбранным фильтрам нет заказов.")
        st.stop()

    period_days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    previous_orders = all_orders[
        all_orders["order_date"].dt.date.between(previous_start, previous_end)
        & all_orders["status"].isin(selected_statuses)
    ]

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

    first_metrics = st.columns(6)
    first_metrics[0].metric("Сумма заказов", format_money(revenue), percent_delta(revenue, previous_revenue))
    first_metrics[1].metric("Заказы", format_number(order_count), percent_delta(order_count, previous_count))
    first_metrics[2].metric("Средний чек", format_money(average_check), percent_delta(average_check, previous_average))
    first_metrics[3].metric("Медианный чек", format_money(float(business["median_check"])))
    first_metrics[4].metric("Продано единиц", format_number(sold_units))
    first_metrics[5].metric("Товаров в заказе", f"{float(business['average_items']):.2f}")

    second_metrics = st.columns(5)
    second_metrics[0].metric("Покупатели", format_number(unique_customers))
    second_metrics[1].metric("Повторные покупатели", f"{repeat_rate:.1f}%")
    second_metrics[2].metric("Сумма от повторных", f"{float(business['repeat_revenue_share']):.1f}%")
    second_metrics[3].metric("Доля топ-5 товаров", f"{float(business['top5_share']):.1f}%")
    second_metrics[4].metric("Заказы с 1 товаром", f"{float(business['single_item_share']):.1f}%")

    st.caption(
        f"В XML найдено {parsed.total_xml_orders} заказов. "
        f"Исключено по статусу: {parsed.skipped_by_status}. "
        f"В текущем фильтре: {order_count}."
    )

    trend_text = float(business["period_trend"])
    trend_word = "выросла" if trend_text >= 0 else "снизилась"
    top_product_name = products.nlargest(1, "revenue")["product_name"].iloc[0] if not products.empty else "нет данных"
    st.markdown(
        f"""
        <div class="summary-box">
            За выбранный период магазин получил <b>{format_money(revenue)}</b> из <b>{order_count}</b> заказов.
            Средняя дневная сумма во второй половине периода {trend_word} на <b>{abs(trend_text):.1f}%</b>.
            Лидер по сумме продаж: <b>{escape(str(top_product_name))}</b>.
            Лучший день недели по средней дневной сумме: <b>{escape(str(business['best_weekday']))}</b>.
        </div>
        """,
        unsafe_allow_html=True,
    )

    overview_tab, products_tab, customers_tab, recommendations_tab, quality_tab = st.tabs(
        ["Обзор", "Товары", "Клиенты", "Рекомендации", "Качество данных"]
    )

    with overview_tab:
        daily = (
            orders.assign(day=orders["order_date"].dt.floor("D"))
            .groupby("day", as_index=False)
            .agg(revenue=("order_total", "sum"), orders=("order_id", "nunique"))
        )

        daily_chart = px.line(
            daily,
            x="day",
            y="revenue",
            markers=True,
            title="Динамика суммы заказов",
            labels={"day": "Дата", "revenue": "Сумма, грн"},
            color_discrete_sequence=[BRAND_YELLOW],
        )
        daily_chart.update_traces(
            line_width=3,
            line_color=BRAND_YELLOW,
            marker=dict(
                color=BRAND_YELLOW,
                size=8,
                line=dict(color=BRAND_BLACK, width=1),
            ),
        )
        daily_chart.update_layout(hovermode="x unified")
        st.plotly_chart(configure_plot(daily_chart, 390), use_container_width=True)

        left, right = st.columns(2)
        with left:
            if not products.empty:
                top_units = products.nlargest(7, "sold_units").sort_values("sold_units")
                units_chart = px.bar(
                    top_units,
                    x="sold_units",
                    y="product_name",
                    orientation="h",
                    title="Топ товаров по количеству",
                    labels={"sold_units": "Продано, шт.", "product_name": "Товар"},
                    text="sold_units",
                    color_discrete_sequence=[BRAND_YELLOW],
                )
                units_chart.update_layout(yaxis_title=None)
                units_chart.update_traces(marker_line_color=BRAND_DARK_GOLD, marker_line_width=0.7)
                st.plotly_chart(configure_plot(units_chart, 430), use_container_width=True)

        with right:
            if not products.empty:
                top_revenue = products.nlargest(7, "revenue").sort_values("revenue")
                revenue_chart = px.bar(
                    top_revenue,
                    x="revenue",
                    y="product_name",
                    orientation="h",
                    title="Топ товаров по сумме",
                    labels={"revenue": "Сумма, грн", "product_name": "Товар"},
                    text_auto=".2s",
                    color_discrete_sequence=[BRAND_GOLD],
                )
                revenue_chart.update_layout(yaxis_title=None)
                revenue_chart.update_traces(marker_line_color=BRAND_DARK_GOLD, marker_line_width=0.7)
                st.plotly_chart(configure_plot(revenue_chart, 430), use_container_width=True)

        status_column, payment_column, region_column = st.columns(3)
        with status_column:
            status_stats = orders.groupby("status", as_index=False)["order_total"].sum()
            status_chart = px.pie(
                status_stats,
                names="status",
                values="order_total",
                hole=0.6,
                title="Сумма по статусам",
                color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK, BRAND_GOLD],
            )
            status_chart.update_layout(legend_orientation="h")
            status_chart.update_traces(
                textfont=dict(color=BRAND_BLACK, size=12),
                marker=dict(line=dict(color="#FFFFFF", width=2)),
            )
            st.plotly_chart(configure_plot(status_chart, 390), use_container_width=True)

        with payment_column:
            payment_stats = (
                orders.groupby("payment_method", as_index=False)["order_id"]
                .nunique()
                .rename(columns={"order_id": "orders"})
                .nlargest(6, "orders")
                .sort_values("orders")
            )
            payment_chart = px.bar(
                payment_stats,
                x="orders",
                y="payment_method",
                orientation="h",
                title="Способы оплаты",
                labels={"orders": "Заказы", "payment_method": "Оплата"},
                color_discrete_sequence=[BRAND_GOLD],
            )
            payment_chart.update_layout(yaxis_title=None)
            payment_chart.update_traces(marker_line_color=BRAND_DARK_GOLD, marker_line_width=0.7)
            st.plotly_chart(configure_plot(payment_chart, 390), use_container_width=True)

        with region_column:
            region_stats = (
                orders.groupby("region", as_index=False)["order_total"]
                .sum()
                .nlargest(7, "order_total")
                .sort_values("order_total")
            )
            region_chart = px.bar(
                region_stats,
                x="order_total",
                y="region",
                orientation="h",
                title="Топ регионов",
                labels={"order_total": "Сумма, грн", "region": "Регион"},
                color_discrete_sequence=[BRAND_DARK_GOLD],
            )
            region_chart.update_layout(yaxis_title=None)
            region_chart.update_traces(marker_line_color=BRAND_DARK_GOLD, marker_line_width=0.7)
            st.plotly_chart(configure_plot(region_chart, 390), use_container_width=True)

        weekday_daily = daily.copy()
        weekday_daily["weekday_num"] = weekday_daily["day"].dt.weekday
        weekday_daily["День недели"] = weekday_daily["weekday_num"].map(WEEKDAY_NAMES)
        weekday_stats = (
            weekday_daily.groupby("День недели", as_index=False)
            .agg(**{"Средняя дневная сумма": ("revenue", "mean"), "Заказы": ("orders", "sum")})
        )
        weekday_stats["День недели"] = pd.Categorical(
            weekday_stats["День недели"], categories=WEEKDAY_ORDER, ordered=True
        )
        weekday_stats = weekday_stats.sort_values("День недели")
        weekday_chart = px.bar(
            weekday_stats,
            x="День недели",
            y="Средняя дневная сумма",
            title="Средняя дневная сумма по дням недели",
            text_auto=".2s",
            color_discrete_sequence=[BRAND_YELLOW],
        )
        st.plotly_chart(configure_plot(weekday_chart, 390), use_container_width=True)

    with products_tab:
        if products.empty:
            st.info("В выбранном периоде нет товарных позиций.")
        else:
            product_table = products.copy()
            product_table["revenue_share"] = product_table["revenue"] / revenue * 100 if revenue else 0
            product_table["last_sale"] = product_table["last_sale"].dt.strftime("%d.%m.%Y")
            product_table = product_table.rename(
                columns={
                    "product_name": "Товар",
                    "sku": "SKU",
                    "sold_units": "Продано, шт.",
                    "revenue": "Сумма, грн",
                    "orders": "Заказов",
                    "average_price": "Средняя цена",
                    "revenue_share": "Доля, %",
                    "growth_percent": "Динамика, %",
                    "last_sale": "Последняя продажа",
                    "days_since_last_sale": "Дней без продаж",
                }
            )
            display_columns = [
                "Товар",
                "SKU",
                "Продано, шт.",
                "Заказов",
                "Сумма, грн",
                "Доля, %",
                "Динамика, %",
                "Последняя продажа",
                "Дней без продаж",
            ]
            st.dataframe(
                product_table[display_columns],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Сумма, грн": st.column_config.NumberColumn(format="%.2f"),
                    "Доля, %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Динамика, %": st.column_config.NumberColumn(format="%+.1f%%"),
                },
            )

            growth_left, growth_right = st.columns(2)
            meaningful_products = products[products["sold_units"] >= 2]
            with growth_left:
                st.subheader("Товары с ростом")
                growing = meaningful_products.nlargest(10, "growth_percent")[[
                    "product_name", "sold_units", "revenue", "growth_percent"
                ]].rename(columns={
                    "product_name": "Товар",
                    "sold_units": "Продано, шт.",
                    "revenue": "Сумма, грн",
                    "growth_percent": "Рост, %",
                })
                st.dataframe(growing, use_container_width=True, hide_index=True)

            with growth_right:
                st.subheader("Товары со снижением")
                declining = meaningful_products.nsmallest(10, "growth_percent")[[
                    "product_name", "sold_units", "revenue", "growth_percent"
                ]].rename(columns={
                    "product_name": "Товар",
                    "sold_units": "Продано, шт.",
                    "revenue": "Сумма, грн",
                    "growth_percent": "Изменение, %",
                })
                st.dataframe(declining, use_container_width=True, hide_index=True)

            st.subheader("Товары, которые покупают вместе")
            pairs = business["pairs"]
            if isinstance(pairs, pd.DataFrame) and not pairs.empty:
                st.dataframe(pairs, use_container_width=True, hide_index=True)
            else:
                st.info("Недостаточно заказов с несколькими товарами для анализа пар.")

            csv_data = product_table.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Скачать отчет по товарам CSV",
                data=csv_data,
                file_name=f"products_{start_date}_{end_date}.csv",
                mime="text/csv",
            )

    with customers_tab:
        customer_summary = (
            orders.groupby("customer_key", as_index=False)
            .agg(orders=("order_id", "nunique"), revenue=("order_total", "sum"), last_order=("order_date", "max"))
        )
        customer_summary["Сегмент"] = customer_summary["orders"].apply(
            lambda count: "Повторные" if count >= 2 else "Одна покупка"
        )
        segment_stats = (
            customer_summary.groupby("Сегмент", as_index=False)
            .agg(Покупатели=("customer_key", "nunique"), **{"Сумма, грн": ("revenue", "sum")})
        )

        customer_left, customer_right = st.columns(2)
        with customer_left:
            customer_chart = px.pie(
                segment_stats,
                names="Сегмент",
                values="Покупатели",
                hole=0.62,
                title="Структура клиентской базы",
                color_discrete_sequence=[BRAND_YELLOW, "#F4E7A5"],
            )
            customer_chart.update_layout(legend_orientation="h")
            customer_chart.update_traces(
                textfont=dict(color=BRAND_BLACK, size=12),
                marker=dict(line=dict(color="#FFFFFF", width=2)),
            )
            st.plotly_chart(configure_plot(customer_chart, 390), use_container_width=True)

        with customer_right:
            revenue_segment_chart = px.bar(
                segment_stats,
                x="Сегмент",
                y="Сумма, грн",
                title="Сумма по клиентским сегментам",
                text_auto=".2s",
                color="Сегмент",
                color_discrete_sequence=[BRAND_GOLD, "#F0D66C"],
            )
            revenue_segment_chart.update_layout(showlegend=False)
            st.plotly_chart(configure_plot(revenue_segment_chart, 390), use_container_width=True)

        frequency = (
            customer_summary.groupby("orders", as_index=False)["customer_key"]
            .nunique()
            .rename(columns={"orders": "Количество заказов", "customer_key": "Покупатели"})
            .sort_values("Количество заказов")
        )
        frequency_chart = px.bar(
            frequency,
            x="Количество заказов",
            y="Покупатели",
            title="Распределение покупателей по количеству заказов",
            text="Покупатели",
            color_discrete_sequence=[BRAND_GOLD],
        )
        st.plotly_chart(configure_plot(frequency_chart, 390), use_container_width=True)

        st.caption(
            "Имена, телефоны и email покупателей не выводятся. Для аналитики используется обезличенный идентификатор."
        )

    with recommendations_tab:
        st.subheader("Автоматические бизнес-рекомендации")
        st.caption("Рекомендации формируются по правилам на основе загруженных заказов и выбранного периода.")
        render_recommendations(recommendations)

    with quality_tab:
        adjustment_orders = orders[orders["adjustment"].abs() > 0.01]
        quality_metrics = st.columns(4)
        quality_metrics[0].metric("Расхождения суммы", format_number(len(adjustment_orders)))
        quality_metrics[1].metric(
            "Сумма расхождений",
            format_money(float(adjustment_orders["adjustment"].sum())),
        )
        quality_metrics[2].metric(
            "Без способа оплаты",
            format_number(int((orders["payment_method"] == "Не указано").sum())),
        )
        quality_metrics[3].metric(
            "Без способа доставки",
            format_number(int((orders["shipping_method"] == "Не указано").sum())),
        )

        st.write(
            "Расхождение между суммой товаров и итогом заказа обычно связано со скидкой, доставкой или ручной корректировкой. "
            "Для точного учета в XML нужны отдельные поля discount_total, shipping_total и coupon_code."
        )

        if not adjustment_orders.empty:
            quality_table = adjustment_orders[[
                "order_id", "order_date", "status", "products_total", "order_total", "adjustment"
            ]].copy()
            quality_table["order_date"] = quality_table["order_date"].dt.strftime("%d.%m.%Y %H:%M")
            quality_table = quality_table.rename(columns={
                "order_id": "Заказ",
                "order_date": "Дата",
                "status": "Статус",
                "products_total": "Сумма товаров",
                "order_total": "Итог заказа",
                "adjustment": "Расхождение",
            })
            st.dataframe(quality_table, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
