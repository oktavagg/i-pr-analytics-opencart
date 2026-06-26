from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analytics_ui import (
    add_trendline,
    configure_plot,
    format_money,
    format_number,
    percent_delta,
    render_recommendations,
    safe_percent,
)
from conclusions import classify_orders_by_customer_history


CATEGORY_TITLE = "Главное"
PAGES = [("overview", "Обзор")]
PAGE_DESCRIPTIONS = {
    "overview": "Ключевая сводка по магазину: основные метрики, динамика, структура продаж и главные точки роста.",
}


def _metric_snapshot(orders: pd.DataFrame) -> dict[str, float]:
    if orders.empty:
        return {
            "revenue": 0.0,
            "order_count": 0,
            "average_check": 0.0,
            "customers": 0,
            "repeat_revenue_share": 0.0,
        }

    classified = classify_orders_by_customer_history(orders)
    revenue = float(classified["order_total"].sum())
    order_count = int(classified["order_id"].nunique())
    average_check = revenue / order_count if order_count else 0.0
    customers = int(classified["customer_key"].nunique())
    repeat_revenue = float(
        classified.loc[classified["comparison_segment"] == "Повторный", "order_total"].sum()
    )
    return {
        "revenue": revenue,
        "order_count": order_count,
        "average_check": average_check,
        "customers": customers,
        "repeat_revenue_share": safe_percent(repeat_revenue, revenue),
    }


