from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title
from judgefinder.domain.source_profiles import EngineType, HtmlProfile

PROFILE = HtmlProfile(
    container_selector="table.board", row_selector="tr", link_selector="a",
    date_selector="td.date", page_param="page",
)


def source(client: Mock, **kwargs: object) -> GenericEngineSource:
    return GenericEngineSource(
        slug="city", municipality="City", source_type=SourceType.HTML,
        list_url="https://city.go.kr/list", engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"), http_client=client,
        html_profile=PROFILE, **kwargs,  # type: ignore[arg-type]
    )


def test_new_municipality_does_not_fetch_or_relabel_migrated_archives() -> None:
    client = Mock()
    city = source(client, available_from=date(2026, 7, 1))
    assert city.fetch(date(2026, 6, 30)) == []
    client.get_text.assert_not_called()
    client.get_text.return_value = (
        '<table class="board"><tr><td>등록된 소식이 없습니다.</td></tr></table>'
    )
    assert city.fetch(date(2026, 7, 1)) == []
    client.get_text.assert_called_once()


def test_profile_page_limit_is_not_reported_as_complete_collection() -> None:
    client = Mock()
    client.get_text.return_value = (
        '<table class="board"><tr><td><a href="/view?id=1">평가위원 모집</a></td>'
        '<td class="date">2026-10-04</td></tr></table>'
    )
    with pytest.raises(ValueError, match="pagination limit.*completeness is unverified"):
        source(client, max_pages=1).fetch(date(2026, 10, 4))


def test_repeated_final_page_still_stops_and_deduplicates() -> None:
    client = Mock()
    client.get_text.return_value = (
        '<table class="board"><tr><td><a href="/view?id=1">평가위원 모집</a></td>'
        '<td class="date">2026-10-04</td></tr></table>'
    )
    notices = source(client, max_pages=2).fetch(date(2026, 10, 4))
    assert len(notices) == 1 and client.get_text.call_count == 2


def test_real_empty_news_message_is_valid_but_error_rows_are_not() -> None:
    payload = '<table class="board"><tr><td>등록된 소식이 없습니다.</td></tr></table>'
    assert parse_profiled_html(payload, list_url="https://city.go.kr/list", profile=PROFILE) == []
    for error_text in ["요청 오류: 접근 제한", "등록된 소식 조회 권한이 없습니다."]:
        with pytest.raises(ValueError, match="notice link missing"):
            parse_profiled_html(
                payload.replace("등록된 소식이 없습니다.", error_text),
                list_url="https://city.go.kr/list", profile=PROFILE,
            )


def test_explicit_result_does_not_request_broken_detail_in_recruitment_mode() -> None:
    profile = HtmlProfile(
        container_selector="table", row_selector="tr", link_selector="a",
        date_selector="td.date", detail_title_selector="h3", detail_date_selector="p.date",
    )
    payload = (
        '<table><tr><td><a href="/view?id=1">제안서 평가위원회 평가점수 공개(...</a></td>'
        '<td class="date">2025-12-11</td></tr></table>'
    )
    loader = Mock(return_value="<title>New Document</title>")
    candidates = parse_profiled_html(
        payload, list_url="https://city.go.kr/list", profile=profile,
        detail_loader=loader, recruitment_only=True,
    )
    assert len(candidates) == 1 and candidates[0].published_date == date(2025, 12, 11)
    assert classify_notice_title(candidates[0].title) is NoticeCategory.RESULT
    loader.assert_not_called()
    for title in ["평가위원 모집", "평가위원회 안내..."]:
        with pytest.raises(ValueError, match="title or registration-date element missing"):
            parse_profiled_html(
                payload.replace("제안서 평가위원회 평가점수 공개(...", title),
                list_url="https://city.go.kr/list", profile=profile,
                detail_loader=loader, recruitment_only=True,
            )
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            payload, list_url="https://city.go.kr/list", profile=profile, detail_loader=loader,
        )


