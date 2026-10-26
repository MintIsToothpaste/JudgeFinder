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
CASES = json.loads((ROOT / "tests/fixtures/daegu_incheon_ten_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-daegu-incheon-ten.example.toml")
DETAIL_SLUGS = [s for s, c in CASES.items() if c["detail_html"]]


@pytest.mark.parametrize("slug", CASES)
def test_real_listing_title_registration_date_and_canonical_url(slug: str) -> None:
    case, source = CASES[slug], SETTINGS.sources[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"], list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert classify_notice_title(actual[0].title).value == case["category"]
    if slug in DETAIL_SLUGS:
        loader.assert_called_once_with(case["url"])
    else:
        loader.assert_not_called()


@pytest.mark.parametrize("slug", DETAIL_SLUGS)
def test_http_200_error_document_does_not_become_a_notice(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            CASES[slug]["list_html"], list_url=source.list_url, profile=source.html_profile,
            detail_loader=Mock(return_value="<title>New Document</title>"),
        )


@pytest.mark.parametrize("slug", CASES)
def test_invalid_listing_is_not_treated_as_proof_of_zero_notices(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h2>Service unavailable</h2>", list_url=source.list_url,
            profile=source.html_profile,
        )


def test_profiles_are_isolated_and_new_districts_have_a_start_date() -> None:
    assert len(CASES) == len(SETTINGS.enabled_sources) == 10
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages >= 40
    assert SETTINGS.sources["jemulpo"].available_from == date(2026, 7, 1)
    assert SETTINGS.sources["yeongjong"].available_from == date(2026, 7, 1)
    for slug in ["jemulpo", "yeongjong", "michuhol"]:
        profile = SETTINGS.sources[slug].html_profile
        assert profile is not None and not profile.search_param
        assert CASES[slug]["category"] != "recruitment"


def test_incheon_uses_actual_euc_kr_request_and_clickable_row_identifier() -> None:
    registry = SourceRegistry(SETTINGS, Mock(), ZoneInfo("Asia/Seoul"))
    source = next(s for s in registry.build_enabled_sources() if s.slug == "incheon")
    assert isinstance(source, GenericEngineSource)
    request_url = source._build_request_url(page_index=2)
    assert "conTitle=%C6%F2%B0%A1%C0%A7%BF%F8" in request_url
    query = parse_qs(urlparse(request_url).query)
    assert query["currPageNo"] == ["2"] and query["conGosiGbn"] == ["A"]
    profile = SETTINGS.sources["incheon"].html_profile
    assert profile is not None and not profile.link_selector and profile.link_attribute == "onclick"
    assert "<nobr>" in CASES["incheon"]["detail_html"]


def test_dalseo_uses_registration_date_not_posting_period_or_truncated_title() -> None:
    case = CASES["dalseo"]
    profile = SETTINGS.sources["dalseo"].html_profile
    assert profile is not None
    assert "등록일" in case["detail_html"]
    assert "게재기간" not in profile.date_selector
    assert "..." not in case["title"]


def test_yeongjong_actual_empty_news_message_is_recognized() -> None:
    source = SETTINGS.sources["yeongjong"]
    assert source.html_profile is not None
    assert parse_profiled_html(
        CASES["yeongjong"]["empty_list_html"], list_url=source.list_url,
        profile=source.html_profile,
    ) == []
