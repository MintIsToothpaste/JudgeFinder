from __future__ import annotations

from dataclasses import replace
from datetime import date
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.source_profiles import EngineType, HtmlProfile

PAGE_PROFILE = HtmlProfile(
    container_selector="table",
    row_selector="tr:has(td)",
    date_selector="td.date",
    page_number_selector="a.on[title='현재페이지']",
)


ROW = (
    '<table><tr><td><a href="/notice/1">평가위원 모집</a></td>'
    '<td class="date">2026-09-22</td></tr></table>'
)


PAGE = '<a class="on" title="현재페이지">{page}</a>'


@pytest.mark.parametrize("page", [1, 2, 12])
def test_actual_page_number_matches_requested_page(page: int) -> None:
    assert (
        len(
            parse_profiled_html(
                ROW + PAGE.format(page=page),
                list_url="https://city.example/list",
                profile=PAGE_PROFILE,
                expected_page=page,
            )
        )
        == 1
    )


@pytest.mark.parametrize("indicator", ["", PAGE.format(page=1), PAGE.format(page="error")])
def test_ignored_page_parameter_is_not_mistaken_for_last_page(indicator: str) -> None:
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            ROW + indicator,
            list_url="https://city.example/list",
            profile=PAGE_PROFILE,
            expected_page=2,
        )


def test_profiles_without_page_number_validation_keep_existing_behavior() -> None:
    assert (
        len(
            parse_profiled_html(
                ROW,
                list_url="https://city.example/list",
                profile=replace(PAGE_PROFILE, page_number_selector=""),
                expected_page=2,
            )
        )
        == 1
    )


@pytest.mark.parametrize("indicator", ["", PAGE.format(page=1), PAGE.format(page="error")])
def test_explicit_empty_terminal_page_can_omit_or_reset_its_pager(indicator: str) -> None:
    empty = '<table><tr><td colspan="4">등록된글이 없습니다.</td></tr></table>'
    assert (
        parse_profiled_html(
            empty + indicator,
            list_url="https://city.example/list",
            profile=PAGE_PROFILE,
            expected_page=3,
        )
        == []
    )


@pytest.mark.parametrize(
    "row",
    [
        "<tr><td>Service error</td></tr>",
        '<tr><td>등록된글이 없습니다.<a href="/notice/1">공고</a></td></tr>',
        "<tr><td>등록된글이 없습니다.<button>공고</button></td></tr>",
    ],
)
def test_error_or_link_bearing_row_does_not_override_page_validation(row: str) -> None:
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            f"<table>{row}</table>",
            list_url="https://city.example/list",
            profile=PAGE_PROFILE,
            expected_page=3,
        )


@pytest.mark.parametrize(
    "attribute,value,pattern",
    [
        ("data-key-no", "123", r"^([1-9][0-9]*)$"),
        ("onclick", "searchDetail('123')", r"searchDetail\('([1-9][0-9]*)'"),
    ],
)
def test_td_identifier_is_not_mistaken_for_empty_message(
    attribute: str,
    value: str,
    pattern: str,
) -> None:
    profile = replace(
        PAGE_PROFILE,
        link_selector=f"td[{attribute}]",
        link_attribute=attribute,
        id_pattern=pattern,
        detail_url_template="/notice/{id}",
    )
    html = f'<table><tr><td {attribute}="{value}">등록된글이 없습니다.</td></tr></table>'
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            html, list_url="https://city.example/list", profile=profile, expected_page=3
        )


COUNTED_PROFILE = HtmlProfile(
    container_selector="ul.notices",
    row_selector=":scope > li",
    date_selector="time",
    title_selector="a",
    page_number_selector="b.current",
    page_size=1,
    total_count_selector="span.total",
    total_count_pattern=r"Total: ([0-9]+)",
)


def listing(total: str = "1", page: int = 1, identifier: int = 1) -> str:
    return (
        f'<span class="total">Total: {total}</span><b class="current">{page}</b>'
        '<ul class="notices"><li>'
        f'<a href="/view?id={identifier}">평가위원 모집 공고</a>'
        "<time>2026-10-05</time></li></ul>"
    )


def source(client: Mock, profile: HtmlProfile = COUNTED_PROFILE, max_pages: int = 2):
    return GenericEngineSource(
        slug="demo",
        municipality="demo",
        source_type=SourceType.HTML,
        list_url="https://example.gov/list",
        engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=client,
        html_profile=profile,
        max_pages=max_pages,
        recruitment_only=True,
    )


def test_declared_last_page_stops_before_an_out_of_range_clamped_request() -> None:
    client = Mock()
    client.get_text.return_value = listing()
    actual = source(client, max_pages=1)
    assert len(actual.fetch(date(2026, 10, 5))) == 1
    assert len(actual.fetch(date(2026, 10, 5))) == 1
    client.get_text.assert_called_once()
    assert actual.profile_total_count_cache == {1: 1}


def test_declared_count_does_not_skip_the_next_real_page() -> None:
    client = Mock()
    client.get_text.side_effect = [listing("2"), listing("2", 2, 2)]
    assert len(source(client).fetch(date(2026, 10, 5))) == 2
    assert client.get_text.call_count == 2


@pytest.mark.parametrize(
    "payload,expected",
    [
        (listing().replace('<span class="total">Total: 1</span>', ""), "missing or ambiguous"),
        (listing() + '<span class="total">Total: 1</span>', "missing or ambiguous"),
        (listing("-1"), "nonnegative integer"),
        (listing("unknown"), "nonnegative integer"),
        (listing("0"), "row count contradicts"),
        (listing("2"), "row count contradicts"),
    ],
)
def test_invalid_or_partial_counted_listing_fails_closed(payload: str, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        parse_profiled_html(
            payload,
            list_url="https://example.gov/list",
            profile=replace(COUNTED_PROFILE, page_size=10),
            expected_page=1,
        )


def test_empty_message_cannot_contradict_a_positive_total() -> None:
    payload = listing().replace(
        '<a href="/view?id=1">평가위원 모집 공고</a><time>2026-10-05</time>',
        "등록된 글이 없습니다.",
    )
    with pytest.raises(ValueError, match="empty listing contradicts"):
        parse_profiled_html(
            payload, list_url="https://example.gov/list", profile=COUNTED_PROFILE, expected_page=1
        )


def test_counted_pagination_still_rejects_an_ignored_page() -> None:
    client = Mock()
    client.get_text.return_value = listing("2")
    with pytest.raises(ValueError, match="page does not match"):
        source(client).fetch(date(2026, 10, 5))


@pytest.mark.parametrize(
    "changes",
    [
        {"total_count_pattern": ""},
        {"total_count_selector": ""},
        {"total_count_pattern": r"([0-9]+)([0-9]+)"},
        {"page_number_selector": ""},
        {"page_param": ""},
    ],
)
def test_count_config_requires_unambiguous_current_page_and_total(changes: dict) -> None:
    with pytest.raises(ValueError, match="total|capture"):
        replace(COUNTED_PROFILE, **changes)


def test_legacy_profile_keeps_existing_page_validation() -> None:
    profile = replace(COUNTED_PROFILE, total_count_selector="", total_count_pattern="")
    client = Mock()
    client.get_text.return_value = listing()
    with pytest.raises(ValueError, match="page does not match"):
        source(client, profile).fetch(date(2026, 10, 5))
