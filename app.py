from __future__ import annotations

from datetime import date, timedelta
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import calendar_daily, product_pairs, products, safe_percent
import cro_module
from parser import ALLOWED_STATUSES, parse_xml

YELLOW, BLACK, GOLD = "#FBF560", "#111111", "#D8D142"


def money(value: float) -> str:
    return f"{value:,.0f} грн".replace(",", " ")


def delta(now: float, before: float) -> str | None:
    return f"{(now - before) / before:+.1%}" if before else None


def style() -> None:
    st.markdown("""<style>
    .block-container {max-width:1480px;padding-top:1.5rem}.stApp{background:#fff;color:#111}
    [data-testid='stMetric']{border:1px solid #d9d267;border-top:4px solid #fbf560;padding:14px}
    .summary,.card{border:1px solid #d9d267;border-left:5px solid #fbf560;padding:16px;background:#fffeee;margin:12px 0}
    .card{background:#fff;height:120px}.stButton button,.stDownloadButton button{background:#fbf560!important;color:#111!important;border:1px solid #111!important;border-radius:0!important;font-weight:700}
    </style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_data(raw: bytes):
    return parse_xml(raw)


def chart(fig, height=380):
    fig.update_layout(template="plotly_white", height=height, paper_bgcolor="#fff", plot_bgcolor="#fff", font_color=BLACK, margin=dict(l=24,r=18,t=60,b=28))
    st.plotly_chart(fig, use_container_width=True)


def recommendations(orders: pd.DataFrame, item_data: pd.DataFrame, product_data: pd.DataFrame, start: date, end: date) -> list[tuple[str, str]]:
    revenue = orders.order_total.sum()
    customer = orders.groupby("customer_key").agg(orders=("order_id", "nunique"), revenue=("order_total", "sum"))
    repeat = customer[customer.orders >= 2].revenue.sum()
    result = []
    waiting = orders[orders.status.eq("Очікування")]
    if not waiting.empty:
        result.append(("Разобрать заказы в ожидании", f"{len(waiting)} заказов на {money(waiting.order_total.sum())}. Проверьте оплату и свяжитесь с клиентами."))
    repeat_share = safe_percent(repeat, revenue)
    result.append(("Повторные продажи", f"Повторные клиенты приносят {repeat_share:.1f}% выручки. {'Запустите цепочку после покупки и персональные предложения.' if repeat_share < 25 else 'Сохраните сегмент: подготовьте отдельные предложения и ранний доступ.'}"))
    one_item = safe_percent((orders.item_quantity <= 1).sum(), len(orders))
    if one_item >= 45:
        result.append(("Увеличить корзину", f"{one_item:.1f}% заказов содержат один товар. Добавьте комплекты и блок «С этим покупают»."))
    if not product_data.empty:
        top5 = safe_percent(product_data.head(5).revenue.sum(), revenue)
        if top5 >= 40:
            result.append(("Снизить зависимость от лидеров", f"Топ‑5 товаров дают {top5:.1f}% выручки. Контролируйте их остатки и развивайте альтернативы."))
    return result


def main() -> None:
    st.set_page_config("Store Analytics", "📊", layout="wide")
    style()
    st.title("Store Analytics")
    st.caption("Прозрачная аналитика заказов: данные обрабатываются только в памяти текущей сессии.")
    with st.sidebar:
        mode = st.radio("Раздел", ["Аналитика", "CRO"], label_visibility="collapsed")
        st.divider()
    if mode == "CRO":
        cro_module.render()
        return
    with st.sidebar:
        uploaded = st.file_uploader("XML с заказами", type="xml")
        st.caption("Поддерживается экспорт со статусами: " + ", ".join(ALLOWED_STATUSES))
    if not uploaded:
        st.info("Загрузите XML с заказами — дашборд построится автоматически.")
        return
    try:
        parsed = load_data(uploaded.getvalue())
    except ValueError as error:
        st.error(str(error)); return
    if parsed.orders.empty:
        st.warning("В файле нет заказов с разрешёнными статусами."); return
    all_orders, all_items = parsed.orders.copy(), parsed.items.copy()
    min_date, max_date = all_orders.order_date.min().date(), all_orders.order_date.max().date()
    with st.sidebar:
        dates = st.date_input("Период", (min_date, max_date), min_date, max_date)
        statuses = st.multiselect("Статусы", ALLOWED_STATUSES, list(ALLOWED_STATUSES))
    start, end = dates if isinstance(dates, tuple) and len(dates) == 2 else (min_date, max_date)
    orders = all_orders[all_orders.order_date.dt.date.between(start, end) & all_orders.status.isin(statuses)].copy()
    if orders.empty:
        st.warning("По выбранным фильтрам нет заказов."); return
    items = all_items[all_items.order_id.isin(orders.order_id)].copy()
    product_data = products(items, start, end)
    period_days = (end - start).days + 1
    previous = all_orders[all_orders.order_date.dt.date.between(start - timedelta(days=period_days), start - timedelta(days=1)) & all_orders.status.isin(statuses)]
    revenue, count = float(orders.order_total.sum()), int(orders.order_id.nunique())
    previous_revenue, previous_count = float(previous.order_total.sum()), int(previous.order_id.nunique())
    customers = orders.customer_key.nunique()
    customer_counts = orders.groupby("customer_key").order_id.nunique()
    cols = st.columns(6)
    cols[0].metric("Выручка", money(revenue), delta(revenue, previous_revenue))
    cols[1].metric("Заказы", f"{count:,}", delta(count, previous_count))
    cols[2].metric("Средний чек", money(revenue / count))
    cols[3].metric("Медианный чек", money(orders.order_total.median()))
    cols[4].metric("Продано единиц", f"{int(items.quantity.sum()):,}")
    cols[5].metric("Повторные клиенты", f"{safe_percent((customer_counts >= 2).sum(), customers):.1f}%")
    notes = []
    if parsed.invalid_orders: notes.append(f"пропущено некорректных/повторных ID: {parsed.invalid_orders}")
    notes.append(f"исключено по статусу: {parsed.skipped_by_status}")
    st.caption(f"В XML: {parsed.total_xml_orders} заказов; " + "; ".join(notes) + ".")
    daily = calendar_daily(orders, start, end)
    daily["weekday"] = daily.day.dt.day_name()
    st.markdown(f"<div class='summary'>За период: <b>{money(revenue)}</b> из <b>{count}</b> заказов. Средняя дневная выручка с учётом дней без продаж — <b>{money(daily.revenue.mean())}</b>.</div>", unsafe_allow_html=True)
    overview, product_tab, client_tab, action_tab, quality = st.tabs(["Обзор", "Товары", "Клиенты", "Действия", "Качество данных"])
    with overview:
        chart(px.line(daily, x="day", y="revenue", markers=True, title="Выручка по календарным дням", labels={"day":"Дата","revenue":"Грн"}, color_discrete_sequence=[YELLOW]))
        left, right = st.columns(2)
        with left:
            if not product_data.empty: chart(px.bar(product_data.head(10).sort_values("revenue"), x="revenue", y="product_name", orientation="h", title="Топ товаров по выручке", color_discrete_sequence=[GOLD]))
        with right:
            status = orders.groupby("status", as_index=False).order_total.sum()
            chart(px.pie(status, names="status", values="order_total", hole=.55, title="Выручка по статусам", color_discrete_sequence=[YELLOW, GOLD, BLACK]))
        weekday = daily.groupby("weekday", as_index=False).revenue.mean()
        order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        weekday.weekday = pd.Categorical(weekday.weekday, order, ordered=True); weekday = weekday.sort_values("weekday")
        chart(px.bar(weekday, x="weekday", y="revenue", title="Средняя выручка по дням недели — включая нулевые дни", color_discrete_sequence=[YELLOW]))
    with product_tab:
        if product_data.empty: st.info("В периоде нет товарных позиций.")
        else:
            view = product_data.copy(); view.last_sale = view.last_sale.dt.strftime("%d.%m.%Y")
            st.dataframe(view.rename(columns={"product_name":"Товар","sold_units":"Продано","revenue":"Выручка","orders":"Заказов","last_sale":"Последняя продажа","growth_percent":"Динамика, %","days_since_last_sale":"Дней без продаж"}), use_container_width=True, hide_index=True)
            pairs = product_pairs(items)
            if not pairs.empty: st.subheader("Часто покупают вместе"); st.dataframe(pairs, hide_index=True, use_container_width=True)
            st.download_button("Скачать отчёт CSV", view.to_csv(index=False).encode("utf-8-sig"), f"products_{start}_{end}.csv", "text/csv")
    with client_tab:
        segments = pd.DataFrame({"Сегмент":["Одна покупка","Повторные"], "Покупатели":[int((customer_counts == 1).sum()),int((customer_counts >= 2).sum())]})
        chart(px.pie(segments, names="Сегмент", values="Покупатели", hole=.6, title="Структура клиентской базы", color_discrete_sequence=[GOLD,YELLOW]))
        st.caption("Клиент определяется по нормализованному телефону; при его отсутствии — по email. Это снижает риск задвоения, но не заменяет полноценную CRM-идентификацию.")
    with action_tab:
        st.subheader("Приоритетные действия")
        for title, text in recommendations(orders, items, product_data, start, end):
            st.markdown(f"<div class='card'><b>{escape(title)}</b><br><br>{escape(text)}</div>", unsafe_allow_html=True)
    with quality:
        difference = orders.adjustment.abs()
        q = pd.DataFrame({"Показатель":["Заказы в текущем фильтре","Заказы с отличием суммы товаров и заказа","Среднее абсолютное отличие","Заказы без товарных строк"], "Значение":[count, int((difference > .01).sum()), money(difference.mean()), int((orders.item_lines == 0).sum())]})
        st.dataframe(q, hide_index=True, use_container_width=True)
        st.caption("Отличие суммы товара и заказа может быть нормальным: доставка, скидки или комиссии. Его важно интерпретировать в контексте выгрузки.")


if __name__ == "__main__":
    main()
