from __future__ import annotations

import plotly.express as px
import streamlit as st

from analytics_ui import (
    BRAND_BLACK,
    BRAND_YELLOW,
    configure_plot,
    format_number,
    render_module_placeholder,
    safe_percent,
)


CATEGORY_TITLE = "Покупатели"
PAGES = [
    ("customers_count", "Количество (новые/старые)"),
    ("repeat_share", "Доля повторных"),
    ("orders_per_customer", "Заказов на покупателя"),
    ("sleeping_customers", "Спящие покупатели (90 дней)"),
    ("top_customers_revenue", "ТОП-10 клиентов по обороту"),
    ("top_customers_orders", "ТОП-10 клиентов по заказам"),
]
PAGE_DESCRIPTIONS = {
    "customers_count": "Новые и повторные покупатели за выбранный период.",
    "repeat_share": "Доля покупателей, которые сделали больше одного заказа.",
    "orders_per_customer": "Распределение покупателей по количеству заказов.",
    "sleeping_customers": "Покупатели без заказов за последние 90 дней.",
    "top_customers_revenue": "Покупатели с наибольшим суммарным оборотом.",
    "top_customers_orders": "Покупатели с наибольшим количеством заказов.",
}


def render_customers_count_page(context: dict[str, object]) -> None:
    segmented = context["segmented_orders"]
    stats = (
        segmented.groupby("customer_segment", as_index=False)["customer_key"]
        .nunique()
        .rename(columns={"customer_key": "customers"})
    )
    total = int(stats["customers"].sum())

    columns = st.columns(max(len(stats), 1))
    for column, (_, row) in zip(columns, stats.iterrows()):
        column.metric(
            str(row["customer_segment"]),
            format_number(int(row["customers"])),
            f"{safe_percent(int(row['customers']), total):.1f}% покупателей",
        )

    chart = px.pie(
        stats,
        names="customer_segment",
        values="customers",
        hole=0.62,
        title="Новые и повторные покупатели",
        color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK],
    )
    chart.update_layout(legend_orientation="h")
    st.plotly_chart(configure_plot(chart, 430), width="stretch")

def render_repeat_share_page(context: dict[str, object]) -> None:
    business = context["business"]
    metrics = st.columns(3)
    metrics[0].metric("Покупатели", format_number(int(context["unique_customers"])))
    metrics[1].metric("Повторные покупатели", f"{float(context['repeat_rate']):.1f}%")
    metrics[2].metric("Оборот от повторных", f"{float(business['repeat_revenue_share']):.1f}%")

    customer_summary = context["customer_summary"]
    segment_stats = (
        customer_summary.groupby("segment", as_index=False)
        .agg(customers=("customer_key", "nunique"), revenue=("revenue", "sum"))
    )
    chart = px.bar(
        segment_stats,
        x="segment",
        y="revenue",
        text_auto=".2s",
        title="Оборот по частоте покупок",
        labels={"segment": "Сегмент", "revenue": "Оборот, грн"},
        color="segment",
        color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK],
    )
    chart.update_layout(showlegend=False)
    st.plotly_chart(configure_plot(chart, 420), width="stretch")

def render_orders_per_customer_page(context: dict[str, object]) -> None:
    customer_summary = context["customer_summary"]
    frequency = (
        customer_summary.groupby("orders", as_index=False)["customer_key"]
        .nunique()
        .rename(columns={"orders": "order_count", "customer_key": "customers"})
        .sort_values("order_count")
    )
    chart = px.bar(
        frequency,
        x="order_count",
        y="customers",
        text="customers",
        title="Распределение покупателей по количеству заказов",
        labels={"order_count": "Заказов на покупателя", "customers": "Покупатели"},
        color_discrete_sequence=[BRAND_YELLOW],
    )
    st.plotly_chart(configure_plot(chart, 440), width="stretch")


def render_sleeping_customers_page(context: dict[str, object]) -> None:
    render_module_placeholder("Спящие покупатели (90 дней)")


def render_top_customers_revenue_page(context: dict[str, object]) -> None:
    render_module_placeholder("ТОП-10 клиентов по обороту")


def render_top_customers_orders_page(context: dict[str, object]) -> None:
    render_module_placeholder("ТОП-10 клиентов по заказам")


def render(page_key: str, context: dict[str, object]) -> bool:
    renderers = {
        "customers_count": render_customers_count_page,
        "repeat_share": render_repeat_share_page,
        "orders_per_customer": render_orders_per_customer_page,
        "sleeping_customers": render_sleeping_customers_page,
        "top_customers_revenue": render_top_customers_revenue_page,
        "top_customers_orders": render_top_customers_orders_page,
    }
    renderer = renderers.get(page_key)
    if renderer is None:
        return False
    renderer(context)
    return True
