from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup, Comment

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/jeonnam_counties_ten_profiles.json").read_text())
NOMINATION = json.loads((ROOT / "tests/fixtures/gangjin_nomination_profile.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-jeonnam-counties-ten.example.toml")
DETAIL_SLUGS = [slug for slug, case in CASES.items() if "detail_html" in case]
TD_SLUGS = ["gokseong", "goheung", "yeongam", "muan"]


@pytest.mark.parametrize("slug", CASES)
def test_actual_full_title_date_url_or_explicit_empty_listing(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case.get("detail_html", ""))
    actual = parse_profiled_html(
        case.get("list_html", case.get("empty_list_html")), list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader, expected_page=1,
        recruitment_only=case.get("listing_only", False),
    )
    if "empty_list_html" in case:
        assert actual == []
        loader.assert_not_called()
    else:
        assert [(n.title, str(n.published_date), n.url) for n in actual] == [
            (case["title"], case["date"], case["url"]),
        ]
        if case.get("listing_only"):
            loader.assert_not_called()
            assert case["category"] == "result"
        else:
            loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", DETAIL_SLUGS)
def test_error_document_is_not_an_authoritative_detail(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            CASES[slug]["list_html"], list_url=source.list_url, profile=source.html_profile,
            detail_loader=Mock(return_value="<h1>Service error</h1>"),
        )


@pytest.mark.parametrize("slug", CASES)
def test_missing_listing_is_not_a_successful_zero_result(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing (container missing|page does not match)"):
        parse_profiled_html(
            "<h1>FORBIDDEN</h1>", list_url=source.list_url, profile=source.html_profile,
            expected_page=1,
        )


@pytest.mark.parametrize("slug", TD_SLUGS)
def test_legacy_td_links_and_td_headers_need_no_anchor_or_javascript(slug: str) -> None:
    profile = SETTINGS.sources[slug].html_profile
    assert profile is not None
    soup = BeautifulSoup(CASES[slug]["list_html"], "html5lib")
    link = soup.select_one(profile.link_selector)
    assert link is not None and link.name == "td" and not link.find("a")
    assert not soup.find("th")
    header = soup.select_one("tbody > tr")
    assert header is not None and "등록일" in header.get_text() and "제목" in header.get_text()


@pytest.mark.parametrize("slug", TD_SLUGS)
def test_non_numeric_legacy_identifier_cannot_be_executed(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    soup = BeautifulSoup(CASES[slug]["list_html"], "html5lib")
    link = soup.select_one(source.html_profile.link_selector)
    assert link is not None
    link["onclick"] = "searchDetail('not-a-number');alert('unexpected')"
    loader = Mock()
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_profiled_html(str(soup), list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader)
    loader.assert_not_called()


@pytest.mark.parametrize("slug", ["gurye", "haenam"])
def test_wrong_current_page_is_rejected_before_fetching_details(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None and source.html_profile.page_number_selector
    loader = Mock()
    with pytest.raises(ValueError, match="HTML listing page does not match requested page"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader, expected_page=2)
    loader.assert_not_called()


def test_official_archive_and_search_parameters_cover_ten_municipalities() -> None:
    assert len(CASES) == len(SETTINGS.enabled_sources) == 12
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 10
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.source_type == "html" and source.html_profile is not None
        assert source.request_strategy.verify_tls and source.max_pages == 40
    for slug in [*TD_SLUGS, "boseong", "hwasun", "gurye"]:
        assert parse_qs(urlparse(SETTINGS.sources[slug].list_url).query)["list_gubun"] == ["A"]
    haenam = SETTINGS.sources["haenam"]
    assert parse_qs(urlparse(haenam.list_url).query)["searchType"] == ["notSj"]
    assert haenam.html_profile is not None and haenam.html_profile.page_param == "nowPageNum"
    jangheung = parse_qs(urlparse(SETTINGS.sources["jangheung"].list_url).query)
    assert jangheung["category_1"] == ["지난 고시공고"]
    assert jangheung["start_date"] == ["2025-10-05"]
    current = parse_qs(urlparse(SETTINGS.sources["jangheung_current"].list_url).query)
    assert "category_1" not in current
    assert "/old_gosi_new" in SETTINGS.sources["gangjin"].list_url
    assert "/notice/gosi" in SETTINGS.sources["gangjin_current"].list_url


def test_archives_supply_recruitment_not_false_success_from_current_results() -> None:
    assert "empty_list_html" in CASES["jangheung_current"]
    assert CASES["gangjin_current"]["listing_only"]
    for slug in ["jangheung", "gangjin"]:
        assert CASES[slug]["category"] == "recruitment"
        assert date.fromisoformat(CASES[slug]["date"]) >= date(2025, 10, 5)


def test_actual_nomination_request_uses_the_same_html_profile() -> None:
    source, case = SETTINGS.sources["gangjin"], NOMINATION["gangjin"]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(case["list_html"], list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader, recruitment_only=True)
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert case["category"] == "recruitment"
    loader.assert_called_once_with(case["url"])


def test_real_response_fixtures_exclude_scripts_comments_hidden_fields_and_contacts() -> None:
    for case in [*CASES.values(), *NOMINATION.values()]:
        for key in ("list_html", "empty_list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script, style, input, iframe")
            assert not soup.find_all(string=lambda node: isinstance(node, Comment))
            assert "담당자" not in soup.get_text() and "연락처" not in soup.get_text()
