from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import (
    _title_text,
    parse_profiled_html,
)
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title
from judgefinder.domain.source_profiles import EngineType, HtmlProfile

ROOT = Path(__file__).parents[2]


CASES = [
    ("seoul", "2026-08-05", "463352"),
    ("jongno", "2026-09-21", "255848"),
    ("seoul_junggu", "2026-04-08", "1440139692"),
    ("yongsan", "2026-07-22", "766379"),
    ("seongdong", "2026-09-22", "361639"),
]


PROFILE = HtmlProfile(
    container_selector="table",
    row_selector="tbody tr",
    date_selector="td.date",
)


HTML = (
    '<table><tbody><tr><td><a href="/view?id=123">2025-01-01 평가<span>위원</span>'
    ' 모집</a></td><td class="date">2026-09-21</td>'
    "<td>모집기간 2026-09-22 ~ 2026-09-30</td></tr></tbody></table>"
)


@pytest.mark.parametrize(("slug", "published", "identifier"), CASES)
def test_official_board_profiles(slug: str, published: str, identifier: str) -> None:
    source = load_config(ROOT / "config/batch-seoul-five.example.toml").sources[slug]
    assert source.html_profile is not None
    candidates = parse_profiled_html(
        (ROOT / f"tests/fixtures/{slug}_profile_list.html").read_text(encoding="utf-8"),
        list_url=source.list_url,
        profile=source.html_profile,
    )
    notice = next(item for item in candidates if identifier in item.url)
    assert notice.published_date == date.fromisoformat(published)
    assert classify_notice_title(notice.title) is NoticeCategory.RECRUITMENT
    assert "pageIndex" not in notice.url
    assert "search" not in notice.url


def test_only_registration_column_is_used_and_inline_words_are_preserved() -> None:
    notice = parse_profiled_html(HTML, list_url="https://example.org/list", profile=PROFILE)[0]
    assert notice.title == "2025-01-01 평가위원 모집"
    assert notice.published_date == date(2026, 9, 21)
    assert notice.url == "https://example.org/view?id=123"


@pytest.mark.parametrize(
    "html",
    [
        "<html>접속 차단</html>",
        HTML.replace('class="date"', 'class="changed"'),
        HTML.replace("2026-09-21", "2026-02-30"),
        HTML.replace("/view?id=123", "javascript:unexpected(123)"),
        HTML.replace("/view?id=123", "https://other.example/view?id=123"),
        HTML.replace("/view?id=123", "http://example.org/view?id=123"),
        HTML.replace("/view?id=123", "/list"),
        HTML.replace('<a href="/view?id=123">', "<span>").replace("</a>", "</span>"),
    ],
)
def test_malformed_page_is_not_silently_treated_as_no_results(html: str) -> None:
    with pytest.raises(ValueError):
        parse_profiled_html(html, list_url="https://example.org/list", profile=PROFILE)


@pytest.mark.parametrize("body", ["", '<tr><td colspan="3">등록된 게시물이 없습니다.</td></tr>'])
def test_real_empty_table_is_supported(body: str) -> None:
    assert (
        parse_profiled_html(
            f"<table><tbody>{body}</tbody></table>",
            list_url="https://example.org/list",
            profile=PROFILE,
        )
        == []
    )


@pytest.mark.parametrize("identifier", ["0", "-1", "1/../../bad", "１２３", "abc"])
def test_invalid_identifier_is_rejected(identifier: str) -> None:
    profile = replace(PROFILE, id_pattern=r"id=(.*)$", detail_url_template="/view?id={id}")
    with pytest.raises(ValueError, match="identifier"):
        parse_profiled_html(
            HTML.replace("id=123", f"id={identifier}"),
            list_url="https://example.org/list",
            profile=profile,
        )


def test_canonical_identity_does_not_depend_on_search_or_page() -> None:
    profile = replace(
        PROFILE,
        id_pattern=r"id=([1-9][0-9]*)(?:&|$)",
        detail_url_template="/view?id={id}",
    )
    first = parse_profiled_html(HTML, list_url="https://example.org/list", profile=profile)
    second = parse_profiled_html(
        HTML.replace("id=123", "id=123&amp;page=5&amp;search=changed"),
        list_url="https://example.org/list",
        profile=profile,
    )
    assert first == second


@pytest.mark.parametrize("separator", ["&", "&amp;"])
def test_html5_query_attributes_are_not_decoded_as_partial_entities(separator: str) -> None:
    profile = replace(
        PROFILE,
        id_pattern=r"[?&]notAncmtMgtNo=([1-9][0-9]*)(?:&|$)",
        detail_url_template="/view?key=294&notAncmtMgtNo={id}",
    )
    html = HTML.replace("/view?id=123", f"/view?key=294{separator}notAncmtMgtNo=28421")
    result = parse_profiled_html(html, list_url="https://example.org/list", profile=profile)
    assert result[0].url == "https://example.org/view?key=294&notAncmtMgtNo=28421"


