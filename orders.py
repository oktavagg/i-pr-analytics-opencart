from __future__ import annotations

from html import escape

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from analytics_ui import (
    BRAND_BLACK,
    BRAND_DARK_GOLD,
    BRAND_GOLD,
    BRAND_PALE,
    BRAND_YELLOW,
    configure_plot,
    format_money,
    format_number,
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
    "average_check": "Средний чек по месяцам с оборотом и количеством заказов.",
    "check_segments": "Средний чек новых и повторных покупателей по месяцам.",
    "items_per_order": "Распределение заказов по количеству товаров и месяцам.",
    "order_statuses": "Количество заказов, оборот и доли по всем статусам из XML.",
    "order_frequency": "Интервалы между повторными заказами и CRO-окно для коммуникаций.",
    "shipping_rating": "Рейтинг способов доставки по заказам, обороту и среднему чеку.",
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



def _monthly_orders(context: dict[str, object]) -> pd.DataFrame:
    return _add_month_columns(context["orders"])



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



def _all_status_period_orders(context: dict[str, object]) -> pd.DataFrame:
    period_orders = context.get("all_status_orders")
    if isinstance(period_orders, pd.DataFrame):
        return period_orders.copy()

    all_orders = context.get("all_status_history", context["all_orders"]).copy()
    return all_orders[
        all_orders["order_date"].dt.date.between(
            context["start_date"],
            context["end_date"],
        )
    ].copy()



def _render_period_caption(context: dict[str, object], extra: str = "") -> None:
    start_date = context["start_date"]
    end_date = context["end_date"]
    text = (
        f"Период отчёта: {start_date:%d.%m.%Y}–{end_date:%d.%m.%Y}. "
        "Неполные месяцы считаются только по датам выбранного диапазона."
    )
    if extra:
        text += f" {extra}"
    st.caption(text)



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



def _render_summary_box(title: str, text: str) -> None:
    st.markdown(
        f"""
        <div class="summary-box">
            <b>{escape(title)}</b><br>
            {escape(text)}
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
    plot_frame["segment"] = plot_frame["segment"].map(
        {"new_value": "Новые", "repeat_value": "Повторные"}
    )

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
        .agg(revenue=("order_total", "sum"), orders=("order_id", "nunique"))
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
    monthly["new_value"] = monthly["Новые"].astype(int) if "Новые" in monthly.columns else 0
    monthly["repeat_value"] = monthly["Повторные"].astype(int) if "Повторные" in monthly.columns else 0
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
    orders = _monthly_orders(context)
    monthly = (
        orders.groupby(["month_start", "month_label"], as_index=False)
        .agg(revenue=("order_total", "sum"), orders=("order_id", "nunique"))
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
    metrics[0].metric("Средний чек", format_money(average_check))
    metrics[1].metric("Заказов в расчёте", format_number(total_orders))
    metrics[2].metric("Оборот", format_money(total_revenue))
    _render_period_caption(context)

    table_column, chart_column = st.columns([1.05, 1.95], gap="large")
    with table_column:
        rows = [
            [
                str(row.month_label),
                format_money(float(row.average_check)),
                format_number(int(row.orders)),
                format_money(float(row.revenue)),
            ]
            for row in monthly.itertuples(index=False)
        ]
        _render_html_table(
            ["Месяц", "Средний чек", "Заказы", "Оборот"],
            rows,
            ["СРЕДНЕЕ / ИТОГО", format_money(average_check), format_number(total_orders), format_money(total_revenue)],
        )
    with chart_column:
        chart = px.bar(
            monthly,
            x="month_label",
            y="average_check",
            title="Средний чек по месяцам",
            labels={"month_label": "Месяц", "average_check": "Средний чек, грн"},
            text_auto=".2f",
            color_discrete_sequence=[BRAND_YELLOW],
            category_orders={"month_label": monthly["month_label"].tolist()},
        )
        chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.7)
        chart.update_layout(showlegend=False, bargap=0.28)
        st.plotly_chart(configure_plot(chart, 500), width="stretch")



def render_check_segments_page(context: dict[str, object]) -> None:
    segmented = _classify_orders(context)
    raw = (
        segmented.groupby(["month_start", "month_label", "customer_segment"], as_index=False)
        .agg(revenue=("order_total", "sum"), orders=("order_id", "nunique"))
    )

    index_columns = ["month_start", "month_label"]
    revenue_pivot = raw.pivot_table(
        index=index_columns,
        columns="customer_segment",
        values="revenue",
        aggfunc="sum",
        fill_value=0,
    )
    orders_pivot = raw.pivot_table(
        index=index_columns,
        columns="customer_segment",
        values="orders",
        aggfunc="sum",
        fill_value=0,
    )
    monthly = revenue_pivot.reset_index()[index_columns].copy()
    monthly["new_revenue"] = revenue_pivot.get("Новые", pd.Series(0, index=revenue_pivot.index)).to_numpy()
    monthly["repeat_revenue"] = revenue_pivot.get("Повторные", pd.Series(0, index=revenue_pivot.index)).to_numpy()
    monthly["new_orders"] = orders_pivot.get("Новые", pd.Series(0, index=orders_pivot.index)).to_numpy()
    monthly["repeat_orders"] = orders_pivot.get("Повторные", pd.Series(0, index=orders_pivot.index)).to_numpy()
    monthly = monthly.sort_values("month_start")
    monthly["new_value"] = np.where(
        monthly["new_orders"] > 0,
        monthly["new_revenue"] / monthly["new_orders"],
        0.0,
    )
    monthly["repeat_value"] = np.where(
        monthly["repeat_orders"] > 0,
        monthly["repeat_revenue"] / monthly["repeat_orders"],
        0.0,
    )
    monthly["total_revenue"] = monthly["new_revenue"] + monthly["repeat_revenue"]
    monthly["total_orders"] = monthly["new_orders"] + monthly["repeat_orders"]
    monthly["total_check"] = np.where(
        monthly["total_orders"] > 0,
        monthly["total_revenue"] / monthly["total_orders"],
        0.0,
    )

    new_revenue = float(monthly["new_revenue"].sum())
    repeat_revenue = float(monthly["repeat_revenue"].sum())
    new_orders = int(monthly["new_orders"].sum())
    repeat_orders = int(monthly["repeat_orders"].sum())
    new_check = new_revenue / new_orders if new_orders else 0.0
    repeat_check = repeat_revenue / repeat_orders if repeat_orders else 0.0
    total_check = (new_revenue + repeat_revenue) / (new_orders + repeat_orders) if new_orders + repeat_orders else 0.0
    difference = ((repeat_check - new_check) / new_check * 100) if new_check else 0.0

    metrics = st.columns(4)
    metrics[0].metric("Средний чек новых", format_money(new_check))
    metrics[1].metric("Средний чек повторных", format_money(repeat_check))
    metrics[2].metric("Разница повторных к новым", f"{difference:+.1f}%")
    metrics[3].metric("Общий средний чек", format_money(total_check))
    _render_period_caption(context)

    table_column, chart_column = st.columns([1.2, 1.8], gap="large")
    with table_column:
        rows = [
            [
                str(row.month_label),
                format_money(float(row.new_value)),
                format_money(float(row.repeat_value)),
                format_money(float(row.total_check)),
                f"{int(row.new_orders)} / {int(row.repeat_orders)}",
            ]
            for row in monthly.itertuples(index=False)
        ]
        _render_html_table(
            ["Месяц", "Новые", "Повторные", "Общий", "Заказы Н / П"],
            rows,
            ["СРЕДНЕЕ", format_money(new_check), format_money(repeat_check), format_money(total_check), f"{new_orders} / {repeat_orders}"],
        )
    with chart_column:
        _render_segment_chart(
            monthly,
            ["new_value", "repeat_value"],
            "Средний чек, грн",
            "Средний чек новых и повторных покупателей",
        )

    st.caption(
        "Новые и повторные заказы определяются по полной загруженной истории, а не только внутри выбранного периода."
    )



def _item_bucket(quantity: int) -> str:
    if quantity <= 1:
        return "1 товар"
    if quantity == 2:
        return "2 товара"
    if quantity == 3:
        return "3 товара"
    return "4+ товаров"



def render_items_per_order_page(context: dict[str, object]) -> None:
    orders = _monthly_orders(context)
    orders["item_bucket"] = orders["item_quantity"].fillna(0).astype(int).map(_item_bucket)
    bucket_order = ["1 товар", "2 товара", "3 товара", "4+ товаров"]

    monthly_raw = (
        orders.groupby(["month_start", "month_label", "item_bucket"], as_index=False)
        .agg(orders=("order_id", "nunique"))
    )
    monthly = (
        monthly_raw.pivot_table(
            index=["month_start", "month_label"],
            columns="item_bucket",
            values="orders",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .sort_values("month_start")
    )
    for bucket in bucket_order:
        if bucket not in monthly.columns:
            monthly[bucket] = 0
    monthly["Итого"] = monthly[bucket_order].sum(axis=1)

    total_orders = int(orders["order_id"].nunique())
    average_items = float(orders["item_quantity"].mean()) if total_orders else 0.0
    one_item_orders = int((orders["item_quantity"] <= 1).sum())
    three_plus_orders = int((orders["item_quantity"] >= 3).sum())
    one_item_share = one_item_orders / total_orders * 100 if total_orders else 0.0
    three_plus_share = three_plus_orders / total_orders * 100 if total_orders else 0.0

    metrics = st.columns(4)
    metrics[0].metric("Всего заказов", format_number(total_orders))
    metrics[1].metric("Среднее товаров", f"{average_items:.2f}")
    metrics[2].metric("Заказы с 1 товаром", f"{one_item_share:.1f}%")
    metrics[3].metric("Заказы с 3+ товарами", f"{three_plus_share:.1f}%")
    _render_period_caption(context)

    table_column, chart_column = st.columns([1.15, 1.85], gap="large")
    with table_column:
        rows = [
            [
                str(row.month_label),
                format_number(int(getattr(row, "_2"))),
                format_number(int(getattr(row, "_3"))),
                format_number(int(getattr(row, "_4"))),
                format_number(int(getattr(row, "_5"))),
                format_number(int(row.Итого)),
            ]
            for row in monthly[["month_start", "month_label", *bucket_order, "Итого"]].itertuples(index=False)
        ]
        totals = [int(monthly[bucket].sum()) for bucket in bucket_order]
        _render_html_table(
            ["Месяц", "1 товар", "2 товара", "3 товара", "4+", "Итого"],
            rows,
            ["ИТОГО", *[format_number(value) for value in totals], format_number(total_orders)],
        )
    with chart_column:
        plot_frame = monthly.melt(
            id_vars=["month_start", "month_label"],
            value_vars=bucket_order,
            var_name="Наполнение",
            value_name="Заказы",
        )
        chart = px.bar(
            plot_frame,
            x="month_label",
            y="Заказы",
            color="Наполнение",
            barmode="group",
            title="Количество товаров в заказе по месяцам",
            labels={"month_label": "Месяц"},
            color_discrete_sequence=[BRAND_YELLOW, BRAND_GOLD, BRAND_DARK_GOLD, BRAND_BLACK],
            category_orders={
                "month_label": monthly["month_label"].tolist(),
                "Наполнение": bucket_order,
            },
        )
        chart.update_layout(legend_orientation="h", bargap=0.22, bargroupgap=0.06)
        st.plotly_chart(configure_plot(chart, 500), width="stretch")

    if one_item_share >= 50:
        _render_summary_box(
            "CRO-наблюдение",
            f"{one_item_share:.1f}% заказов содержат один товар. Проверьте блоки допродаж, комплекты, порог бесплатной доставки и рекомендации в корзине.",
        )



def render_order_statuses_page(context: dict[str, object]) -> None:
    orders = _all_status_period_orders(context)
    if orders.empty:
        st.info("В выбранном периоде нет заказов для отчёта по статусам.")
        return

    stats = (
        orders.groupby("status", as_index=False)
        .agg(orders=("order_id", "nunique"), revenue=("order_total", "sum"))
        .sort_values("orders", ascending=False)
    )
    total_orders = int(stats["orders"].sum())
    total_revenue = float(stats["revenue"].sum())
    stats["order_share"] = stats["orders"] / total_orders * 100 if total_orders else 0.0
    stats["revenue_share"] = stats["revenue"] / total_revenue * 100 if total_revenue else 0.0
    top_status = str(stats.iloc[0]["status"])

    metrics = st.columns(4)
    metrics[0].metric("Всего заказов", format_number(total_orders))
    metrics[1].metric("Общий оборот", format_money(total_revenue))
    metrics[2].metric("Статусов", format_number(len(stats)))
    metrics[3].metric("Основной статус", top_status)
    _render_period_caption(
        context,
        "Эта страница показывает все статусы из XML и не ограничивается фильтром статусов слева.",
    )

    rows = [
        [
            str(row.status),
            format_number(int(row.orders)),
            format_money(float(row.revenue)),
            f"{float(row.order_share):.1f}%",
            f"{float(row.revenue_share):.1f}%",
        ]
        for row in stats.itertuples(index=False)
    ]
    _render_html_table(
        ["Статус", "Заказы", "Оборот", "% заказов", "% оборота"],
        rows,
        ["ИТОГО", format_number(total_orders), format_money(total_revenue), "100.0%", "100.0%"],
    )

    left, right = st.columns([1.35, 1], gap="large")
    with left:
        bar_data = stats.sort_values("orders")
        bar = px.bar(
            bar_data,
            x="orders",
            y="status",
            orientation="h",
            title="Количество заказов по статусам",
            labels={"orders": "Заказы", "status": "Статус"},
            text="orders",
            color_discrete_sequence=[BRAND_YELLOW],
        )
        bar.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.6)
        bar.update_layout(showlegend=False, yaxis_title=None)
        st.plotly_chart(configure_plot(bar, 470), width="stretch")
    with right:
        pie = px.pie(
            stats,
            names="status",
            values="orders",
            hole=0.48,
            title="Доля по количеству заказов",
            color_discrete_sequence=[BRAND_YELLOW, BRAND_GOLD, BRAND_BLACK, BRAND_DARK_GOLD, BRAND_PALE],
        )
        pie.update_layout(legend_orientation="h")
        pie.update_traces(marker=dict(line=dict(color="#FFFFFF", width=2)))
        st.plotly_chart(configure_plot(pie, 470), width="stretch")



def render_order_frequency_page(context: dict[str, object]) -> None:
    history = context["all_orders"].copy()
    selected_statuses = context.get("selected_statuses", [])
    if selected_statuses:
        history = history[history["status"].isin(selected_statuses)].copy()

    history = history.sort_values(["customer_key", "order_date", "order_id"], kind="stable")
    history["previous_order_date"] = history.groupby("customer_key")["order_date"].shift(1)
    history["interval_days"] = (
        history["order_date"].dt.normalize() - history["previous_order_date"].dt.normalize()
    ).dt.days
    intervals = history[
        history["order_date"].dt.date.between(context["start_date"], context["end_date"])
        & history["interval_days"].notna()
        & (history["interval_days"] >= 0)
    ].copy()

    if intervals.empty:
        st.info("В выбранном периоде нет повторных заказов, для которых можно рассчитать интервал.")
        _render_period_caption(context)
        return

    average_interval = float(intervals["interval_days"].mean())
    median_interval = float(intervals["interval_days"].median())
    repeat_orders = int(intervals["order_id"].nunique())
    repeat_customers = int(intervals["customer_key"].nunique())
    within_30_share = float((intervals["interval_days"] <= 30).mean() * 100)

    metrics = st.columns(4)
    metrics[0].metric("Средний интервал", f"{average_interval:.1f} дня")
    metrics[1].metric("Медианный интервал", f"{median_interval:.1f} дня")
    metrics[2].metric("Повторных заказов", format_number(repeat_orders))
    metrics[3].metric("До 30 дней", f"{within_30_share:.1f}%")
    _render_period_caption(context)

    bins = [-1, 7, 14, 30, 60, 90, np.inf]
    labels = ["0–7 дней", "8–14 дней", "15–30 дней", "31–60 дней", "61–90 дней", "91+ дней"]
    intervals["interval_group"] = pd.cut(
        intervals["interval_days"],
        bins=bins,
        labels=labels,
        ordered=True,
    )
    distribution = (
        intervals.groupby("interval_group", observed=False, as_index=False)
        .agg(orders=("order_id", "nunique"))
    )
    distribution["share"] = distribution["orders"] / repeat_orders * 100 if repeat_orders else 0.0

    table_column, chart_column = st.columns([0.9, 2.1], gap="large")
    with table_column:
        rows = [
            [str(row.interval_group), format_number(int(row.orders)), f"{float(row.share):.1f}%"]
            for row in distribution.itertuples(index=False)
        ]
        _render_html_table(
            ["Интервал", "Заказы", "Доля"],
            rows,
            ["ИТОГО", format_number(repeat_orders), "100.0%"],
        )
    with chart_column:
        chart = px.bar(
            distribution,
            x="interval_group",
            y="orders",
            title="Распределение интервалов между заказами",
            labels={"interval_group": "Интервал", "orders": "Повторные заказы"},
            text="orders",
            color_discrete_sequence=[BRAND_YELLOW],
            category_orders={"interval_group": labels},
        )
        chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.6)
        chart.update_layout(showlegend=False)
        st.plotly_chart(configure_plot(chart, 470), width="stretch")

    reminder_start = max(1, int(round(median_interval * 0.70)))
    reminder_end = max(reminder_start + 1, int(round(median_interval * 0.85)))
    _render_summary_box(
        "CRO-рекомендация",
        f"Запускайте напоминание о повторной покупке примерно на {reminder_start}–{reminder_end} день после заказа. Медианный повтор происходит через {median_interval:.1f} дня. В расчёте участвуют {repeat_customers} покупателей с повторными заказами.",
    )



def render_shipping_rating_page(context: dict[str, object]) -> None:
    orders = context["orders"].copy()
    if orders.empty:
        st.info("В выбранном периоде нет заказов для рейтинга доставок.")
        return

    stats = (
        orders.groupby("shipping_method", as_index=False)
        .agg(orders=("order_id", "nunique"), revenue=("order_total", "sum"))
        .sort_values(["orders", "revenue"], ascending=False)
    )
    total_orders = int(stats["orders"].sum())
    total_revenue = float(stats["revenue"].sum())
    stats["order_share"] = stats["orders"] / total_orders * 100 if total_orders else 0.0
    stats["revenue_share"] = stats["revenue"] / total_revenue * 100 if total_revenue else 0.0
    stats["average_check"] = np.where(stats["orders"] > 0, stats["revenue"] / stats["orders"], 0.0)
    leader = str(stats.iloc[0]["shipping_method"])

    metrics = st.columns(4)
    metrics[0].metric("Заказов с доставкой", format_number(total_orders))
    metrics[1].metric("Оборот", format_money(total_revenue))
    metrics[2].metric("Способов доставки", format_number(len(stats)))
    metrics[3].metric("Лидер", leader)
    _render_period_caption(context)

    rows = [
        [
            str(row.shipping_method),
            format_number(int(row.orders)),
            format_money(float(row.revenue)),
            f"{float(row.order_share):.1f}%",
            f"{float(row.revenue_share):.1f}%",
            format_money(float(row.average_check)),
        ]
        for row in stats.itertuples(index=False)
    ]
    _render_html_table(
        ["Способ доставки", "Заказы", "Оборот", "% заказов", "% оборота", "Средний чек"],
        rows,
        ["ИТОГО", format_number(total_orders), format_money(total_revenue), "100.0%", "100.0%", format_money(total_revenue / total_orders if total_orders else 0.0)],
    )

    chart_data = stats.sort_values("orders")
    chart = px.bar(
        chart_data,
        x="orders",
        y="shipping_method",
        orientation="h",
        title="Рейтинг способов доставки по количеству заказов",
        labels={"orders": "Заказы", "shipping_method": "Способ доставки"},
        text="orders",
        color_discrete_sequence=[BRAND_YELLOW],
    )
    chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.6)
    chart.update_layout(showlegend=False, yaxis_title=None)
    st.plotly_chart(configure_plot(chart, max(450, 70 * len(stats))), width="stretch")

    missing = stats.loc[stats["shipping_method"] == "Не указано", "orders"]
    if not missing.empty and int(missing.iloc[0]) > 0:
        _render_summary_box(
            "Качество данных",
            f"У {int(missing.iloc[0])} заказов не указан способ доставки. Заполнение этого поля улучшит точность отчёта и сегментацию клиентов.",
        )



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
