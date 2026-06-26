from __future__ import annotations

from html import escape

import numpy as np
import plotly.graph_objects as go
import streamlit as st


BRAND_BLACK = "#1F2937"
BRAND_YELLOW = "#4285F4"
BRAND_GOLD = "#F4B400"
BRAND_DARK_GOLD = "#C58B00"
BRAND_PALE = "#EAF2FF"
BRAND_CREAM = "#F8FAFC"
BRAND_BORDER = "#E5E7EB"
BRAND_MUTED = "#6B7280"
CHART_COLORS = [
    "#4285F4",
    "#5B8FF9",
    "#34A853",
    "#F4B400",
    "#A142F4",
    "#1F2937",
]
TREND_COLOR = "#374151"


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
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        colorway=CHART_COLORS,
        font=dict(
            color=BRAND_BLACK,
            family="Inter, Arial, sans-serif",
            size=13,
        ),
        title=dict(
            font=dict(color=BRAND_BLACK, size=17),
            x=0.02,
            xanchor="left",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color=BRAND_MUTED, size=12),
            title_font=dict(color=BRAND_MUTED),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=28, r=16, t=62, b=28),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor=BRAND_BORDER,
            font=dict(color=BRAND_BLACK),
        ),
    )

    fig.update_xaxes(
        tickfont=dict(color=BRAND_MUTED),
        title_font=dict(color=BRAND_MUTED),
        gridcolor="#EFF2F6",
        linecolor="#E5E7EB",
        zerolinecolor="#E5E7EB",
        showline=False,
    )
    fig.update_yaxes(
        tickfont=dict(color=BRAND_MUTED),
        title_font=dict(color=BRAND_MUTED),
        gridcolor="#EFF2F6",
        linecolor="#E5E7EB",
        zerolinecolor="#E5E7EB",
        showline=False,
    )

    fig.update_traces(
        textfont=dict(color=BRAND_BLACK),
        selector=dict(type="bar"),
    )

    if height:
        fig.update_layout(height=height)
    return fig


def add_trendline(fig: go.Figure, x_values: list, y_values: list[float], name: str = "Тренд") -> go.Figure:
    if len(y_values) < 2:
        return fig

    numeric_values = np.array(y_values, dtype=float)
    positions = np.arange(len(numeric_values), dtype=float)
    coefficients = np.polyfit(positions, numeric_values, 1)
    trend_values = np.polyval(coefficients, positions)

    fig.add_trace(
        go.Scatter(
            x=list(x_values),
            y=trend_values,
            mode="lines",
            name=name,
            line=dict(color=TREND_COLOR, width=2.2, dash="dot"),
            hovertemplate="Тренд: %{y:.2f}<extra></extra>",
        )
    )
    return fig

PRIORITY_LABELS = {
    "critical": "Критично",
    "important": "Важно",
    "recommendation": "Рекомендация",
    "idea": "Идея",
}


def render_recommendations(recommendations: list[dict[str, str]]) -> None:
    for start in range(0, len(recommendations), 2):
        columns = st.columns(2)
        for index, recommendation in enumerate(recommendations[start:start + 2]):
            priority = recommendation.get("priority", "recommendation")
            priority_label = PRIORITY_LABELS.get(priority, "Рекомендация")
            with columns[index]:
                st.markdown(
                    f"""
                    <div class="recommendation-card {escape(priority)}">
                        <div class="recommendation-priority">{escape(priority_label)}</div>
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
