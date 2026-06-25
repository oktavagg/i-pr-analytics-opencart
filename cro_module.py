from __future__ import annotations

import base64
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
    if logo_path and logo_path.exists():
        logo_base64 = base64.b64encode(
            logo_path.read_bytes()
        ).decode("ascii")
        logo_html = (
            f'<img src="data:image/jpeg;base64,{logo_base64}" '
            'alt="IPR ecommerce agency">'
        )
    else:
        logo_html = "<strong>IPR</strong>"

    st.markdown(
        f"""
        <div class="brand-header">
            <div class="brand-logo">{logo_html}</div>
            <div class="brand-copy">
                <h1>CRO-аудит магазина</h1>
                <p>Чек-лист конверсии, приоритеты и контроль выполнения задач</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_priority_backlog(sections: pd.DataFrame) -> None:
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

    priority = priority.sort_values(
        ["todo", "backlog_share"],
        ascending=False,
    )

    display = priority.rename(
        columns={
            "section": "Раздел",
            "all_tasks": "Всего проверок",
            "relevant": "Релевантно",
            "todo": "К выполнению",
            "done": "Выполнено",
            "backlog_share": "Доля бэклога, %",
        }
    )

    st.dataframe(
        display[
            [
                "Раздел",
                "Всего проверок",
                "Релевантно",
                "К выполнению",
                "Доля бэклога, %",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "Доля бэклога, %": st.column_config.ProgressColumn(
                min_value=0,
                max_value=100,
                format="%.1f%%",
            ),
        },
    )


def _render_focus(sections: pd.DataFrame) -> None:
    focus = (
        sections[sections["section"] != "Загалом"]
        .sort_values("todo", ascending=False)
        .head(3)
    )

    columns = st.columns(3)

    for column, (_, row) in zip(columns, focus.iterrows()):
        with column:
            st.markdown(
                f"""
                <div class="recommendation-card medium">
                    <h4>{row['section']}</h4>
                    <p>
                        К выполнению: <b>{int(row['todo'])}</b> из
                        <b>{int(row['relevant'])}</b> релевантных пунктов.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_cro_page(logo_path: Path | None = None) -> None:
    _render_header(logo_path)

    sections, score, loaded_live = load_cro_summary()

    total_row = {
        "all_tasks": int(sections["all_tasks"].sum()),
        "relevant": int(sections["relevant"].sum()),
        "todo": int(sections["todo"].sum()),
    }

    first, second, third, fourth = st.columns(4)
    first.metric("CRO-оценка", f"{score}/100")
    second.metric("Всего проверок", total_row["all_tasks"])
    third.metric("Релевантных", total_row["relevant"])
    fourth.metric("К выполнению", total_row["todo"])

    st.progress(
        min(max(score / 100, 0.0), 1.0),
        text=f"Уровень CRO-оптимизации: {score} из 100",
    )

    source_text = (
        "Данные обновлены из Google Sheets."
        if loaded_live
        else "Показана резервная сводка. Живая таблица доступна ниже."
    )
    st.caption(source_text)

    left, right = st.columns([3, 1])

    with left:
        st.subheader("Приоритетный бэклог")
        st.caption(
            "Разделы отсортированы по количеству пунктов, "
            "которые требуют выполнения."
        )
        _render_priority_backlog(sections)

    with right:
        st.subheader("Управление")

        if st.button(
            "Обновить из Google Sheets",
            width="stretch",
        ):
            load_cro_summary.clear()
            st.rerun()

        st.link_button(
            "Открыть исходный чек-лист",
            SHEET_URL,
            width="stretch",
        )

        st.markdown(
            """
            <div class="summary-box">
                Google-таблица остается источником правды.
                Изменения в чек-листе появятся в модуле после обновления.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.subheader("Фокус работ")
    _render_focus(sections)

    st.subheader("Живой CRO-чек-лист")
    st.caption(
        "Встроена исходная Google-таблица со всеми разделами и вкладками."
    )

    components.iframe(
        SHEET_PREVIEW_URL,
        height=920,
        scrolling=True,
    )
