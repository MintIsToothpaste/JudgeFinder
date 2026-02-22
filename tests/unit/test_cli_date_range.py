from __future__ import annotations

from datetime import date

from judgefinder.interfaces.cli.main import _resolve_target_dates


def test_resolve_target_dates_returns_single_day_when_days_is_one() -> None:
    dates = _resolve_target_dates(raw_date="2026-02-18", timezone_name="Asia/Seoul", days=1)

    assert dates == [date(2026, 2, 18)]


def test_resolve_target_dates_returns_chronological_range() -> None:
    dates = _resolve_target_dates(raw_date="2026-02-18", timezone_name="Asia/Seoul", days=3)

    assert dates == [
        date(2026, 2, 16),
        date(2026, 2, 17),
        date(2026, 2, 18),
    ]
