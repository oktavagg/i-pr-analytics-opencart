from __future__ import annotations

from datetime import timedelta
from html import escape

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
    "repeat_share": "Доля повторных заказов и их вклад в оборот магазина.",
    "orders_per_customer": "Частота покупок и распределение покупателей по количеству заказов.",
    "sleeping_customers": "Покупатели с двумя и более заказами, которые не покупали 90 дней.",
    "top_customers_revenue": "Покупатели с наибольшим суммарным оборотом за выбранный период.",
    "top_customers_orders": "Покупатели с наибольшим количеством заказов за выбранный период.",
}


def _apply_customer_styles() -> None:
    st.markdown(
        """
        <style>
        .customer-report-table-wrap {
            width: 100%;
            overflow-x: auto;
            border: 1px solid #D9D267;
            background: #FFFFFF;
        }

        .customer-report-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
        }

        .customer-report-table th {
            padding: 10px 9px;
            background: #FBF560;
            color: #111111 !important;
            border: 1px solid #111111;
            font-weight: 800;
            text-align: center;
            white-space: nowrap;
        }

        .customer-report-table td {
            padding: 9px;
            border: 1px solid #D9D267;
            color: #111111 !important;
            background: #FFFFFF;
            vertical-align: middle;
        }

        .customer-report-table tbody tr:nth-child(even) td {
            background: #FFFEEE;
        }

        .customer-report-table tfoot td {
            background: #FFFCD0;
            border-color: #111111;
            font-weight: 800;
        }

        .customer-report-table .rank-cell,
        .customer-report-table .number-cell {
            text-align: center;
            white-space: nowrap;
        }

        .customer-report-table .money-cell {
            text-align: right;
            white-space: nowrap;
        }

        .sleeping-status {
            margin: 12px 0 18px;
            padding: 18px 20px;
            border: 1px solid #85C88A;
            background: #E8F8E9;
            color: #174D1B !important;
            font-size: 1rem;
            font-weight: 750;
            text-align: center;
        }

        .sleeping-status.has-data {
            border-color: #D9D267;
            background: #FFFCD0;
            color: #111111 !important;
            text-align: left;
        }

        .customer-insight {
            padding: 16px 18px;
            border: 1px solid #D9D267;
            border-left: 5px solid #FBF560;
            background: #FFFEEE;
            color: #111111 !important;
            line-height: 1.5;
        }

        .customer-insight strong {
            color: #111111 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_period_caption(context: dict[str, object], extra: str = "") -> None:
    start_date = context["start_date"]
    end_date = context["end_date"]
    text = f"Период отчёта: {start_date:%d.%m.%Y}–{end_date:%d.%m.%Y}."
    if extra:
        text += f" {extra}"
    st.caption(text)


def _selected_history(context: dict[str, object], until_snapshot: bool = False) -> pd.DataFrame:
    history = context["all_orders"].copy()
    selected_statuses = context.get("selected_statuses", [])
    if selected_statuses:
        history = history[history["status"].isin(selected_statuses)].copy()
    if until_snapshot:
        history = history[history["order_date"].dt.date <= context["end_date"]].copy()
    return history


def _classified_period_orders(context: dict[str, object]) -> pd.DataFrame:
    history = _selected_history(context)
    history = history.sort_values(
        ["customer_key", "order_date", "order_id"],
        kind="stable",
    )
    history["customer_order_number"] = history.groupby("customer_key").cumcount() + 1
    history["customer_segment"] = history["customer_order_number"].apply(
        lambda number: "Новые клиенты" if number == 1 else "Повторные заказы"
    )
    return history[
        history["order_date"].dt.date.between(
            context["start_date"],
            context["end_date"],
        )
    ].copy()


def _customer_rollup(orders: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame(
            columns=[
                "customer_key",
                "customer_name",
                "phone",
                "email",
                "orders",
                "revenue",
                "average_check",
                "first_order",
                "last_order",
            ]
        )

    ordered = orders.sort_values(["customer_key", "order_date", "order_id"], kind="stable")

    summary = (
        ordered.groupby("customer_key", as_index=False)
        .agg(
            customer_name=("customer_name", "last"),
            phone=("phone", "last"),
            email=("email", "last"),
            orders=("order_id", "nunique"),
            revenue=("order_total", "sum"),
            first_order=("order_date", "min"),
            last_order=("order_date", "max"),
        )
    )
    summary["customer_name"] = summary["customer_name"].fillna("Не указано").replace("", "Не указано")
    summary["phone"] = summary["phone"].fillna("").replace("", "Не указано")
    summary["email"] = summary["email"].fillna("").replace("", "Не указано")
    summary["average_check"] = summary.apply(
        lambda row: row["revenue"] / row["orders"] if row["orders"] else 0.0,
        axis=1,
    )
    return summary


def _table_html(
    headers: list[str],
    rows: list[list[str]],
    alignments: list[str] | None = None,
    total_row: list[str] | None = None,
) -> None:
    alignments = alignments or ["left"] * len(headers)
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)

    body_parts: list[str] = []
    for row in rows:
        cells = []
        for index, cell in enumerate(row):
            alignment = alignments[index] if index < len(alignments) else "left"
            class_name = {
                "center": "number-cell",
                "right": "money-cell",
            }.get(alignment, "")
            cells.append(f'<td class="{class_name}">{escape(str(cell))}</td>')
        body_parts.append("<tr>" + "".join(cells) + "</tr>")

    footer_html = ""
    if total_row is not None:
        footer_cells = []
        for index, cell in enumerate(total_row):
            alignment = alignments[index] if index < len(alignments) else "left"
            class_name = {
                "center": "number-cell",
                "right": "money-cell",
            }.get(alignment, "")
            footer_cells.append(f'<td class="{class_name}">{escape(str(cell))}</td>')
        footer_html = "<tfoot><tr>" + "".join(footer_cells) + "</tr></tfoot>"

    st.markdown(
        f"""
        <div class="customer-report-table-wrap">
            <table class="customer-report-table">
                <thead><tr>{header_html}</tr></thead>
                <tbody>{''.join(body_parts)}</tbody>
                {footer_html}
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_top_customer_table(frame: pd.DataFrame) -> None:
    rows: list[list[str]] = []
    for rank, row in enumerate(frame.itertuples(index=False), start=1):
        rows.append(
            [
                str(rank),
                str(row.customer_name),
                str(row.phone),
                str(row.email),
                format_number(int(row.orders)),
                format_money(float(row.revenue)),
                format_money(float(row.average_check)),
            ]
        )

    _table_html(
        ["#", "Клиент", "Телефон", "Email", "Заказы", "Оборот", "Средний чек"],
        rows,
        ["center", "left", "left", "left", "center", "right", "right"],
    )


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
    _apply_customer_styles()
    orders = _classified_period_orders(context)
    stats = (
        orders.groupby("customer_segment", as_index=False)
        .agg(
            revenue=("order_total", "sum"),
            orders=("order_id", "nunique"),
        )
    )

    segment_order = ["Новые клиенты", "Повторные заказы"]
    stats = (
        stats.set_index("customer_segment")
        .reindex(segment_order, fill_value=0)
        .reset_index()
    )
    total_revenue = float(stats["revenue"].sum())
    total_orders = int(stats["orders"].sum())
    stats["revenue_share"] = stats["revenue"].apply(
        lambda value: safe_percent(float(value), total_revenue)
    )
    stats["orders_share"] = stats["orders"].apply(
        lambda value: safe_percent(int(value), total_orders)
    )

    new_revenue = float(stats.loc[stats["customer_segment"] == "Новые клиенты", "revenue"].sum())
    repeat_revenue = float(stats.loc[stats["customer_segment"] == "Повторные заказы", "revenue"].sum())
    repeat_revenue_share = safe_percent(repeat_revenue, total_revenue)

    metrics = st.columns(3)
    metrics[0].metric("Общий оборот", format_money(total_revenue))
    metrics[1].metric("Оборот новых клиентов", format_money(new_revenue))
    metrics[2].metric("Оборот повторных заказов", format_money(repeat_revenue))
    _render_period_caption(
        context,
        "Новый заказ является первой покупкой клиента в загруженной истории.",
    )

    table_column, chart_column = st.columns([1.08, 1.92], gap="large")
    with table_column:
        rows = [
            [
                str(row.customer_segment),
                format_money(float(row.revenue)),
                format_number(int(row.orders)),
                f"{float(row.revenue_share):.1f}%",
                f"{float(row.orders_share):.1f}%",
            ]
            for row in stats.itertuples(index=False)
        ]
        _table_html(
            ["Сегмент", "Оборот", "Заказы", "% оборота", "% заказов"],
            rows,
            ["left", "right", "center", "center", "center"],
            ["ИТОГО", format_money(total_revenue), format_number(total_orders), "100.0%", "100.0%"],
        )

        if repeat_revenue_share < 15:
            insight = (
                f"Повторные заказы дают {repeat_revenue_share:.1f}% оборота. "
                "Стоит усилить коммуникации после первой покупки и сценарии повторного заказа."
            )
        elif repeat_revenue_share < 30:
            insight = (
                f"Повторные заказы дают {repeat_revenue_share:.1f}% оборота. "
                "Есть резерв роста через персональные предложения и напоминания."
            )
        else:
            insight = (
                f"Повторные заказы дают {repeat_revenue_share:.1f}% оборота. "
                "Удержание уже вносит заметный вклад, важно сохранить работающие механики."
            )
        st.markdown(
            f'<div class="customer-insight"><strong>CRO-вывод.</strong> {escape(insight)}</div>',
            unsafe_allow_html=True,
        )

    with chart_column:
        chart = px.pie(
            stats,
            names="customer_segment",
            values="revenue",
            hole=0.56,
            title="Доля повторных заказов в обороте",
            color_discrete_sequence=[BRAND_YELLOW, BRAND_BLACK],
            category_orders={"customer_segment": segment_order},
        )
        chart.update_traces(
            textposition="inside",
            textinfo="percent+label",
            marker=dict(line=dict(color="#FFFFFF", width=2)),
        )
        chart.update_layout(legend_orientation="h")
        st.plotly_chart(configure_plot(chart, 520), width="stretch")


def render_orders_per_customer_page(context: dict[str, object]) -> None:
    _apply_customer_styles()
    customers = _customer_rollup(context["orders"])
    total_customers = int(len(customers))
    total_orders = int(customers["orders"].sum())
    average_orders = total_orders / total_customers if total_customers else 0.0
    repeat_customers = int((customers["orders"] >= 2).sum())
    customers_3_plus = int((customers["orders"] >= 3).sum())
    maximum_orders = int(customers["orders"].max()) if total_customers else 0

    metrics = st.columns(4)
    metrics[0].metric("Заказов на покупателя", f"{average_orders:.2f}")
    metrics[1].metric("Повторные покупатели", f"{safe_percent(repeat_customers, total_customers):.1f}%")
    metrics[2].metric("Покупатели с 3+ заказами", format_number(customers_3_plus))
    metrics[3].metric("Максимум заказов", format_number(maximum_orders))
    _render_period_caption(context)

    frequency = (
        customers.groupby("orders", as_index=False)["customer_key"]
        .nunique()
        .rename(columns={"orders": "order_count", "customer_key": "customers"})
        .sort_values("order_count")
    )
    frequency["share"] = frequency["customers"].apply(
        lambda value: safe_percent(int(value), total_customers)
    )

    table_column, chart_column = st.columns([0.86, 2.14], gap="large")
    with table_column:
        rows = [
            [
                format_number(int(row.order_count)),
                format_number(int(row.customers)),
                f"{float(row.share):.1f}%",
            ]
            for row in frequency.itertuples(index=False)
        ]
        _table_html(
            ["Заказов у клиента", "Покупателей", "Доля"],
            rows,
            ["center", "center", "center"],
            ["ИТОГО", format_number(total_customers), "100.0%"],
        )

        repeat_share = safe_percent(repeat_customers, total_customers)
        if repeat_share < 10:
            action = "Настройте серию сообщений после первой покупки и отдельный оффер на второй заказ."
        elif repeat_share < 25:
            action = "Сегментируйте покупателей после первой покупки и тестируйте персональные поводы вернуться."
        else:
            action = "Повторная база заметна. Разделите её по частоте и среднему чеку для разных предложений."
        st.markdown(
            f"""
            <div class="customer-insight">
                <strong>CRO-действие.</strong> {escape(action)}
            </div>
            """,
            unsafe_allow_html=True,
        )

    with chart_column:
        chart = px.bar(
            frequency,
            x="order_count",
            y="customers",
            text="customers",
            title="Распределение покупателей по количеству заказов",
            labels={"order_count": "Заказов на покупателя", "customers": "Покупатели"},
            color_discrete_sequence=[BRAND_YELLOW],
        )
        chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.7)
        chart.update_layout(showlegend=False, bargap=0.25)
        st.plotly_chart(configure_plot(chart, 500), width="stretch")


