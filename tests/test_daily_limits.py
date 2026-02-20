"""
Минимальные unit-тесты для «Лимиты по дням»: конвертация руб↔коп и выбор дня недели.
"""
from datetime import date, timedelta

import pytest


def rub_to_penny(rub: int) -> int:
    """Рубли в копейки (целое, кратное 100)."""
    return rub * 100


def penny_to_rub(penny: int) -> int:
    """Копейки в рубли (целое)."""
    return penny // 100


def weekday_for_date(d: date) -> int:
    """День недели: 0=Пн .. 6=Вс (как в ProfileDailyLimits)."""
    return d.weekday()


def tomorrow_weekday() -> int:
    """Weekday для завтрашнего дня (для job 23:59)."""
    return weekday_for_date(date.today() + timedelta(days=1))


class TestRubPenny:
    def test_rub_to_penny(self):
        assert rub_to_penny(0) == 0
        assert rub_to_penny(1) == 100
        assert rub_to_penny(100) == 10000

    def test_penny_to_rub(self):
        assert penny_to_rub(0) == 0
        assert penny_to_rub(100) == 1
        assert penny_to_rub(10050) == 100

    def test_roundtrip(self):
        for rub in (0, 1, 100, 999):
            assert penny_to_rub(rub_to_penny(rub)) == rub


class TestTomorrowWeekday:
    def test_weekday_monday_is_zero(self):
        # 2026-02-23 Monday
        assert weekday_for_date(date(2026, 2, 23)) == 0

    def test_weekday_sunday_is_six(self):
        assert weekday_for_date(date(2026, 2, 22)) == 6

    def test_tomorrow_weekday_in_range(self):
        w = tomorrow_weekday()
        assert 0 <= w <= 6
