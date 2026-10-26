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
CASES = json.loads((ROOT / "tests/fixtures/gyeonggi_cities_ten_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-gyeonggi-cities-ten.example.toml")
DETAILS = [s for s, c in CASES.items() if not c["listing_only"]]
PAGED = [s for s, source in SETTINGS.sources.items()
    if source.html_profile is not None and source.html_profile.page_number_selector]


@pytest.mark.parametrize("slug", CASES)
def test_actual_full_title_date_and_canonical_notice_url(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case.get("detail_html", ""))
    actual = parse_profiled_html(case["list_html"], list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader, expected_page=1,
        recruitment_only=case["listing_only"])
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    if case["listing_only"]:
        assert case["category"] == "result"
        loader.assert_not_called()
    else:
        assert case["category"] == "recruitment"
        loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", DETAILS)
def test_missing_authoritative_detail_cannot_pass(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=Mock(return_value="<h1>Error</h1>"))


@pytest.mark.parametrize("slug", CASES)
def test_broken_listing_is_not_successful_zero(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html("<h1>FORBIDDEN</h1>", list_url=source.list_url,
            profile=source.html_profile, expected_page=1)


@pytest.mark.parametrize("slug", PAGED)
def test_ignored_pagination_fails_before_detail_fetch(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    loader = Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader, expected_page=2)
    loader.assert_not_called()


def test_official_live_profiles_are_isolated_and_explicit() -> None:
    assert len(CASES) == len(SETTINGS.enabled_sources) == 10
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 10
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
        assert urlparse(source.list_url).scheme == "https"
    for slug in ("seongnam", "anyang", "goyang"):
        assert parse_qs(urlparse(SETTINGS.sources[slug].list_url).query)["list_gubun"] == ["A"]
    uijeongbu = SETTINGS.sources["uijeongbu"].html_profile
    bucheon = SETTINGS.sources["bucheon"].html_profile
    assert uijeongbu is not None and bucheon is not None
    assert uijeongbu.search_param == "searchTxt"
    assert parse_qs(urlparse(SETTINGS.sources["uijeongbu"].list_url).query)[
        "searchType"
    ] == ["not_ancmt_sj"]
    assert bucheon.detail_date_selector == (
        "th:-soup-contains-own('게재(공고)일자') + td"
    )
    assert CASES["bucheon"]["date"] == "2026-09-28"
    assert CASES["pyeongtaek"]["listing_only"]


def test_real_response_fixtures_are_sanitized() -> None:
    for case in CASES.values():
        for key in ("list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert all(s not in soup.get_text() for s in ("담당자", "연락처", "전화번호"))
