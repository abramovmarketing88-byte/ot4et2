"""
Единая логика часовых поясов.

- БД: все datetime хранятся в UTC (datetime.utcnow()).
- Планировщик: сравнение report_time с текущим временем — Europe/Moscow.
- Диапазоны дат для API (вчера и т.д.) считаются по Москве.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Все timestamp в БД — UTC
DB_TZ = ZoneInfo("UTC")
SCHEDULER_TZ = ZoneInfo("Europe/Moscow")


def utc_now() -> datetime:
    """Текущее время в UTC, naive (для записи и сравнения в БД)."""
    return datetime.now(DB_TZ).replace(tzinfo=None)


def moscow_now() -> datetime:
    """Текущее время в Europe/Moscow (для планировщика и отчётов)."""
    return datetime.now(SCHEDULER_TZ)


def moscow_time_str() -> str:
    """Текущее время в Москве в формате HH:MM (для сравнения с report_time)."""
    return moscow_now().strftime("%H:%M")


def moscow_date_range_yesterday() -> tuple[str, str]:
    """Вчера по Москве в формате YYYY-MM-DD."""
    today = moscow_now().date()
    yesterday = today - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")


def moscow_yesterday_formatted() -> str:
    """Вчера по Москве в формате DD.MM.YYYY для отчёта."""
    return (moscow_now().date() - timedelta(days=1)).strftime("%d.%m.%Y")


def date_range_formatted(date_from: str, date_to: str) -> str:
    """Форматирование диапазона дат для заголовка отчёта (YYYY-MM-DD -> DD.MM.YYYY)."""
    from datetime import date
    try:
        d1 = date.fromisoformat(date_from)
        d2 = date.fromisoformat(date_to)
        if d1 == d2:
            return d1.strftime("%d.%m.%Y")
        return f"{d1.strftime('%d.%m.%Y')} – {d2.strftime('%d.%m.%Y')}"
    except (ValueError, TypeError):
        return f"{date_from} – {date_to}"
