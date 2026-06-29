from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics_ui import format_money, format_number, percent_delta, safe_percent
from conclusions import classify_orders_by_customer_history


CATEGORY_TITLE = "Головне"
PAGES = [("overview", "Огляд")]
PAGE_DESCRIPTIONS = {
    "overview": "Головні показники магазину за вибраний період.",
}


def _snapshot(orders: pd.DataFrame) -> dict[str, float]:
    if orders.empty:
        return {"revenue": 0.0, "orders": 0, "average": 0.0, "customers": 0, "repeat_share": 0.0}
    classified = classify_orders_by_customer_history(orders)
    revenue = float(classified["order_total"].sum())
    order_count = int(classified["order_id"].nunique())
    repeat_revenue = float(classified.loc[classified["comparison_segment"] == "Повторний", "order_total"].sum())
    return {
        "revenue": revenue,
        "orders": order_count,
        "average": revenue / order_count if order_count else 0.0,
        "customers": int(classified["customer_key"].nunique()),
        "repeat_share": safe_percent(repeat_revenue, revenue),
    }


def render_overview_page(context: dict[str, object]) -> None:
    orders: pd.DataFrame = context["orders"]
    previous_orders: pd.DataFrame = context["previous_orders"]
    products: pd.DataFrame = context["products"]
    catalog: pd.DataFrame = context["product_catalog"]
    items: pd.DataFrame = context["items"]
    business = context["business"]

    current = _snapshot(orders)
    previous = _snapshot(previous_orders)

    active_catalog = catalog[catalog["status"] == True].copy() if not catalog.empty else pd.DataFrame()
    in_stock = int((active_catalog["quantity"] > 0).sum()) if not active_catalog.empty else 0
    sold_ids = set(items["product_id"].astype(str)) if not items.empty else set()
    no_sales = int((~active_catalog["product_id"].astype(str).isin(sold_ids)).sum()) if not active_catalog.empty else 0
    top5_share = float(business.get("top5_share", 0.0))
    avg_items = float(business.get("average_items", 0.0))

    cards = [
        ("Оборот", format_money(current["revenue"]), percent_delta(current["revenue"], previous["revenue"])),
        ("Замовлення", format_number(current["orders"]), percent_delta(current["orders"], previous["orders"])),
        ("Середній чек", format_money(current["average"]), percent_delta(current["average"], previous["average"])),
        ("Покупці", format_number(current["customers"]), percent_delta(current["customers"], previous["customers"])),
        ("Повторний оборот", f"{current['repeat_share']:.1f}%", percent_delta(current["repeat_share"], previous["repeat_share"])),
        ("Товарів у замовленні", f"{avg_items:.1f}", None),
        ("Активні товари в наявності", format_number(in_stock), None),
        ("Товари без продажів", format_number(no_sales), None),
        ("Частка топ-5 товарів", f"{top5_share:.1f}%", None),
        ("Продано одиниць", format_number(int(context.get("sold_units", 0))), None),
    ]

    for start in range(0, len(cards), 5):
        columns = st.columns(5)
        for column, (label, value, delta) in zip(columns, cards[start:start + 5]):
            column.metric(label, value, delta=delta)


def render(page_key: str, context: dict[str, object]) -> bool:
    if page_key != "overview":
        return False
    render_overview_page(context)
    return True
