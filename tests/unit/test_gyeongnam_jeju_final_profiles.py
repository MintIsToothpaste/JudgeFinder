from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlparse

import pytest
from bs4 import BeautifulSoup, Comment

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/gyeongnam_jeju_final_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-gyeongnam-jeju-final-twenty.example.toml")
POSITIVE = [slug for slug, case in CASES.items() if not case.get("empty")]
HTML = [slug for slug in POSITIVE if SETTINGS.sources[slug].html_profile]
PAGED = [slug for slug in HTML if SETTINGS.sources[slug].html_profile.page_number_selector]


@pytest.mark.parametrize("slug", POSITIVE)
def test_actual_full_title_registration_date_and_stable_url(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    if source.json_profile:
        actual = parse_profiled_json(case["list_json"], list_url=source.list_url,
            profile=source.json_profile, expected_page=1)
    else:
        loader = Mock(return_value=case["detail_html"])
        actual = parse_profiled_html(case["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader, expected_page=1,
            recruitment_only=True)
        loader.assert_called_once_with(case["url"])
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]


@pytest.mark.parametrize("slug", HTML)
def test_missing_detail_is_not_a_successful_zero(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(case["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=Mock(return_value="<h1>Error</h1>"))


@pytest.mark.parametrize("slug", [*HTML, "haman-current"])
def test_missing_container_is_not_a_successful_zero(slug: str) -> None:
    source = SETTINGS.sources[slug]
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html("<h1>Forbidden</h1>", list_url=source.list_url,
            profile=source.html_profile, expected_page=1)


@pytest.mark.parametrize("slug", PAGED)
def test_ignored_page_fails_before_details_are_loaded(slug: str) -> None:
    source = SETTINGS.sources[slug]
    loader = Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, expected_page=2, detail_loader=loader)
    loader.assert_not_called()


def test_haman_current_empty_is_paired_with_verified_past_recruitment() -> None:
    source = SETTINGS.sources["haman-current"]
    assert parse_profiled_html(CASES["haman-current"]["list_html"],
        list_url=source.list_url, profile=source.html_profile, expected_page=1) == []
    assert SETTINGS.sources["haman"].municipality == source.municipality
    assert "모집" in CASES["haman"]["title"]


def test_haman_current_retains_the_boards_verified_detail_and_date_rules() -> None:
    source, case = SETTINGS.sources["haman-current"], CASES["haman"]
    assert source.html_profile == SETTINGS.sources["haman"].html_profile
    actual = parse_profiled_html(case["list_html"], list_url=source.list_url,
        profile=source.html_profile, expected_page=1,
        detail_loader=Mock(return_value=case["detail_html"]), recruitment_only=True)
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]


def test_jinju_label_exclusion_and_reported_count_survive_config_loading() -> None:
    source, case = SETTINGS.sources["jinju"], CASES["jinju"]
    assert source.html_profile.total_count_selector == ".infomenu .right"
    assert source.html_profile.total_count_pattern.count("(") == 1
    assert not case["title"].startswith("제목 ")
    with pytest.raises(ValueError, match="row count contradicts"):
        parse_profiled_html(case["list_html"].replace("전체게시물:1개", "전체게시물:2개"),
            list_url=source.list_url, profile=source.html_profile, expected_page=1)


def test_jeju_uses_verified_rows_not_inconsistent_total_field() -> None:
    source, case = SETTINGS.sources["jeju"], CASES["jeju"]
    assert source.json_profile.total_path == "query.rows"
    data = json.loads(case["list_json"])
    assert data["query"]["total"] == 0 and data["query"]["rows"] == 1
    with pytest.raises(ValueError, match="total|row"):
        parse_profiled_json(case["list_json"], list_url=source.list_url,
            profile=replace(source.json_profile, total_path="query.total"), expected_page=1)


def test_only_verified_public_sources_are_enabled() -> None:
    assert len(CASES) == len(SETTINGS.enabled_sources) == 22
    assert len(POSITIVE) == 21
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 20
    assert "jejusi" not in SETTINGS.enabled_sources
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 80
        assert urlparse(source.list_url).scheme == "https"


def test_fixtures_exclude_contact_metadata_and_remote_scripts() -> None:
    for case in CASES.values():
        for key in ("list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html5lib")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert not re.search(r"[\w.+-]+@[\w.-]+|\b0\d{1,2}-\d{3,4}-\d{4}\b", soup.get_text())
            assert not any(x in soup.get_text() for x in ("담당자", "연락처", "전화번호"))
