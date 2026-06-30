from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics_ui import add_trendline, configure_plot, format_money, format_number, safe_percent


CATEGORY_TITLE = "Покупці"
PAGES = [
    ("customers_count", "Кількість (нові/старі)"),
    ("orders_per_customer", "Замовлень на покупця"),
    ("sleeping_customers", "Сплячі покупці"),
    ("top_customers", "ТОП-10 покупців"),
]
PAGE_DESCRIPTIONS = {
    "customers_count": "Кількість нових і старих покупців за вибраний період.",
    "orders_per_customer": "Середня кількість замовлень на покупця і розподіл покупців за частотою.",
    "sleeping_customers": "Покупці з двома і більше замовленнями, які давно не купували.",
    "top_customers": "ТОП-10 покупців за оборотом і кількістю замовлень за вибраний період.",
}


def _group_time(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    view = str(st.session_state.get("current_view_granularity", "month"))
    if view == "day":
        frame["period_start"] = frame["order_date"].dt.floor("D")
        frame["period_label"] = frame["period_start"].dt.strftime("%d.%m.%Y")
    elif view == "week":
        frame["period_start"] = frame["order_date"].dt.to_period("W-MON").apply(lambda period: period.start_time)
        frame["period_label"] = frame["period_start"].dt.strftime("%d.%m") + "–" + (frame["period_start"] + pd.Timedelta(days=6)).dt.strftime("%d.%m")
    else:
        frame["period_start"] = frame["order_date"].dt.to_period("M").dt.to_timestamp()
        frame["period_label"] = frame["period_start"].dt.strftime("%m.%Y")
    return frame


def _customer_rollup(orders: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame()
    summary = orders.groupby("customer_key", as_index=False).agg(
        customer_name=("customer_name", "last"),
        phone=("phone", "last"),
        email=("email", "last"),
        orders=("order_id", "nunique"),
        revenue=("order_total", "sum"),
        last_order=("order_date", "max"),
    )
    summary["average_check"] = (summary["revenue"] / summary["orders"].replace(0, pd.NA)).fillna(0).round(0)
    summary["revenue"] = summary["revenue"].round(0)
    return summary


def _classify(context: dict[str, object]) -> pd.DataFrame:
    orders = context["orders"].copy()
    history = context["all_orders"].copy()
    selected_statuses = context.get("selected_statuses", [])
    if selected_statuses:
        history = history[history["status"].isin(selected_statuses)].copy()
    first_dates = history.groupby("customer_key")["order_date"].min()
    orders["first_order_date"] = orders["customer_key"].map(first_dates)
    orders["segment"] = "Старі"
    orders.loc[orders["order_date"].dt.normalize() == orders["first_order_date"].dt.normalize(), "segment"] = "Нові"
    return orders


def _table(df: pd.DataFrame, config: dict | None = None) -> None:
    st.dataframe(df, width="stretch", hide_index=True, column_config=config or {})


def render_customers_count_page(context: dict[str, object]) -> None:
    orders = _classify(context)
    data = orders.groupby("segment", as_index=False).agg(customers=("customer_key", "nunique"), orders=("order_id", "nunique"), revenue=("order_total", "sum"))
    total_customers = int(data["customers"].sum())
    data["% покупців"] = data["customers"].apply(lambda value: safe_percent(float(value), total_customers))
    fig = px.pie(data, names="segment", values="customers", hole=0.55, title="Нові та старі покупці")
    configure_plot(fig, 430)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    table = data.rename(columns={"segment": "Сегмент", "customers": "Покупці", "orders": "Замовлення", "revenue": "Оборот"})
    _table(table[["Сегмент", "Покупці", "Замовлення", "Оборот", "% покупців"]], {"Оборот": st.column_config.NumberColumn(format="%.0f грн"), "% покупців": st.column_config.NumberColumn(format="%.1f%%")})


def render_orders_per_customer_page(context: dict[str, object]) -> None:
    orders = context["orders"].copy()
    rollup = _customer_rollup(orders)
    if rollup.empty:
        st.info("За вибраний період немає покупців.")
        return

    buyers_2 = int((rollup["orders"] == 2).sum())
    buyers_3 = int((rollup["orders"] == 3).sum())
    buyers_3_plus = int((rollup["orders"] >= 3).sum())
    avg_orders = float(rollup["orders"].mean())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Замовлень на покупця", f"{avg_orders:.2f}")
    c2.metric("Покупців з 2", format_number(buyers_2))
    c3.metric("Покупців з 3", format_number(buyers_3))
    c4.metric("Покупців з 3+", format_number(buyers_3_plus))

    grouped = _group_time(orders)
    monthly = grouped.groupby(["period_start", "period_label"], as_index=False).agg(orders=("order_id", "nunique"), customers=("customer_key", "nunique")).sort_values("period_start")
    monthly["orders_per_customer"] = monthly["orders"] / monthly["customers"].replace(0, pd.NA)
    fig = px.line(monthly, x="period_label", y="orders_per_customer", markers=True, title="Замовлень на покупця в динаміці", labels={"period_label": "Період", "orders_per_customer": "Замовлень на покупця"})
    add_trendline(fig, monthly["period_label"].tolist(), monthly["orders_per_customer"].fillna(0).astype(float).tolist())
    configure_plot(fig, 430)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    _table(monthly.rename(columns={"period_label": "Період", "orders": "Замовлення", "customers": "Покупці", "orders_per_customer": "Замовлень на покупця"})[["Період", "Замовлення", "Покупці", "Замовлень на покупця"]], {"Замовлень на покупця": st.column_config.NumberColumn(format="%.2f")})

    distribution = rollup.copy()
    distribution["Група"] = distribution["orders"].apply(lambda value: "2" if value == 2 else "3" if value == 3 else "3+" if value >= 3 else "1")
    dist = distribution.groupby("Група", as_index=False).agg(Покупці=("customer_key", "nunique"), Оборот=("revenue", "sum"))
    _table(dist, {"Оборот": st.column_config.NumberColumn(format="%.0f грн")})


def render_sleeping_customers_page(context: dict[str, object]) -> None:
    history = context["all_orders"].copy()
    selected_statuses = context.get("selected_statuses", [])
    if selected_statuses:
        history = history[history["status"].isin(selected_statuses)].copy()
    cutoff = pd.Timestamp(context["end_date"] - pd.Timedelta(days=90))
    until_end = history[history["order_date"].dt.date <= context["end_date"]].copy()
    rollup = _customer_rollup(until_end)
    sleeping = rollup[(rollup["orders"] >= 2) & (rollup["last_order"] <= cutoff)].copy() if not rollup.empty else pd.DataFrame()
    st.metric("Кількість сплячих", format_number(len(sleeping)))

    if not history.empty:
        min_month = history["order_date"].min().to_period("M").to_timestamp()
        max_month = pd.Timestamp(context["end_date"]).to_period("M").to_timestamp()
        months = pd.date_range(min_month, max_month, freq="MS")
        rows = []
        for month_start in months:
            month_end = month_start + pd.offsets.MonthEnd(0)
            hist = history[history["order_date"] <= month_end].copy()
            snap = _customer_rollup(hist)
            if snap.empty:
                count = 0
            else:
                cutoff_m = month_end - pd.Timedelta(days=90)
                count = int(((snap["orders"] >= 2) & (snap["last_order"] <= cutoff_m)).sum())
            rows.append({"period_label": month_start.strftime("%m.%Y"), "sleeping": count})
        dynamic = pd.DataFrame(rows)
        fig = px.bar(dynamic, x="period_label", y="sleeping", text="sleeping", title="Сплячі покупці по місяцях", labels={"period_label": "Місяць", "sleeping": "Кількість"})
        add_trendline(fig, dynamic["period_label"].tolist(), dynamic["sleeping"].astype(float).tolist())
        configure_plot(fig, 430)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    if not sleeping.empty:
        table = sleeping.rename(columns={"customer_name": "Покупець", "phone": "Телефон", "email": "Email", "orders": "Замовлення", "revenue": "Оборот", "last_order": "Останнє замовлення", "average_check": "Середній чек"})
        _table(table[["Покупець", "Телефон", "Email", "Замовлення", "Оборот", "Середній чек", "Останнє замовлення"]], {"Оборот": st.column_config.NumberColumn(format="%.0f грн"), "Середній чек": st.column_config.NumberColumn(format="%.0f грн")})


def render_top_customers_page(context: dict[str, object]) -> None:
    rollup = _customer_rollup(context["orders"])
    if rollup.empty:
        st.info("За вибраний період немає покупців.")
        return

    chart_left, chart_right = st.columns(2, gap="large")
    with chart_left:
        by_revenue = rollup.sort_values(["revenue", "orders"], ascending=False).head(10).sort_values("revenue")
        fig = px.bar(by_revenue, x="revenue", y="customer_name", orientation="h", title="ТОП-10 за оборотом", labels={"revenue": "Оборот, грн", "customer_name": "Покупець"}, color_discrete_sequence=["#007FC5"])
        configure_plot(fig, 430)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with chart_right:
        by_orders = rollup.sort_values(["orders", "revenue"], ascending=False).head(10).sort_values("orders")
        fig = px.bar(by_orders, x="orders", y="customer_name", orientation="h", title="ТОП-10 за замовленнями", labels={"orders": "Замовлення", "customer_name": "Покупець"}, color_discrete_sequence=["#4285F4"])
        configure_plot(fig, 430)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    ranked = rollup.sort_values(["revenue", "orders"], ascending=False).head(10).copy()
    ranked.insert(0, "#", range(1, len(ranked) + 1))
    table = ranked.rename(columns={"customer_name": "Клієнт", "phone": "Телефон", "email": "Email", "orders": "Замовл.", "revenue": "Виторг", "average_check": "Середній чек"})
    _table(table[["#", "Клієнт", "Телефон", "Email", "Замовл.", "Виторг", "Середній чек"]], {"Виторг": st.column_config.NumberColumn(format="%.0f грн"), "Середній чек": st.column_config.NumberColumn(format="%.0f грн")})


def render_top_customers_revenue_page(context: dict[str, object]) -> None:
    render_top_customers_page(context)


def render_top_customers_orders_page(context: dict[str, object]) -> None:
    render_top_customers_page(context)


def render(page_key: str, context: dict[str, object]) -> bool:
    renderers = {
        "customers_count": render_customers_count_page,
        "orders_per_customer": render_orders_per_customer_page,
        "sleeping_customers": render_sleeping_customers_page,
        "top_customers": render_top_customers_page,
        "top_customers_revenue": render_top_customers_revenue_page,
        "top_customers_orders": render_top_customers_orders_page,
    }
    renderer = renderers.get(page_key)
    if renderer is None:
        return False
    renderer(context)
    return True
