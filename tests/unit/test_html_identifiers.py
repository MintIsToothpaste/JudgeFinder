from __future__ import annotations

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

HEX_PROFILE = HtmlProfile(
    container_selector="table",
    row_selector="tr",
    date_selector="time",
    id_pattern=r"no=([^&]+)",
    detail_url_template="/view?no={id}",
    id_format="hex32",
)


IDENTIFIER = "0123456789abcdef0123456789ABCDEF"


def parse_hex_notice(identifier: str, profile: HtmlProfile = HEX_PROFILE):
    payload = (
        f'<table><tr><td><a href="/view?no={identifier}&amp;GotoPage=8">'
        "평가위원 모집</a><time>2026-10-02</time></td></tr></table>"
    )
    return parse_profiled_html(payload, list_url="https://example.org/list", profile=profile)


def test_explicit_hex_id_produces_pagination_independent_url():
    assert parse_hex_notice(IDENTIFIER)[0].url == f"https://example.org/view?no={IDENTIFIER}"


def test_default_numeric_format_remains_strict():
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_hex_notice(IDENTIFIER, replace(HEX_PROFILE, id_format="numeric"))


@pytest.mark.parametrize("identifier", ["123", "a" * 31, "a" * 33, "g" * 32, "../view", "%2f" * 16])
def test_hex_format_rejects_unvalidated_identifiers(identifier):
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_hex_notice(identifier)


def test_hex_format_does_not_weaken_origin_validation():
    with pytest.raises(ValueError, match="configured host"):
        parse_hex_notice(
            IDENTIFIER, replace(HEX_PROFILE, detail_url_template="https://other.org/?no={id}")
        )


@pytest.mark.parametrize("format", ["uuid", "", "anything"])
def test_unknown_format_is_rejected(format):
    with pytest.raises(ValueError, match="id_format"):
        replace(HEX_PROFILE, id_format=format)


def test_hex_format_requires_extraction_pattern():
    with pytest.raises(ValueError, match="identifier pattern"):
        replace(HEX_PROFILE, id_pattern="", detail_url_template="")


DATA_PROFILE = HtmlProfile(
    container_selector="table",
    row_selector="tbody tr",
    date_selector="td.date",
    link_selector="td.subject",
    link_attribute="data-key-no",
    id_pattern=r"^([1-9][0-9]*)$",
    detail_url_template="/view?id={id}",
)


DATA_LISTING = (
    '<table><tbody><tr><td class="subject" data-key-no="123">평가위원 모집</td>'
    '<td class="date">2026-09-10</td></tr></tbody></table>'
)


def test_numeric_data_attribute_builds_canonical_detail_without_running_js() -> None:
    notice = parse_profiled_html(
        DATA_LISTING, list_url="https://example.org/list", profile=DATA_PROFILE
    )[0]
    assert notice.url == "https://example.org/view?id=123"
    assert notice.published_date == date(2026, 9, 10)


@pytest.mark.parametrize(
    "value", ["0", "-1", "１２３", "12/../3", "123;alert(1)", "https://evil/123"]
)
def test_invalid_data_identifier_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="identifier"):
        parse_profiled_html(
            DATA_LISTING.replace('data-key-no="123"', f'data-key-no="{value}"'),
            list_url="https://example.org/list",
            profile=DATA_PROFILE,
        )


@pytest.mark.parametrize("attribute", ["src", "onmouseover", "data-", "data-Key", "data-x y"])
def test_unsupported_attribute_is_rejected(attribute: str) -> None:
    with pytest.raises(ValueError, match="link_attribute"):
        replace(DATA_PROFILE, link_attribute=attribute)


def test_numeric_data_attribute_requires_pattern_and_retains_origin_validation() -> None:
    with pytest.raises(ValueError, match="identifier pattern"):
        replace(DATA_PROFILE, id_pattern="", detail_url_template="")
    with pytest.raises(ValueError, match="configured host"):
        parse_profiled_html(
            DATA_LISTING,
            list_url="https://example.org/list",
            profile=replace(DATA_PROFILE, detail_url_template="https://evil.example/view?id={id}"),
        )


def test_zero_based_html_offsets_do_not_change_page_or_keyword() -> None:
    source = GenericEngineSource(
        slug="demo",
        municipality="demo",
        source_type=SourceType.HTML,
        list_url="https://example.org/list?board=notice&offset=99",
        timezone=ZoneInfo("Asia/Seoul"),
        engine_type=EngineType.GENERIC_EGOV_BBS,
        http_client=Mock(),
        html_profile=replace(
            DATA_PROFILE,
            page_param="page",
            offset_param="offset",
            page_size=10,
            search_param="keyword",
        ),
    )
    for page, offset in [(1, "0"), (2, "10"), (3, "20")]:
        query = parse_qs(urlparse(source._build_request_url(page_index=page)).query)
        assert query == {
            "board": ["notice"],
            "offset": [offset],
            "page": [str(page)],
            "keyword": ["평가위원"],
        }


@pytest.mark.parametrize("size", [True, "10", 0, -1, 1001])
def test_invalid_html_page_size_is_rejected(size: object) -> None:
    with pytest.raises(ValueError, match="page_size"):
        replace(DATA_PROFILE, page_size=cast(int, size))


