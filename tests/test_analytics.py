from datetime import date

import pandas as pd

from analytics import calendar_daily, safe_percent


def test_calendar_includes_days_without_orders() -> None:
    orders = pd.DataFrame({
        "day": pd.to_datetime(["2026-06-01", "2026-06-03"]),
        "order_total": [100, 200],
        "order_id": ["1", "2"],
    })
    result = calendar_daily(orders, date(2026, 6, 1), date(2026, 6, 3))
    assert result.revenue.tolist() == [100, 0, 200]
    assert result.orders.tolist() == [1, 0, 1]


def test_percent_has_safe_zero_denominator() -> None:
    assert safe_percent(10, 0) == 0
