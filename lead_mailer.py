from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import streamlit as st


LEAD_RECIPIENT = "oktavagg@gmail.com"


class LeadMailError(RuntimeError):
    """Raised when the lead email cannot be delivered."""


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    use_ssl: bool
    use_tls: bool


def _secret_mapping() -> dict[str, Any]:
    try:
        section = st.secrets.get("smtp", {})
        return dict(section) if section else {}
    except Exception:
        return {}


def load_smtp_settings() -> SMTPSettings:
    secrets = _secret_mapping()

    host = str(secrets.get("host") or os.getenv("SMTP_HOST", "smtp.gmail.com")).strip()
    port_raw = secrets.get("port") or os.getenv("SMTP_PORT", "587")
    username = str(secrets.get("username") or os.getenv("SMTP_USERNAME", "")).strip()
    password = str(secrets.get("password") or os.getenv("SMTP_PASSWORD", "")).strip()
    from_email = str(
        secrets.get("from_email")
        or os.getenv("SMTP_FROM_EMAIL", "")
        or username
    ).strip()

    try:
        port = int(port_raw)
    except (TypeError, ValueError) as exc:
        raise LeadMailError("Некорректный SMTP-порт.") from exc

    use_ssl_raw = secrets.get("use_ssl", os.getenv("SMTP_USE_SSL", "false"))
    use_tls_raw = secrets.get("use_tls", os.getenv("SMTP_USE_TLS", "true"))
    use_ssl = str(use_ssl_raw).lower() in {"1", "true", "yes", "on"}
    use_tls = str(use_tls_raw).lower() in {"1", "true", "yes", "on"}

    if not host or not username or not password or not from_email:
        raise LeadMailError(
            "Отправка заявок ещё не настроена. Добавьте SMTP-доступы в Streamlit Secrets."
        )

    return SMTPSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        from_email=from_email,
        use_ssl=use_ssl,
        use_tls=use_tls,
    )


def send_lead_email(
    *,
    recommendation: dict[str, Any],
    project: str,
    contact: str,
    name: str = "",
    comment: str = "",
    context: dict[str, Any] | None = None,
) -> None:
    settings = load_smtp_settings()
    context = context or {}

    title = str(recommendation.get("title", "Рекомендация по сайту"))
    priority = str(recommendation.get("priority_label") or recommendation.get("priority", ""))
    text = str(recommendation.get("text", ""))
    actions = recommendation.get("actions", [])
    actions_text = "\n".join(f"- {item}" for item in actions) if actions else "Не указаны"

    start_date = context.get("start_date")
    end_date = context.get("end_date")
    period = ""
    if start_date and end_date:
        period = f"{start_date:%d.%m.%Y}–{end_date:%d.%m.%Y}"

    message = EmailMessage()
    message["Subject"] = f"[I-PR Dashboard] Заявка: {title}"
    message["From"] = settings.from_email
    message["To"] = LEAD_RECIPIENT
    if "@" in contact and " " not in contact:
        message["Reply-To"] = contact

    body = f"""Новая заявка из аналитического дашборда I-PR.

ПРОЕКТ
{project}

КОНТАКТ
Имя: {name or 'Не указано'}
Связь: {contact}

РЕКОМЕНДАЦИЯ
Приоритет: {priority or 'Не указан'}
Название: {title}
Описание: {text}

ПРЕДЛОЖЕННЫЕ ДОРАБОТКИ
{actions_text}

КОММЕНТАРИЙ КЛИЕНТА
{comment or 'Не указан'}

КОНТЕКСТ ОТЧЁТА
Период: {period or 'Не указан'}
Оборот: {context.get('revenue', 'Не указан')}
Заказов: {context.get('order_count', 'Не указано')}
"""
    message.set_content(body)

    try:
        ssl_context = ssl.create_default_context()
        if settings.use_ssl:
            with smtplib.SMTP_SSL(
                settings.host,
                settings.port,
                timeout=20,
                context=ssl_context,
            ) as server:
                server.login(settings.username, settings.password)
                server.send_message(message)
        else:
            with smtplib.SMTP(settings.host, settings.port, timeout=20) as server:
                server.ehlo()
                if settings.use_tls:
                    server.starttls(context=ssl_context)
                    server.ehlo()
                server.login(settings.username, settings.password)
                server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise LeadMailError(
            "Не удалось отправить заявку. Проверьте SMTP-настройки и повторите попытку."
        ) from exc
