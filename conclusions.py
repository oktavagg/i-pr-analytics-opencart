from __future__ import annotations

from datetime import date, timedelta
from html import escape

import pandas as pd
import streamlit as st

from analytics_ui import format_money, format_number, render_recommendations
from xml_parser import ALLOWED_STATUSES


CATEGORY_TITLE = "Выводы и рекомендации"
PAGES = [
    ("period_changes", "Изменения за период"),
    ("recommendations", "Рекомендации"),
]
PAGE_DESCRIPTIONS = {
    "period_changes": "Сводная таблица ключевых показателей с автоматическим сравнением с предыдущим периодом такой же длины.",
    "recommendations": "Автоматические выводы на основе заказов, покупателей и товаров.",
}

RUSSIAN_MONTHS = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def format_period_label(start_date: date, end_date: date) -> str:
    if start_date == end_date:
        return start_date.strftime("%d.%m.%Y")

    next_month = (
        date(start_date.year + 1, 1, 1)
        if start_date.month == 12
        else date(start_date.year, start_date.month + 1, 1)
    )
    month_end = next_month - timedelta(days=1)
    if start_date.day == 1 and end_date == month_end:
        return f"{RUSSIAN_MONTHS[start_date.month]} {start_date.year}"

    return f"{start_date:%d.%m.%Y}–{end_date:%d.%m.%Y}"

def classify_orders_by_customer_history(orders: pd.DataFrame) -> pd.DataFrame:
    segmented = orders.copy()
    if segmented.empty:
        segmented["comparison_segment"] = pd.Series(dtype="object")
        return segmented

    segmented = segmented.sort_values(
        ["customer_key", "order_date", "order_id"],
        kind="stable",
    )
    segmented["customer_order_number"] = (
        segmented.groupby("customer_key").cumcount() + 1
    )
    segmented["comparison_segment"] = segmented["customer_order_number"].apply(
        lambda number: "Новый" if number == 1 else "Повторный"
    )
    return segmented

