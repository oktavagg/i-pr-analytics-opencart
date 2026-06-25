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

PAYMENT_ALIASES = {
    "Оплата при доставке": "Оплата при доставці",
    "Оплата при доставці": "Оплата при доставці",
    "На рахунок": "На рахунок",
    "LiqPay": "LiqPay",
}

SHIPPING_ALIASES = {
    "Новая почта (в отделение)": "Нова пошта (до відділення)",
    "Нова пошта (до відділення)": "Нова пошта (до відділення)",
    "Новая почта (в почтомат)": "Нова пошта (до поштомату)",
    "Нова пошта (до поштомату)": "Нова пошта (до поштомату)",
    "Новая почта (адресная доставка)": "Нова пошта (адресна доставка)",
    "Нова пошта (адресна доставка)": "Нова пошта (адресна доставка)",
    "Самовывоз (г. Киев, ул. А. Довбуша, 37)": "Самовивіз (Київ)",
    "Самовивіз (м. Київ, вул. О. Довбуша, 37)": "Самовивіз (Київ)",
    "Доставка в точку выдачи Розетка": "Точка видачі Rozetka",
    "Доставка в точку видачі Розетка": "Точка видачі Rozetka",
    "Курьером по Киеву от 3000 грн (бесплатно)": "Кур’єр по Києву",
    "Кур’єром по Києву від 3000 грн (безкоштовно)": "Кур’єр по Києву",
}


@dataclass(frozen=True)
class ParsedData:
    orders: pd.DataFrame
    items: pd.DataFrame
    all_orders: pd.DataFrame
    all_items: pd.DataFrame
    total_xml_orders: int
    skipped_by_status: int


