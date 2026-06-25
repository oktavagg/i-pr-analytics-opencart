from __future__ import annotations

from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics_ui import (
    BRAND_BLACK,
    BRAND_GOLD,
    BRAND_YELLOW,
    configure_plot,
    format_money,
    format_number,
    render_module_placeholder,
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
    "revenue": "Сводный оборот и динамика продаж по месяцам.",
    "revenue_segments": "Оборот новых и повторных покупателей по месяцам.",
    "orders_count": "Количество заказов по месяцам.",
    "orders_segments": "Количество заказов новых и повторных покупателей по месяцам.",
    "average_check": "Средний чек и его изменение по дням.",
    "check_segments": "Средний чек новых и повторных покупателей.",
    "items_per_order": "Среднее количество товаров и распределение заказов по наполнению.",
    "order_statuses": "Структура заказов по текущим статусам.",
    "order_frequency": "Интервалы между повторными заказами покупателей.",
    "shipping_rating": "Сравнение способов доставки по заказам и обороту.",
}

MONTH_NAMES = {
    1: "Янв",
    2: "Фев",
    3: "Мар",
    4: "Апр",
    5: "Май",
    6: "Июн",
    7: "Июл",
    8: "Авг",
    9: "Сен",
    10: "Окт",
    11: "Ноя",
    12: "Дек",
}


def _month_label(value: pd.Timestamp) -> str:
    return f"{MONTH_NAMES[int(value.month)]} {int(value.year)}"


def _add_month_columns(orders: pd.DataFrame) -> pd.DataFrame:
    prepared = orders.copy()
    prepared["month_start"] = prepared["order_date"].dt.to_period("M").dt.to_timestamp()
    prepared["month_label"] = prepared["month_start"].map(_month_label)
    return prepared


def _classify_orders(context: dict[str, object]) -> pd.DataFrame:
    all_orders = context["all_orders"].copy()
    selected_statuses = context.get("selected_statuses", [])
    if selected_statuses:
        all_orders = all_orders[all_orders["status"].isin(selected_statuses)].copy()

    all_orders = all_orders.sort_values(
        ["customer_key", "order_date", "order_id"],
        kind="stable",
    )
    all_orders["customer_order_number"] = all_orders.groupby("customer_key").cumcount() + 1
    all_orders["customer_segment"] = all_orders["customer_order_number"].apply(
        lambda number: "Новые" if number == 1 else "Повторные"
    )

    start_date = context["start_date"]
    end_date = context["end_date"]
    period_orders = all_orders[
        all_orders["order_date"].dt.date.between(start_date, end_date)
    ].copy()
    return _add_month_columns(period_orders)


def _monthly_orders(context: dict[str, object]) -> pd.DataFrame:
    return _add_month_columns(context["orders"])


def _render_period_caption(context: dict[str, object]) -> None:
    start_date = context["start_date"]
    end_date = context["end_date"]
    st.caption(
        f"Период отчёта: {start_date:%d.%m.%Y}–{end_date:%d.%m.%Y}. "
        "Неполные месяцы считаются только по датам выбранного диапазона."
    )


