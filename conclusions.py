from __future__ import annotations

from datetime import date, timedelta
from html import escape

import pandas as pd
import streamlit as st

from analytics_ui import format_money, format_number
from lead_mailer import LeadMailError, send_lead_email
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



def _render_recommendation_lead_form(
    recommendation: dict[str, object],
    context: dict[str, object],
    form_key: str,
) -> None:
    priority_labels = {
        "critical": "Критично",
        "important": "Важно",
        "recommendation": "Рекомендация",
        "idea": "Идея",
    }
    priority = str(recommendation.get("priority", "recommendation"))
    priority_label = priority_labels.get(priority, "Рекомендация")

    st.markdown(
        f"""
        <div class="lead-form-heading">
            <div class="lead-form-heading__label">Выбранная рекомендация</div>
            <div class="lead-form-heading__title">{escape(str(recommendation.get('title', 'Доработка сайта')))}</div>
            <div class="lead-form-heading__text">Заполните проект и контакт. Заявка будет отправлена на oktavagg@gmail.com.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form(key=form_key, clear_on_submit=False):
        first, second = st.columns(2, gap="large")
        with first:
            project = st.text_input(
                "Проект или адрес сайта",
                placeholder="https://example.com",
            )
            name = st.text_input(
                "Ваше имя",
                placeholder="Как к вам обращаться",
            )
        with second:
            contact = st.text_input(
                "Телефон, email или Telegram",
                placeholder="Контакт для обратной связи",
            )
            comment = st.text_area(
                "Комментарий",
                placeholder="Что нужно учесть или уточнить",
                height=104,
            )

        consent = st.checkbox(
            "Согласен на обработку данных для связи по заявке",
            value=False,
        )
        submitted = st.form_submit_button(
            "Отправить заявку",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not project.strip():
            st.error("Укажите проект или адрес сайта.")
            return
        if not contact.strip():
            st.error("Укажите контакт для обратной связи.")
            return
        if not consent:
            st.error("Подтвердите согласие на обработку данных.")
            return

        payload = dict(recommendation)
        payload["priority_label"] = priority_label
        try:
            send_lead_email(
                recommendation=payload,
                project=project.strip(),
                name=name.strip(),
                contact=contact.strip(),
                comment=comment.strip(),
                context={
                    "start_date": context.get("start_date"),
                    "end_date": context.get("end_date"),
                    "revenue": format_money(float(context.get("revenue", 0.0))),
                    "order_count": format_number(int(context.get("order_count", 0))),
                },
            )
        except LeadMailError as exc:
            st.error(str(exc))
        else:
            st.success("Заявка отправлена. Мы свяжемся с вами по указанному контакту.")


def render_site_recommendations(context: dict[str, object]) -> None:
    recommendations = context.get("recommendations", [])
    if not recommendations:
        st.info("За выбранный период рекомендации не сформированы.")
        return

    priority_labels = {
        "critical": "Критично",
        "important": "Важно",
        "recommendation": "Рекомендация",
        "idea": "Идея",
    }

    st.markdown(
        """
        <style>
        [class*="st-key-site_rec_"] {
            height: 100%;
            padding: 18px;
            border: 1px solid #E7EAF0;
            border-left: 5px solid #CBD5E1;
            border-radius: 18px;
            background: #FFFFFF;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }

        [class*="st-key-site_rec_"] h4 {
            margin: 0.25rem 0 0.45rem;
            color: #111827 !important;
            font-size: 1.04rem;
        }

        [class*="st-key-site_rec_"] p,
        [class*="st-key-site_rec_"] li {
            color: #4B5563 !important;
            font-size: 0.92rem;
            line-height: 1.5;
        }

        [class*="st-key-site_rec_"] ul {
            margin: 0.45rem 0 0.8rem;
            padding-left: 1.1rem;
        }

        [class*="st-key-site_rec_"] .stButton button {
            margin-top: 0.3rem;
            background: #FFF7D6 !important;
            border-color: #F4C430 !important;
            color: #111827 !important;
            font-weight: 800 !important;
        }

        [class*="st-key-site_rec_"] .stButton button:hover {
            background: #F4C430 !important;
        }

        .site-rec-priority {
            display: inline-flex;
            align-items: center;
            padding: 5px 9px;
            border-radius: 999px;
            font-size: 0.7rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .site-rec-priority.critical { background: #FEECEC; color: #B42318 !important; }
        .site-rec-priority.important { background: #FFF2D8; color: #A15C00 !important; }
        .site-rec-priority.recommendation { background: #EAF2FF; color: #245FA8 !important; }
        .site-rec-priority.idea { background: #F1ECFF; color: #6842A8 !important; }

        .site-rec-actions-title {
            margin-top: 0.7rem;
            color: #111827 !important;
            font-size: 0.82rem;
            font-weight: 850;
        }

        .lead-form-heading {
            margin: 1.6rem 0 1rem;
            padding: 18px 20px;
            border: 1px solid #E7EAF0;
            border-left: 5px solid #F4C430;
            border-radius: 18px;
            background: #FFFFFF;
        }

        .lead-form-heading__label {
            margin-bottom: 5px;
            color: #8A94A6 !important;
            font-size: 0.72rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .lead-form-heading__title {
            color: #111827 !important;
            font-size: 1.08rem;
            font-weight: 850;
        }

        .lead-form-heading__text {
            margin-top: 5px;
            color: #6B7280 !important;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    selected_key = "selected_site_recommendation"
    selected_index = st.session_state.get(selected_key)

    for start in range(0, len(recommendations), 2):
        columns = st.columns(2, gap="large")
        for offset, recommendation in enumerate(recommendations[start:start + 2]):
            index = start + offset
            priority = str(recommendation.get("priority", "recommendation"))
            label = priority_labels.get(priority, "Рекомендация")
            actions = recommendation.get("actions", [])

            with columns[offset]:
                with st.container(key=f"site_rec_{index}"):
                    st.markdown(
                        f'<div class="site-rec-priority {escape(priority)}">{escape(label)}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"#### {escape(str(recommendation.get('title', 'Рекомендация')))}")
                    st.write(str(recommendation.get("text", "")))

                    if isinstance(actions, list) and actions:
                        st.markdown(
                            '<div class="site-rec-actions-title">Что доработать на сайте</div>',
                            unsafe_allow_html=True,
                        )
                        for action in actions:
                            st.markdown(f"- {escape(str(action))}")

                    if st.button(
                        "Меня интересует",
                        key=f"site_interest_{index}",
                        use_container_width=True,
                    ):
                        st.session_state[selected_key] = index
                        st.rerun()

    if isinstance(selected_index, int) and 0 <= selected_index < len(recommendations):
        _render_recommendation_lead_form(
            recommendations[selected_index],
            context,
            form_key=f"site_lead_form_{selected_index}",
        )


def render(page_key: str, context: dict[str, object]) -> bool:
    renderers = {
        "period_changes": render_period_changes_page,
        "recommendations": render_site_recommendations,
    }
    renderer = renderers.get(page_key)
    if renderer is None:
        return False
    renderer(context)
    return True
