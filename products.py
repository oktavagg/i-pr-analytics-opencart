from __future__ import annotations

from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics_ui import (
    BRAND_BLACK,
    BRAND_DARK_GOLD,
    BRAND_GOLD,
    BRAND_YELLOW,
    add_trendline,
    configure_plot,
    format_money,
    format_number,
    safe_percent,
)


CATEGORY_TITLE = "Товары"
PAGES = [
    ("products_no_sales", "Товары без продаж"),
    ("top_products_revenue", "Топ товаров по выручке"),
    ("top_products_units", "Топ товаров по количеству продаж"),
    ("products_together", "Покупают вместе"),
]
PAGE_DESCRIPTIONS = {
    "products_no_sales": "Активные товары каталога без продаж, сегменты внимания и CRO-действия.",
    "top_products_revenue": "Топ-10 товаров по обороту, заказам и проданным единицам.",
    "top_products_units": "Топ-10 товаров по количеству заказов с товаром.",
    "products_together": "Пары товаров, которые чаще всего встречаются в одном заказе.",
}


def _period_caption(context: dict[str, object], extra: str = "") -> None:
    start_date = context["start_date"]
    end_date = context["end_date"]
    text = f"Период отчёта: {start_date:%d.%m.%Y}–{end_date:%d.%m.%Y}."
    if extra:
        text += f" {extra}"
    st.caption(text)


def _short_name(value: object, limit: int = 62) -> str:
    text = str(value or "Без названия").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _sales_frame(context: dict[str, object]) -> pd.DataFrame:
    products = context["products"].copy()
    if products.empty:
        return products

    for column in ("orders", "sold_units", "revenue"):
        products[column] = pd.to_numeric(products[column], errors="coerce").fillna(0)
    products["product_id"] = products["product_id"].astype(str)
    return products


