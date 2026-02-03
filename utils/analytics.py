"""
Расчёт метрик аналитики Avito.

CR  = (uniqContacts / views) * 100
CPL = total_spending / uniqContacts
"""
from dataclasses import dataclass
from typing import Optional


# Ключи характеристик для настройки отчёта (максимум)
ALL_REPORT_METRIC_KEYS = [
    "views",
    "contacts",
    "favorites",
    "total_spending",
    "presence_spending",
    "promo_spending",
    "rest_spending",
    "wallet_balance",
    "advance_balance",
    "cr",
    "cpl",
    "cpv",
    "active_items",
]

REPORT_METRIC_LABELS = {
    "views": "👁 Просмотры",
    "contacts": "📞 Контакты",
    "favorites": "✉️ В избранном",
    "total_spending": "💰 Расходы (всего)",
    "presence_spending": "💰 Расходы на размещение",
    "promo_spending": "💰 Расходы на продвижение",
    "rest_spending": "💰 Прочие расходы",
    "wallet_balance": "💳 Кошелёк",
    "advance_balance": "📅 Аванс",
    "cr": "📈 CR (%)",
    "cpl": "💵 CPL (₽)",
    "cpv": "📊 CPV (₽)",
    "active_items": "📦 Активные объявления",
}


@dataclass
class AnalyticsMetrics:
    """Метрики аналитики."""
    views: int = 0
    uniq_views: int = 0
    contacts: int = 0
    uniq_contacts: int = 0
    favorites: int = 0
    uniq_favorites: int = 0
    total_spending: float = 0.0  # в рублях, за период
    presence_spending: float = 0.0
    promo_spending: float = 0.0
    rest_spending: float = 0.0
    wallet_balance: Optional[float] = None  # текущий баланс кошелька
    advance_balance: Optional[float] = None  # аванс
    active_items: int = 0

    @property
    def cr(self) -> Optional[float]:
        """CR = (uniqContacts / views) * 100 (%)."""
        if self.views <= 0:
            return None
        return round((self.uniq_contacts / self.views) * 100, 2)
    
    @property
    def cpl(self) -> Optional[float]:
        """CPL = total_spending / uniqContacts (руб/контакт)."""
        if self.uniq_contacts <= 0:
            return None
        return round(self.total_spending / self.uniq_contacts, 2)
    
    @property
    def cpv(self) -> Optional[float]:
        """CPV = total_spending / views (руб/просмотр)."""
        if self.views <= 0:
            return None
        return round(self.total_spending / self.views, 2)


def calc_cr(uniq_contacts: int, views: int) -> Optional[float]:
    """
    Conversion Rate: CR = (uniqContacts / views) * 100.
    
    :param uniq_contacts: уникальные контакты
    :param views: просмотры
    :return: CR в процентах или None
    """
    if views <= 0:
        return None
    return round((uniq_contacts / views) * 100, 2)


def calc_cpl(total_spending: float, uniq_contacts: int) -> Optional[float]:
    """
    Cost Per Lead: CPL = total_spending / uniqContacts.
    
    :param total_spending: общие расходы (рубли)
    :param uniq_contacts: уникальные контакты
    :return: CPL в рублях или None
    """
    if uniq_contacts <= 0:
        return None
    return round(total_spending / uniq_contacts, 2)


def calc_cpv(total_spending: float, views: int) -> Optional[float]:
    """
    Cost Per View: CPV = total_spending / views.
    
    :param total_spending: общие расходы (рубли)
    :param views: просмотры
    :return: CPV в рублях или None
    """
    if views <= 0:
        return None
    return round(total_spending / views, 4)


def parse_avito_stats(data: dict) -> AnalyticsMetrics:
    """
    Парсинг ответа Avito API stats в AnalyticsMetrics.
    
    Ожидает структуру result.items[].stats[].
    """
    metrics = AnalyticsMetrics()
    
    items = data.get("result", {}).get("items", [])
    for item in items:
        for stat in item.get("stats", []):
            metrics.views += stat.get("views", 0)
            metrics.uniq_views += stat.get("uniqViews", 0)
            metrics.contacts += stat.get("contacts", 0)
            metrics.uniq_contacts += stat.get("uniqContacts", 0)
            metrics.favorites += stat.get("favorites", 0)
            metrics.uniq_favorites += stat.get("uniqFavorites", 0)
    
    return metrics
