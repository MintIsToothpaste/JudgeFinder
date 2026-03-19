from __future__ import annotations

import logging

from judgefinder.interfaces.cli.main import _SuppressMalformedHeaderWarning


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
