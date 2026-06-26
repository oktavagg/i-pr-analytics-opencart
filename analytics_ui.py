from __future__ import annotations

from html import escape

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from lead_mailer import LeadMailError, send_lead_email


BRAND_BLACK = "#1F2937"
BRAND_YELLOW = "#4285F4"
BRAND_GOLD = "#F4B400"
BRAND_DARK_GOLD = "#C58B00"
BRAND_PALE = "#EAF2FF"
BRAND_CREAM = "#F8FAFC"
BRAND_BORDER = "#E5E7EB"
BRAND_MUTED = "#6B7280"
CHART_COLORS = [
    "#4285F4",
    "#5B8FF9",
    "#34A853",
    "#F4B400",
    "#A142F4",
    "#1F2937",
]
TREND_COLOR = "#374151"


def format_money(value: float) -> str:
    return f"{value:,.2f} грн".replace(",", " ")


def format_number(value: float | int) -> str:
    return f"{value:,.0f}".replace(",", " ")


def percent_delta(current: float, previous: float) -> str | None:
    if previous == 0:
        return None
    return f"{((current - previous) / previous) * 100:+.1f}%"


def safe_percent(part: float, total: float) -> float:
    return part / total * 100 if total else 0.0


def configure_plot(fig: go.Figure, height: int | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        colorway=CHART_COLORS,
        font=dict(
            color=BRAND_BLACK,
            family="Inter, Arial, sans-serif",
            size=13,
        ),
        title=dict(
            font=dict(color=BRAND_BLACK, size=17),
            x=0.02,
            xanchor="left",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color=BRAND_MUTED, size=12),
            title_font=dict(color=BRAND_MUTED),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=28, r=16, t=62, b=28),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor=BRAND_BORDER,
            font=dict(color=BRAND_BLACK),
        ),
    )

    fig.update_xaxes(
        tickfont=dict(color=BRAND_MUTED),
        title_font=dict(color=BRAND_MUTED),
        gridcolor="#EFF2F6",
        linecolor="#E5E7EB",
        zerolinecolor="#E5E7EB",
        showline=False,
    )
    fig.update_yaxes(
        tickfont=dict(color=BRAND_MUTED),
        title_font=dict(color=BRAND_MUTED),
        gridcolor="#EFF2F6",
        linecolor="#E5E7EB",
        zerolinecolor="#E5E7EB",
        showline=False,
    )

    fig.update_traces(
        textfont=dict(color=BRAND_BLACK),
        selector=dict(type="bar"),
    )

    if height:
        fig.update_layout(height=height)
    return fig


def add_trendline(fig: go.Figure, x_values: list, y_values: list[float], name: str = "Тренд") -> go.Figure:
    if len(y_values) < 2:
        return fig

    numeric_values = np.array(y_values, dtype=float)
    positions = np.arange(len(numeric_values), dtype=float)
    coefficients = np.polyfit(positions, numeric_values, 1)
    trend_values = np.polyval(coefficients, positions)

    fig.add_trace(
        go.Scatter(
            x=list(x_values),
            y=trend_values,
            mode="lines",
            name=name,
            line=dict(color=TREND_COLOR, width=2.2, dash="dot"),
            hovertemplate="Тренд: %{y:.2f}<extra></extra>",
        )
    )
    return fig

PRIORITY_LABELS = {
    "critical": "Критично",
    "important": "Важно",
    "recommendation": "Рекомендация",
    "idea": "Идея",
}


