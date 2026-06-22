from __future__ import annotations

import re
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

SHEET_ID = "1qrxMuLqCagiAt1A9TWAJ288VGn0ZwcN_Z6-q0-YZa3w"
GID = "162177676"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={GID}#gid={GID}"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={GID}"
SECTION_ORDER = ["Загальне", "Головна сторінка", "Категорія", "Товар", "Замовлення", "Дякую за замовлення", "Мобільна версія"]


def _number(value: object) -> int | None:
    match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)%?\s*", str(value).replace("\xa0", " "))
    return int(round(float(match.group(1).replace(",", ".")))) if match else None


def _fetch() -> pd.DataFrame:
    request = Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=12) as response:
        return pd.read_csv(BytesIO(response.read()), header=None, dtype=str, keep_default_na=False)


@st.cache_data(ttl=300, show_spinner=False)
def load_summary() -> tuple[pd.DataFrame, bool]:
    try:
        frame = _fetch(); rows = []
        for _, row in frame.iterrows():
            cells = [str(x).strip() for x in row.tolist()]
            section = next((name for name in SECTION_ORDER if name in cells), None)
            if not section: continue
            values = [n for n in (_number(x) for x in cells[cells.index(section)+1:]) if n is not None]
            if len(values) >= 3: rows.append({"Раздел": section, "Всего": values[0], "Релевантно": values[1], "К выполнению": values[2], "Выполнено": values[3] if len(values) > 3 else 0})
        summary = pd.DataFrame(rows).drop_duplicates("Раздел")
        if summary.empty: raise ValueError("В таблице не найдены разделы")
        return summary, True
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame(columns=["Раздел", "Всего", "Релевантно", "К выполнению", "Выполнено"]), False


def render() -> None:
    st.header("CRO-аудит магазина")
    st.caption("Источник — Google Sheets. Обновление автоматически раз в 5 минут или вручную.")
    if st.button("Обновить данные"): load_summary.clear()
    summary, live = load_summary()
    if not live:
        st.warning("Не удалось получить свежие данные из Google Sheets. Никакие резервные цифры не показаны, чтобы не вводить в заблуждение.")
        st.link_button("Открыть исходный чек-лист", SHEET_URL)
        return
    total = int(summary["Всего"].sum()); relevant = int(summary["Релевантно"].sum()); todo = int(summary["К выполнению"].sum()); done = int(summary["Выполнено"].sum())
    score = round(100 * done / relevant) if relevant else 0
    a,b,c,d = st.columns(4); a.metric("CRO-оценка", f"{score}/100"); b.metric("Проверок", total); c.metric("К выполнению", todo); d.metric("Выполнено", done)
    st.progress(score / 100, text=f"Выполнено {done} из {relevant} релевантных пунктов")
    summary["Доля бэклога, %"] = (100 * summary["К выполнению"] / summary["Релевантно"].replace(0, pd.NA)).fillna(0)
    st.subheader("Приоритетный бэклог")
    st.dataframe(summary.sort_values(["К выполнению", "Доля бэклога, %"], ascending=False), hide_index=True, use_container_width=True, column_config={"Доля бэклога, %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%")})
    st.link_button("Открыть и редактировать чек-лист", SHEET_URL)
