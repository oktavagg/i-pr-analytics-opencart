from __future__ import annotations

import base64
from html import escape
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


SHEET_ID = "1qrxMuLqCagiAt1A9TWAJ288VGn0ZwcN_Z6-q0-YZa3w"
DASHBOARD_GID = "162177676"

SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    f"?gid={DASHBOARD_GID}#gid={DASHBOARD_GID}"
)
SHEET_PREVIEW_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/preview"
    f"?gid={DASHBOARD_GID}"
)
SHEET_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
    f"?tqx=out:csv&gid={DASHBOARD_GID}"
)

SECTION_ORDER = [
    "Загальне",
    "Головна сторінка",
    "Категорія",
    "Товар",
    "Замовлення",
    "Дякую за замовлення",
    "Мобільна версія",
]

FALLBACK_SECTIONS = [
    {
        "section": "Загальне",
        "all_tasks": 28,
        "relevant": 27,
        "todo": 5,
        "done": 0,
    },
    {
        "section": "Головна сторінка",
        "all_tasks": 16,
        "relevant": 13,
        "todo": 6,
        "done": 0,
    },
    {
        "section": "Категорія",
        "all_tasks": 26,
        "relevant": 24,
        "todo": 7,
        "done": 0,
    },
    {
        "section": "Товар",
        "all_tasks": 41,
        "relevant": 33,
        "todo": 9,
        "done": 0,
    },
    {
        "section": "Замовлення",
        "all_tasks": 29,
        "relevant": 28,
        "todo": 8,
        "done": 0,
    },
    {
        "section": "Дякую за замовлення",
        "all_tasks": 7,
        "relevant": 7,
        "todo": 5,
        "done": 0,
    },
    {
        "section": "Мобільна версія",
        "all_tasks": 31,
        "relevant": 30,
        "todo": 3,
        "done": 0,
    },
]

FALLBACK_SCORE = 73


def _number_from_cell(value: object) -> float | None:
    text = str(value).strip().replace("\xa0", " ")
    if not text or text.lower() == "nan":
        return None

    match = re.fullmatch(r"-?\d+(?:[.,]\d+)?%?", text)
    if not match:
        return None

    try:
        return float(text.rstrip("%").replace(",", "."))
    except ValueError:
        return None


