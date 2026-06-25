from __future__ import annotations

from html import escape

import plotly.graph_objects as go
import streamlit as st


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


def render_module_placeholder(title: str) -> None:
    st.markdown(
        f"""
        <div class="module-placeholder">
            <div class="module-status">МОДУЛЬ ПОДГОТОВЛЕН</div>
            <h3>{escape(title)}</h3>
            <p>
                Пункт уже добавлен в структуру системы. Расчеты, таблицы и графики
                для него подключим отдельно, не затрагивая остальные разделы.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