def calculate_period_snapshot(
    classified_orders: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> dict[str, float]:
    period_orders = classified_orders[
        classified_orders["order_date"].dt.date.between(start_date, end_date)
    ].copy()

    new_orders = period_orders[
        period_orders["comparison_segment"] == "Новый"
    ]
    repeat_orders = period_orders[
        period_orders["comparison_segment"] == "Повторный"
    ]

    total_revenue = float(period_orders["order_total"].sum())
    new_revenue = float(new_orders["order_total"].sum())
    repeat_revenue = float(repeat_orders["order_total"].sum())
    total_orders = int(period_orders["order_id"].nunique())
    new_order_count = int(new_orders["order_id"].nunique())
    repeat_order_count = int(repeat_orders["order_id"].nunique())

    return {
        "total_revenue": total_revenue,
        "new_revenue": new_revenue,
        "repeat_revenue": repeat_revenue,
        "total_orders": total_orders,
        "new_orders": new_order_count,
        "repeat_orders": repeat_order_count,
        "average_check": total_revenue / total_orders if total_orders else 0.0,
        "new_average_check": (
            new_revenue / new_order_count if new_order_count else 0.0
        ),
        "repeat_average_check": (
            repeat_revenue / repeat_order_count if repeat_order_count else 0.0
        ),
        "one_item_orders": int((period_orders["item_quantity"] == 1).sum()),
        "two_item_orders": int((period_orders["item_quantity"] == 2).sum()),
        "three_item_orders": int((period_orders["item_quantity"] == 3).sum()),
        "four_plus_item_orders": int((period_orders["item_quantity"] >= 4).sum()),
        "unique_customers": int(period_orders["customer_key"].nunique()),
    }

def comparison_change(current_value: float, previous_value: float) -> float | None:
    if previous_value == 0:
        return 0.0 if current_value == 0 else None
    return (current_value - previous_value) / previous_value * 100

def format_change(change: float | None) -> str:
    if change is None:
        return "Новый"
    return f"{change:+.1f}%"

def comparison_conclusion(change: float | None) -> tuple[str, str]:
    if change is None:
        return "Новый показатель", "positive"
    if change <= -25:
        return f"● Значительное падение {change:.1f}%", "negative"
    if change < -5:
        return f"▼ Снижение {change:.1f}%", "negative"
    if change < 5:
        return f"● Без существенных изменений {change:+.1f}%", "neutral"
    if change < 25:
        return f"▲ Рост {change:+.1f}%", "positive"
    return f"● Значительный рост {change:+.1f}%", "positive"

def render_period_comparison_table(
    previous_snapshot: dict[str, float],
    current_snapshot: dict[str, float],
    previous_label: str,
    current_label: str,
) -> None:
    rows = [
        ("Общий оборот", "total_revenue", "money"),
        ("Оборот новых клиентов", "new_revenue", "money"),
        ("Оборот повторных заказов", "repeat_revenue", "money"),
        ("Количество заказов", "total_orders", "number"),
        ("Заказы новых клиентов", "new_orders", "number"),
        ("Повторные заказы", "repeat_orders", "number"),
        ("Средний чек", "average_check", "money"),
        ("Средний чек новых клиентов", "new_average_check", "money"),
        ("Средний чек повторных заказов", "repeat_average_check", "money"),
        ("Заказы с 1 товаром", "one_item_orders", "number"),
        ("Заказы с 2 товарами", "two_item_orders", "number"),
        ("Заказы с 3 товарами", "three_item_orders", "number"),
        ("Заказы с 4+ товарами", "four_plus_item_orders", "number"),
        ("Уникальные покупатели", "unique_customers", "number"),
    ]

    body_rows: list[str] = []
    for title, key, value_type in rows:
        previous_value = float(previous_snapshot[key])
        current_value = float(current_snapshot[key])
        change = comparison_change(current_value, previous_value)
        conclusion, state = comparison_conclusion(change)
        value_formatter = format_money if value_type == "money" else format_number

        body_rows.append(
            f'''<tr class="{state}">
                <td>{escape(title)}</td>
                <td>{escape(value_formatter(previous_value))}</td>
                <td>{escape(value_formatter(current_value))}</td>
                <td class="change-{state}">{escape(format_change(change))}</td>
                <td class="conclusion-{state}">{escape(conclusion)}</td>
            </tr>'''
        )

    table_html = f'''
        <div class="period-comparison-title">
            Изменения: {escape(previous_label)} → {escape(current_label)}
        </div>
        <div class="comparison-table-wrap">
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Показатель</th>
                        <th>{escape(previous_label)}</th>
                        <th>{escape(current_label)}</th>
                        <th>Изменение</th>
                        <th>Вывод</th>
                    </tr>
                </thead>
                <tbody>{''.join(body_rows)}</tbody>
            </table>
        </div>
    '''
    st.markdown(table_html, unsafe_allow_html=True)

def render_period_changes_page(context: dict[str, object]) -> None:
    all_orders = context["all_orders"]
    selected_statuses = context.get("selected_statuses", list(ALLOWED_STATUSES))
    eligible_orders = all_orders[
        all_orders["status"].isin(selected_statuses)
    ].copy()

    if eligible_orders.empty:
        st.warning("Нет заказов с выбранными статусами.")
        return

    min_date = eligible_orders["order_date"].min().date()
    current_start = context["start_date"]
    current_end = context["end_date"]
    period_days = (current_end - current_start).days + 1
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)

    period_info, comparison_info = st.columns(2)
    with period_info:
        st.metric("Длина выбранного периода", f"{period_days} дн.")
    with comparison_info:
        st.metric(
            "Предыдущий период",
            format_period_label(previous_start, previous_end),
        )

    classified_orders = classify_orders_by_customer_history(eligible_orders)
    previous_snapshot = calculate_period_snapshot(
        classified_orders,
        previous_start,
        previous_end,
    )
    current_snapshot = calculate_period_snapshot(
        classified_orders,
        current_start,
        current_end,
    )

    previous_label = format_period_label(previous_start, previous_end)
    current_label = format_period_label(current_start, current_end)
    render_period_comparison_table(
        previous_snapshot,
        current_snapshot,
        previous_label,
        current_label,
    )

    if previous_start < min_date:
        st.warning(
            "В загруженном XML нет полного предыдущего периода. "
            "Часть показателей сравнения рассчитана только по доступным данным."
        )

    st.markdown(
        '<div class="comparison-footnote">'
        'Новый клиент означает первый заказ покупателя в загруженном XML. '
        'Учитываются рабочие статусы заказов.'
        '</div>',
        unsafe_allow_html=True,
    )


def render(page_key: str, context: dict[str, object]) -> bool:
    renderers = {
        "period_changes": render_period_changes_page,
        "recommendations": lambda data: render_recommendations(data["recommendations"]),
    }
    renderer = renderers.get(page_key)
    if renderer is None:
        return False
    renderer(context)
    return True
