from __future__ import annotations

from datetime import date
from itertools import combinations
from collections import Counter

import pandas as pd


def safe_percent(part: float, whole: float) -> float:
    return 100 * part / whole if whole else 0.0


def calendar_daily(orders: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """A complete calendar prevents zero-sales days from inflating averages."""
    days = pd.date_range(start, end, freq="D", name="day")
    grouped = orders.groupby("day", as_index=True).agg(revenue=("order_total", "sum"), orders=("order_id", "nunique"))
    return grouped.reindex(days, fill_value=0).rename_axis("day").reset_index()


def products(items: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if items.empty:
        return pd.DataFrame()
    result = items.groupby(["product_id", "product_name", "sku"], as_index=False).agg(sold_units=("quantity", "sum"), revenue=("product_total", "sum"), orders=("order_id", "nunique"), last_sale=("order_date", "max"), average_price=("unit_price", "mean"))
    midpoint = pd.Timestamp(start) + (pd.Timestamp(end) - pd.Timestamp(start)) / 2
    first_days = max((midpoint.normalize() - pd.Timestamp(start)).days, 1)
    second_days = max((pd.Timestamp(end) - midpoint.normalize()).days + 1, 1)
    first = items[items.order_date < midpoint].groupby("product_id").quantity.sum() / first_days
    second = items[items.order_date >= midpoint].groupby("product_id").quantity.sum() / second_days
    result["first_daily_rate"] = result.product_id.map(first).fillna(0)
    result["second_daily_rate"] = result.product_id.map(second).fillna(0)
    result["growth_percent"] = ((result.second_daily_rate - result.first_daily_rate) / result.first_daily_rate * 100).where(result.first_daily_rate.gt(0))
    result["days_since_last_sale"] = (pd.Timestamp(end) - result.last_sale.dt.normalize()).dt.days.clip(lower=0)
    return result.sort_values(["revenue", "sold_units"], ascending=False)


def product_pairs(items: pd.DataFrame) -> pd.DataFrame:
    names = items.drop_duplicates("product_id").set_index("product_id").product_name.to_dict()
    counter = Counter(pair for _, group in items.groupby("order_id") for pair in combinations(sorted(set(group.product_id.astype(str))), 2))
    return pd.DataFrame([{"Товар 1": names.get(a, a), "Товар 2": names.get(b, b), "Совместных заказов": count} for (a, b), count in counter.most_common(10)])
