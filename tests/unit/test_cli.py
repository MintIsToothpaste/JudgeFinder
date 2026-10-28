from __future__ import annotations

import logging
from datetime import date

from judgefinder.interfaces.cli.main import _resolve_target_dates, _SuppressMalformedHeaderWarning


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


def test_suppress_malformed_header_warning_filters_header_parse_message() -> None:
    record = logging.LogRecord(
        name="urllib3.connection",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Failed to parse headers (url=https://example.com): bad header",
        args=(),
        exc_info=None,
    )

    assert _SuppressMalformedHeaderWarning().filter(record) is False


def test_suppress_malformed_header_warning_keeps_other_messages() -> None:
    record = logging.LogRecord(
        name="urllib3.connection",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Connection pool is full, discarding connection",
        args=(),
        exc_info=None,
    )

    assert _SuppressMalformedHeaderWarning().filter(record) is True
