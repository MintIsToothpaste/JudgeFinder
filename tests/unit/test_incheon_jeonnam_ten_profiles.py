from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.notice_classification import classify_notice_title

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/incheon_jeonnam_ten_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-incheon-jeonnam-ten.example.toml")
DETAIL_SLUGS = [slug for slug, case in CASES.items() if case.get("detail_html")]


@pytest.mark.parametrize("slug", CASES)
def test_actual_html_title_date_url_or_explicit_empty_search(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case.get("detail_html", ""))
    actual = parse_profiled_html(
        case.get("list_html", case.get("empty_list_html")), list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader,
    )
    if "empty_list_html" in case:
        assert actual == []
        loader.assert_not_called()
    else:
        assert [(n.title, str(n.published_date), n.url) for n in actual] == [
            (case["title"], case["date"], case["url"]),
        ]
        assert classify_notice_title(actual[0].title).value == case["category"]
        loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", DETAIL_SLUGS)
def test_http_200_error_document_cannot_replace_authoritative_detail(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            CASES[slug]["list_html"], list_url=source.list_url, profile=source.html_profile,
            detail_loader=Mock(return_value="<title>JSP compile error</title>"),
        )


@pytest.mark.parametrize("slug", CASES)
def test_missing_listing_is_not_proof_of_no_recruitment(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h2>Service unavailable</h2>", list_url=source.list_url,
            profile=source.html_profile,
        )


def test_isolated_profiles_cover_ten_municipalities_and_both_mokpo_boards() -> None:
    assert len(CASES) == len(SETTINGS.enabled_sources) == 12
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 10
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
    for slug in ["seohae", "geomdan", "geomdan_news", "jeonnam_gwangju"]:
        assert SETTINGS.sources[slug].available_from == date(2026, 7, 1)
    for slug in ["yeonsu", "namdong", "bupyeong", "gyeyang"]:
        query = parse_qs(urlparse(SETTINGS.sources[slug].list_url).query)
        assert query["list_gubun"] == ["A"]
    assert "old_public_notice" in SETTINGS.sources["mokpo"].list_url
    assert "old_public_notice" not in SETTINGS.sources["mokpo_current"].list_url
    assert "등록 신청" in CASES["mokpo"]["title"]
    assert CASES["mokpo"]["category"] == "recruitment"


def test_integrated_province_keeps_official_period_bounds_and_euc_kr_search() -> None:
    sources = SourceRegistry(SETTINGS, Mock(), ZoneInfo("Asia/Seoul")).build_enabled_sources()
    source = next(s for s in sources if s.slug == "jeonnam_gwangju")
    assert isinstance(source, GenericEngineSource)
    request = source._build_request_url(page_index=2)
    assert "conTitle=%C6%F2%B0%A1%C0%A7%BF%F8" in request
    query = parse_qs(urlparse(request).query)
    assert query["conIfmStdt"] == ["20260701"]
    assert query["conIfmEnddt"] == ["99991231"]
    assert query["currPageNo"] == ["2"]


def test_geomdan_uses_detail_date_instead_of_time_only_listing() -> None:
    case = CASES["geomdan"]
    profile = SETTINGS.sources["geomdan"].html_profile
    assert profile is not None
    assert "작성일" in case["detail_html"] and "년" in case["detail_html"]
    assert case["category"] != "recruitment"
    assert not profile.search_param


def test_ganghwa_actual_final_empty_page_is_not_a_failed_collection() -> None:
    source = SETTINGS.sources["ganghwa"]
    assert source.html_profile is not None
    assert parse_profiled_html(
        CASES["ganghwa"]["last_empty_list_html"], list_url=source.list_url,
        profile=source.html_profile,
    ) == []
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            '<p class="nocontens">조회 권한이 없습니다.</p>', list_url=source.list_url,
            profile=source.html_profile,
        )
