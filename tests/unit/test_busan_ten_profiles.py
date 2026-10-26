from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/busan_ten_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-busan-ten.example.toml")


@pytest.mark.parametrize("slug", CASES)
def test_real_busan_title_registration_date_and_public_detail(slug: str) -> None:
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
def test_http_200_block_or_error_is_not_valid_detail(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<h2>Web firewall security policies: blocked.</h2>"),
        )


@pytest.mark.parametrize("slug", CASES)
def test_invalid_listing_is_not_a_successful_empty_search(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h2>The request / response that are contrary to the Web firewall "
            "security policies have been blocked.</h2><table><tr><td>Detect time</td>"
            "<td>2026-10-03</td></tr></table>",
            list_url=source.list_url, profile=source.html_profile,
        )


def test_archive_routes_do_not_apply_portal_relative_date_cutoff() -> None:
    assert len(SETTINGS.enabled_sources) == 10
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 10
    for source in SETTINGS.sources.values():
        params = parse_qs(urlparse(source.list_url).query)
        assert params["list_gubun"] == ["A"]
        assert "nodate_recent_mm" not in params
        assert source.fixture_path is None
        assert source.recruitment_only and source.request_strategy.verify_tls


def test_native_post_search_and_clickable_table_cells_use_existing_profiles() -> None:
    donggu = SETTINGS.sources["busan_donggu"].html_profile
    yeongdo = SETTINGS.sources["yeongdo"].html_profile
    assert donggu is not None and donggu.request_method == "POST"
    assert yeongdo is not None and yeongdo.link_attribute == "onclick"
    assert yeongdo.link_selector == "td:nth-of-type(3)"
    assert "<a " not in CASES["yeongdo"]["list_html"]
    busanjin = SETTINGS.sources["busanjin"]
    assert parse_qs(urlparse(busanjin.list_url).query)["epcCheck"] == ["Y"]


def test_historical_full_title_does_not_include_nested_registration_paragraph() -> None:
    case = CASES["haeundae"]
    source = SETTINGS.sources["haeundae"]
    assert source.html_profile is not None
    assert "등록일" in case["detail_html"]
    actual = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert actual[0].title == case["title"] and "등록일" not in actual[0].title


@pytest.mark.parametrize("title", [
    "제안서 평가위원회 개최 일정 변경 공고",
    "제안서 평가위원회 위원별 점수 공개",
    "제안서 평가위원(후보자) 모집 취소 공고",
    "제안서 평가위원회 평가 결과 공개",
])
def test_results_cancellations_and_schedule_changes_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT
