from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics_ui import configure_plot, format_number, safe_percent


CATEGORY_TITLE = "Товари"
PAGES = [
    ("active_products_stock", "Активні товари в наявності"),
    ("top_products", "Топ товарів"),
    ("products_no_sales", "Товари без продажів"),
    ("products_no_views", "Товари без переглядів"),
    ("product_conversion", "Конверсія по товарах"),
    ("products_together", "Купують разом"),
]
PAGE_DESCRIPTIONS = {
    "active_products_stock": "Кількість активних товарів у наявності та структура каталогу.",
    "top_products": "ТОП-10 товарів за виручкою та кількістю продажів за вибраний період.",
    "products_no_sales": "Товари каталогу без продажів за вибраний період.",
    "products_no_views": "Активні товари без переглядів у каталозі.",
    "product_conversion": "Співвідношення продажів і переглядів товарів.",
    "products_together": "Пари товарів, які часто потрапляють в одне замовлення.",
}


def _sales_frame(context: dict[str, object]) -> pd.DataFrame:
    products = context["products"].copy()
    for col in ("orders", "sold_units", "revenue"):
        if col in products.columns:
            products[col] = pd.to_numeric(products[col], errors="coerce").fillna(0)
    return products


def _catalog_sales(context: dict[str, object]) -> pd.DataFrame:
    catalog = context["product_catalog"].copy()
    sales = _sales_frame(context)
    if catalog.empty:
        return pd.DataFrame()
    catalog["product_id"] = catalog["product_id"].astype(str)
    if sales.empty:
        catalog["orders"] = 0
        catalog["sold_units"] = 0
        catalog["revenue"] = 0.0
        return catalog
    sales = sales[["product_id", "orders", "sold_units", "revenue"]].copy()
    sales["product_id"] = sales["product_id"].astype(str)
    merged = catalog.merge(sales, on="product_id", how="left")
    for col in ("orders", "sold_units", "revenue"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)
    return merged


def _table(df: pd.DataFrame, config: dict | None = None) -> None:
    st.dataframe(df, width="stretch", hide_index=True, column_config=config or {})


def render_active_products_stock_page(context: dict[str, object]) -> None:
    catalog = context["product_catalog"].copy()
    if catalog.empty:
        st.info("Каталог товарів порожній.")
        return
    active = catalog[catalog["status"] == True].copy()
    in_stock = int((active["quantity"] > 0).sum())
    st.metric("Активні товари в наявності", format_number(in_stock))
    data = pd.DataFrame([
        {"Стан": "В наявності", "Кількість": in_stock},
        {"Стан": "Без залишку", "Кількість": int((active["quantity"] <= 0).sum())},
        {"Стан": "Вимкнені", "Кількість": int((catalog["status"] == False).sum())},
    ])
    fig = px.pie(data, names="Стан", values="Кількість", hole=0.5, title="Структура товарів каталогу")
    configure_plot(fig, 430)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_top_products_page(context: dict[str, object]) -> None:
    products = _sales_frame(context)
    if products.empty:
        st.info("За вибраний період немає продажів товарів.")
        return

    left, right = st.columns(2, gap="large")
    with left:
        by_revenue = products.sort_values(["revenue", "orders"], ascending=False).head(10).sort_values("revenue")
        fig = px.bar(by_revenue, x="revenue", y="product_name", orientation="h", title="ТОП-10 за виручкою", labels={"revenue": "Виручка, грн", "product_name": "Товар"}, color_discrete_sequence=["#D4A91F"])
        configure_plot(fig, 430)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with right:
        by_orders = products.sort_values(["orders", "revenue"], ascending=False).head(10).sort_values("orders")
        fig = px.bar(by_orders, x="orders", y="product_name", orientation="h", title="ТОП-10 за замовленнями", labels={"orders": "Замовлення", "product_name": "Товар"}, color_discrete_sequence=["#24B47E"])
        configure_plot(fig, 430)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    ranked = products.sort_values(["revenue", "orders"], ascending=False).head(10).copy()
    ranked.insert(0, "#", range(1, len(ranked) + 1))
    table = ranked.rename(columns={"product_name": "Товар", "orders": "Замовл.", "sold_units": "Шт.", "revenue": "Виторг"})
    _table(table[["#", "Товар", "Замовл.", "Шт.", "Виторг"]], {"Виторг": st.column_config.NumberColumn(format="%.0f грн")})


def render_top_products_revenue_page(context: dict[str, object]) -> None:
    render_top_products_page(context)


def render_top_products_units_page(context: dict[str, object]) -> None:
    render_top_products_page(context)