def _render_interest_dialog(
    recommendation: dict[str, object],
    lead_context: dict[str, object],
    dialog_key: str,
) -> None:
    title = str(recommendation.get("title", "Рекомендация по сайту"))

    @st.dialog("Обсудить доработку сайта", width="large")
    def interest_dialog() -> None:
        st.markdown(f"#### {escape(title)}")
        st.caption(
            "Оставьте проект и контакт. Заявка придёт специалисту I-PR вместе с выбранной рекомендацией."
        )

        with st.form(key=f"lead_form_{dialog_key}", clear_on_submit=False):
            project = st.text_input(
                "Проект или адрес сайта",
                placeholder="https://example.com",
            )
            name = st.text_input(
                "Ваше имя",
                placeholder="Как к вам обращаться",
            )
            contact = st.text_input(
                "Телефон, email или Telegram",
                placeholder="Контакт для обратной связи",
            )
            comment = st.text_area(
                "Комментарий",
                placeholder="Что нужно учесть, какие есть вопросы или ограничения",
                height=120,
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

            recommendation_with_label = dict(recommendation)
            recommendation_with_label["priority_label"] = PRIORITY_LABELS.get(
                str(recommendation.get("priority", "recommendation")),
                "Рекомендация",
            )
            try:
                send_lead_email(
                    recommendation=recommendation_with_label,
                    project=project.strip(),
                    name=name.strip(),
                    contact=contact.strip(),
                    comment=comment.strip(),
                    context=lead_context,
                )
            except LeadMailError as exc:
                st.error(str(exc))
            else:
                st.success("Заявка отправлена. Мы свяжемся с вами по указанному контакту.")

    interest_dialog()


def render_recommendations(
    recommendations: list[dict[str, object]],
    *,
    lead_context: dict[str, object] | None = None,
    key_prefix: str = "recommendations",
) -> None:
    lead_context = lead_context or {}

    st.markdown(
        """
        <style>
        [class*="st-key-rec_card_"] {
            height: 100%;
            padding: 18px 18px 16px;
            border: 1px solid #E7EAF0;
            border-left: 5px solid #CBD5E1;
            border-radius: 18px;
            background: #FFFFFF;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }

        [class*="st-key-rec_card_"] h4 {
            margin: 0.1rem 0 0.45rem;
            font-size: 1.02rem;
            color: #111827 !important;
        }

        [class*="st-key-rec_card_"] p,
        [class*="st-key-rec_card_"] li {
            color: #4B5563 !important;
            font-size: 0.91rem;
            line-height: 1.5;
        }

        [class*="st-key-rec_card_"] ul {
            margin: 0.55rem 0 0.8rem;
            padding-left: 1.15rem;
        }

        [class*="st-key-rec_card_"] .stButton button {
            margin-top: 0.35rem;
            border-color: #F4C430 !important;
            background: #FFF8D8 !important;
            color: #111827 !important;
        }

        [class*="st-key-rec_card_"] .stButton button:hover {
            background: #F4C430 !important;
            color: #111827 !important;
        }

        .recommendation-priority {
            display: inline-flex;
            align-items: center;
            min-height: 26px;
            padding: 4px 8px;
            margin-bottom: 8px;
            border-radius: 999px;
            background: #F3F4F6;
            color: #374151 !important;
            font-size: 0.7rem;
            font-weight: 850;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .recommendation-priority.critical {
            background: #FEECEC;
            color: #B42318 !important;
        }

        .recommendation-priority.important {
            background: #FFF2D8;
            color: #A15C00 !important;
        }

        .recommendation-priority.recommendation {
            background: #EAF2FF;
            color: #245FA8 !important;
        }

        .recommendation-priority.idea {
            background: #F1ECFF;
            color: #6842A8 !important;
        }

        .recommendation-actions-title {
            margin-top: 0.65rem;
            color: #111827 !important;
            font-size: 0.82rem;
            font-weight: 800;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for start in range(0, len(recommendations), 2):
        columns = st.columns(2, gap="large")
        for index, recommendation in enumerate(recommendations[start:start + 2]):
            global_index = start + index
            priority = str(recommendation.get("priority", "recommendation"))
            priority_label = PRIORITY_LABELS.get(priority, "Рекомендация")
            actions = recommendation.get("actions", [])

            with columns[index]:
                with st.container(key=f"rec_card_{key_prefix}_{global_index}"):
                    st.markdown(
                        f'<div class="recommendation-priority {escape(priority)}">{escape(priority_label)}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"#### {escape(str(recommendation['title']))}")
                    st.markdown(str(recommendation["text"]))

                    if isinstance(actions, list) and actions:
                        st.markdown(
                            '<div class="recommendation-actions-title">Что доработать на сайте</div>',
                            unsafe_allow_html=True,
                        )
                        action_lines = "\n".join(
                            f"- {escape(str(action))}" for action in actions
                        )
                        st.markdown(action_lines)

                    if st.button(
                        "Меня интересует",
                        key=f"interest_{key_prefix}_{global_index}",
                        use_container_width=True,
                    ):
                        _render_interest_dialog(
                            recommendation,
                            lead_context,
                            f"{key_prefix}_{global_index}",
                        )


def render_module_placeholder(title: str) -> None:
    st.markdown(
        f"""
        <div class="module-placeholder">
            <div class="module-status">МОДУЛЬ ПОДГОТОВЛЕН</div>
            <h3>{escape(title)}</h3>
            <p>
                Пункт уже добавлен в структуру системы. Расчеты, таблицы и графики
                для него подключим отдельно, не затрагивая остальные разделы.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
