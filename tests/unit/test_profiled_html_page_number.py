from __future__ import annotations

from dataclasses import replace

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.domain.source_profiles import HtmlProfile

PROFILE = HtmlProfile(
    container_selector="table", row_selector="tr:has(td)", date_selector="td.date",
    page_number_selector="a.on[title='현재페이지']",
)
ROW = '<table><tr><td><a href="/notice/1">평가위원 모집</a></td>' \
    '<td class="date">2026-09-22</td></tr></table>'
PAGE = '<a class="on" title="현재페이지">{page}</a>'


@pytest.mark.parametrize("page", [1, 2, 12])
def test_actual_page_number_matches_requested_page(page: int) -> None:
    assert len(parse_profiled_html(
        ROW + PAGE.format(page=page), list_url="https://city.example/list",
        profile=PROFILE, expected_page=page,
    )) == 1


@pytest.mark.parametrize("indicator", ["", PAGE.format(page=1), PAGE.format(page="error")])
def test_ignored_page_parameter_is_not_mistaken_for_last_page(indicator: str) -> None:
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            ROW + indicator, list_url="https://city.example/list",
            profile=PROFILE, expected_page=2,
        )


def test_profiles_without_page_number_validation_keep_existing_behavior() -> None:
    assert len(parse_profiled_html(
        ROW, list_url="https://city.example/list",
        profile=replace(PROFILE, page_number_selector=""), expected_page=2,
    )) == 1


@pytest.mark.parametrize("indicator", ["", PAGE.format(page=1), PAGE.format(page="error")])
def test_explicit_empty_terminal_page_can_omit_or_reset_its_pager(indicator: str) -> None:
    empty = '<table><tr><td colspan="4">등록된글이 없습니다.</td></tr></table>'
    assert parse_profiled_html(empty + indicator, list_url="https://city.example/list",
        profile=PROFILE, expected_page=3) == []


@pytest.mark.parametrize("row", [
    '<tr><td>Service error</td></tr>',
    '<tr><td>등록된글이 없습니다.<a href="/notice/1">공고</a></td></tr>',
    '<tr><td>등록된글이 없습니다.<button>공고</button></td></tr>',
])
def test_error_or_link_bearing_row_does_not_override_page_validation(row: str) -> None:
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(f'<table>{row}</table>', list_url="https://city.example/list",
            profile=PROFILE, expected_page=3)


@pytest.mark.parametrize("attribute,value,pattern", [
    ("data-key-no", "123", r"^([1-9][0-9]*)$"),
    ("onclick", "searchDetail('123')", r"searchDetail\('([1-9][0-9]*)'"),
])
def test_td_identifier_is_not_mistaken_for_empty_message(
    attribute: str, value: str, pattern: str,
) -> None:
    profile = replace(PROFILE, link_selector=f"td[{attribute}]", link_attribute=attribute,
        id_pattern=pattern, detail_url_template="/notice/{id}")
    html = f'<table><tr><td {attribute}="{value}">등록된글이 없습니다.</td></tr></table>'
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(html, list_url="https://city.example/list",
            profile=profile, expected_page=3)
