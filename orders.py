from __future__ import annotations

from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics_ui import add_trendline, configure_plot, format_money, format_number, safe_percent


CATEGORY_TITLE = "Замовлення"
PAGES = [
    ("revenue", "Оборот"),
    ("revenue_segments", "Оборот (нові/старі)"),
    ("orders_count", "Замовлення"),
    ("orders_segments", "Замовлення (нові/старі)"),
    ("average_check", "Середній чек"),
    ("check_segments", "Середній чек (нові/старі)"),
    ("items_per_order", "Товарів у замовленні"),
    ("order_frequency", "Частота між замовленнями"),
    ("order_statuses", "Статуси"),
    ("shipping_rating", "Доставки"),
]
PAGE_DESCRIPTIONS = {
    "revenue": "Динаміка обороту за вибраний період.",
    "revenue_segments": "Оборот нових і повторних покупців.",
    "orders_count": "Динаміка кількості замовлень.",
    "orders_segments": "Кількість нових і повторних замовлень.",
    "average_check": "Динаміка середнього чека.",
    "check_segments": "Середній чек нових і повторних покупців.",
    "items_per_order": "Скільки товарів потрапляє в одне замовлення.",
    "order_statuses": "Розподіл замовлень за статусами.",
    "order_frequency": "Інтервал між повторними замовленнями покупців.",
    "shipping_rating": "Розподіл замовлень за способами доставки.",
}

VIEW_LABELS = {
    "day": "День",
    "week": "Тиждень",
    "month": "Місяць",
}


def _group_time(df: pd.DataFrame, date_col: str = "order_date") -> pd.DataFrame:
    frame = df.copy()
    view = str(st.session_state.get("current_view_granularity", "month"))
    if view == "day":
        frame["period_start"] = frame[date_col].dt.floor("D")
        frame["period_label"] = frame["period_start"].dt.strftime("%d.%m.%Y")
    elif view == "week":
        frame["period_start"] = frame[date_col].dt.to_period("W-MON").apply(lambda period: period.start_time)
        frame["period_label"] = frame["period_start"].dt.strftime("%d.%m") + "–" + (frame["period_start"] + pd.Timedelta(days=6)).dt.strftime("%d.%m")
    else:
        frame["period_start"] = frame[date_col].dt.to_period("M").dt.to_timestamp()
        frame["period_label"] = frame["period_start"].dt.strftime("%m.%Y")
    return frame


def _classify_orders(context: dict[str, object]) -> pd.DataFrame:
    orders = context["orders"].copy()
    history = context["all_orders"].copy()
    selected_statuses = context.get("selected_statuses", [])
    if selected_statuses:
        history = history[history["status"].isin(selected_statuses)].copy()
    first_dates = history.groupby("customer_key")["order_date"].min()
    orders["first_order_date"] = orders["customer_key"].map(first_dates)
    orders["segment"] = "Старі"
    first_mask = orders["order_date"].dt.normalize() == orders["first_order_date"].dt.normalize()
    orders.loc[first_mask, "segment"] = "Нові"
    return orders


def _table(df: pd.DataFrame, column_config: dict | None = None) -> None:
    st.dataframe(df, width="stretch", hide_index=True, column_config=column_config or {})


def _bar_chart(df: pd.DataFrame, y: str, title: str, y_label: str) -> None:
    fig = px.bar(
        df,
        x="period_label",
        y=y,
        text=df[y].round(0),
        title=title,
        labels={"period_label": "Період", y: y_label},
        color_discrete_sequence=["#4285F4"],
        category_orders={"period_label": df["period_label"].tolist()},
    )
    fig.update_traces(
        marker_line_color="#FFFFFF",
        marker_line_width=1.0,
        texttemplate="%{text:.0f}",
        textposition="inside",
        selector=dict(type="bar"),
    )
    add_trendline(fig, df["period_label"].tolist(), df[y].astype(float).tolist())
    configure_plot(fig, 470)
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _segmented_chart(df: pd.DataFrame, value_col: str, title: str, y_label: str, trend_label: str) -> None:
    fig = px.bar(
        df,
        x="period_label",
        y=value_col,
        color="segment",
        barmode="group",
        title=title,
        labels={"period_label": "Період", value_col: y_label, "segment": "Сегмент"},
        color_discrete_sequence=["#4285F4", "#007FC5"],
        category_orders={"period_label": df["period_label"].drop_duplicates().tolist(), "segment": ["Нові", "Старі"]},
    )
    fig.update_traces(marker_line_color="#FFFFFF", marker_line_width=1.0, selector=dict(type="bar"))
    for segment, segment_df in df.groupby("segment"):
        ordered = segment_df.sort_values("period_start")
        add_trendline(fig, ordered["period_label"].tolist(), ordered[value_col].astype(float).tolist(), name=f"Тренд: {segment}")
    configure_plot(fig, 470)
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_revenue_page(context: dict[str, object]) -> None:
    grouped = _group_time(context["orders"])
    monthly = grouped.groupby(["period_start", "period_label"], as_index=False).agg(
        revenue=("order_total", "sum"), orders=("order_id", "nunique")
    ).sort_values("period_start")
    monthly["average_check"] = (monthly["revenue"] / monthly["orders"].replace(0, pd.NA)).fillna(0).round(0)
    _bar_chart(monthly, "revenue", "Оборот за періодами", "Оборот, грн")
    table = monthly.rename(columns={"period_label": "Період", "revenue": "Оборот", "orders": "Замовлення", "average_check": "Середній чек"})
    _table(table[["Період", "Оборот", "Замовлення", "Середній чек"]], {
        "Оборот": st.column_config.NumberColumn(format="%.0f грн"),
        "Середній чек": st.column_config.NumberColumn(format="%.0f грн"),
    })


