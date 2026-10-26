from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup, Comment

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json

ROOT = Path(__file__).parents[2]
CASES = json.loads(
    (ROOT / "tests/fixtures/daejeon_ulsan_sejong_gyeonggi_ten_profiles.json").read_text(),
)
SETTINGS = load_config(ROOT / "config/batch-daejeon-ulsan-sejong-gyeonggi-ten.example.toml")
HTML_SLUGS = [s for s in SETTINGS.enabled_sources if SETTINGS.sources[s].html_profile]


@pytest.mark.parametrize("slug", HTML_SLUGS)
def test_actual_full_title_registration_date_and_canonical_url(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(case["list_html"], list_url=source.list_url,
        profile=source.html_profile, detail_loader=loader, expected_page=1)
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", HTML_SLUGS)
def test_missing_authoritative_detail_is_not_success(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=Mock(return_value="<h1>Error</h1>"))


@pytest.mark.parametrize("slug", HTML_SLUGS)
def test_error_document_is_not_successful_zero(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html("<h1>FORBIDDEN</h1>", list_url=source.list_url,
            profile=source.html_profile, expected_page=1)


@pytest.mark.parametrize("slug", ["ulsan", "ulju", "suwon"])
def test_ignored_page_is_rejected_before_detail_requests(slug: str) -> None:
    source = SETTINGS.sources[slug]
    assert source.html_profile is not None
    loader = Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, detail_loader=loader, expected_page=2)
    loader.assert_not_called()


def test_real_counted_json_without_status_and_zero_based_offset() -> None:
    source, case = SETTINGS.sources["gyeonggi"], CASES["gyeonggi"]
    profile = source.json_profile
    assert profile is not None
    assert profile.status_path == profile.success_value == ""
    assert profile.total_path == "total" and profile.offset_base == 0
    assert profile.request_method == "POST" and profile.search_param == "keyword"
    actual = parse_profiled_json(case["list_json"], list_url=source.list_url,
        profile=profile, expected_page=1)
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert parse_profiled_json('{"total":1,"items":[]}', list_url=source.list_url,
        profile=profile, expected_page=2) == []
    query = parse_qs(urlparse(source.list_url).query)
    assert query["keyfield"] == ["SUBJECT"]


def test_actual_api_escaped_titles_match_the_public_detail_display() -> None:
    source = SETTINGS.sources["gyeonggi"]
    assert source.json_profile is not None
    records = CASES["gyeonggi"]["escaped_title_rows"]
    assert len(records) == 5
    for record in records:
        payload = json.dumps({"total": 1, "items": [record["row"]]})
        actual = parse_profiled_json(payload, list_url=source.list_url,
            profile=replace(source.json_profile, page_size=1))
        assert [(n.title, str(n.published_date), n.url) for n in actual] == [
            (record["title"], record["date"], record["url"]),
        ]


@pytest.mark.parametrize("payload", [
    "<h1>Error</h1>", '{"error":"unavailable"}', '{"total":1,"items":[]}',
    '{"total":true,"items":[]}', '{"total":0,"items":{}}',
])
def test_counted_json_error_or_partial_response_fails_closed(payload: str) -> None:
    source = SETTINGS.sources["gyeonggi"]
    assert source.json_profile is not None
    with pytest.raises(ValueError):
        parse_profiled_json(payload, list_url=source.list_url, profile=source.json_profile)


def test_sejong_real_blank_dates_are_not_guessed_or_enabled() -> None:
    source, case = SETTINGS.sources["sejong"], CASES["sejong"]
    assert "sejong" not in SETTINGS.enabled_sources and case["held"]
    profile = source.html_profile
    assert profile is not None
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(case["list_html"], list_url=source.list_url,
            profile=profile, detail_loader=Mock(return_value=case["detail_html"]),
            expected_page=1)
    soup = BeautifulSoup(case["detail_html"], "html.parser")
    date_node = soup.select_one(profile.detail_date_selector)
    assert date_node is not None and not date_node.get_text(strip=True)


def test_official_archive_scope_and_security_settings() -> None:
    assert len(CASES) == len(SETTINGS.sources) == 10
    assert len(SETTINGS.enabled_sources) == 9
    assert len({s.municipality for s in SETTINGS.sources.values()}) == 10
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
        assert source.request_strategy.session and source.request_strategy.referer
    for slug in ["daedeok", "ulsan_junggu", "ulsan_namgu", "ulsan_donggu", "ulsan_bukgu"]:
        assert parse_qs(urlparse(SETTINGS.sources[slug].list_url).query)["list_gubun"] == ["A"]
    query = parse_qs(urlparse(SETTINGS.sources["ulju"].list_url).query)
    assert query["seCode"] == ["04"] and query["searchType"] == ["tit"]
    assert parse_qs(urlparse(SETTINGS.sources["suwon"].list_url).query)["q_searchKey"] == ["SJ"]


def test_real_response_fixtures_exclude_hidden_fields_scripts_and_contacts() -> None:
    for case in CASES.values():
        for key in ("list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert not any(label in soup.get_text() for label in
                ("담당자", "연락처", "전화번호", "문의전화"))
    wire = json.loads(CASES["gyeonggi"]["list_json"])
    assert set(wire) == {"total", "items"}
    assert set(wire["items"][0]) == {"B_IDX", "WRITE_DATE2", "SUBJECT"}