def test_html5_preserves_real_title_entities() -> None:
    result = parse_profiled_html(
        HTML.replace("2025-01-01", "A &amp; B &quot;공고&quot;"),
        list_url="https://example.org/list",
        profile=PROFILE,
    )
    assert result[0].title == 'A & B "공고" 평가위원 모집'


def test_declarative_data_action_link_does_not_execute_javascript() -> None:
    profile = replace(PROFILE, link_attribute="data-action")
    html = HTML.replace(
        '<a href="/view?id=123">',
        '<a href="#" data-action="/view?id=123" onclick="req.post(this)">',
    )
    result = parse_profiled_html(html, list_url="https://example.org/list", profile=profile)
    assert result[0].url == "https://example.org/view?id=123"
    assert result[0].published_date == date(2026, 9, 21)


@pytest.mark.parametrize(
    "action",
    [
        "https://other.example/view?id=123",
        "http://example.org/view?id=123",
        "javascript:alert(123)",
        "/list",
        "https://user:password@example.org/view?id=123",
    ],
)
def test_data_action_retains_detail_origin_validation(action: str) -> None:
    profile = replace(PROFILE, link_attribute="data-action")
    html = HTML.replace('<a href="/view?id=123">', f'<a href="#" data-action="{action}">')
    with pytest.raises(ValueError):
        parse_profiled_html(html, list_url="https://example.org/list", profile=profile)


def test_missing_data_action_does_not_fall_back_to_placeholder_href() -> None:
    with pytest.raises(ValueError, match="data-action missing"):
        parse_profiled_html(
            HTML,
            list_url="https://example.org/list",
            profile=replace(PROFILE, link_attribute="data-action"),
        )


@pytest.mark.parametrize(
    "title",
    [
        "제5차 교통안전기본계획 용역 제안서 평가위원회 결과 공고",
        "제안서평가위원회 기술제안평가(정성적 평가) 결과 홈페이지 공개",
        "제안서평가위원회 평가결과 공개",
    ],
)
def test_result_notices_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RESULT


def test_repeated_last_page_stops_and_parsed_pages_are_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.get_text.return_value = HTML
    parser = Mock(wraps=parse_profiled_html)
    monkeypatch.setattr(
        "judgefinder.adapters.sources.generic_engine.source.parse_profiled_html",
        parser,
    )
    source = GenericEngineSource(
        slug="demo",
        municipality="demo",
        source_type=SourceType.HTML,
        list_url="https://example.org/list",
        engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=client,
        html_profile=PROFILE,
    )
    assert len(source.fetch(date(2026, 9, 21))) == 1
    assert source.fetch(date(2026, 9, 20)) == []
    assert len(source.fetch(date(2026, 9, 21))) == 1
    assert client.get_text.call_count == 2
    assert parser.call_count == 2


def test_profile_can_disable_pagination_and_search_parameters() -> None:
    client = Mock()
    client.get_text.return_value = HTML
    source = GenericEngineSource(
        slug="demo",
        municipality="demo",
        source_type=SourceType.HTML,
        list_url="https://example.org/list",
        engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=client,
        html_profile=replace(PROFILE, page_param="", search_param=""),
    )
    assert len(source.fetch(date(2026, 9, 21))) == 1
    assert client.get_text.call_count == 1
    assert client.get_text.call_args.args[0] == "https://example.org/list"


TITLE_PROFILE = HtmlProfile(
    container_selector="table",
    row_selector="tbody tr",
    date_selector="td.date",
    id_pattern=r"id=([1-9][0-9]*)(?:&|$)",
    detail_url_template="/view?id={id}",
)


TITLE_LISTING = (
    '<table><tbody><tr><td><a href="/view?id=123">평가위원 모집'
    '<span class="badge">결과</span></a></td>'
    '<td class="date">2026-09-21</td></tr></tbody></table>'
)


def test_title_badge_exclusion_is_opt_in_and_does_not_mutate_the_node() -> None:
    soup = BeautifulSoup(
        '<h1><span class="badge">고시공고</span>평가<b>위원</b> 모집</h1>', "html.parser"
    )
    node = soup.find("h1")
    assert node is not None
    assert _title_text(node, ".badge") == "평가위원 모집"
    assert _title_text(node, "") == "고시공고평가위원 모집"
    assert node.find("span", class_="badge") is not None


def test_default_title_extraction_preserves_existing_behavior() -> None:
    notice = parse_profiled_html(
        TITLE_LISTING, list_url="https://example.org/list", profile=TITLE_PROFILE
    )[0]
    assert notice.title == "평가위원 모집결과"


