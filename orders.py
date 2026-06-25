from __future__ import annotations

import plotly.express as px
import streamlit as st

from analytics_ui import (
    BRAND_BLACK,
    BRAND_GOLD,
    BRAND_YELLOW,
    configure_plot,
    format_money,
    format_number,
    percent_delta,
    render_module_placeholder,
    safe_percent,
)


CATEGORY_TITLE = "Заказы"
PAGES = [
    ("revenue", "Оборот"),
    ("revenue_segments", "Оборот (от новых/старых)"),
    ("orders_count", "Количество заказов"),
    ("orders_segments", "Количество заказов (от новых/старых)"),
    ("average_check", "Средний чек"),
    ("check_segments", "Чек (от новых/старых)"),
    ("items_per_order", "Кол-во товаров в заказе"),
    ("order_statuses", "Статусы заказов"),
    ("order_frequency", "Частота между заказами"),
    ("shipping_rating", "Рейтинг доставок"),
]
PAGE_DESCRIPTIONS = {
    "revenue": "Динамика оборота за выбранный период.",
    "revenue_segments": "Распределение оборота между новыми и повторными покупателями.",
    "orders_count": "Количество заказов по дням.",
    "orders_segments": "Заказы новых и повторных покупателей.",
    "average_check": "Средний чек и его изменение по дням.",
    "check_segments": "Средний чек новых и повторных покупателей.",
    "items_per_order": "Среднее количество товаров и распределение заказов по наполнению.",
    "order_statuses": "Структура заказов по текущим статусам.",
    "order_frequency": "Интервалы между повторными заказами покупателей.",
    "shipping_rating": "Сравнение способов доставки по заказам и обороту.",
}


def render_revenue_page(context: dict[str, object]) -> None:
    revenue = float(context["revenue"])
    previous_revenue = float(context["previous_revenue"])
    daily = context["daily"]

    st.metric("Оборот", format_money(revenue), percent_delta(revenue, previous_revenue))
    chart = px.line(
        daily,
        x="day",
        y="revenue",
        markers=True,
        title="Оборот по дням",
        labels={"day": "Дата", "revenue": "Оборот, грн"},
        color_discrete_sequence=[BRAND_YELLOW],
    )
    chart.update_traces(
        line_width=3,
        line_color=BRAND_YELLOW,
        marker=dict(color=BRAND_YELLOW, size=8, line=dict(color=BRAND_BLACK, width=1)),
    )
    st.plotly_chart(configure_plot(chart, 440), width="stretch")

def render_revenue_segments_page(context: dict[str, object]) -> None:
    segmented = context["segmented_orders"]
    stats = (
        segmented.groupby("customer_segment", as_index=False)
        .agg(revenue=("order_total", "sum"), orders=("order_id", "nunique"))
    )
    total = float(stats["revenue"].sum())
    stats["share"] = stats["revenue"].apply(lambda value: safe_percent(value, total))

    columns = st.columns(max(len(stats), 1))
    for column, (_, row) in zip(columns, stats.iterrows()):
        column.metric(
            str(row["customer_segment"]),
            format_money(float(row["revenue"])),
            f"{float(row['share']):.1f}% оборота",
        )

    daily = (
        segmented.assign(day=segmented["order_date"].dt.floor("D"))
        .groupby(["day", "customer_segment"], as_index=False)
        .agg(revenue=("order_total", "sum"))
    )
    chart = px.area(
        daily,
        x="day",
        y="revenue",
        color="customer_segment",
        title="Оборот новых и повторных покупателей",
        labels={"day": "Дата", "revenue": "Оборот, грн", "customer_segment": "Покупатели"},
        color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK],
    )
    st.plotly_chart(configure_plot(chart, 440), width="stretch")

def render_orders_count_page(context: dict[str, object]) -> None:
    order_count = int(context["order_count"])
    previous_count = int(context["previous_count"])
    daily = context["daily"]

    st.metric(
        "Количество заказов",
        format_number(order_count),
        percent_delta(order_count, previous_count),
    )
    chart = px.line(
        daily,
        x="day",
        y="orders",
        markers=True,
        title="Количество заказов по дням",
        labels={"day": "Дата", "orders": "Заказы"},
        color_discrete_sequence=[BRAND_YELLOW],
    )
    chart.update_traces(
        line_width=3,
        marker=dict(color=BRAND_YELLOW, size=8, line=dict(color=BRAND_BLACK, width=1)),
    )
    st.plotly_chart(configure_plot(chart, 440), width="stretch")

def render_orders_segments_page(context: dict[str, object]) -> None:
    segmented = context["segmented_orders"]
    stats = (
        segmented.groupby("customer_segment", as_index=False)
        .agg(orders=("order_id", "nunique"))
    )
    total_orders = int(stats["orders"].sum())
    stats["share"] = stats["orders"].apply(lambda value: safe_percent(value, total_orders))

    columns = st.columns(max(len(stats), 1))
    for column, (_, row) in zip(columns, stats.iterrows()):
        column.metric(
            str(row["customer_segment"]),
            format_number(int(row["orders"])),
            f"{float(row['share']):.1f}% заказов",
        )

    chart = px.bar(
        stats,
        x="customer_segment",
        y="orders",
        text="orders",
        title="Количество заказов по типу покупателя",
        labels={"customer_segment": "Покупатели", "orders": "Заказы"},
        color="customer_segment",
        color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK],
    )
    chart.update_layout(showlegend=False)
    st.plotly_chart(configure_plot(chart, 420), width="stretch")

def render_average_check_page(context: dict[str, object]) -> None:
    average_check = float(context["average_check"])
    previous_average = float(context["previous_average"])
    daily = context["daily"]

    st.metric(
        "Средний чек",
        format_money(average_check),
        percent_delta(average_check, previous_average),
    )
    chart = px.line(
        daily,
        x="day",
        y="average_check",
        markers=True,
        title="Средний чек по дням",
        labels={"day": "Дата", "average_check": "Средний чек, грн"},
        color_discrete_sequence=[BRAND_YELLOW],
    )
    chart.update_traces(
        line_width=3,
        marker=dict(color=BRAND_YELLOW, size=8, line=dict(color=BRAND_BLACK, width=1)),
    )
    st.plotly_chart(configure_plot(chart, 440), width="stretch")

def render_check_segments_page(context: dict[str, object]) -> None:
    segmented = context["segmented_orders"]
    stats = (
        segmented.groupby("customer_segment", as_index=False)
        .agg(
            revenue=("order_total", "sum"),
            orders=("order_id", "nunique"),
        )
    )
    stats["average_check"] = stats.apply(
        lambda row: row["revenue"] / row["orders"] if row["orders"] else 0,
        axis=1,
    )

    columns = st.columns(max(len(stats), 1))
    for column, (_, row) in zip(columns, stats.iterrows()):
        column.metric(str(row["customer_segment"]), format_money(float(row["average_check"])))

    chart = px.bar(
        stats,
        x="customer_segment",
        y="average_check",
        text_auto=".2s",
        title="Средний чек новых и повторных покупателей",
        labels={"customer_segment": "Покупатели", "average_check": "Средний чек, грн"},
        color="customer_segment",
        color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK],
    )
    chart.update_layout(showlegend=False)
    st.plotly_chart(configure_plot(chart, 420), width="stretch")

def render_items_per_order_page(context: dict[str, object]) -> None:
    orders = context["orders"]
    business = context["business"]

    metrics = st.columns(3)
    metrics[0].metric("Среднее товаров в заказе", f"{float(business['average_items']):.2f}")
    metrics[1].metric("Заказы с одним товаром", f"{float(business['single_item_share']):.1f}%")
    metrics[2].metric("Максимум товаров", format_number(int(orders["item_quantity"].max())))

    distribution = (
        orders.groupby("item_quantity", as_index=False)["order_id"]
        .nunique()
        .rename(columns={"item_quantity": "items", "order_id": "orders"})
        .sort_values("items")
    )
    chart = px.bar(
        distribution,
        x="items",
        y="orders",
        text="orders",
        title="Распределение заказов по количеству товаров",
        labels={"items": "Товаров в заказе", "orders": "Заказы"},
        color_discrete_sequence=[BRAND_YELLOW],
    )
    st.plotly_chart(configure_plot(chart, 430), width="stretch")

def render_order_statuses_page(context: dict[str, object]) -> None:
    orders = context["orders"]
    stats = (
        orders.groupby("status", as_index=False)
        .agg(orders=("order_id", "nunique"), revenue=("order_total", "sum"))
        .sort_values("orders", ascending=False)
    )

    left, right = st.columns([1.4, 1])
    with left:
        chart = px.pie(
            stats,
            names="status",
            values="orders",
            hole=0.58,
            title="Заказы по статусам",
            color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK, BRAND_GOLD],
        )
        chart.update_layout(legend_orientation="h")
        st.plotly_chart(configure_plot(chart, 420), width="stretch")
    with right:
        display = stats.rename(
            columns={"status": "Статус", "orders": "Заказы", "revenue": "Оборот, грн"}
        )
        st.dataframe(
            display,
            width="stretch",
            hide_index=True,
            column_config={"Оборот, грн": st.column_config.NumberColumn(format="%.2f")},
        )


def render_order_frequency_page(context: dict[str, object]) -> None:
    render_module_placeholder("Частота между заказами")


def render_shipping_rating_page(context: dict[str, object]) -> None:
    render_module_placeholder("Рейтинг доставок")


def render(page_key: str, context: dict[str, object]) -> bool:
    renderers = {
        "revenue": render_revenue_page,
        "revenue_segments": render_revenue_segments_page,
        "orders_count": render_orders_count_page,
        "orders_segments": render_orders_segments_page,
        "average_check": render_average_check_page,
        "check_segments": render_check_segments_page,
        "items_per_order": render_items_per_order_page,
        "order_statuses": render_order_statuses_page,
        "order_frequency": render_order_frequency_page,
        "shipping_rating": render_shipping_rating_page,
    }
    renderer = renderers.get(page_key)
    if renderer is None:
        return False
    renderer(context)
    return True