def test_result_without_listing_date_still_requires_detail() -> None:
    profile = HtmlProfile(
        container_selector="table", row_selector="tr", link_selector="a",
        detail_title_selector="h3", detail_date_selector="p.date",
    )
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            '<table><tr><td><a href="/view?id=1">평가위원 평가점수 공개</a></td></tr></table>',
            list_url="https://city.go.kr/list", profile=profile,
            detail_loader=Mock(return_value="<title>New Document</title>"), recruitment_only=True,
        )


def test_out_of_window_details_are_not_required_but_older_fetch_refreshes_cache() -> None:
    profile = HtmlProfile(
        container_selector="table.board", row_selector="tr", link_selector="a",
        date_selector="td.date", detail_title_selector="h3", detail_date_selector="p.date",
        page_param="page",
    )
    payload = (
        '<table class="board"><tr><td><a href="/view?id=1">평가위원 모집...</a></td>'
        '<td class="date">2025-12-11</td></tr></table>'
    )
    client = Mock()
    client.get_text.side_effect = lambda url, **kwargs: (
        '<h3>평가위원 모집 원문</h3><p class="date">2025-12-11</p>'
        if "/view?" in url else payload
    )
    city = source(client, max_pages=2)
    city.html_profile = profile
    assert city.fetch(date(2026, 10, 4)) == []
    assert client.get_text.call_count == 1
    assert city.fetch(date(2026, 10, 3)) == []
    assert client.get_text.call_count == 1
    notices = city.fetch(date(2025, 12, 11))
    assert len(notices) == 1 and notices[0].title == "평가위원 모집 원문"
    assert client.get_text.call_count == 3


def test_recruitment_detail_missing_inside_window_is_still_an_error() -> None:
    profile = HtmlProfile(
        container_selector="table", row_selector="tr", link_selector="a",
        date_selector="td.date", detail_title_selector="h3", detail_date_selector="p.date",
    )
    payload = (
        '<table><tr><td><a href="/view?id=1">평가위원 모집...</a></td>'
        '<td class="date">2025-12-11</td></tr></table>'
    )
    loader = Mock(return_value="<title>New Document</title>")
    candidates = parse_profiled_html(
        payload, list_url="https://city.go.kr/list", profile=profile,
        detail_loader=loader, detail_not_before=date(2026, 1, 1),
    )
    assert len(candidates) == 1
    loader.assert_not_called()
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            payload, list_url="https://city.go.kr/list", profile=profile,
            detail_loader=loader, detail_not_before=date(2025, 12, 11),
        )


@pytest.mark.parametrize("value", ["true", "0", "1001", '"10"'])
def test_config_rejects_invalid_page_limits(tmp_path: Path, value: str) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'timezone="Asia/Seoul"\ndb_path="test.db"\nenabled_sources=["city"]\n'
        '[sources.city]\nmunicipality="City"\nsource_type="html"\n'
        f'list_url="https://city.go.kr/list"\nmax_pages={value}\n',
    )
    with pytest.raises(ValueError, match="max_pages"):
        load_config(config)


@pytest.mark.parametrize("value", ['"20260701"', '"2026-02-30"', "2026-07-01", "true"])
def test_config_rejects_non_iso_available_from(tmp_path: Path, value: str) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'timezone="Asia/Seoul"\ndb_path="test.db"\nenabled_sources=["city"]\n'
        '[sources.city]\nmunicipality="City"\nsource_type="html"\n'
        f'list_url="https://city.go.kr/list"\navailable_from={value}\n',
    )
    with pytest.raises(ValueError, match="available_from"):
        load_config(config)


def test_registry_passes_scope_and_page_limit_to_generic_sources() -> None:
    root = Path(__file__).parents[2]
    config = load_config(root / "config/batch-daegu-incheon-ten.example.toml")
    registry = SourceRegistry(config=config, http_client=Mock(), timezone=ZoneInfo("Asia/Seoul"))
    sources = {s.slug: s for s in registry.build_enabled_sources()}
    city = sources["yeongjong"]
    assert isinstance(city, GenericEngineSource)
    assert city.max_pages == 400 and city.available_from == date(2026, 7, 1)