def test_excluded_listing_badge_cannot_make_recruitment_skip_its_detail() -> None:
    profile = replace(
        TITLE_PROFILE,
        title_exclude_selector=".badge",
        detail_title_selector="h1",
        detail_date_selector="time",
    )
    loader = Mock(
        return_value=(
            '<h1><span class="badge">고시공고</span>평가위원 모집</h1><time>2026-09-21</time>'
        )
    )
    notices = parse_profiled_html(
        TITLE_LISTING,
        list_url="https://example.org/list",
        profile=profile,
        detail_loader=loader,
        recruitment_only=True,
    )
    assert notices[0].title == "평가위원 모집"
    loader.assert_called_once_with("https://example.org/view?id=123")


def test_only_out_of_window_unsupported_identifier_is_skipped() -> None:
    old = TITLE_LISTING.replace("id=123", "id=01_8723").replace("2026-09-21", "2015-12-29")
    mixed = old.replace("</tbody>", TITLE_LISTING.split("<tbody>")[1])
    actual = parse_profiled_html(
        mixed,
        list_url="https://example.org/list",
        profile=TITLE_PROFILE,
        detail_not_before=date(2025, 10, 5),
    )
    assert len(actual) == 1 and actual[0].url == "https://example.org/view?id=123"


@pytest.mark.parametrize("published", ["2025-10-05", "2026-09-21", "2026-12-01", "invalid"])
def test_current_or_undated_unsupported_identifier_still_fails(published: str) -> None:
    payload = TITLE_LISTING.replace("id=123", "id=01_8723").replace("2026-09-21", published)
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_profiled_html(
            payload,
            list_url="https://example.org/list",
            profile=TITLE_PROFILE,
            detail_not_before=date(2025, 10, 5),
        )


def test_without_date_boundary_legacy_identifier_is_not_silently_ignored() -> None:
    payload = TITLE_LISTING.replace("id=123", "id=01_8723").replace("2026-09-21", "2015-12-29")
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_profiled_html(payload, list_url="https://example.org/list", profile=TITLE_PROFILE)


EMPTY_PROFILE = HtmlProfile(
    container_selector="table",
    row_selector="tr",
    link_selector="a",
    date_selector="td.date",
)


def test_mokpo_empty_search_row_is_not_a_broken_notice() -> None:
    assert (
        parse_profiled_html(
            '<table><tr><td colspan="6">검색내역이 없습니다.</td></tr></table>',
            list_url="https://www.mokpo.go.kr/",
            profile=EMPTY_PROFILE,
        )
        == []
    )


@pytest.mark.parametrize(
    "message",
    [
        "검색내역이 없습니다만 서비스 오류가 발생했습니다.",
        "검색내역이 조회되지 않습니다.",
        "검색내역이 조회 권한이 없습니다.",
    ],
)
def test_search_failure_is_not_accepted_as_an_empty_search(message: str) -> None:
    with pytest.raises(ValueError, match="notice link missing"):
        parse_profiled_html(
            f"<table><tr><td>{message}</td></tr></table>",
            list_url="https://www.mokpo.go.kr/",
            profile=EMPTY_PROFILE,
        )


@pytest.mark.parametrize("text,expected", [
    ("26.10.21", date(2026, 10, 21)),
    ("00.2.29", date(2000, 2, 29)),
    ("24-02-29", date(2024, 2, 29)),
    ("99/12/31", date(2099, 12, 31)),
])
def test_two_digit_registration_year_requires_explicit_century(text: str, expected: date) -> None:
    listing = HTML.replace("2026-09-21", text)
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(listing, list_url="https://example.org/list", profile=PROFILE)
    actual = parse_profiled_html(
        listing, list_url="https://example.org/list",
        profile=replace(PROFILE, two_digit_year_base=2000),
    )
    assert actual[0].published_date == expected


@pytest.mark.parametrize("text", [
    "26.02.30", "25.02.29", "26.13.01", "26.00.21", "26.10.21junk", "10:21:26",
    "26.10.21 ~ 26.10.22",
])
def test_two_digit_registration_date_rejects_invalid_or_ambiguous_values(text: str) -> None:
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            HTML.replace("2026-09-21", text), list_url="https://example.org/list",
            profile=replace(PROFILE, two_digit_year_base=2000),
        )


@pytest.mark.parametrize("base", [True, "2000", 0, 1901, 2026])
def test_registration_century_rejects_invalid_configuration(base: object) -> None:
    with pytest.raises(ValueError, match="two_digit_year_base"):
        replace(PROFILE, two_digit_year_base=base)


def test_explicit_century_applies_before_the_detail_date_boundary() -> None:
    loader = Mock()
    profile = replace(
        PROFILE, two_digit_year_base=1900, detail_date_selector="time",
    )
    actual = parse_profiled_html(
        HTML.replace("2026-09-21", "26.10.21"), list_url="https://example.org/list",
        profile=profile, detail_loader=loader, detail_not_before=date(2000, 1, 1),
    )
    assert actual[0].published_date == date(1926, 10, 21)
    loader.assert_not_called()


@pytest.mark.parametrize("attribute", ["title", "datetime", "data-registered-at"])
def test_absolute_registration_attribute_overrides_relative_display(attribute: str) -> None:
    profile = replace(PROFILE, listing_date_attribute=attribute)
    html = HTML.replace(
        '<td class="date">2026-09-21</td>',
        f'<td class="date" {attribute}="2026-10-26 20:07">2일 전</td>',
    )
    loader = Mock()
    notice = parse_profiled_html(
        html, list_url="https://example.org/list", profile=profile, detail_loader=loader,
    )[0]
    assert notice.published_date == date(2026, 10, 26)
    loader.assert_not_called()


@pytest.mark.parametrize("value", ["", "invalid", "2026-02-30", "2일 전"])
def test_invalid_registration_attribute_does_not_fall_back_to_other_dates(value: str) -> None:
    html = HTML.replace('class="date"', f'class="date" title="{value}"')
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            html, list_url="https://example.org/list",
            profile=replace(PROFILE, listing_date_attribute="title"),
        )


def test_absolute_registration_attribute_supports_recent_detail_cutoff() -> None:
    html = HTML.replace(
        '<td class="date">2026-09-21</td>',
        '<td class="date" title="2026-10-20 20:07">9일 전</td>',
    )
    loader = Mock(side_effect=AssertionError("Old detail must not be requested"))
    candidate = parse_profiled_html(
        html, list_url="https://example.org/list",
        profile=replace(PROFILE, listing_date_attribute="title", detail_title_selector="h1"),
        detail_loader=loader, detail_not_before=date(2026, 10, 23),
    )[0]
    assert candidate.published_date == date(2026, 10, 20)
    loader.assert_not_called()


@pytest.mark.parametrize("attribute", ["href", "onclick", "data-", "Title", "data-등록일"])
def test_registration_attribute_requires_explicit_metadata_name(attribute: str) -> None:
    with pytest.raises(ValueError, match="listing_date_attribute"):
        replace(PROFILE, listing_date_attribute=attribute)


def test_registration_attribute_requires_listing_selector() -> None:
    with pytest.raises(ValueError, match="listing_date_attribute"):
        replace(
            PROFILE, date_selector="", detail_date_selector="time", listing_date_attribute="title",
        )


def test_missing_registration_attribute_does_not_use_display_date() -> None:
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            HTML, list_url="https://example.org/list",
            profile=replace(PROFILE, listing_date_attribute="title"),
        )


@pytest.mark.parametrize("attribute", ["content", "datetime", "title", "data-published-at"])
def test_detail_registration_attribute_uses_explicit_year(attribute: str) -> None:
    profile = replace(
        PROFILE, date_selector="", detail_title_selector="h1",
        detail_date_selector='[itemprop="datePublished"]', detail_date_attribute=attribute,
    )
    detail = (
        '<h1>2027년 평가위원 모집</h1>'
        f'<span itemprop="datePublished" {attribute}="2026-10-28KST15:09:11">10.28</span>'
        '<p>접수마감: 2026-11-03</p>'
    )
    candidate = parse_profiled_html(
        HTML, list_url="https://example.org/list", profile=profile,
        detail_loader=Mock(return_value=detail),
    )[0]
    assert candidate.published_date == date(2026, 10, 28)
    assert candidate.title == "2027년 평가위원 모집"


@pytest.mark.parametrize("value", [None, "", "invalid", "2026-02-30", "10.28"])
def test_detail_registration_attribute_does_not_guess_from_display_or_deadline(
    value: str | None,
) -> None:
    attribute = "" if value is None else f'content="{value}"'
    detail = (
        f'<span itemprop="datePublished" {attribute}>2026-10-28</span>'
        '<p>접수기간: 2026-10-28 ~ 2026-11-03</p>'
    )
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            HTML, list_url="https://example.org/list",
            profile=replace(
                PROFILE, detail_date_selector='[itemprop="datePublished"]',
                detail_date_attribute="content",
            ),
            detail_loader=Mock(return_value=detail),
        )


@pytest.mark.parametrize("attribute", ["href", "onclick", "data-", "Content", "data-등록일"])
def test_detail_registration_attribute_rejects_unsupported_names(attribute: str) -> None:
    with pytest.raises(ValueError, match="detail_date_attribute"):
        replace(PROFILE, detail_date_selector="time", detail_date_attribute=attribute)


def test_detail_registration_attribute_requires_detail_selector() -> None:
    with pytest.raises(ValueError, match="detail_date_attribute"):
        replace(PROFILE, detail_date_attribute="content")