def _render_html_table(headers: list[str], rows: list[list[str]], total_row: list[str]) -> None:
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    total_html = "".join(f"<td>{escape(cell)}</td>" for cell in total_row)

    st.markdown(
        f"""
        <div class="monthly-table-wrap">
            <table class="monthly-report-table">
                <thead><tr>{header_html}</tr></thead>
                <tbody>{body_html}</tbody>
                <tfoot><tr>{total_html}</tr></tfoot>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_revenue_chart(monthly: pd.DataFrame) -> None:
    chart = px.bar(
        monthly,
        x="month_label",
        y="revenue",
        title="Оборот по месяцам",
        labels={"month_label": "Месяц", "revenue": "Оборот, грн"},
        text_auto=".3s",
        color_discrete_sequence=[BRAND_YELLOW],
        category_orders={"month_label": monthly["month_label"].tolist()},
    )
    chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.7)
    chart.update_layout(showlegend=False, bargap=0.28)
    st.plotly_chart(configure_plot(chart, 500), width="stretch")


def _render_orders_chart(monthly: pd.DataFrame) -> None:
    chart = px.bar(
        monthly,
        x="month_label",
        y="orders",
        title="Количество заказов по месяцам",
        labels={"month_label": "Месяц", "orders": "Заказы"},
        text="orders",
        color_discrete_sequence=[BRAND_YELLOW],
        category_orders={"month_label": monthly["month_label"].tolist()},
    )
    chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.7)
    chart.update_layout(showlegend=False, bargap=0.28)
    st.plotly_chart(configure_plot(chart, 500), width="stretch")


def _render_segment_chart(
    monthly: pd.DataFrame,
    value_columns: list[str],
    value_label: str,
    title: str,
) -> None:
    plot_frame = monthly.melt(
        id_vars=["month_start", "month_label"],
        value_vars=value_columns,
        var_name="segment",
        value_name="value",
    )
    segment_labels = {
        "new_value": "Новые",
        "repeat_value": "Повторные",
    }
    plot_frame["segment"] = plot_frame["segment"].map(segment_labels)

    chart = px.bar(
        plot_frame,
        x="month_label",
        y="value",
        color="segment",
        barmode="group",
        title=title,
        labels={
            "month_label": "Месяц",
            "value": value_label,
            "segment": "Покупатели",
        },
        color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK],
        category_orders={
            "month_label": monthly["month_label"].tolist(),
            "segment": ["Новые", "Повторные"],
        },
    )
    chart.update_traces(marker_line_color=BRAND_GOLD, marker_line_width=0.5)
    chart.update_layout(bargap=0.24, bargroupgap=0.08, legend_orientation="h")
    st.plotly_chart(configure_plot(chart, 500), width="stretch")


def render_revenue_page(context: dict[str, object]) -> None:
    orders = _monthly_orders(context)
    monthly = (
        orders.groupby(["month_start", "month_label"], as_index=False)
        .agg(
            revenue=("order_total", "sum"),
            orders=("order_id", "nunique"),
        )
        .sort_values("month_start")
    )
    monthly["average_check"] = monthly.apply(
        lambda row: row["revenue"] / row["orders"] if row["orders"] else 0.0,
        axis=1,
    )

    total_revenue = float(monthly["revenue"].sum())
    total_orders = int(monthly["orders"].sum())
    average_check = total_revenue / total_orders if total_orders else 0.0

    metrics = st.columns(3)
    metrics[0].metric("Общий оборот", format_money(total_revenue))
    metrics[1].metric("Количество заказов", format_number(total_orders))
    metrics[2].metric("Средний чек", format_money(average_check))
    _render_period_caption(context)

    table_column, chart_column = st.columns([1.05, 1.9], gap="large")
    with table_column:
        rows = [
            [
                str(row.month_label),
                format_money(float(row.revenue)),
                format_number(int(row.orders)),
                format_money(float(row.average_check)),
            ]
            for row in monthly.itertuples(index=False)
        ]
        _render_html_table(
            ["Месяц", "Оборот", "Заказы", "Средний чек"],
            rows,
            ["ИТОГО", format_money(total_revenue), format_number(total_orders), format_money(average_check)],
        )
    with chart_column:
        _render_revenue_chart(monthly)


def render_revenue_segments_page(context: dict[str, object]) -> None:
    segmented = _classify_orders(context)
    monthly_raw = (
        segmented.groupby(["month_start", "month_label", "customer_segment"], as_index=False)
        .agg(revenue=("order_total", "sum"))
    )
    monthly = (
        monthly_raw.pivot_table(
            index=["month_start", "month_label"],
            columns="customer_segment",
            values="revenue",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .sort_values("month_start")
    )
    monthly["new_value"] = monthly.get("Новые", 0.0)
    monthly["repeat_value"] = monthly.get("Повторные", 0.0)
    monthly["total"] = monthly["new_value"] + monthly["repeat_value"]
    monthly["repeat_share"] = monthly.apply(
        lambda row: row["repeat_value"] / row["total"] * 100 if row["total"] else 0.0,
        axis=1,
    )

    new_total = float(monthly["new_value"].sum())
    repeat_total = float(monthly["repeat_value"].sum())
    total = new_total + repeat_total
    repeat_share = repeat_total / total * 100 if total else 0.0

    metrics = st.columns(3)
    metrics[0].metric("Оборот новых покупателей", format_money(new_total))
    metrics[1].metric("Оборот повторных покупателей", format_money(repeat_total))
    metrics[2].metric("Доля повторного оборота", f"{repeat_share:.1f}%")
    _render_period_caption(context)

    table_column, chart_column = st.columns([1.12, 1.88], gap="large")
    with table_column:
        rows = [
            [
                str(row.month_label),
                format_money(float(row.new_value)),
                format_money(float(row.repeat_value)),
                format_money(float(row.total)),
                f"{float(row.repeat_share):.1f}%",
            ]
            for row in monthly.itertuples(index=False)
        ]
        _render_html_table(
            ["Месяц", "Новые", "Повторные", "Итого", "Доля повторных"],
            rows,
            ["ИТОГО", format_money(new_total), format_money(repeat_total), format_money(total), f"{repeat_share:.1f}%"],
        )
    with chart_column:
        _render_segment_chart(
            monthly,
            ["new_value", "repeat_value"],
            "Оборот, грн",
            "Оборот новых и повторных покупателей",
        )

    st.caption(
        "Новый покупатель определяется по первому заказу в загруженной истории. "
        "Все следующие заказы этого покупателя считаются повторными."
    )


def render_orders_count_page(context: dict[str, object]) -> None:
    orders = _monthly_orders(context)
    monthly = (
        orders.groupby(["month_start", "month_label"], as_index=False)
        .agg(orders=("order_id", "nunique"))
        .sort_values("month_start")
    )

    total_orders = int(monthly["orders"].sum())
    month_count = max(len(monthly), 1)
    average_per_month = total_orders / month_count
    unique_customers = int(context["orders"]["customer_key"].nunique())

    metrics = st.columns(3)
    metrics[0].metric("Всего заказов", format_number(total_orders))
    metrics[1].metric("Уникальные покупатели", format_number(unique_customers))
    metrics[2].metric("В среднем за месяц", f"{average_per_month:.1f}")
    _render_period_caption(context)

    table_column, chart_column = st.columns([0.82, 2.18], gap="large")
    with table_column:
        rows = [
            [str(row.month_label), format_number(int(row.orders))]
            for row in monthly.itertuples(index=False)
        ]
        _render_html_table(
            ["Месяц", "Количество заказов"],
            rows,
            ["ИТОГО", format_number(total_orders)],
        )
    with chart_column:
        _render_orders_chart(monthly)


def render_orders_segments_page(context: dict[str, object]) -> None:
    segmented = _classify_orders(context)
    monthly_raw = (
        segmented.groupby(["month_start", "month_label", "customer_segment"], as_index=False)
        .agg(orders=("order_id", "nunique"))
    )
    monthly = (
        monthly_raw.pivot_table(
            index=["month_start", "month_label"],
            columns="customer_segment",
            values="orders",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .sort_values("month_start")
    )
    monthly["new_value"] = (
        monthly["Новые"].astype(int) if "Новые" in monthly.columns else 0
    )
    monthly["repeat_value"] = (
        monthly["Повторные"].astype(int) if "Повторные" in monthly.columns else 0
    )
    monthly["total"] = monthly["new_value"] + monthly["repeat_value"]
    monthly["repeat_share"] = monthly.apply(
        lambda row: row["repeat_value"] / row["total"] * 100 if row["total"] else 0.0,
        axis=1,
    )

    new_total = int(monthly["new_value"].sum())
    repeat_total = int(monthly["repeat_value"].sum())
    total = new_total + repeat_total
    repeat_share = repeat_total / total * 100 if total else 0.0

    metrics = st.columns(3)
    metrics[0].metric("Заказы новых покупателей", format_number(new_total))
    metrics[1].metric("Повторные заказы", format_number(repeat_total))
    metrics[2].metric("Доля повторных заказов", f"{repeat_share:.1f}%")
    _render_period_caption(context)

    table_column, chart_column = st.columns([1.05, 1.95], gap="large")
    with table_column:
        rows = [
            [
                str(row.month_label),
                format_number(int(row.new_value)),
                format_number(int(row.repeat_value)),
                format_number(int(row.total)),
                f"{float(row.repeat_share):.1f}%",
            ]
            for row in monthly.itertuples(index=False)
        ]
        _render_html_table(
            ["Месяц", "Новые", "Повторные", "Итого", "Доля повторных"],
            rows,
            ["ИТОГО", format_number(new_total), format_number(repeat_total), format_number(total), f"{repeat_share:.1f}%"],
        )
    with chart_column:
        _render_segment_chart(
            monthly,
            ["new_value", "repeat_value"],
            "Заказы",
            "Количество заказов новых и повторных покупателей",
        )

    st.caption(
        "Первый заказ покупателя считается новым. Каждый следующий заказ этого покупателя считается повторным."
    )


def render_average_check_page(context: dict[str, object]) -> None:
    average_check = float(context["average_check"])
    previous_average = float(context["previous_average"])
    daily = context["daily"]

    delta = None
    if previous_average:
        delta = f"{((average_check - previous_average) / previous_average) * 100:+.1f}%"
    st.metric("Средний чек", format_money(average_check), delta)
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
        .agg(revenue=("order_total", "sum"), orders=("order_id", "nunique"))
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
