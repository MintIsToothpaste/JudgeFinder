from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup, Comment

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/jeonnam_gwangju_ten_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-jeonnam-gwangju-ten.example.toml")
HTML_SLUGS = [slug for slug, case in CASES.items() if "list_json" not in case]
DETAIL_SLUGS = [slug for slug, case in CASES.items() if "detail_html" in case]


@pytest.mark.parametrize("slug", CASES)
def test_actual_title_date_url_or_explicit_empty_listing(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    loader = Mock(return_value=case.get("detail_html", ""))
    if source.json_profile:
        actual = parse_profiled_json(
            case["list_json"], list_url=source.list_url, profile=source.json_profile,
        )
    else:
        assert source.html_profile is not None
        actual = parse_profiled_html(
            case.get("list_html", case.get("empty_list_html")), list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader, expected_page=1,
        )
    if "empty_list_html" in case:
        assert actual == []
        loader.assert_not_called()
    else:
        assert [(n.title, str(n.published_date), n.url) for n in actual] == [
            (case["title"], case["date"], case["url"]),
        ]
        if source.html_profile:
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


@pytest.mark.parametrize("slug", HTML_SLUGS)
def test_missing_listing_cannot_be_mistaken_for_zero_notices(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h1>FORBIDDEN</h1>", list_url=source.list_url, profile=source.html_profile,
        )


def test_north_district_registration_date_is_not_the_shared_class_first_value() -> None:
    case = CASES["gwangju_bukgu"]
    soup = BeautifulSoup(case["detail_html"], "html.parser")
    assert "게재제호" in soup.select_one("dt.field02").get_text()  # type: ignore[union-attr]
    assert not soup.select_one("dt.field02 + dd").get_text(strip=True)  # type: ignore[union-attr]
    profile = SETTINGS.sources["gwangju_bukgu"].html_profile
    assert profile is not None
    assert "등록일" in profile.detail_date_selector
    assert date.fromisoformat(case["date"]) > date(2025, 10, 4)


def test_official_pagination_and_archive_profiles_cover_ten_municipalities() -> None:
    assert len(CASES) == len(SETTINGS.enabled_sources) == 13
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 10
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
    profile = SETTINGS.sources["suncheon"].html_profile
    assert profile is not None and profile.page_param == "pageIndex"
    assert profile.page_number_selector
    for slug in ["yeosu", "naju", "gwangju_seogu"]:
        assert f"{slug}_current" in SETTINGS.enabled_sources
    assert SETTINGS.sources["damyang"].json_profile is not None


def test_real_response_fixtures_exclude_scripts_comments_and_hidden_inputs() -> None:
    for case in CASES.values():
        for key in ("list_html", "empty_list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script, style, input, iframe")
            assert not soup.find_all(string=lambda node: isinstance(node, Comment))
