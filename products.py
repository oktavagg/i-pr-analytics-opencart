from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics_ui import BRAND_YELLOW, configure_plot, render_module_placeholder


CATEGORY_TITLE = "Товары"
PAGES = [
    ("products_no_sales", "Товары без продаж"),
    ("top_products_revenue", "Топ товаров по выручке"),
    ("top_products_units", "Топ товаров по количеству продаж"),
    ("products_together", "Покупают вместе"),
]
PAGE_DESCRIPTIONS = {
    "products_no_sales": "Товары каталога, которые не продавались в выбранном периоде.",
    "top_products_revenue": "Товары, которые сформировали наибольший оборот.",
    "top_products_units": "Товары с наибольшим количеством проданных единиц.",
    "products_together": "Пары товаров, которые встречаются в одном заказе.",
}


def render_top_products_revenue_page(context: dict[str, object]) -> None:
    products = context["products"]
    if products.empty:
        st.info("В выбранном периоде нет товарных позиций.")
        return

    top_products_frame = products.nlargest(10, "revenue").sort_values("revenue")
    chart = px.bar(
        top_products_frame,
        x="revenue",
        y="product_name",
        orientation="h",
        text_auto=".2s",
        title="Топ-10 товаров по обороту",
        labels={"revenue": "Оборот, грн", "product_name": "Товар"},
        color_discrete_sequence=[BRAND_YELLOW],
    )
    chart.update_layout(yaxis_title=None)
    st.plotly_chart(configure_plot(chart, 500), width="stretch")

def render_top_products_units_page(context: dict[str, object]) -> None:
    products = context["products"]
    if products.empty:
        st.info("В выбранном периоде нет товарных позиций.")
        return

    top_products_frame = products.nlargest(10, "sold_units").sort_values("sold_units")
    chart = px.bar(
        top_products_frame,
        x="sold_units",
        y="product_name",
        orientation="h",
        text="sold_units",
        title="Топ-10 товаров по количеству продаж",
        labels={"sold_units": "Продано, шт.", "product_name": "Товар"},
        color_discrete_sequence=[BRAND_YELLOW],
    )
    chart.update_layout(yaxis_title=None)
    st.plotly_chart(configure_plot(chart, 500), width="stretch")

def render_products_together_page(context: dict[str, object]) -> None:
    pairs = context["business"]["pairs"]
    if isinstance(pairs, pd.DataFrame) and not pairs.empty:
        st.dataframe(pairs, width="stretch", hide_index=True)
    else:
        st.info("Недостаточно заказов с несколькими товарами для анализа пар.")


def render_products_no_sales_page(context: dict[str, object]) -> None:
    render_module_placeholder("Товары без продаж")


def render(page_key: str, context: dict[str, object]) -> bool:
    renderers = {
        "products_no_sales": render_products_no_sales_page,
        "top_products_revenue": render_top_products_revenue_page,
        "top_products_units": render_top_products_units_page,
        "products_together": render_products_together_page,
    }
    renderer = renderers.get(page_key)
    if renderer is None:
        return False
    renderer(context)
    return True
