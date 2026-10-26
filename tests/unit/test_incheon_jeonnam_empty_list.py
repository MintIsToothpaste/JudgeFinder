from __future__ import annotations

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.domain.source_profiles import HtmlProfile

PROFILE = HtmlProfile(
    container_selector="table", row_selector="tr", link_selector="a",
    date_selector="td.date",
)


def test_mokpo_empty_search_row_is_not_a_broken_notice() -> None:
    assert parse_profiled_html(
        '<table><tr><td colspan="6">검색내역이 없습니다.</td></tr></table>',
        list_url="https://www.mokpo.go.kr/", profile=PROFILE,
    ) == []


@pytest.mark.parametrize("message", [
    "검색내역이 없습니다만 서비스 오류가 발생했습니다.",
    "검색내역이 조회되지 않습니다.",
    "검색내역이 조회 권한이 없습니다.",
])
def test_search_failure_is_not_accepted_as_an_empty_search(message: str) -> None:
    with pytest.raises(ValueError, match="notice link missing"):
        parse_profiled_html(
            f"<table><tr><td>{message}</td></tr></table>",
            list_url="https://www.mokpo.go.kr/", profile=PROFILE,
        )