def render_revenue_segments_page(context: dict[str, object]) -> None:
    orders = _group_time(_classify_orders(context))
    data = orders.groupby(["period_start", "period_label", "segment"], as_index=False).agg(
        value=("order_total", "sum"), orders=("order_id", "nunique")
    ).sort_values("period_start")
    _segmented_chart(data, "value", "Оборот нових і старих покупців", "Оборот, грн", "Оборот")
    table = data.rename(columns={"period_label": "Період", "segment": "Сегмент", "value": "Оборот", "orders": "Замовлення"})
    _table(table[["Період", "Сегмент", "Оборот", "Замовлення"]], {"Оборот": st.column_config.NumberColumn(format="%.0f грн")})


def render_orders_count_page(context: dict[str, object]) -> None:
    grouped = _group_time(context["orders"])
    data = grouped.groupby(["period_start", "period_label"], as_index=False).agg(orders=("order_id", "nunique")).sort_values("period_start")
    _bar_chart(data, "orders", "Кількість замовлень за періодами", "Замовлення")
    _table(data.rename(columns={"period_label": "Період", "orders": "Замовлення"})[["Період", "Замовлення"]])


def render_orders_segments_page(context: dict[str, object]) -> None:
    orders = _group_time(_classify_orders(context))
    data = orders.groupby(["period_start", "period_label", "segment"], as_index=False).agg(value=("order_id", "nunique")).sort_values("period_start")
    _segmented_chart(data, "value", "Замовлення нових і старих покупців", "Замовлення", "Замовлення")
    _table(data.rename(columns={"period_label": "Період", "segment": "Сегмент", "value": "Замовлення"})[["Період", "Сегмент", "Замовлення"]])


def render_average_check_page(context: dict[str, object]) -> None:
    grouped = _group_time(context["orders"])
    data = grouped.groupby(["period_start", "period_label"], as_index=False).agg(revenue=("order_total", "sum"), orders=("order_id", "nunique")).sort_values("period_start")
    data["average_check"] = (data["revenue"] / data["orders"].replace(0, pd.NA)).fillna(0).round(0)
    _bar_chart(data, "average_check", "Середній чек за періодами", "Середній чек, грн")
    table = data.rename(columns={"period_label": "Період", "average_check": "Середній чек", "orders": "Замовлення", "revenue": "Оборот"})
    _table(table[["Період", "Середній чек", "Замовлення", "Оборот"]], {
        "Середній чек": st.column_config.NumberColumn(format="%.0f грн"),
        "Оборот": st.column_config.NumberColumn(format="%.0f грн"),
    })


def render_check_segments_page(context: dict[str, object]) -> None:
    orders = _group_time(_classify_orders(context))
    data = orders.groupby(["period_start", "period_label", "segment"], as_index=False).agg(revenue=("order_total", "sum"), orders=("order_id", "nunique")).sort_values("period_start")
    data["value"] = (data["revenue"] / data["orders"].replace(0, pd.NA)).fillna(0).round(0)
    _segmented_chart(data, "value", "Середній чек нових і старих покупців", "Середній чек, грн", "Середній чек")
    table = data.rename(columns={"period_label": "Період", "segment": "Сегмент", "value": "Середній чек", "orders": "Замовлення", "revenue": "Оборот"})
    _table(table[["Період", "Сегмент", "Середній чек", "Замовлення", "Оборот"]], {
        "Середній чек": st.column_config.NumberColumn(format="%.0f грн"),
        "Оборот": st.column_config.NumberColumn(format="%.0f грн"),
    })


def render_items_per_order_page(context: dict[str, object]) -> None:
    orders = _group_time(context["orders"])
    data = orders.groupby(["period_start", "period_label"], as_index=False).agg(
        orders=("order_id", "nunique"), items=("item_quantity", "sum")
    ).sort_values("period_start")
    data["items_per_order"] = data["items"] / data["orders"].replace(0, pd.NA)
    _bar_chart(data, "items_per_order", "Товарів у замовленні за періодами", "Товарів у замовленні")
    table = data.rename(columns={"period_label": "Період", "items_per_order": "Товарів у замовленні", "orders": "Замовлення", "items": "Товарів загалом"})
    _table(table[["Період", "Товарів у замовленні", "Замовлення", "Товарів загалом"]], {"Товарів у замовленні": st.column_config.NumberColumn(format="%.2f")})


def render_order_statuses_page(context: dict[str, object]) -> None:
    orders = context["all_status_orders"].copy()
    if orders.empty:
        st.info("За вибраний період немає замовлень.")
        return
    data = orders.groupby("status", as_index=False).agg(orders=("order_id", "nunique"), revenue=("order_total", "sum")).sort_values("orders", ascending=False)
    fig = px.pie(data, names="status", values="orders", hole=0.45, title="Статуси замовлень")
    configure_plot(fig, 470)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    total_orders = int(data["orders"].sum())
    total_revenue = float(data["revenue"].sum())
    data["% замовлень"] = data["orders"].apply(lambda value: safe_percent(float(value), total_orders))
    data["% обороту"] = data["revenue"].apply(lambda value: safe_percent(float(value), total_revenue))
    table = data.rename(columns={"status": "Статус", "orders": "Замовлення", "revenue": "Оборот"})
    _table(table[["Статус", "Замовлення", "Оборот", "% замовлень", "% обороту"]], {"Оборот": st.column_config.NumberColumn(format="%.0f грн"), "% замовлень": st.column_config.NumberColumn(format="%.1f%%"), "% обороту": st.column_config.NumberColumn(format="%.1f%%")})


def render_shipping_rating_page(context: dict[str, object]) -> None:
    orders = context["orders"].copy()
    if orders.empty:
        st.info("За вибраний період немає замовлень з доставкою.")
        return
    data = orders.groupby("shipping_method", as_index=False).agg(orders=("order_id", "nunique"), revenue=("order_total", "sum")).sort_values("orders", ascending=False)
    fig = px.pie(data, names="shipping_method", values="orders", hole=0.45, title="Доставки")
    configure_plot(fig, 470)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    total_orders = int(data["orders"].sum())
    total_revenue = float(data["revenue"].sum())
    data["% замовлень"] = data["orders"].apply(lambda value: safe_percent(float(value), total_orders))
    data["% обороту"] = data["revenue"].apply(lambda value: safe_percent(float(value), total_revenue))
    table = data.rename(columns={"shipping_method": "Доставка", "orders": "Замовлення", "revenue": "Оборот"})
    _table(table[["Доставка", "Замовлення", "Оборот", "% замовлень", "% обороту"]], {"Оборот": st.column_config.NumberColumn(format="%.0f грн"), "% замовлень": st.column_config.NumberColumn(format="%.1f%%"), "% обороту": st.column_config.NumberColumn(format="%.1f%%")})
    missing = int(data.loc[data["shipping_method"].str.contains("Не", case=False, na=False), "orders"].sum())
    if missing:
        st.warning(f"У {missing} замовленнях спосіб доставки не вказано. Це варто перевірити в оформленні замовлення та XML-експорті.")


def render_order_frequency_page(context: dict[str, object]) -> None:
    history = context["all_orders"].copy()
    selected_statuses = context.get("selected_statuses", [])
    if selected_statuses:
        history = history[history["status"].isin(selected_statuses)].copy()
    history = history.sort_values(["customer_key", "order_date", "order_id"], kind="stable")
    history["previous_order_date"] = history.groupby("customer_key")["order_date"].shift(1)
    history["interval_days"] = (history["order_date"].dt.normalize() - history["previous_order_date"].dt.normalize()).dt.days
    intervals = history[
        history["order_date"].dt.date.between(context["start_date"], context["end_date"])
        & history["interval_days"].notna()
        & (history["interval_days"] >= 0)
    ].copy()
    if intervals.empty:
        st.info("У вибраному періоді немає повторних замовлень для розрахунку інтервалу.")
        return
    average_interval = float(intervals["interval_days"].mean())
    repeat_orders = int(intervals["order_id"].nunique())
    repeat_customers = int(intervals["customer_key"].nunique())
    col1, col2, col3 = st.columns(3)
    col1.metric("Середній інтервал", f"{average_interval:.0f} дн.")
    col2.metric("Повторних замовлень", format_number(repeat_orders))
    col3.metric("Покупців з повтором", format_number(repeat_customers))
    table = intervals[["customer_name", "phone", "email", "order_date", "previous_order_date", "interval_days", "order_total"]].copy()
    table = table.rename(columns={"customer_name": "Покупець", "phone": "Телефон", "email": "Email", "order_date": "Дата замовлення", "previous_order_date": "Попереднє замовлення", "interval_days": "Днів між замовленнями", "order_total": "Оборот"})
    _table(table, {"Оборот": st.column_config.NumberColumn(format="%.0f грн")})


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