def text_of(parent, tag: str, default: str = "") -> str:
    node = parent.find(tag)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def to_float(value: str) -> float:
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def to_int(value: str) -> int:
    try:
        return int(float(str(value).replace(" ", "").replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("380") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 10:
        return f"+38{digits}"
    return f"+{digits}" if digits else ""


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not email or email.endswith("@localhost.net"):
        return ""
    return email


def normalize_dimension(value: str, aliases: dict[str, str]) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    return aliases.get(cleaned, cleaned or "Не указано")


def make_customer_key(phone: str, email: str, first_name: str, last_name: str) -> str:
    source = phone or email or f"{first_name.lower()}|{last_name.lower()}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _prepare_frames(orders: list[dict], items: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    orders_df = pd.DataFrame(orders)
    items_df = pd.DataFrame(items)

    if not orders_df.empty:
        orders_df["order_date"] = pd.to_datetime(orders_df["order_date"])
        orders_df["day"] = orders_df["order_date"].dt.date
        orders_df["month"] = orders_df["order_date"].dt.to_period("M").astype(str)

    if not items_df.empty:
        items_df["order_date"] = pd.to_datetime(items_df["order_date"])

    return orders_df, items_df


def parse_xml(xml_bytes: bytes) -> ParsedData:
    try:
        root = SafeET.fromstring(xml_bytes)
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать XML: {exc}") from exc

    order_nodes = root.findall(".//item")
    supported_orders: list[dict] = []
    supported_items: list[dict] = []
    all_orders: list[dict] = []
    all_items: list[dict] = []
    skipped = 0

    for order_node in order_nodes:
        status = text_of(order_node, "order_status")
        is_supported = status in ALLOWED_STATUSES
        if not is_supported:
            skipped += 1

        order_id = text_of(order_node, "order_id")
        order_date = pd.to_datetime(text_of(order_node, "date_added"), errors="coerce")
        if pd.isna(order_date):
            continue

        first_name = text_of(order_node, "firstname")
        last_name = text_of(order_node, "lastname")
        phone = normalize_phone(text_of(order_node, "telephone"))
        email = normalize_email(text_of(order_node, "email"))
        customer_key = make_customer_key(phone, email, first_name, last_name)

        payment_method = normalize_dimension(
            text_of(order_node, "payment_method"),
            PAYMENT_ALIASES,
        )
        shipping_method = normalize_dimension(
            text_of(order_node, "shipping_method"),
            SHIPPING_ALIASES,
        )

        item_quantity = 0
        item_lines = 0
        products_total = 0.0
        order_items: list[dict] = []

        for product in order_node.findall("./products/product"):
            quantity = to_int(text_of(product, "product_quantity"))
            unit_price = to_float(text_of(product, "product_price"))
            product_total = to_float(text_of(product, "product_total"))
            if product_total == 0 and quantity and unit_price:
                product_total = quantity * unit_price

            item_record = {
                "order_id": order_id,
                "order_date": order_date,
                "status": status,
                "product_id": text_of(product, "product_id"),
                "product_name": text_of(product, "product_name", "Без названия"),
                "model": text_of(product, "product_model"),
                "sku": text_of(product, "product_sku"),
                "quantity": quantity,
                "unit_price": unit_price,
                "product_total": product_total,
            }
            order_items.append(item_record)
            item_quantity += quantity
            item_lines += 1
            products_total += product_total

        order_total = to_float(text_of(order_node, "total"))
        order_record = {
            "order_id": order_id,
            "order_date": order_date,
            "status": status or "Не указано",
            "order_total": order_total,
            "products_total": products_total,
            "adjustment": products_total - order_total,
            "item_quantity": item_quantity,
            "item_lines": item_lines,
            "customer_key": customer_key,
            "customer_name": f"{first_name} {last_name}".strip() or "Не указано",
            "phone": phone,
            "email": email,
            "payment_method": payment_method,
            "shipping_method": shipping_method,
            "city": text_of(order_node, "shipping_city") or "Не указано",
            "region": text_of(order_node, "shipping_zone") or "Не указано",
        }

        all_orders.append(order_record)
        all_items.extend(order_items)
        if is_supported:
            supported_orders.append(order_record)
            supported_items.extend(order_items)

    orders_df, items_df = _prepare_frames(supported_orders, supported_items)
    all_orders_df, all_items_df = _prepare_frames(all_orders, all_items)

    return ParsedData(
        orders=orders_df,
        items=items_df,
        all_orders=all_orders_df,
        all_items=all_items_df,
        total_xml_orders=len(order_nodes),
        skipped_by_status=skipped,
    )


def top_products(items: pd.DataFrame) -> pd.DataFrame:
    if items.empty:
        return pd.DataFrame()

    return (
        items.groupby(
            ["product_id", "product_name", "sku"],
            as_index=False,
        )
        .agg(
            sold_units=("quantity", "sum"),
            revenue=("product_total", "sum"),
            orders=("order_id", "nunique"),
        )
        .sort_values(
            ["sold_units", "revenue"],
            ascending=False,
        )
    )


@dataclass(frozen=True)
class ProductCatalogSummary:
    total_products: int
    active_products: int


def validate_product_xml(xml_bytes: bytes) -> ProductCatalogSummary:
    """Validate an OpenCart product export and return a lightweight summary."""
    try:
        root = SafeET.fromstring(xml_bytes)
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать XML товаров: {exc}") from exc

    product_nodes = root.findall(".//item")
    if not product_nodes:
        raise ValueError("В XML товаров не найдено ни одного товара.")

    required_fields = ("product_id", "name")
    valid_products = 0
    active_products = 0

    for product_node in product_nodes:
        if all(text_of(product_node, field) for field in required_fields):
            valid_products += 1
            if text_of(product_node, "status", "1") == "1":
                active_products += 1

    if valid_products == 0:
        raise ValueError(
            "Файл не похож на XML каталога. Нужны поля product_id и name."
        )

    return ProductCatalogSummary(
        total_products=valid_products,
        active_products=active_products,
    )

@dataclass(frozen=True)
class OrderXmlSummary:
    total_orders: int
    supported_orders: int
    product_lines: int


def validate_order_xml(xml_bytes: bytes) -> OrderXmlSummary:
    """Validate an OpenCart order export before saving it."""
    try:
        root = SafeET.fromstring(xml_bytes)
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать XML заказов: {exc}") from exc

    order_nodes = root.findall(".//item")
    if not order_nodes:
        raise ValueError("В XML заказов не найдено ни одного заказа.")

    valid_orders = 0
    supported_orders = 0
    product_lines = 0

    for order_node in order_nodes:
        order_id = text_of(order_node, "order_id")
        date_added = text_of(order_node, "date_added")
        status = text_of(order_node, "order_status")
        products = order_node.findall("./products/product")

        if not order_id or not date_added or order_node.find("order_status") is None:
            continue

        valid_orders += 1
        product_lines += len(products)
        if status in ALLOWED_STATUSES:
            supported_orders += 1

    if valid_orders == 0:
        raise ValueError(
            "Файл не похож на XML заказов. Нужны поля order_id, date_added и order_status."
        )

    return OrderXmlSummary(
        total_orders=valid_orders,
        supported_orders=supported_orders,
        product_lines=product_lines,
    )

