"""
Форматирование отчётов для Telegram (MarkdownV2).

Поддержка выбора характеристик: selected_metrics — список ключей (пусто = все).
"""
import re
from typing import Optional

from utils.analytics import AnalyticsMetrics, ALL_REPORT_METRIC_KEYS


def escape_md(text: str) -> str:
    """Экранирование спецсимволов для MarkdownV2."""
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", str(text))


def format_number(value: int | float) -> str:
    """Форматирование чисел с разделителями тысяч."""
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return f"{value:,}".replace(",", " ")


def _line(key: str, value_str: str) -> str:
    return f"{value_str}"


def format_report_md2(
    profile_name: str,
    period: str,
    metrics: AnalyticsMetrics,
    selected_metrics: list[str] | None = None,
) -> str:
    """
    Генерация отчёта в MarkdownV2.
    selected_metrics: список ключей (views, contacts, total_spending, wallet_balance и т.д.). Пусто = все.
    """
    show = set(selected_metrics) if selected_metrics else set(ALL_REPORT_METRIC_KEYS)
    profile_esc = escape_md(profile_name)
    period_esc = escape_md(period)
    lines: list[str] = []
    # Заголовок
    lines.append("📊 *Отчёт Avito*")
    lines.append(f"_{profile_esc}_")
    lines.append(period_esc)
    lines.append("")
    # Блок показателей по выбранным ключам
    blocks: list[str] = []
    if "views" in show:
        blocks.append(f"👁 Просмотры: *{escape_md(format_number(metrics.views))}* \\(уник\\. {escape_md(format_number(metrics.uniq_views))}\\)")
    if "contacts" in show:
        blocks.append(f"📞 Контакты: *{escape_md(format_number(metrics.uniq_contacts))}*")
    if "favorites" in show:
        blocks.append(f"✉️ В избранном: *{escape_md(format_number(metrics.uniq_favorites))}*")
    if "total_spending" in show:
        blocks.append(f"💰 Расходы \\(всего\\): *{escape_md(format_number(metrics.total_spending))} ₽*")
    if "presence_spending" in show and (metrics.presence_spending or metrics.presence_spending == 0):
        blocks.append(f"💰 На размещение: *{escape_md(format_number(metrics.presence_spending))} ₽*")
    if "promo_spending" in show and (metrics.promo_spending or metrics.promo_spending == 0):
        blocks.append(f"💰 На продвижение: *{escape_md(format_number(metrics.promo_spending))} ₽*")
    if "rest_spending" in show and (metrics.rest_spending or metrics.rest_spending == 0):
        blocks.append(f"💰 Прочие расходы: *{escape_md(format_number(metrics.rest_spending))} ₽*")
    if "wallet_balance" in show and metrics.wallet_balance is not None:
        blocks.append(f"💳 Кошелёк: *{escape_md(format_number(metrics.wallet_balance))} ₽*")
    if "advance_balance" in show and metrics.advance_balance is not None:
        blocks.append(f"📅 Аванс: *{escape_md(format_number(metrics.advance_balance))} ₽*")
    if "active_items" in show:
        blocks.append(f"📦 Активные объявления: *{escape_md(format_number(metrics.active_items))}*")
    if "cr" in show and metrics.cr is not None:
        blocks.append(f"📈 CR: *{escape_md(f'{metrics.cr}%')}*")
    if "cpl" in show and metrics.cpl is not None:
        blocks.append(f"💵 CPL: *{escape_md(format_number(metrics.cpl))} ₽*")
    if "cpv" in show and metrics.cpv is not None:
        blocks.append(f"📊 CPV: *{escape_md(format_number(metrics.cpv))} ₽*")
    if blocks:
        lines.append("*Показатели:*")
        lines.extend(blocks)
    return "\n".join(lines)


def format_daily_report_md2(
    profile_name: str,
    date: str,
    views: int,
    uniq_contacts: int,
    spending: float,
    cr: Optional[float],
    cpl: Optional[float],
) -> str:
    """
    Краткий ежедневный отчёт в MarkdownV2.
    
    :param profile_name: название профиля
    :param date: дата (например, "07.02.2025")
    :param views: просмотры
    :param uniq_contacts: уникальные контакты
    :param spending: расходы
    :param cr: конверсия (%)
    :param cpl: стоимость контакта (руб)
    """
    cr_str = f"{cr}%" if cr is not None else "—"
    cpl_str = f"{format_number(cpl)} ₽" if cpl is not None else "—"
    
    profile_esc = escape_md(profile_name)
    date_esc = escape_md(date)
    views_esc = escape_md(format_number(views))
    contacts_esc = escape_md(format_number(uniq_contacts))
    spending_esc = escape_md(format_number(spending))
    cr_esc = escape_md(cr_str)
    cpl_esc = escape_md(cpl_str)
    
    return f"""📊 *{profile_esc}* \\| {date_esc}

👁 *{views_esc}*  📞 *{contacts_esc}*  💰 *{spending_esc} ₽*
📈 CR: {cr_esc}  💵 CPL: {cpl_esc}"""


def format_error_md2(profile_name: str, error: str) -> str:
    """Сообщение об ошибке в MarkdownV2."""
    profile_esc = escape_md(profile_name)
    error_esc = escape_md(error)
    return f"""⚠️ *Ошибка отчёта*
_{profile_esc}_

```
{error_esc}
```"""
