from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from parser import ALLOWED_STATUSES, parse_xml, top_products


@st.cache_data(show_spinner=False)
def parse_xml_cached(xml_bytes: bytes):
    return parse_xml(xml_bytes)


def format_money(value: float) -> str:
    return f"{value:,.2f} грн".replace(",", " ")


def percent_delta(current: float, previous: float) -> str | None:
    if previous == 0:
        return None
    return f"{((current - previous) / previous) * 100:+.1f}%"


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.6rem;
            padding-bottom: 3rem;
            max-width: 1440px;
        }

        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e9edf3;
            padding: 18px;
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
        }

        [data-testid="stMetricLabel"] {
            font-size: 0.9rem;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.7rem;
        }

        div[data-testid="stPlotlyChart"] {
            background: #ffffff;
            border: 1px solid #e9edf3;
            border-radius: 16px;
            padding: 8px;
        }

        .dashboard-header {
            padding: 24px 26px;
            border-radius: 20px;
            background: linear-gradient(135deg, #111827 0%, #1f2937 100%);
            color: white;
            margin-bottom: 20px;
        }

        .dashboard-header h1 {
            margin: 0 0 6px 0;
            font-size: 2rem;
        }

        .dashboard-header p {
            margin: 0;
            opacity: 0.76;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Store Analytics",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    apply_theme()

    st.markdown(
        """
        <div class="dashboard-header">
            <h1>Store Analytics</h1>
            <p>Аналитика заказов OpenCart и WooCommerce из XML</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Загрузка данных")

        uploaded_file = st.file_uploader(
            "XML с заказами",
            type=["xml"],
        )

        st.caption(
            "Файл обрабатывается в памяти и не сохраняется приложением."
        )

    if uploaded_file is None:
        st.info(
            "Загрузите XML-файл с заказами, чтобы построить дашборд."
        )
        st.stop()

    try:
        parsed = parse_xml_cached(uploaded_file.getvalue())
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if parsed.orders.empty:
        st.warning(
            "В XML нет заказов с разрешенными статусами."
        )
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

    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        selected_date = (
            selected_dates
            if isinstance(selected_dates, date)
            else min_date
        )
        start_date = selected_date
        end_date = selected_date

    orders = all_orders[
        all_orders["order_date"].dt.date.between(
            start_date,
            end_date,
        )
        & all_orders["status"].isin(selected_statuses)
    ].copy()

    items = all_items[
        all_items["order_id"].isin(orders["order_id"])
    ].copy()

    if orders.empty:
        st.warning("По выбранным фильтрам нет заказов.")
        st.stop()

    period_days = (end_date - start_date).days + 1
    previous_end = start_date - pd.Timedelta(days=1)
    previous_start = previous_end - pd.Timedelta(
        days=period_days - 1
    )

    previous_orders = all_orders[
        all_orders["order_date"].dt.date.between(
            previous_start,
            previous_end,
        )
        & all_orders["status"].isin(selected_statuses)
    ]

    revenue = orders["order_total"].sum()
    order_count = orders["order_id"].nunique()
    average_check = revenue / order_count if order_count else 0
    sold_units = (
        int(items["quantity"].sum())
        if not items.empty
        else 0
    )

    unique_customers = orders["customer_key"].nunique()
    customer_orders = orders.groupby(
        "customer_key"
    )["order_id"].nunique()

    repeat_customers = int(
        (customer_orders >= 2).sum()
    )

    repeat_rate = (
        repeat_customers / unique_customers * 100
        if unique_customers
        else 0
    )

    previous_revenue = previous_orders["order_total"].sum()
    previous_count = previous_orders["order_id"].nunique()
    previous_average = (
        previous_revenue / previous_count
        if previous_count
        else 0
    )

    metrics = st.columns(6)

    metrics[0].metric(
        "Сумма заказов",
        format_money(revenue),
        percent_delta(revenue, previous_revenue),
    )

    metrics[1].metric(
        "Заказы",
        f"{order_count:,}".replace(",", " "),
        percent_delta(order_count, previous_count),
    )

    metrics[2].metric(
        "Средний чек",
        format_money(average_check),
        percent_delta(average_check, previous_average),
    )

    metrics[3].metric(
        "Продано единиц",
        f"{sold_units:,}".replace(",", " "),
    )

    metrics[4].metric(
        "Покупатели",
        f"{unique_customers:,}".replace(",", " "),
    )

    metrics[5].metric(
        "Повторные",
        f"{repeat_rate:.1f}%",
    )

    st.caption(
        f"В XML найдено {parsed.total_xml_orders} заказов. "
        f"Исключено по статусу: {parsed.skipped_by_status}. "
        f"В текущем фильтре: {order_count}."
    )

    daily = (
        orders.assign(
            day=orders["order_date"].dt.floor("D")
        )
        .groupby("day", as_index=False)
        .agg(
            revenue=("order_total", "sum"),
            orders=("order_id", "nunique"),
        )
    )

    daily_chart = px.line(
        daily,
        x="day",
        y="revenue",
        markers=True,
        title="Динамика суммы заказов",
        labels={
            "day": "Дата",
            "revenue": "Сумма, грн",
        },
    )

    daily_chart.update_layout(
        margin=dict(l=20, r=20, t=55, b=20),
        hovermode="x unified",
    )

    st.plotly_chart(
        daily_chart,
        use_container_width=True,
    )

    products = top_products(items)
    left, right = st.columns(2)

    with left:
        if products.empty:
            st.info("Нет товарных позиций.")
        else:
            top_units = (
                products.nlargest(5, "sold_units")
                .sort_values("sold_units")
            )

            units_chart = px.bar(
                top_units,
                x="sold_units",
                y="product_name",
                orientation="h",
                title="Топ-5 товаров по количеству",
                labels={
                    "sold_units": "Продано, шт.",
                    "product_name": "Товар",
                },
                text="sold_units",
            )

            units_chart.update_layout(
                margin=dict(l=20, r=20, t=55, b=20),
                yaxis_title=None,
            )

            st.plotly_chart(
                units_chart,
                use_container_width=True,
            )

    with right:
        if products.empty:
            st.info("Нет товарных позиций.")
        else:
            top_revenue = (
                products.nlargest(5, "revenue")
                .sort_values("revenue")
            )

            product_revenue_chart = px.bar(
                top_revenue,
                x="revenue",
                y="product_name",
                orientation="h",
                title="Топ-5 товаров по сумме",
                labels={
                    "revenue": "Сумма, грн",
                    "product_name": "Товар",
                },
                text_auto=".2s",
            )

            product_revenue_chart.update_layout(
                margin=dict(l=20, r=20, t=55, b=20),
                yaxis_title=None,
            )

            st.plotly_chart(
                product_revenue_chart,
                use_container_width=True,
            )

    status_column, payment_column, region_column = st.columns(3)

    with status_column:
        status_stats = (
            orders.groupby("status", as_index=False)[
                "order_total"
            ]
            .sum()
        )

        status_chart = px.pie(
            status_stats,
            names="status",
            values="order_total",
            hole=0.58,
            title="Сумма по статусам",
        )

        status_chart.update_layout(
            margin=dict(l=10, r=10, t=55, b=10),
            legend_orientation="h",
        )

        st.plotly_chart(
            status_chart,
            use_container_width=True,
        )

    with payment_column:
        payment_stats = (
            orders.groupby(
                "payment_method",
                as_index=False,
            )["order_id"]
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
            labels={
                "orders": "Заказы",
                "payment_method": "Оплата",
            },
        )

        payment_chart.update_layout(
            margin=dict(l=10, r=10, t=55, b=10),
            yaxis_title=None,
        )

        st.plotly_chart(
            payment_chart,
            use_container_width=True,
        )

    with region_column:
        region_stats = (
            orders.groupby(
                "region",
                as_index=False,
            )["order_total"]
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
            labels={
                "order_total": "Сумма, грн",
                "region": "Регион",
            },
        )

        region_chart.update_layout(
            margin=dict(l=10, r=10, t=55, b=10),
            yaxis_title=None,
        )

        st.plotly_chart(
            region_chart,
            use_container_width=True,
        )

    st.subheader("Товары")

    if not products.empty:
        product_table = products.copy()

        product_table["revenue_share"] = (
            product_table["revenue"] / revenue * 100
            if revenue
            else 0
        )

        product_table = product_table.rename(
            columns={
                "product_name": "Товар",
                "sku": "SKU",
                "sold_units": "Продано, шт.",
                "revenue": "Сумма, грн",
                "orders": "Заказов",
                "revenue_share": "Доля, %",
            }
        )

        display_columns = [
            "Товар",
            "SKU",
            "Продано, шт.",
            "Заказов",
            "Сумма, грн",
            "Доля, %",
        ]

        st.dataframe(
            product_table[display_columns],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Сумма, грн": st.column_config.NumberColumn(
                    format="%.2f"
                ),
                "Доля, %": st.column_config.NumberColumn(
                    format="%.2f%%"
                ),
            },
        )

        csv_data = product_table.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            "Скачать отчет по товарам CSV",
            data=csv_data,
            file_name=(
                f"products_{start_date}_{end_date}.csv"
            ),
            mime="text/csv",
        )

    with st.expander("Проверка качества данных"):
        adjustment_orders = orders[
            orders["adjustment"].abs() > 0.01
        ]

        st.write(
            "Заказов с расхождением суммы товаров "
            f"и заказа: {len(adjustment_orders)}"
        )

        st.write(
            "Общая сумма расхождений: "
            f"{format_money(adjustment_orders['adjustment'].sum())}"
        )

        st.write(
            "Заказов без способа оплаты: "
            f"{(orders['payment_method'] == 'Не указано').sum()}"
        )

        st.write(
            "Заказов без способа доставки: "
            f"{(orders['shipping_method'] == 'Не указано').sum()}"
        )


if __name__ == "__main__":
    main()
