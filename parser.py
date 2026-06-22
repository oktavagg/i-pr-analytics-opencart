from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import pandas as pd
from defusedxml import ElementTree as SafeET


ALLOWED_STATUSES = (
    "Обробляється менеджером",
    "Успішна оплата LiqPay",
    "Очікування",
)


@dataclass(frozen=True)
class ParsedData:
    orders: pd.DataFrame
    items: pd.DataFrame
    total_xml_orders: int
    skipped_by_status: int
    invalid_orders: int


def _text(parent, *tags: str, default: str = "") -> str:
    for tag in tags:
        node = parent.find(tag)
        if node is not None and node.text:
            return node.text.strip()
    return default


def _number(value: str) -> float:
    value = str(value).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    value = re.sub(r"[^0-9.\-]", "", value)
    try:
        return float(value)
    except ValueError:
        return 0.0


def _quantity(value: str) -> int:
    return max(0, round(_number(value)))


def _phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("380") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 10:
        return f"+38{digits}"
    return f"+{digits}" if digits else ""


def _email(value: str) -> str:
    value = (value or "").strip().lower()
    return "" if not value or value.endswith("@localhost.net") else value


def _customer_key(phone: str, email: str, first_name: str, last_name: str) -> str:
    # Stable identity favors a phone; email/name are graceful fallbacks.
    source = phone or email or f"{first_name.strip().lower()}|{last_name.strip().lower()}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def parse_xml(xml_bytes: bytes, allowed_statuses: tuple[str, ...] = ALLOWED_STATUSES) -> ParsedData:
    try:
        root = SafeET.fromstring(xml_bytes)
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать XML: {exc}") from exc

    orders, items, seen_ids = [], [], set()
    skipped = invalid = 0
    nodes = root.findall(".//item")
    for node in nodes:
        status = _text(node, "order_status", "status")
        if status not in allowed_statuses:
            skipped += 1
            continue
        order_id = _text(node, "order_id", "id")
        order_date = pd.to_datetime(_text(node, "date_added", "date"), errors="coerce")
        if not order_id or pd.isna(order_date) or order_id in seen_ids:
            invalid += 1
            continue
        seen_ids.add(order_id)

        first, last = _text(node, "firstname", "first_name"), _text(node, "lastname", "last_name")
        phone, email = _phone(_text(node, "telephone", "phone")), _email(_text(node, "email"))
        product_sum, unit_count, line_count = 0.0, 0, 0
        for product in node.findall("./products/product"):
            quantity = _quantity(_text(product, "product_quantity", "quantity"))
            price = _number(_text(product, "product_price", "price"))
            total = _number(_text(product, "product_total", "total")) or quantity * price
            product_sum += total
            unit_count += quantity
            line_count += 1
            items.append({"order_id": order_id, "order_date": order_date, "product_id": _text(product, "product_id", "id"), "product_name": _text(product, "product_name", "name", default="Без названия"), "sku": _text(product, "product_sku", "sku"), "quantity": quantity, "unit_price": price, "product_total": total})

        total = _number(_text(node, "total", "order_total"))
        orders.append({"order_id": order_id, "order_date": order_date, "status": status, "order_total": total, "products_total": product_sum, "adjustment": total - product_sum, "item_quantity": unit_count, "item_lines": line_count, "customer_key": _customer_key(phone, email, first, last), "customer_name": f"{first} {last}".strip() or "Не указан", "payment_method": _text(node, "payment_method", default="Не указан"), "shipping_method": _text(node, "shipping_method", default="Не указан"), "region": _text(node, "shipping_zone", "region", default="Не указан"), "city": _text(node, "shipping_city", "city", default="Не указан")})

    orders_df, items_df = pd.DataFrame(orders), pd.DataFrame(items)
    if not orders_df.empty:
        orders_df["day"] = orders_df["order_date"].dt.normalize()
    return ParsedData(orders_df, items_df, len(nodes), skipped, invalid)
