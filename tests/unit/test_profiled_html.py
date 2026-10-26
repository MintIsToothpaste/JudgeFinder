from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
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
    container_selector="table", row_selector="tbody tr", date_selector="td.date",
)
HTML = (
    '<table><tbody><tr><td><a href="/view?id=123">2025-01-01 평가<span>위원</span>'
    ' 모집</a></td><td class="date">2026-09-21</td>'
    '<td>모집기간 2026-09-22 ~ 2026-09-30</td></tr></tbody></table>'
)


@pytest.mark.parametrize(("slug", "published", "identifier"), CASES)
def test_official_board_profiles(slug: str, published: str, identifier: str) -> None:
    source = load_config(ROOT / "config/batch-seoul-five.example.toml").sources[slug]
    assert source.html_profile is not None
    candidates = parse_profiled_html(
        (ROOT / f"tests/fixtures/{slug}_profile_list.html").read_text(encoding="utf-8"),
        list_url=source.list_url, profile=source.html_profile,
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


@pytest.mark.parametrize("html", [
    "<html>접속 차단</html>",
    HTML.replace('class="date"', 'class="changed"'),
    HTML.replace("2026-09-21", "2026-02-30"),
    HTML.replace("/view?id=123", "javascript:unexpected(123)"),
    HTML.replace("/view?id=123", "https://other.example/view?id=123"),
    HTML.replace("/view?id=123", "http://example.org/view?id=123"),
    HTML.replace("/view?id=123", "/list"),
    HTML.replace('<a href="/view?id=123">', '<span>').replace("</a>", "</span>"),
])
def test_malformed_page_is_not_silently_treated_as_no_results(html: str) -> None:
    with pytest.raises(ValueError):
        parse_profiled_html(html, list_url="https://example.org/list", profile=PROFILE)


@pytest.mark.parametrize("body", ["", '<tr><td colspan="3">등록된 게시물이 없습니다.</td></tr>'])
def test_real_empty_table_is_supported(body: str) -> None:
    assert parse_profiled_html(
        f"<table><tbody>{body}</tbody></table>",
        list_url="https://example.org/list", profile=PROFILE,
    ) == []


@pytest.mark.parametrize("identifier", ["0", "-1", "1/../../bad", "１２３", "abc"])
def test_invalid_identifier_is_rejected(identifier: str) -> None:
    profile = replace(PROFILE, id_pattern=r"id=(.*)$", detail_url_template="/view?id={id}")
    with pytest.raises(ValueError, match="identifier"):
        parse_profiled_html(
            HTML.replace("id=123", f"id={identifier}"),
            list_url="https://example.org/list", profile=profile,
        )


def test_canonical_identity_does_not_depend_on_search_or_page() -> None:
    profile = replace(
        PROFILE, id_pattern=r"id=([1-9][0-9]*)(?:&|$)",
        detail_url_template="/view?id={id}",
    )
    first = parse_profiled_html(HTML, list_url="https://example.org/list", profile=profile)
    second = parse_profiled_html(
        HTML.replace("id=123", "id=123&amp;page=5&amp;search=changed"),
        list_url="https://example.org/list", profile=profile,
    )
    assert first == second


@pytest.mark.parametrize("separator", ["&", "&amp;"])
def test_html5_query_attributes_are_not_decoded_as_partial_entities(separator: str) -> None:
    profile = replace(
        PROFILE, id_pattern=r"[?&]notAncmtMgtNo=([1-9][0-9]*)(?:&|$)",
        detail_url_template="/view?key=294&notAncmtMgtNo={id}",
    )
    html = HTML.replace("/view?id=123", f"/view?key=294{separator}notAncmtMgtNo=28421")
    result = parse_profiled_html(html, list_url="https://example.org/list", profile=profile)
    assert result[0].url == "https://example.org/view?key=294&notAncmtMgtNo=28421"


def test_html5_preserves_real_title_entities() -> None:
    result = parse_profiled_html(
        HTML.replace("2025-01-01", "A &amp; B &quot;공고&quot;"),
        list_url="https://example.org/list", profile=PROFILE,
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


@pytest.mark.parametrize("action", [
    "https://other.example/view?id=123", "http://example.org/view?id=123",
    "javascript:alert(123)", "/list", "https://user:password@example.org/view?id=123",
])
def test_data_action_retains_detail_origin_validation(action: str) -> None:
    profile = replace(PROFILE, link_attribute="data-action")
    html = HTML.replace('<a href="/view?id=123">', f'<a href="#" data-action="{action}">')
    with pytest.raises(ValueError):
        parse_profiled_html(html, list_url="https://example.org/list", profile=profile)


def test_missing_data_action_does_not_fall_back_to_placeholder_href() -> None:
    with pytest.raises(ValueError, match="data-action missing"):
        parse_profiled_html(
            HTML, list_url="https://example.org/list",
            profile=replace(PROFILE, link_attribute="data-action"),
        )


@pytest.mark.parametrize("title", [
    "제5차 교통안전기본계획 용역 제안서 평가위원회 결과 공고",
    "제안서평가위원회 기술제안평가(정성적 평가) 결과 홈페이지 공개",
    "제안서평가위원회 평가결과 공개",
])
def test_result_notices_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RESULT


def test_repeated_last_page_stops_and_parsed_pages_are_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.get_text.return_value = HTML
    parser = Mock(wraps=parse_profiled_html)
    monkeypatch.setattr(
        "judgefinder.adapters.sources.generic_engine.source.parse_profiled_html", parser,
    )
    source = GenericEngineSource(
        slug="demo", municipality="demo", source_type=SourceType.HTML,
        list_url="https://example.org/list", engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"), http_client=client, html_profile=PROFILE,
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
        slug="demo", municipality="demo", source_type=SourceType.HTML,
        list_url="https://example.org/list", engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"), http_client=client,
        html_profile=replace(PROFILE, page_param="", search_param=""),
    )
    assert len(source.fetch(date(2026, 9, 21))) == 1
    assert client.get_text.call_count == 1
    assert client.get_text.call_args.args[0] == "https://example.org/list"