def test_offset_may_be_the_only_pagination_parameter_but_cannot_overlap() -> None:
    assert replace(DATA_PROFILE, offset_param="offset", page_param="").offset_param == "offset"
    with pytest.raises(ValueError, match="must differ"):
        replace(DATA_PROFILE, offset_param="pageIndex")


def test_legacy_empty_spelling_is_not_an_error_document() -> None:
    empty = "<table><tbody><tr><td>데이타가 없습니다.</td></tr></tbody></table>"
    assert (
        parse_profiled_html(empty, list_url="https://example.org/list", profile=DATA_PROFILE) == []
    )


ORIGIN_PROFILE = HtmlProfile(
    container_selector="table",
    row_selector="tbody tr",
    date_selector="td.date",
    link_attribute="onclick",
    link_selector="td.subject",
    id_pattern="searchDetail[(]'([1-9][0-9]*)'",
    detail_url_template="https://www.example.org/notice?id={id}",
    detail_title_selector="h2",
    detail_origin="https://www.example.org",
)


ORIGIN_LISTING = (
    '<table><tbody><tr><td class="subject" onclick="searchDetail(\'42274\')">'
    '제안서 평가...</td><td class="date">2026-09-08</td></tr></tbody></table>'
)


def test_explicit_public_detail_origin_preserves_listing_registration_date() -> None:
    urls = []

    def load(url: str) -> str:
        urls.append(url)
        return "<h2>제안서 평가위원 후보자 공개모집 공고</h2><p>게시기간 2026-09-01</p>"

    notice = parse_profiled_html(
        ORIGIN_LISTING,
        list_url="https://archive.example.org/list",
        profile=ORIGIN_PROFILE,
        detail_loader=load,
    )[0]
    assert notice.title == "제안서 평가위원 후보자 공개모집 공고"
    assert notice.published_date == date(2026, 9, 8)
    assert urls == ["https://www.example.org/notice?id=42274"]


def test_cross_host_details_still_fail_without_explicit_origin() -> None:
    with pytest.raises(ValueError, match="configured host"):
        parse_profiled_html(
            ORIGIN_LISTING,
            list_url="https://archive.example.org/list",
            profile=replace(ORIGIN_PROFILE, detail_origin=""),
        )


@pytest.mark.parametrize(
    "origin",
    [
        "http://www.example.org",
        "//www.example.org",
        "https://other.example.org",
        "https://www.example.org/",
        "https://www.example.org/path",
        "https://www.example.org?next=x",
        "https://www.example.org#fragment",
        "https://user:pass@www.example.org",
        "https://www.example.org:443",
        "https://www.example.org;params",
        "https://",
        "https://{id}.example.org",
    ],
)
def test_invalid_or_unmatched_origin_is_rejected(origin: str) -> None:
    with pytest.raises(ValueError, match="detail_origin"):
        replace(ORIGIN_PROFILE, detail_origin=origin)


@pytest.mark.parametrize(
    "template",
    [
        "/notice?id={id}",
        "https://other.example.org/notice?id={id}",
        "http://www.example.org/notice?id={id}",
        "https://user:pass@www.example.org/notice?id={id}",
        "https://www.example.org.evil.test/notice?id={id}",
    ],
)
def test_unpinned_template_cannot_use_origin(template: str) -> None:
    with pytest.raises(ValueError, match="detail_origin"):
        replace(ORIGIN_PROFILE, detail_url_template=template)


def test_origin_requires_validated_identifier_mapping() -> None:
    with pytest.raises(ValueError, match="detail_origin"):
        replace(ORIGIN_PROFILE, link_attribute="href", id_pattern="", detail_url_template="")


def test_invalid_identifier_is_not_sent_to_detail_host() -> None:
    with pytest.raises(ValueError, match="identifier"):
        parse_profiled_html(
            ORIGIN_LISTING.replace("42274", "0"),
            list_url="https://archive.example.org/list",
            profile=ORIGIN_PROFILE,
        )


@pytest.mark.parametrize("identifier", ["00000009153", "000123", "123"])
def test_zero_padded_numeric_identifier_preserves_original_width(identifier: str) -> None:
    profile = replace(HEX_PROFILE, id_format="zero_padded_numeric")
    notice = parse_hex_notice(identifier, profile)[0]
    assert notice.url == f"https://example.org/view?no={identifier}"


@pytest.mark.parametrize("identifier", ["0", "000", "-001", "１２３", "../123", "00abc123"])
def test_zero_padded_numeric_identifier_rejects_invalid_values(identifier: str) -> None:
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_hex_notice(identifier, replace(HEX_PROFILE, id_format="zero_padded_numeric"))


def test_zero_padding_is_opt_in_and_keeps_origin_validation() -> None:
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_hex_notice("0009153", replace(HEX_PROFILE, id_format="numeric"))
    with pytest.raises(ValueError, match="configured host"):
        parse_hex_notice(
            "0009153",
            replace(HEX_PROFILE, id_format="zero_padded_numeric",
                    detail_url_template="https://other.org/?no={id}"),
        )