def render_products_no_sales_page(context: dict[str, object]) -> None:
    data = _catalog_sales(context)
    if data.empty:
        st.info("Каталог товарів порожній.")
        return
    active = data[data["status"] == True].copy()
    no_sales = active[active["sold_units"] <= 0].copy()
    st.metric("Товарів без продажів", format_number(len(no_sales)))
    table = no_sales.rename(columns={"product_name": "Товар", "quantity": "Залишок", "effective_price": "Ціна", "viewed": "Перегляди", "manufacturer": "Виробник", "link": "Посилання"})
    cols = [c for c in ["Товар", "Виробник", "Ціна", "Залишок", "Перегляди", "Посилання"] if c in table.columns]
    _table(table[cols], {"Ціна": st.column_config.NumberColumn(format="%.0f грн")})


def render_products_no_views_page(context: dict[str, object]) -> None:
    data = _catalog_sales(context)
    if data.empty or "viewed" not in data.columns:
        st.info("У каталозі немає даних по переглядах.")
        return
    active = data[data["status"] == True].copy()
    no_views = active[pd.to_numeric(active["viewed"], errors="coerce").fillna(0) <= 0].copy()
    st.metric("Товарів без переглядів", format_number(len(no_views)))
    fig = px.bar(pd.DataFrame({"Показник": ["Без переглядів"], "Кількість": [len(no_views)]}), x="Показник", y="Кількість", text="Кількість", title="Товари без переглядів")
    configure_plot(fig, 360)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    table = no_views.rename(columns={"product_name": "Товар", "quantity": "Залишок", "effective_price": "Ціна", "viewed": "Перегляди", "manufacturer": "Виробник", "link": "Посилання"})
    cols = [c for c in ["Товар", "Виробник", "Ціна", "Залишок", "Перегляди", "Посилання"] if c in table.columns]
    _table(table[cols], {"Ціна": st.column_config.NumberColumn(format="%.0f грн")})


def render_product_conversion_page(context: dict[str, object]) -> None:
    data = _catalog_sales(context)
    if data.empty or "viewed" not in data.columns:
        st.info("У каталозі немає даних для розрахунку конверсії.")
        return
    data["viewed"] = pd.to_numeric(data["viewed"], errors="coerce").fillna(0)
    data["conversion"] = data.apply(lambda row: row["orders"] / row["viewed"] * 100 if row["viewed"] else 0.0, axis=1)
    ranked = data[data["viewed"] > 0].sort_values(["conversion", "orders"], ascending=False).copy()
    table = ranked.rename(columns={"product_name": "Товар", "viewed": "Перегляди", "orders": "Замовлення", "sold_units": "Шт.", "revenue": "Виручка", "conversion": "Конверсія"})
    _table(table[["Товар", "Перегляди", "Замовлення", "Шт.", "Виручка", "Конверсія"]], {"Виручка": st.column_config.NumberColumn(format="%.0f грн"), "Конверсія": st.column_config.NumberColumn(format="%.2f%%")})


def render_products_together_page(context: dict[str, object]) -> None:
    items = context["items"].copy()
    if items.empty:
        st.info("Немає товарів у замовленнях за вибраний період.")
        return
    names = items.drop_duplicates("product_id").set_index("product_id")["product_name"].to_dict()
    pairs: dict[tuple[str, str], int] = {}
    for _, group in items.groupby("order_id"):
        product_ids = sorted(set(group["product_id"].astype(str)))
        for i, first in enumerate(product_ids):
            for second in product_ids[i + 1:]:
                key = (first, second)
                pairs[key] = pairs.get(key, 0) + 1
    rows = [{"Товар 1": names.get(a, a), "Товар 2": names.get(b, b), "Спільних замовлень": c} for (a, b), c in sorted(pairs.items(), key=lambda item: item[1], reverse=True)[:20]]
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("У вибраному періоді немає замовлень з двома і більше товарами.")
        return
    top = df.head(10).copy()
    top["Пара"] = top["Товар 1"].str.slice(0, 28) + " + " + top["Товар 2"].str.slice(0, 28)
    fig = px.bar(top.sort_values("Спільних замовлень"), x="Спільних замовлень", y="Пара", orientation="h", title="Купують разом")
    configure_plot(fig, 520)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    _table(df)


def render(page_key: str, context: dict[str, object]) -> bool:
    renderers = {
        "active_products_stock": render_active_products_stock_page,
        "top_products": render_top_products_page,
        "top_products_revenue": render_top_products_revenue_page,
        "top_products_units": render_top_products_units_page,
        "products_no_sales": render_products_no_sales_page,
        "products_no_views": render_products_no_views_page,
        "product_conversion": render_product_conversion_page,
        "products_together": render_products_together_page,
    }
    renderer = renderers.get(page_key)
    if renderer is None:
        return False
    renderer(context)
    return True
