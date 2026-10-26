from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/seoul_busan_ten_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-seoul-busan-ten.example.toml")


@pytest.mark.parametrize("slug", CASES)
def test_real_board_title_registration_date_and_public_link(slug: str) -> None:
    case = CASES[slug]
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"], list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    loader.assert_called_once_with(case["url"])
    assert classify_notice_title(actual[0].title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize("slug", CASES)
def test_detail_error_page_is_not_silently_accepted(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=Mock(return_value="<p>점검 중</p>"),
        )


def test_truncated_songpa_listing_is_enriched_before_recruitment_filtering() -> None:
    source = SETTINGS.sources["songpa"]
    profile = source.html_profile
    assert profile is not None
    case = CASES["songpa"]
    listing_only = parse_profiled_html(
        case["list_html"], list_url=source.list_url,
        profile=replace(profile, detail_title_selector="", detail_date_selector="",
                        date_selector="td:nth-of-type(5)"),
    )
    assert listing_only[0].title.endswith("...")
    assert classify_notice_title(listing_only[0].title) is not NoticeCategory.RECRUITMENT
    actual = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert "공개모집 수정 공고" in actual[0].title


def test_registration_date_is_not_announcement_period_start() -> None:
    source = SETTINGS.sources["geumcheon"]
    assert source.html_profile is not None
    case = CASES["geumcheon"]
    assert "2026-09-09 ~ 2026-09-11" in case["list_html"]
    actual = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert str(actual[0].published_date) == "2026-09-08"


@pytest.mark.parametrize("message", ["결과가 없습니다.", "결과가 없습니다"])
def test_gangnam_last_page_is_a_verified_empty_list(message: str) -> None:
    source = SETTINGS.sources["gangnam"]
    assert source.html_profile is not None
    assert parse_profiled_html(
        '<table class="table-hover"><tbody><tr><td colspan="100%">'
        f'<div class="empty-list"><div class="center">{message}</div></div>'
        '</td></tr></tbody></table>', list_url=source.list_url, profile=source.html_profile,
    ) == []


def test_unavailable_search_result_is_not_a_verified_empty_list() -> None:
    source = SETTINGS.sources["gangnam"]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="notice link missing"):
        parse_profiled_html(
            '<table class="table-hover"><tbody><tr><td>결과를 불러올 수 없습니다.</td>'
            '</tr></tbody></table>', list_url=source.list_url, profile=source.html_profile,
        )


def test_busan_http_200_deleted_notice_is_not_valid_detail() -> None:
    source = SETTINGS.sources["busan"]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            CASES["busan"]["list_html"], list_url=source.list_url, profile=source.html_profile,
            detail_loader=Mock(return_value=(
                "<html><head><title>통합 공지사항 : 부산광역시</title>"
                "<script>alert('삭제된 게시물 입니다.');location.href='/nbnews/';</script>"
                "</head></html>"
            )),
        )


def test_public_archive_form_parameters_and_javascript_link_variants() -> None:
    for slug in ("guro", "geumcheon", "dongjak", "seocho", "songpa", "gangdong"):
        source = SETTINGS.sources[slug]
        assert parse_qs(urlparse(source.list_url).query)["list_gubun"] == ["A"]
        assert source.fixture_path is None
    gangdong = SETTINGS.sources["gangdong"]
    assert parse_qs(urlparse(gangdong.list_url).query)["epcCheck"] == ["Y"]
    assert gangdong.html_profile is not None
    assert gangdong.html_profile.link_attribute == "href"
    soup = BeautifulSoup(CASES["gangdong"]["list_html"], "html5lib")
    anchor = soup.select_one("td.title a")
    assert anchor is not None and anchor["href"] == "javascript:searchDetail(58540)"


@pytest.mark.parametrize("title", [
    "제안서 평가위원회 평가결과 공개",
    "제안서 평가위원(후보자) 모집 취소 공고",
    "제안서 평가위원회 구성 결과 알림",
])
def test_non_recruitment_notices_remain_excluded(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT
