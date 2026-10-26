from dataclasses import replace
from datetime import date
from typing import cast
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.source_profiles import EngineType, HtmlProfile

PROFILE = HtmlProfile(container_selector="table", row_selector="tbody tr", date_selector="td.date",
    link_selector="td.subject", link_attribute="data-key-no", id_pattern=r"^([1-9][0-9]*)$",
    detail_url_template="/view?id={id}")
HTML = ('<table><tbody><tr><td class="subject" data-key-no="123">평가위원 모집</td>'
    '<td class="date">2026-09-10</td></tr></tbody></table>')


def test_numeric_data_attribute_builds_canonical_detail_without_running_js() -> None:
    notice = parse_profiled_html(HTML, list_url="https://example.org/list", profile=PROFILE)[0]
    assert notice.url == "https://example.org/view?id=123"
    assert notice.published_date == date(2026, 9, 10)


@pytest.mark.parametrize("value", ["0", "-1", "１２３", "12/../3", "123;alert(1)", "https://evil/123"])
def test_invalid_data_identifier_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="identifier"):
        parse_profiled_html(HTML.replace('data-key-no="123"', f'data-key-no="{value}"'),
            list_url="https://example.org/list", profile=PROFILE)


@pytest.mark.parametrize("attribute", ["src", "onmouseover", "data-", "data-Key", "data-x y"])
def test_unsupported_attribute_is_rejected(attribute: str) -> None:
    with pytest.raises(ValueError, match="link_attribute"):
        replace(PROFILE, link_attribute=attribute)


def test_numeric_data_attribute_requires_pattern_and_retains_origin_validation() -> None:
    with pytest.raises(ValueError, match="identifier pattern"):
        replace(PROFILE, id_pattern="", detail_url_template="")
    with pytest.raises(ValueError, match="configured host"):
        parse_profiled_html(HTML, list_url="https://example.org/list",
            profile=replace(PROFILE, detail_url_template="https://evil.example/view?id={id}"))


def test_zero_based_html_offsets_do_not_change_page_or_keyword() -> None:
    source = GenericEngineSource(slug="demo", municipality="demo", source_type=SourceType.HTML,
        list_url="https://example.org/list?board=notice&offset=99", timezone=ZoneInfo("Asia/Seoul"),
        engine_type=EngineType.GENERIC_EGOV_BBS, http_client=Mock(),
        html_profile=replace(PROFILE, page_param="page", offset_param="offset", page_size=10,
            search_param="keyword"))
    for page, offset in [(1, "0"), (2, "10"), (3, "20")]:
        query = parse_qs(urlparse(source._build_request_url(page_index=page)).query)
        assert query == {"board": ["notice"], "offset": [offset], "page": [str(page)],
            "keyword": ["평가위원"]}


@pytest.mark.parametrize("size", [True, "10", 0, -1, 1001])
def test_invalid_html_page_size_is_rejected(size: object) -> None:
    with pytest.raises(ValueError, match="page_size"):
        replace(PROFILE, page_size=cast(int, size))


def test_offset_requires_distinct_page_parameter() -> None:
    with pytest.raises(ValueError, match="page parameter"):
        replace(PROFILE, offset_param="offset", page_param="")
    with pytest.raises(ValueError, match="must differ"):
        replace(PROFILE, offset_param="pageIndex")


def test_legacy_empty_spelling_is_not_an_error_document() -> None:
    empty = '<table><tbody><tr><td>데이타가 없습니다.</td></tr></tbody></table>'
    assert parse_profiled_html(empty, list_url="https://example.org/list", profile=PROFILE) == []