def _render_top_table(frame: pd.DataFrame, include_share: bool = True) -> None:
    display = frame.copy().reset_index(drop=True)
    display.insert(0, "#", range(1, len(display) + 1))
    display = display.rename(
        columns={
            "product_name": "Товар",
            "orders": "Заказов",
            "sold_units": "Продано, шт.",
            "revenue": "Оборот, грн",
            "share": "Доля оборота, %",
        }
    )
    columns = ["#", "Товар", "Заказов", "Продано, шт.", "Оборот, грн"]
    if include_share:
        columns.append("Доля оборота, %")

    st.dataframe(
        display[columns],
        width="stretch",
        hide_index=True,
        column_config={
            "#": st.column_config.NumberColumn(width="small", format="%d"),
            "Заказов": st.column_config.NumberColumn(format="%d"),
            "Продано, шт.": st.column_config.NumberColumn(format="%d"),
            "Оборот, грн": st.column_config.NumberColumn(format="%.2f грн"),
            "Доля оборота, %": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )


def render_top_products_revenue_page(context: dict[str, object]) -> None:
    products = _sales_frame(context)
    if products.empty:
        st.info("В выбранном периоде нет товарных позиций.")
        return

    ranked = products.sort_values(
        ["revenue", "orders", "sold_units"],
        ascending=False,
        kind="stable",
    ).head(10).copy()
    total_revenue = float(context["revenue"])
    top_revenue = float(ranked["revenue"].sum())
    ranked["share"] = ranked["revenue"].apply(
        lambda value: safe_percent(float(value), total_revenue)
    )
    leader = ranked.iloc[0]

    first, second, third = st.columns(3)
    first.metric("Оборот товара-лидера", format_money(float(leader["revenue"])))
    first.caption(f"Лидер: {_short_name(leader['product_name'], 42)}")
    second.metric("Оборот топ-10", format_money(top_revenue))
    second.caption(f"{int(ranked['orders'].sum())} товарных вхождений в заказы")
    third.metric("Доля в общем обороте", f"{safe_percent(top_revenue, total_revenue):.1f}%")
    third.caption("Концентрация оборота на десяти товарах")

    left, right = st.columns([1.05, 1.35], gap="large")
    with left:
        _render_top_table(ranked)

    with right:
        chart_frame = ranked.sort_values("revenue").copy()
        chart_frame["product_label"] = chart_frame["product_name"].map(
            lambda value: _short_name(value, 48)
        )
        chart = px.bar(
            chart_frame,
            x="revenue",
            y="product_label",
            orientation="h",
            title="Топ-10 товаров по обороту",
            labels={"revenue": "Оборот, грн", "product_label": "Товар"},
            text_auto=".3s",
            color_discrete_sequence=[BRAND_YELLOW],
        )
        chart.update_traces(
            marker_line_color=BRAND_BLACK,
            marker_line_width=0.7,
        )
        chart.update_layout(showlegend=False, yaxis_title=None, bargap=0.24)
        chart.update_yaxes(automargin=True)
        st.plotly_chart(configure_plot(chart, 560), width="stretch")

    concentration = safe_percent(top_revenue, total_revenue)
    if concentration >= 60:
        st.markdown(
            f"""
            <div class="summary-box">
                <b>Высокая зависимость от лидеров.</b><br>
                Топ-10 формирует {concentration:.1f}% оборота. Контролируйте остатки,
                рекламу и карточки этих товаров. Подготовьте замены на случай отсутствия.
            </div>
            """,
            unsafe_allow_html=True,
        )
    _period_caption(context)


def render_top_products_units_page(context: dict[str, object]) -> None:
    products = _sales_frame(context)
    if products.empty:
        st.info("В выбранном периоде нет товарных позиций.")
        return

    ranked = products.sort_values(
        ["orders", "sold_units", "revenue"],
        ascending=False,
        kind="stable",
    ).head(10).copy()
    total_orders = int(context["order_count"])
    top_order_entries = int(ranked["orders"].sum())
    total_revenue = float(context["revenue"])
    ranked["share"] = ranked["revenue"].apply(
        lambda value: safe_percent(float(value), total_revenue)
    )
    leader = ranked.iloc[0]

    first, second, third = st.columns(3)
    first.metric("Заказов у товара-лидера", format_number(int(leader["orders"])))
    first.caption(f"Лидер: {_short_name(leader['product_name'], 42)}")
    second.metric("Заказов у топ-10", format_number(top_order_entries))
    second.caption("Сумма вхождений товаров в заказы")
    third.metric("Относительно всех заказов", f"{safe_percent(top_order_entries, total_orders):.1f}%")
    third.caption("Один заказ может содержать несколько товаров топ-10")

    left, right = st.columns([1.05, 1.35], gap="large")
    with left:
        _render_top_table(ranked)

    with right:
        chart_frame = ranked.sort_values("orders").copy()
        chart_frame["product_label"] = chart_frame["product_name"].map(
            lambda value: _short_name(value, 48)
        )
        chart = px.bar(
            chart_frame,
            x="orders",
            y="product_label",
            orientation="h",
            title="Топ-10 товаров по количеству заказов",
            labels={"orders": "Заказы", "product_label": "Товар"},
            text="orders",
            color_discrete_sequence=[BRAND_YELLOW],
        )
        chart.update_traces(
            marker_line_color=BRAND_BLACK,
            marker_line_width=0.7,
        )
        chart.update_layout(showlegend=False, yaxis_title=None, bargap=0.24)
        chart.update_yaxes(automargin=True)
        st.plotly_chart(configure_plot(chart, 560), width="stretch")

    _period_caption(
        context,
        "Рейтинг строится по количеству заказов с товаром, а не только по числу проданных единиц.",
    )


def _prepare_no_sales(context: dict[str, object]) -> pd.DataFrame:
    catalog = context.get("product_catalog")
    if not isinstance(catalog, pd.DataFrame) or catalog.empty:
        return pd.DataFrame()

    active = catalog[catalog["status"]].copy()
    active["product_id"] = active["product_id"].astype(str)

    period_items = context["items"].copy()
    period_sold_ids = set(period_items["product_id"].astype(str)) if not period_items.empty else set()

    history_items = context.get("all_items_history")
    if not isinstance(history_items, pd.DataFrame):
        history_items = pd.DataFrame()

    history_summary = pd.DataFrame(columns=["product_id", "last_sale", "history_orders", "history_units"])
    if not history_items.empty:
        history_items = history_items.copy()
        history_items["product_id"] = history_items["product_id"].astype(str)
        history_summary = (
            history_items.groupby("product_id", as_index=False)
            .agg(
                last_sale=("order_date", "max"),
                history_orders=("order_id", "nunique"),
                history_units=("quantity", "sum"),
            )
        )

    no_sales = active[~active["product_id"].isin(period_sold_ids)].copy()
    no_sales = no_sales.merge(history_summary, on="product_id", how="left")
    no_sales["history_orders"] = no_sales["history_orders"].fillna(0).astype(int)
    no_sales["history_units"] = no_sales["history_units"].fillna(0).astype(int)
    no_sales["never_sold"] = no_sales["history_orders"].eq(0)
    no_sales["days_since_sale"] = (
        pd.Timestamp(context["end_date"]) - pd.to_datetime(no_sales["last_sale"]).dt.normalize()
    ).dt.days

    in_stock = no_sales["quantity"] > 0
    views_threshold = float(no_sales.loc[in_stock, "viewed"].quantile(0.75)) if in_stock.any() else 0.0
    views_threshold = max(views_threshold, 20.0)

    def segment(row: pd.Series) -> str:
        if int(row["quantity"]) <= 0:
            return "Нет остатка"
        if int(row["viewed"]) >= views_threshold:
            return "Высокий интерес, нет продаж"
        if bool(row["never_sold"]):
            return "Никогда не продавался"
        return "Нет продаж в периоде"

    no_sales["cro_segment"] = no_sales.apply(segment, axis=1)
    priority = {
        "Высокий интерес, нет продаж": 0,
        "Никогда не продавался": 1,
        "Нет продаж в периоде": 2,
        "Нет остатка": 3,
    }
    no_sales["priority"] = no_sales["cro_segment"].map(priority).fillna(9)
    return no_sales.sort_values(
        ["priority", "viewed", "quantity"],
        ascending=[True, False, False],
        kind="stable",
    )


def render_products_no_sales_page(context: dict[str, object]) -> None:
    catalog = context.get("product_catalog")
    if not isinstance(catalog, pd.DataFrame) or catalog.empty:
        st.info("Каталог товаров не загружен или не распознан.")
        return

    no_sales = _prepare_no_sales(context)
    active_count = int(catalog["status"].sum())
    high_interest = int((no_sales["cro_segment"] == "Высокий интерес, нет продаж").sum()) if not no_sales.empty else 0
    never_sold = int(no_sales["never_sold"].sum()) if not no_sales.empty else 0
    out_of_stock = int((no_sales["cro_segment"] == "Нет остатка").sum()) if not no_sales.empty else 0

    first, second, third, fourth = st.columns(4)
    first.metric("Активных товаров", format_number(active_count))
    second.metric("Без продаж", format_number(len(no_sales)))
    second.caption(f"{safe_percent(len(no_sales), active_count):.1f}% активного каталога")
    third.metric("Есть интерес, нет продаж", format_number(high_interest))
    third.caption("Высокие просмотры при наличии остатка")
    fourth.metric("Никогда не продавались", format_number(never_sold))
    fourth.caption(f"Без остатка: {out_of_stock}")

    if no_sales.empty:
        st.success("Все активные товары каталога продавались в выбранном периоде.")
        _period_caption(context)
        return

    st.markdown(
        """
        <div class="summary-box">
            <b>CRO-приоритет.</b><br>
            Сначала проверьте товары с высоким числом просмотров и нулём продаж:
            цену, наличие, первый экран карточки, кнопку покупки, доставку, отзывы и мобильную версию.
            Товары без просмотров требуют проверки индексации, категорий и внутренней перелинковки.
        </div>
        """,
        unsafe_allow_html=True,
    )

    segment_options = [
        "Все товары без продаж",
        "Высокий интерес, нет продаж",
        "Никогда не продавался",
        "Нет продаж в периоде",
        "Нет остатка",
    ]
    selected_segment = st.selectbox(
        "Сегмент",
        segment_options,
        key="products_no_sales_segment",
    )
    visible = no_sales if selected_segment == "Все товары без продаж" else no_sales[
        no_sales["cro_segment"] == selected_segment
    ]

    display = visible.copy()
    display["last_sale_display"] = pd.to_datetime(display["last_sale"]).dt.strftime("%d.%m.%Y")
    display["last_sale_display"] = display["last_sale_display"].fillna("Нет в истории")
    display["days_display"] = display["days_since_sale"].apply(
        lambda value: "Нет в истории" if pd.isna(value) else str(int(value))
    )
    display = display.rename(
        columns={
            "product_name": "Товар",
            "model": "Модель",
            "manufacturer": "Производитель",
            "effective_price": "Цена, грн",
            "quantity": "Остаток",
            "viewed": "Просмотры",
            "last_sale_display": "Последняя продажа",
            "days_display": "Дней без продаж",
            "cro_segment": "Сегмент",
            "link": "Карточка",
        }
    )
    st.dataframe(
        display[
            [
                "Товар",
                "Модель",
                "Производитель",
                "Цена, грн",
                "Остаток",
                "Просмотры",
                "Последняя продажа",
                "Дней без продаж",
                "Сегмент",
                "Карточка",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "Цена, грн": st.column_config.NumberColumn(format="%.2f грн"),
            "Остаток": st.column_config.NumberColumn(format="%d"),
            "Просмотры": st.column_config.NumberColumn(format="%d"),
            "Карточка": st.column_config.LinkColumn(display_text="Открыть"),
        },
    )

    csv_columns = [
        "product_id",
        "product_name",
        "model",
        "manufacturer",
        "effective_price",
        "quantity",
        "viewed",
        "last_sale",
        "days_since_sale",
        "cro_segment",
        "link",
    ]
    st.download_button(
        "Скачать товары без продаж CSV",
        data=visible[csv_columns].to_csv(index=False).encode("utf-8-sig"),
        file_name=f"products_without_sales_{context['start_date']}_{context['end_date']}.csv",
        mime="text/csv",
    )
    _period_caption(
        context,
        "В отчёт входят только активные товары каталога. Продажи учитывают выбранные статусы заказов.",
    )


def render_products_together_page(context: dict[str, object]) -> None:
    pairs = context["business"]["pairs"]
    if not isinstance(pairs, pd.DataFrame) or pairs.empty:
        st.info("Недостаточно заказов с несколькими товарами для анализа пар.")
        return

    pairs = pairs.copy().head(10)
    pairs["Совместных заказов"] = pd.to_numeric(
        pairs["Совместных заказов"], errors="coerce"
    ).fillna(0).astype(int)
    multi_item_orders = int((context["orders"]["item_lines"] >= 2).sum())
    top_pair = pairs.iloc[0]
    top_pair_share = safe_percent(int(top_pair["Совместных заказов"]), multi_item_orders)

    first, second, third = st.columns(3)
    first.metric("Лучшая пара", format_number(int(top_pair["Совместных заказов"])))
    first.caption(
        f"{_short_name(top_pair['Товар 1'], 24)} + {_short_name(top_pair['Товар 2'], 24)}"
    )
    second.metric("Заказов с 2+ товарами", format_number(multi_item_orders))
    second.caption("База для кросс-продаж и комплектов")
    third.metric("Доля лучшей пары", f"{top_pair_share:.1f}%")
    third.caption("От заказов с несколькими товарными позициями")

    st.subheader("Три основные связки")
    columns = st.columns(min(3, len(pairs)))
    for index, (_, row) in enumerate(pairs.head(3).iterrows()):
        with columns[index]:
            st.markdown(
                f"""
                <div class="recommendation-card idea">
                    <div class="recommendation-priority">Связка №{index + 1}</div>
                    <h4>{escape(_short_name(row['Товар 1'], 48))}</h4>
                    <p>Вместе с: <b>{escape(_short_name(row['Товар 2'], 55))}</b><br>
                    Совместных заказов: <b>{int(row['Совместных заказов'])}</b></p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    chart_frame = pairs.copy()
    chart_frame["Пара"] = chart_frame.apply(
        lambda row: f"{_short_name(row['Товар 1'], 28)} + {_short_name(row['Товар 2'], 28)}",
        axis=1,
    )
    chart_frame = chart_frame.sort_values("Совместных заказов")
    chart = px.bar(
        chart_frame,
        x="Совместных заказов",
        y="Пара",
        orientation="h",
        title="Товары, которые покупают вместе",
        text="Совместных заказов",
        color_discrete_sequence=[BRAND_YELLOW],
    )
    chart.update_traces(marker_line_color=BRAND_BLACK, marker_line_width=0.7)
    chart.update_layout(showlegend=False, yaxis_title=None, bargap=0.24)
    chart.update_yaxes(automargin=True)
    st.plotly_chart(configure_plot(chart, 520), width="stretch")

    table = pairs.rename(columns={"Товар 1": "Основной товар", "Товар 2": "С ним покупают"})
    st.dataframe(
        table[["Основной товар", "С ним покупают", "Совместных заказов"]],
        width="stretch",
        hide_index=True,
        column_config={
            "Совместных заказов": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.markdown(
        """
        <div class="summary-box">
            <b>Как использовать данные.</b><br>
            Добавьте взаимные рекомендации в карточках товаров, блок в корзине и готовые комплекты.
            Сначала тестируйте пары с наибольшим количеством совместных заказов.
        </div>
        """,
        unsafe_allow_html=True,
    )
    _period_caption(context)


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