def render_sleeping_customers_page(context: dict[str, object]) -> None:
    _apply_customer_styles()
    snapshot_date = context["end_date"]
    threshold_days = 90
    history = _selected_history(context, until_snapshot=True)
    customers = _customer_rollup(history)
    customers["days_since_last_order"] = (
        pd.Timestamp(snapshot_date) - customers["last_order"].dt.normalize()
    ).dt.days

    sleeping = customers[
        (customers["orders"] >= 2)
        & (customers["days_since_last_order"] >= threshold_days)
    ].copy()
    sleeping = sleeping.sort_values(
        ["revenue", "days_since_last_order"],
        ascending=[False, False],
    )

    sleeping_count = int(len(sleeping))
    sleeping_revenue = float(sleeping["revenue"].sum()) if sleeping_count else 0.0
    repeat_base = int((customers["orders"] >= 2).sum())
    sleeping_share = safe_percent(sleeping_count, repeat_base)

    metrics = st.columns(3)
    metrics[0].metric("Спящие покупатели", format_number(sleeping_count))
    metrics[1].metric("Критерий", f"{threshold_days}+ дней")
    metrics[2].metric("Их исторический оборот", format_money(sleeping_revenue))
    st.caption(
        f"Дата среза: {snapshot_date:%d.%m.%Y}. Клиент считается спящим после второй покупки, "
        f"если с последнего заказа прошло не менее {threshold_days} дней."
    )

    if sleeping.empty:
        st.markdown(
            '<div class="sleeping-status">Спящих покупателей не найдено. По выбранному срезу повторная база активна.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <div class="sleeping-status has-data">
            <strong>{sleeping_count} покупателей требуют реактивации.</strong><br>
            Это {sleeping_share:.1f}% клиентов, которые ранее сделали минимум два заказа.
        </div>
        """,
        unsafe_allow_html=True,
    )

    table_rows = [
        [
            str(row.customer_name),
            str(row.phone),
            str(row.email),
            format_number(int(row.orders)),
            format_money(float(row.revenue)),
            row.last_order.strftime("%d.%m.%Y"),
            format_number(int(row.days_since_last_order)),
        ]
        for row in sleeping.itertuples(index=False)
    ]
    _table_html(
        ["Клиент", "Телефон", "Email", "Заказы", "Оборот", "Последний заказ", "Дней без заказа"],
        table_rows,
        ["left", "left", "left", "center", "right", "center", "center"],
    )

    export = sleeping[
        [
            "customer_name",
            "phone",
            "email",
            "orders",
            "revenue",
            "last_order",
            "days_since_last_order",
        ]
    ].copy()
    export.columns = [
        "Клиент",
        "Телефон",
        "Email",
        "Заказы",
        "Оборот",
        "Последний заказ",
        "Дней без заказа",
    ]
    export["Последний заказ"] = export["Последний заказ"].dt.strftime("%d.%m.%Y")
    st.download_button(
        "Скачать список для реактивации CSV",
        data=export.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"sleeping_customers_{snapshot_date}.csv",
        mime="text/csv",
    )


def render_top_customers_revenue_page(context: dict[str, object]) -> None:
    _apply_customer_styles()
    customers = _customer_rollup(context["orders"])
    top = customers.sort_values(
        ["revenue", "orders", "last_order"],
        ascending=[False, False, False],
    ).head(10)

    total_revenue = float(customers["revenue"].sum())
    top_revenue = float(top["revenue"].sum())
    leader_revenue = float(top.iloc[0]["revenue"]) if not top.empty else 0.0
    leader_name = str(top.iloc[0]["customer_name"]) if not top.empty else "Нет данных"

    metrics = st.columns(3)
    metrics[0].metric("Лидер по обороту", format_money(leader_revenue), leader_name)
    metrics[1].metric("Оборот ТОП-10", format_money(top_revenue))
    metrics[2].metric("Доля ТОП-10 в обороте", f"{safe_percent(top_revenue, total_revenue):.1f}%")
    _render_period_caption(context)

    table_column, chart_column = st.columns([1.22, 1.78], gap="large")
    with table_column:
        _render_top_customer_table(top)
    with chart_column:
        chart_data = top.sort_values("revenue", ascending=True)
        chart = px.bar(
            chart_data,
            x="revenue",
            y="customer_name",
            orientation="h",
            title="ТОП-10 клиентов по обороту",
            labels={"revenue": "Оборот, грн", "customer_name": "Клиент"},
            text_auto=".3s",
            color_discrete_sequence=[BRAND_YELLOW],
        )
        chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.7)
        chart.update_layout(showlegend=False, yaxis_title=None)
        st.plotly_chart(configure_plot(chart, 560), width="stretch")


def render_top_customers_orders_page(context: dict[str, object]) -> None:
    _apply_customer_styles()
    customers = _customer_rollup(context["orders"])
    top = customers.sort_values(
        ["orders", "revenue", "last_order"],
        ascending=[False, False, False],
    ).head(10)

    total_orders = int(customers["orders"].sum())
    top_orders = int(top["orders"].sum())
    leader_orders = int(top.iloc[0]["orders"]) if not top.empty else 0
    leader_name = str(top.iloc[0]["customer_name"]) if not top.empty else "Нет данных"

    metrics = st.columns(3)
    metrics[0].metric("Максимум заказов", format_number(leader_orders), leader_name)
    metrics[1].metric("Заказы ТОП-10", format_number(top_orders))
    metrics[2].metric("Доля ТОП-10 в заказах", f"{safe_percent(top_orders, total_orders):.1f}%")
    _render_period_caption(context)

    table_column, chart_column = st.columns([1.22, 1.78], gap="large")
    with table_column:
        _render_top_customer_table(top)
    with chart_column:
        chart_data = top.sort_values(["orders", "revenue"], ascending=[True, True])
        chart = px.bar(
            chart_data,
            x="orders",
            y="customer_name",
            orientation="h",
            title="ТОП-10 клиентов по количеству заказов",
            labels={"orders": "Количество заказов", "customer_name": "Клиент"},
            text="orders",
            color_discrete_sequence=[BRAND_YELLOW],
        )
        chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.7)
        chart.update_layout(showlegend=False, yaxis_title=None)
        st.plotly_chart(configure_plot(chart, 560), width="stretch")


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