def _download_csv() -> pd.DataFrame:
    request = Request(
        SHEET_CSV_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urlopen(request, timeout=12) as response:
        raw = response.read()

    return pd.read_csv(
        pd.io.common.BytesIO(raw),
        header=None,
        dtype=str,
        keep_default_na=False,
    )


def _parse_sections(frame: pd.DataFrame) -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []

    for _, source_row in frame.iterrows():
        cells = [str(value).strip() for value in source_row.tolist()]
        section = next(
            (name for name in SECTION_ORDER if name in cells),
            None,
        )
        if section is None:
            continue

        section_index = cells.index(section)
        numbers = [
            number
            for number in (
                _number_from_cell(cell)
                for cell in cells[section_index + 1:]
            )
            if number is not None
        ]

        if len(numbers) < 3:
            continue

        rows.append(
            {
                "section": section,
                "all_tasks": int(numbers[0]),
                "relevant": int(numbers[1]),
                "todo": int(numbers[2]),
                "done": int(numbers[3]) if len(numbers) >= 4 else 0,
            }
        )

    unique_rows: dict[str, dict[str, int | str]] = {
        str(row["section"]): row for row in rows
    }

    return [
        unique_rows[name]
        for name in SECTION_ORDER
        if name in unique_rows
    ]


def _parse_score(frame: pd.DataFrame) -> int:
    rows = frame.astype(str).values.tolist()

    for row_index, row in enumerate(rows):
        row_text = " ".join(row)
        if "Рівень оптимізації" not in row_text:
            continue

        for next_row in rows[row_index + 1:row_index + 5]:
            for cell in next_row:
                number = _number_from_cell(cell)
                if number is not None and 0 <= number <= 100:
                    return int(round(number))

    return FALLBACK_SCORE


@st.cache_data(ttl=300, show_spinner=False)
def load_cro_summary() -> tuple[pd.DataFrame, int, bool]:
    try:
        frame = _download_csv()
        sections = _parse_sections(frame)
        score = _parse_score(frame)

        if not sections:
            raise ValueError("Не удалось найти разделы CRO")

        return pd.DataFrame(sections), score, True
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return pd.DataFrame(FALLBACK_SECTIONS), FALLBACK_SCORE, False



def _render_header(logo_path: Path | None) -> None:
    st.markdown(
        """
        <div class="page-heading">
            <span class="page-heading__label">Conversion rate optimization</span>
            <h1>CRO-аудит магазина</h1>
            <p>Чек-лист конверсии, приоритетный бэклог и контроль выполнения задач</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _score_status(score: int) -> tuple[str, str]:
    if score >= 85:
        return (
            "Сильный уровень",
            "Основная задача сейчас, точечные A/B-тесты и контроль просадок.",
        )
    if score >= 70:
        return (
            "Хорошая база",
            "Критических провалов немного. Рост даст системная работа с приоритетным бэклогом.",
        )
    if score >= 50:
        return (
            "Есть заметные потери",
            "Начните с карточки товара, оформления заказа и мобильной версии.",
        )
    return (
        "Нужна базовая оптимизация",
        "Сначала закройте критические проблемы, которые мешают пользователю завершить заказ.",
    )


def _render_score_overview(
    sections: pd.DataFrame,
    score: int,
    loaded_live: bool,
) -> None:
    total_tasks = int(sections["all_tasks"].sum())
    relevant_tasks = int(sections["relevant"].sum())
    todo_tasks = int(sections["todo"].sum())
    backlog_share = (
        todo_tasks / relevant_tasks * 100
        if relevant_tasks
        else 0
    )
    status, description = _score_status(score)

    left, right = st.columns([1.05, 2.15], gap="medium")

    with left:
        st.markdown(
            f"""
            <div class="cro-score-panel">
                <div class="cro-score-panel__label">CRO score</div>
                <div class="cro-score-panel__value">{score}<span>/100</span></div>
                <div class="cro-score-panel__status">{escape(status)}</div>
                <div class="cro-score-panel__text">{escape(description)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        source_hint = (
            "Живые данные"
            if loaded_live
            else "Резервная сводка"
        )
        st.markdown(
            f"""
            <div class="cro-kpi-grid">
                <div class="cro-kpi">
                    <div class="cro-kpi__label">Всего проверок</div>
                    <div class="cro-kpi__value">{total_tasks}</div>
                    <div class="cro-kpi__hint">Полный объем аудита</div>
                </div>
                <div class="cro-kpi">
                    <div class="cro-kpi__label">Релевантных</div>
                    <div class="cro-kpi__value">{relevant_tasks}</div>
                    <div class="cro-kpi__hint">Применимо к магазину</div>
                </div>
                <div class="cro-kpi">
                    <div class="cro-kpi__label">К выполнению</div>
                    <div class="cro-kpi__value">{todo_tasks}</div>
                    <div class="cro-kpi__hint">{backlog_share:.1f}% релевантных пунктов</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress(
            min(max(score / 100, 0.0), 1.0),
            text=f"Уровень CRO-оптимизации: {score} из 100",
        )
        st.caption(f"{source_hint}. Обновление доступно во вкладке с чек-листом.")


def _prepare_priority(sections: pd.DataFrame) -> pd.DataFrame:
    priority = sections.copy()
    priority = priority[priority["section"] != "Загалом"]
    priority["backlog_share"] = priority.apply(
        lambda row: (
            row["todo"] / row["relevant"] * 100
            if row["relevant"]
            else 0
        ),
        axis=1,
    )
    return priority.sort_values(
        ["todo", "backlog_share"],
        ascending=False,
    ).reset_index(drop=True)


def _render_priority_backlog(sections: pd.DataFrame) -> None:
    priority = _prepare_priority(sections)

    rows: list[str] = []
    for index, row in priority.iterrows():
        share = float(row["backlog_share"])
        rows.append(
            f"""
            <div class="cro-backlog__row">
                <div class="cro-backlog__rank">{index + 1:02d}</div>
                <div class="cro-backlog__section">{escape(str(row['section']))}</div>
                <div class="cro-backlog__number">{int(row['relevant'])}</div>
                <div class="cro-backlog__number">{int(row['todo'])}</div>
                <div class="cro-backlog__progress">
                    <div class="cro-backlog__track">
                        <div class="cro-backlog__fill" style="width:{min(share, 100):.1f}%"></div>
                    </div>
                    <div class="cro-backlog__percent">{share:.1f}%</div>
                </div>
            </div>
            """
        )

    st.markdown(
        f"""
        <div class="cro-backlog">
            <div class="cro-backlog__head">
                <span>№</span>
                <span>Раздел</span>
                <span>Релевантно</span>
                <span>К выполнению</span>
                <span>Доля бэклога</span>
            </div>
            {''.join(rows)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_focus(sections: pd.DataFrame) -> None:
    focus = _prepare_priority(sections).head(3)
    columns = st.columns(3, gap="medium")

    for rank, (column, (_, row)) in enumerate(
        zip(columns, focus.iterrows()),
        start=1,
    ):
        with column:
            st.markdown(
                f"""
                <div class="cro-focus-card">
                    <div class="cro-focus-card__rank">{rank:02d}</div>
                    <div class="cro-focus-card__section">{escape(str(row['section']))}</div>
                    <div class="cro-focus-card__todo">
                        {int(row['todo'])}
                        <span>задач к выполнению</span>
                    </div>
                    <div class="cro-focus-card__text">
                        Проверено {int(row['relevant'])} релевантных пунктов.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_action_panel(
    sections: pd.DataFrame,
    loaded_live: bool,
) -> None:
    top = _prepare_priority(sections).iloc[0]
    source = (
        "Google Sheets подключен и данные получены."
        if loaded_live
        else "Сводка недоступна, показаны сохраненные значения."
    )

    st.markdown(
        f"""
        <div class="cro-action-panel">
            <div class="cro-action-panel__eyebrow">Следующий шаг</div>
            <h3>Начать с раздела «{escape(str(top['section']))}»</h3>
            <p>
                В нем {int(top['todo'])} задач к выполнению.
                Это самый крупный текущий блок работ по чек-листу.
            </p>
        </div>
        <div class="summary-box">{escape(source)}</div>
        """,
        unsafe_allow_html=True,
    )


def _render_checklist_tab(loaded_live: bool) -> None:
    st.markdown(
        """
        <div class="cro-sheet-toolbar">
            <div>
                <h3>Исходный CRO-чек-лист</h3>
                <p>Работайте в Google Sheets, дашборд использует таблицу как источник данных.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    first, second = st.columns(2, gap="small")

    with first:
        if st.button(
            "Обновить данные из Google Sheets",
            use_container_width=True,
            type="primary",
        ):
            load_cro_summary.clear()
            st.rerun()

    with second:
        st.link_button(
            "Открыть чек-лист в новой вкладке",
            SHEET_URL,
            use_container_width=True,
        )

    st.caption(
        "Статус подключения: "
        + (
            "данные Google Sheets получены."
            if loaded_live
            else "используется резервная сводка."
        )
    )

    components.iframe(
        SHEET_PREVIEW_URL,
        height=980,
        scrolling=True,
    )


def render_cro_page(logo_path: Path | None = None) -> None:
    _render_header(logo_path)
    sections, score, loaded_live = load_cro_summary()

    overview_tab, checklist_tab = st.tabs(
        ["ОБЗОР АУДИТА", "ЖИВОЙ ЧЕК-ЛИСТ"]
    )

    with overview_tab:
        _render_score_overview(sections, score, loaded_live)

        st.markdown("<br>", unsafe_allow_html=True)
        left, right = st.columns([2.25, 1], gap="medium")

        with left:
            st.subheader("Приоритетный бэклог")
            st.caption(
                "Разделы отсортированы по количеству задач, "
                "которые требуют выполнения."
            )
            _render_priority_backlog(sections)

        with right:
            st.subheader("План действий")
            _render_action_panel(sections, loaded_live)

        st.subheader("Фокус работ")
        _render_focus(sections)

    with checklist_tab:
        _render_checklist_tab(loaded_live)