def _render_overview_styles() -> None:
    st.markdown(
        """
        <style>
        .overview-note {
            padding: 14px 16px;
            border: 1px solid #E7EAF0;
            border-left: 4px solid #F4C430;
            border-radius: 16px;
            background: #FFFFFF;
            color: #111827 !important;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
            line-height: 1.55;
            margin-bottom: 1rem;
        }

        .overview-section-title {
            margin: 1.6rem 0 0.75rem;
            font-size: 1.12rem;
            font-weight: 800;
            color: #111827 !important;
        }

        .overview-mini-card {
            height: 100%;
            padding: 18px 18px 16px;
            border: 1px solid #E7EAF0;
            border-radius: 18px;
            background: #FFFFFF;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }

        .overview-mini-card h4 {
            margin: 0 0 10px;
            font-size: 1rem;
            color: #111827 !important;
        }

        .overview-mini-card p,
        .overview-mini-card li,
        .overview-mini-card span {
            color: #4B5563 !important;
            font-size: 0.92rem;
            line-height: 1.55;
        }

        .overview-mini-card ul {
            margin: 0;
            padding-left: 18px;
        }

        .overview-list {
            display: grid;
            gap: 10px;
        }

        .overview-list-item {
            padding: 12px 13px;
            border-radius: 14px;
            background: #F8FAFC;
            border: 1px solid #EEF2F7;
        }

        .overview-list-item strong {
            display: block;
            margin-bottom: 4px;
            color: #111827 !important;
            font-size: 0.92rem;
        }

        .overview-top-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }

        .overview-top-table th {
            padding: 10px 10px;
            text-align: left;
            color: #6B7280 !important;
            background: #F8FAFC;
            border-bottom: 1px solid #EEF2F7;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }

        .overview-top-table td {
            padding: 10px 10px;
            border-bottom: 1px solid #EEF2F7;
            color: #111827 !important;
            vertical-align: top;
        }

        .overview-top-table tr:last-child td {
            border-bottom: none;
        }

        .overview-top-table .num,
        .overview-top-table .money {
            white-space: nowrap;
            text-align: right;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_top_products_table(products: pd.DataFrame) -> None:
    if products.empty:
        st.info("В выбранном периоде нет данных по товарам.")
        return

    top_products = products.nlargest(5, "revenue").copy()
    top_products = top_products[["product_name", "orders", "sold_units", "revenue"]].rename(
        columns={
            "product_name": "Товар",
            "orders": "Заказы",
            "sold_units": "Шт.",
            "revenue": "Выручка",
        }
    )

    with st.container(border=True):
        st.markdown("#### Топ-5 товаров по выручке")
        st.dataframe(
            top_products,
            width="stretch",
            hide_index=True,
            column_config={
                "Товар": st.column_config.TextColumn(width="large"),
                "Заказы": st.column_config.NumberColumn(format="%d"),
                "Шт.": st.column_config.NumberColumn(format="%d"),
                "Выручка": st.column_config.NumberColumn(format="%.2f грн"),
            },
        )


def render_overview_page(context: dict[str, object]) -> None:
    _render_overview_styles()

    orders: pd.DataFrame = context["orders"]
    previous_orders: pd.DataFrame = context["previous_orders"]
    products: pd.DataFrame = context["products"]
    product_catalog: pd.DataFrame = context["product_catalog"]
    items: pd.DataFrame = context["items"]
    daily: pd.DataFrame = context["daily"]
    business: dict[str, object] = context["business"]
    recommendations: list[dict[str, str]] = context["recommendations"]
    start_date = context["start_date"]
    end_date = context["end_date"]

    current_metrics = _metric_snapshot(orders)
    previous_metrics = _metric_snapshot(previous_orders)

    sold_product_ids = set(items["product_id"].astype(str)) if not items.empty else set()
    active_catalog = product_catalog[product_catalog["status"] == True].copy() if not product_catalog.empty else pd.DataFrame()
    no_sales_count = int((~active_catalog["product_id"].astype(str).isin(sold_product_ids)).sum()) if not active_catalog.empty else 0

    total_products = int(len(active_catalog)) if not active_catalog.empty else int(len(product_catalog))
    covered_products_share = safe_percent(max(total_products - no_sales_count, 0), total_products) if total_products else 0.0

    cards = st.columns(6)
    card_data = [
        ("Оборот", format_money(current_metrics["revenue"]), percent_delta(current_metrics["revenue"], previous_metrics["revenue"]), "к предыдущему периоду"),
        ("Заказы", format_number(current_metrics["order_count"]), percent_delta(current_metrics["order_count"], previous_metrics["order_count"]), "к предыдущему периоду"),
        ("Средний чек", format_money(current_metrics["average_check"]), percent_delta(current_metrics["average_check"], previous_metrics["average_check"]), "к предыдущему периоду"),
        ("Покупатели", format_number(current_metrics["customers"]), percent_delta(current_metrics["customers"], previous_metrics["customers"]), "к предыдущему периоду"),
        ("Доля повторных", f"{current_metrics['repeat_revenue_share']:.1f}%", percent_delta(current_metrics["repeat_revenue_share"], previous_metrics["repeat_revenue_share"]), "доля выручки"),
        ("Товары без продаж", format_number(no_sales_count), None, f"{covered_products_share:.1f}% каталога с продажами"),
    ]
    for column, (label, value, delta, help_text) in zip(cards, card_data):
        with column:
            st.metric(label, value, delta=delta, help=help_text)

    st.markdown(
        f"""
        <div class="overview-note">
            В обзоре собраны главные показатели магазина за период <strong>{start_date:%d.%m.%Y}–{end_date:%d.%m.%Y}</strong>.
            Ниже показана динамика продаж, структура выручки и основные сигналы, которые стоит проверить в первую очередь.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not daily.empty:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=daily["day"],
                y=daily["revenue"],
                name="Оборот",
                hovertemplate="%{x|%d.%m.%Y}<br>Оборот: %{y:,.2f} грн<extra></extra>",
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=daily["day"],
                y=daily["orders"],
                name="Заказы",
                mode="lines+markers",
                line=dict(width=2.5, color="#1F2937"),
                marker=dict(size=7),
                hovertemplate="%{x|%d.%m.%Y}<br>Заказы: %{y}<extra></extra>",
            ),
            secondary_y=True,
        )
        add_trendline(fig, daily["day"].tolist(), daily["revenue"].tolist(), name="Тренд оборота")
        fig.update_layout(title="Динамика продаж по дням")
        fig.update_yaxes(title_text="Оборот, грн", secondary_y=False)
        fig.update_yaxes(title_text="Заказы", secondary_y=True, rangemode="tozero")
        configure_plot(fig, height=420)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    lower_left, lower_right = st.columns([1.15, 0.85], gap="large")

    with lower_left:
        product_col, status_col = st.columns(2, gap="large")
        with product_col:
            _render_top_products_table(products)
        with status_col:
            status_summary = (
                orders.groupby("status", as_index=False)
                .agg(orders=("order_id", "nunique"), revenue=("order_total", "sum"))
                .sort_values("orders", ascending=True)
            )
            if status_summary.empty:
                st.info("Нет данных по статусам.")
            else:
                status_fig = go.Figure(
                    go.Bar(
                        x=status_summary["orders"],
                        y=status_summary["status"],
                        orientation="h",
                        text=status_summary["orders"],
                        textposition="outside",
                        name="Заказы",
                        hovertemplate="%{y}<br>Заказы: %{x}<extra></extra>",
                    )
                )
                status_fig.update_layout(title="Статусы заказов")
                configure_plot(status_fig, height=340)
                st.plotly_chart(status_fig, use_container_width=True, config={"displayModeBar": False})

    with lower_right:
        segmented = classify_orders_by_customer_history(orders)
        segment_summary = pd.DataFrame(
            {
                "segment": ["Новые", "Повторные"],
                "revenue": [
                    float(segmented.loc[segmented["comparison_segment"] == "Новый", "order_total"].sum()),
                    float(segmented.loc[segmented["comparison_segment"] == "Повторный", "order_total"].sum()),
                ],
                "orders": [
                    int(segmented.loc[segmented["comparison_segment"] == "Новый", "order_id"].nunique()),
                    int(segmented.loc[segmented["comparison_segment"] == "Повторный", "order_id"].nunique()),
                ],
            }
        )
        segment_summary = segment_summary[segment_summary["revenue"] > 0]
        if not segment_summary.empty:
            donut_fig = go.Figure(
                go.Pie(
                    labels=segment_summary["segment"],
                    values=segment_summary["revenue"],
                    hole=0.58,
                    textinfo="percent",
                    hovertemplate="%{label}<br>Выручка: %{value:,.2f} грн<extra></extra>",
                )
            )
            donut_fig.update_layout(title="Новые vs повторные")
            configure_plot(donut_fig, height=320)
            st.plotly_chart(donut_fig, use_container_width=True, config={"displayModeBar": False})

        insight_items = [
            ("Товары без продаж", f"{no_sales_count} шт. без продаж в выбранном периоде. Это {100 - covered_products_share:.1f}% активного каталога."),
            ("Концентрация оборота", f"Топ-5 товаров дают {float(business.get('top5_share', 0.0)):.1f}% общей выручки."),
            ("Структура корзины", f"Среднее количество товаров в заказе — {float(business.get('average_items', 0.0)):.1f}. Заказы с 1 товаром: {float(business.get('single_item_share', 0.0)):.1f}%."),
            ("Лучший день недели", f"По средней дневной выручке лучше всего работает: {escape(str(business.get('best_weekday', '—')))}."),
        ]
        list_html = ''.join(
            f'<div class="overview-list-item"><strong>{escape(title)}</strong><span>{escape(text)}</span></div>'
            for title, text in insight_items
        )
        st.markdown(
            f"""
            <div class="overview-mini-card">
                <h4>Ключевые наблюдения</h4>
                <div class="overview-list">{list_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="overview-section-title">Что требует внимания</div>', unsafe_allow_html=True)
    render_recommendations(recommendations[:4])


def render(page_key: str, context: dict[str, object]) -> bool:
    if page_key != "overview":
        return False
    render_overview_page(context)
    return True
