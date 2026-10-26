from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup, Comment

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/jeonnam_daejeon_ten_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-jeonnam-daejeon-ten.example.toml")


@pytest.mark.parametrize("slug", CASES)
def test_actual_complete_title_registration_date_and_canonical_url(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(case["list_html"], list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader, expected_page=1)
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert case["category"] == "recruitment"
    loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", CASES)
def test_missing_authoritative_detail_is_not_success(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=Mock(return_value="<h1>Error</h1>"))


@pytest.mark.parametrize("slug", CASES)
def test_missing_listing_is_not_successful_zero(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html("<h1>FORBIDDEN</h1>", list_url=source.list_url,
            profile=source.html_profile, expected_page=1)


@pytest.mark.parametrize("slug", ["yeonggwang", "jangseong", "wando", "jindo",
    "shinan", "daejeon", "daejeon_seogu"])
def test_ignored_page_parameter_fails_before_detail_requests(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    loader = Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader, expected_page=2)
    loader.assert_not_called()


def test_official_city_only_archive_and_search_scope() -> None:
    assert len(CASES) == len(SETTINGS.enabled_sources) == 10
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 10
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
    for slug in ["hampyeong", "daejeon_donggu", "yuseong"]:
        query = parse_qs(urlparse(SETTINGS.sources[slug].list_url).query)
        assert query.get("listGubun", query.get("list_gubun")) == ["A"]
    city = SETTINGS.sources["daejeon"]
    assert urlparse(city.list_url).path == "/drh/drhGosiList.do"
    query = parse_qs(urlparse(city.list_url).query)
    assert query["gosigbn"] == ["A"] and query["menuSeq"] == ["1908"]
    assert query["conifmstdt"] == ["2025-10-05"] and query["conifmenddt"] == ["2026-10-04"]


def test_real_button_attribute_and_zero_based_offset_are_configurable() -> None:
    seogu, yeonggwang = SETTINGS.sources["daejeon_seogu"], SETTINGS.sources["yeonggwang"]
    assert seogu.html_profile is not None and yeonggwang.html_profile is not None
    assert seogu.html_profile.link_attribute == "data-key-no"
    soup = BeautifulSoup(CASES["daejeon_seogu"]["list_html"], "html5lib")
    link = soup.select_one(seogu.html_profile.link_selector)
    assert link is not None and link.name == "td" and not link.find("a")
    assert link["data-key-no"] == "51899"
    assert yeonggwang.html_profile.offset_param == "offset"
    assert yeonggwang.html_profile.page_size == 10


def test_actual_empty_terminal_page_does_not_require_current_page_marker() -> None:
    source = SETTINGS.sources["daejeon"]
    assert source.html_profile is not None
    loader = Mock()
    assert parse_profiled_html(CASES["daejeon"]["empty_list_html"], list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader, expected_page=3) == []
    loader.assert_not_called()


def test_real_response_fixtures_exclude_hidden_fields_scripts_and_contacts() -> None:
    for case in CASES.values():
        for key in ("list_html", "detail_html", "empty_list_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda node: isinstance(node, Comment))
            assert "담당자" not in soup.get_text() and "연락처" not in soup.get_text()
