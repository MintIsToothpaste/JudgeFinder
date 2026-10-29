from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title
from judgefinder.domain.source_profiles import EngineType, HtmlProfile, JsonProfile


def epoch_profile() -> JsonProfile:
    return JsonProfile(
        rows_path="data", title_key="subject", date_key="startDate", id_key="articleId",
        detail_url_template="/board/notice/article/{id}", total_path="recordsFiltered",
        page_path="draw", page_param="draw", page_size=15, offset_param="start", offset_base=0,
        date_format="unix_ms", date_timezone="Asia/Seoul", date_fallback_key="regDatetime",
    )


def document(start: object, registered: object = 1790841687000) -> str:
    return json.dumps({"draw": 1, "recordsFiltered": 1, "data": [{
        "articleId": 285467, "subject": "위촉직 평가위원 공모 안내",
        "startDate": start, "regDatetime": registered,
    }]})


def test_unix_milliseconds_follow_the_configured_publication_timezone() -> None:
    timestamp = int(datetime(2026, 9, 30, 23, 30, tzinfo=ZoneInfo("UTC")).timestamp() * 1000)
    profile = epoch_profile()
    for primary in (None, timestamp):
        row = parse_profiled_json(
            document(primary, timestamp), list_url="https://example.test/api", profile=profile,
        )[0]
        assert row.published_date == date(2026, 10, 1)
    row = parse_profiled_json(
        document(timestamp), list_url="https://example.test/api",
        profile=replace(profile, date_timezone="UTC"),
    )[0]
    assert row.published_date == date(2026, 9, 30)


def test_publication_date_takes_precedence_over_registration_timestamp() -> None:
    published = int(datetime(2026, 10, 3, tzinfo=ZoneInfo("Asia/Seoul")).timestamp() * 1000)
    row = parse_profiled_json(
        document(published), list_url="https://example.test/api", profile=epoch_profile(),
    )[0]
    assert row.published_date == date(2026, 10, 3)


@pytest.mark.parametrize("value", [True, -1, 1.5, "1790841687000", "2026-10-01", 10**30])
def test_invalid_primary_date_never_falls_back_to_a_valid_other_date(value: object) -> None:
    with pytest.raises(ValueError, match="date"):
        parse_profiled_json(
            document(value), list_url="https://example.test/api", profile=epoch_profile(),
        )


def test_missing_primary_key_or_unconfigured_fallback_is_an_error() -> None:
    data = json.loads(document(None))
    del data["data"][0]["startDate"]
    for profile, payload in (
        (epoch_profile(), json.dumps(data)),
        (replace(epoch_profile(), date_fallback_key=""), document(None)),
        (epoch_profile(), document(None, None)),
    ):
        with pytest.raises(ValueError, match="date"):
            parse_profiled_json(payload, list_url="https://example.test/api", profile=profile)


@pytest.mark.parametrize("changes", [
    {"date_format": "auto"}, {"date_timezone": "Not/A_Zone"},
    {"date_fallback_key": "startDate"},
])
def test_invalid_explicit_date_options_fail_at_configuration(changes: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        replace(
            epoch_profile(), date_format=changes.get("date_format", "unix_ms"),
            date_timezone=changes.get("date_timezone", "Asia/Seoul"),
            date_fallback_key=changes.get("date_fallback_key", "regDatetime"),
        )


def test_text_json_dates_still_require_strings_without_timestamp_guessing() -> None:
    with pytest.raises(ValueError, match="date"):
        parse_profiled_json(
            document(None), list_url="https://example.test/api",
            profile=replace(epoch_profile(), date_format="text"),
        )


def test_offset_only_html_fetches_the_second_page_and_validates_it() -> None:
    profile = HtmlProfile(
        container_selector="table", row_selector="tbody tr", date_selector="td.date",
        page_param="", offset_param="per_page", page_size=15,
        page_number_selector="a.current", search_param="query",
    )
    client = Mock()
    offsets: list[str] = []

    def get_text(url: str, **_: object) -> str:
        query = parse_qs(urlparse(url).query)
        assert "pageIndex" not in query and "page" not in query
        assert query["query"] == ["평가위원"]
        offset = query["per_page"][0]
        offsets.append(offset)
        if offset == "30":
            return "<table><tbody><tr><td>게시물이 없습니다.</td></tr></tbody></table>"
        page = 1 if offset == "0" else 2
        return (f'<a class="current">{page}</a><table><tbody><tr><td>'
                f'<a href="/view/{page}">평가위원 모집 {page}</a></td>'
                '<td class="date">2026-10-14</td></tr></tbody></table>')

    client.get_text.side_effect = get_text
    source = GenericEngineSource(
        slug="example", municipality="example", source_type=SourceType.HTML,
        list_url="https://example.test/list", timezone=ZoneInfo("Asia/Seoul"),
        http_client=client, engine_type=EngineType.GENERIC_EGOV_BBS, html_profile=profile,
    )
    assert len(source.fetch(date(2026, 10, 14))) == 2
    assert offsets == ["0", "15", "30"]
    source.page_cache[2] = source.page_cache[1]
    source.profile_candidate_cache.clear()
    with pytest.raises(ValueError, match="page does not match"):
        source.fetch(date(2026, 10, 14))


@pytest.mark.parametrize("title", [
    "위촉직 평가위원 공모 안내", "공공기관 안전활동 수준평가 평가위원 공모 알림",
    "제안서 평가위원(후보자) 공모 공고", "평가위원 후보자 공모",
])
def test_explicit_evaluator_open_calls_are_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize("title", [
    "평가위원 공모 취소", "평가위원 공모 결과 공고", "평가위원 공모 명단 안내",
    "평가위원 공모 마감", "평가위원 공모 현황", "작품 공모 평가위원 안내",
])
def test_open_call_results_and_unrelated_contests_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT


@pytest.mark.parametrize("title", [
    "[~10/12] 서울특별시 제안서 평가위원(후보자) 등록 안내",
    "제안서 평가위원 후보자 등록 공고", "제안서 평가위원 등록 안내",
])
def test_explicit_evaluator_registration_does_not_require_the_word_application(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize("title", [
    "평가위원 등록 안내 취소", "평가위원 등록 현황 공개", "평가위원 등록 결과 안내",
    "평가위원 등록 시스템 구축 공고", "사업자 등록 안내",
])
def test_registration_status_and_system_procurement_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT
