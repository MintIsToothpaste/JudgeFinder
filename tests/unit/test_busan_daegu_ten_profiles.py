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
CASES = json.loads((ROOT / "tests/fixtures/busan_daegu_ten_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-busan-daegu-ten.example.toml")


@pytest.mark.parametrize("slug", CASES)
def test_real_title_registration_date_and_official_detail(slug: str) -> None:
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
def test_http_200_error_document_is_not_a_valid_detail(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<h2>Web firewall security policies: blocked.</h2>"),
        )


@pytest.mark.parametrize("slug", CASES)
def test_invalid_listing_does_not_become_a_successful_empty_result(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h2>Service unavailable</h2><table><tr><td>2026-10-03</td></tr></table>",
            list_url=source.list_url, profile=source.html_profile,
        )


def test_archive_profiles_do_not_keep_relative_dates_or_fixed_2018_year() -> None:
    assert len(SETTINGS.enabled_sources) == len(CASES) == 10
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 10
    for source in SETTINGS.sources.values():
        query = parse_qs(urlparse(source.list_url).query, keep_blank_values=True)
        assert "yyyy" not in query and "recent_mm" not in query
        assert source.fixture_path is None
        assert source.recruitment_only and source.request_strategy.verify_tls
        if source.slug not in {"yeonje", "daegu", "daegu_seogu"}:
            assert query["list_gubun"] == ["A"]
    assert parse_qs(
        urlparse(SETTINGS.sources["daegu_seogu"].list_url).query, keep_blank_values=True,
    )["endYn"] == [""]
    assert parse_qs(urlparse(SETTINGS.sources["daegu"].list_url).query)["searchGosi_gbn"] == ["A"]


def test_data_action_profiles_preserve_menu_context_and_notice_identifier() -> None:
    for slug, menu_key, menu_id in [
        ("yeonje", "mId", "0206030000"), ("daegu_seogu", "mid", "0601020100"),
    ]:
        profile = SETTINGS.sources[slug].html_profile
        assert profile is not None and profile.link_attribute == "data-action"
        assert not profile.id_pattern
        query = parse_qs(urlparse(CASES[slug]["url"]).query)
        assert query[menu_key] == [menu_id] and int(query["notAncmtMgtNo"][0]) > 0


def test_suyeong_creation_date_and_full_detail_title_are_used() -> None:
    profile = SETTINGS.sources["suyeong"].html_profile
    assert profile is not None
    assert "작성일" in profile.detail_date_selector
    assert "..." in CASES["suyeong"]["list_html"]
    assert "..." not in CASES["suyeong"]["title"]


def test_clickable_donggu_table_cell_and_daegu_form_are_declarative() -> None:
    profile = SETTINGS.sources["daegu_donggu"].html_profile
    assert profile is not None and profile.link_selector == "td:nth-of-type(3)"
    assert profile.link_attribute == "onclick" and "<a " not in CASES["daegu_donggu"]["list_html"]
    query = parse_qs(urlparse(CASES["daegu"]["url"]).query)
    assert query["gosi_gbn"] == ["A"]
    assert query["menu_link"] == ["/front/daeguSidoGosi/daeguSidoGosiView.do"]
