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

PROFILE = HtmlProfile(
    container_selector="ul.notices", row_selector=":scope > li", date_selector="time",
    title_selector="a", page_number_selector="b.current", page_size=1,
    total_count_selector="span.total", total_count_pattern=r"Total: ([0-9]+)",
)


def listing(total: str = "1", page: int = 1, identifier: int = 1) -> str:
    return (
        f'<span class="total">Total: {total}</span><b class="current">{page}</b>'
        '<ul class="notices"><li>'
        f'<a href="/view?id={identifier}">평가위원 모집 공고</a>'
        '<time>2026-10-05</time></li></ul>'
    )


def source(client: Mock, profile: HtmlProfile = PROFILE, max_pages: int = 2):
    return GenericEngineSource(
        slug="demo", municipality="demo", source_type=SourceType.HTML,
        list_url="https://example.gov/list", engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"), http_client=client,
        html_profile=profile, max_pages=max_pages, recruitment_only=True,
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


@pytest.mark.parametrize("payload,expected", [
    (listing().replace('<span class="total">Total: 1</span>', ''), "missing or ambiguous"),
    (listing() + '<span class="total">Total: 1</span>', "missing or ambiguous"),
    (listing("-1"), "nonnegative integer"),
    (listing("unknown"), "nonnegative integer"),
    (listing("0"), "row count contradicts"),
    (listing("2"), "row count contradicts"),
])
def test_invalid_or_partial_counted_listing_fails_closed(payload: str, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        parse_profiled_html(payload, list_url="https://example.gov/list",
            profile=replace(PROFILE, page_size=10), expected_page=1)


def test_empty_message_cannot_contradict_a_positive_total() -> None:
    payload = listing().replace(
        '<a href="/view?id=1">평가위원 모집 공고</a><time>2026-10-05</time>',
        '등록된 글이 없습니다.',
    )
    with pytest.raises(ValueError, match="empty listing contradicts"):
        parse_profiled_html(payload, list_url="https://example.gov/list", profile=PROFILE,
            expected_page=1)


def test_counted_pagination_still_rejects_an_ignored_page() -> None:
    client = Mock()
    client.get_text.return_value = listing("2")
    with pytest.raises(ValueError, match="page does not match"):
        source(client).fetch(date(2026, 10, 5))


@pytest.mark.parametrize("changes", [
    {"total_count_pattern": ""},
    {"total_count_selector": ""},
    {"total_count_pattern": r"([0-9]+)([0-9]+)"},
    {"page_number_selector": ""},
    {"page_param": ""},
])
def test_count_config_requires_unambiguous_current_page_and_total(changes: dict) -> None:
    with pytest.raises(ValueError, match="total|capture"):
        replace(PROFILE, **changes)


def test_legacy_profile_keeps_existing_page_validation() -> None:
    profile = replace(PROFILE, total_count_selector="", total_count_pattern="")
    client = Mock()
    client.get_text.return_value = listing()
    with pytest.raises(ValueError, match="page does not match"):
        source(client, profile).fetch(date(2026, 10, 5))
