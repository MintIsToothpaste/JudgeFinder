from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup, Comment

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice

ROOT = Path(__file__).parents[2]
CASES = json.loads(
    (ROOT / "tests/fixtures/jeonbuk_gyeongbuk_gyeongnam_thirty_profiles.json").read_text(),
)
SETTINGS = load_config(ROOT / "config/batch-jeonbuk-gyeongbuk-gyeongnam-thirty.example.toml")
HTML = [slug for slug, source in SETTINGS.sources.items() if source.html_profile]
PAGED = [slug for slug in HTML if SETTINGS.sources[slug].html_profile.page_number_selector]
RECOVERED = json.loads(
    (ROOT / "tests/fixtures/jeonbuk_gyeongbuk_gyeongnam_recovered_profiles.json").read_text(),
)


@pytest.mark.parametrize("slug", RECOVERED)
def test_actual_recovered_notice_retains_original_title_date_and_url(slug: str) -> None:
    source, case = SETTINGS.sources[slug], RECOVERED[slug]
    actual = parse_profiled_html(case["list_html"], list_url=source.list_url,
        profile=source.html_profile, detail_loader=Mock(return_value=case["detail_html"]),
        recruitment_only=True)
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert classify_notice(actual[0].title, actual[0].body_text) is NoticeCategory.RECRUITMENT


def test_recovered_fixtures_do_not_include_contact_values_or_scripts() -> None:
    for case in RECOVERED.values():
        soup = BeautifulSoup(case["detail_html"], "html5lib")
        assert not soup.select("script,style,input,iframe")
        assert not re.search(r"[\w.+-]+@[\w.-]+|\b0\d{1,2}-\d{3,4}-\d{4}\b", soup.get_text())


@pytest.mark.parametrize("slug", CASES)
def test_actual_title_display_date_and_stable_official_url(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    if source.json_profile:
        actual = parse_profiled_json(case["list_json"], list_url=source.list_url,
            profile=source.json_profile, expected_page=1)
    else:
        assert source.html_profile is not None
        loader = Mock(return_value=case["detail_html"])
        actual = parse_profiled_html(case["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader, expected_page=1,
            recruitment_only=True)
        loader.assert_called_once_with(case["url"])
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]


@pytest.mark.parametrize("slug", HTML)
def test_missing_detail_title_is_a_failure_not_successful_zero(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=Mock(return_value="<h1>Error</h1>"))


@pytest.mark.parametrize("slug", HTML)
def test_broken_official_listing_fails_closed(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html("<h1>Forbidden</h1>", list_url=source.list_url,
            profile=source.html_profile, expected_page=1)


@pytest.mark.parametrize("slug", PAGED)
def test_ignored_page_number_fails_before_loading_details(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    loader = Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader, expected_page=2)
    loader.assert_not_called()


def test_settings_do_not_enable_unverified_sources_or_fixtures() -> None:
    assert len(CASES) == len(SETTINGS.enabled_sources) == 25
    assert {"andong", "sangju", "uiseong", "yecheon", "changwon"}.isdisjoint(
        SETTINGS.enabled_sources,
    )
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 25
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 80
        assert urlparse(source.list_url).scheme == "https"
        if "eminwon" in urlparse(source.list_url).hostname:
            assert parse_qs(urlparse(source.list_url).query)["list_gubun"] == ["A"]
    for slug in HTML:
        assert SETTINGS.sources[slug].html_profile.id_format == "numeric"
    assert SETTINGS.sources["gumi"].html_profile.detail_body_selector == ".view_cont"
    assert SETTINGS.sources["yeongyang"].html_profile.detail_title_selector == (
        ".view_title > p.title"
    )
    assert "cmd=258" in SETTINGS.sources["seongju"].html_profile.detail_url_template


def test_actual_fixtures_do_not_include_contact_metadata_or_remote_scripts() -> None:
    for case in CASES.values():
        for key in ("list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html5lib")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert all(s not in soup.get_text() for s in ("담당자", "연락처", "전화번호"))
