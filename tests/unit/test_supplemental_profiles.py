from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup

from judgefinder.adapters.config import load_config
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.infrastructure.http.client import RequestsHttpClient

ROOT = Path(__file__).parents[2]


FIVE_CASES = json.loads(
    (ROOT / "tests/fixtures/cafe_five_recovered_profiles.json").read_text(encoding="utf-8"),
)


@pytest.mark.parametrize("slug", FIVE_CASES)
def test_recovered_live_notice_is_collected_with_pagination_and_cached_details(slug: str) -> None:
    case = FIVE_CASES[slug]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [slug]
    config = settings.sources[slug]
    profile = config.html_profile
    assert profile is not None
    client = Mock()

    def response(url: str, **_: object) -> str:
        if url == case["url"]:
            return str(case["detail_html"])
        query = parse_qs(urlparse(url).query)
        if slug == "seocho_katia":
            assert query["Dosearch"] == ["subject"]
            assert query["search_order"] == ["서초"]
        else:
            assert query[profile.search_param] == ["평가위원"]
        if slug == "busan_gosi":
            assert query["schKeyType"] == ["A"]
            assert query["conGosiGbn"] == ["A"]
        assert not {"searchStrtDt", "searchEndDt", "srchBeginDt", "srchEndDt"} & query.keys()
        if query[profile.page_param] == ["1"]:
            return str(case["list_html"])
        assert query[profile.page_param] == ["2"]
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        container.clear()
        return str(soup)

    client.get_text.side_effect = response
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    target = date.fromisoformat(case["date"])
    for _ in range(2):
        assert [(n.title, str(n.published_date), n.url) for n in source.fetch(target)] == [
            (case["title"], case["date"], case["url"]),
        ]
    assert client.get_text.call_count == 3
    assert sum(call.args[0] == case["url"] for call in client.get_text.call_args_list) == 1


@pytest.mark.parametrize("slug", FIVE_CASES)
def test_recovered_profiles_still_reject_invalid_registration_dates(slug: str) -> None:
    case = FIVE_CASES[slug]
    config = load_config(ROOT / case["config_path"]).sources[slug]
    assert config.html_profile is not None
    # Remove the date from both list and detail so it cannot fall back to either one.
    listing = case["list_html"].replace("2026-10-26", "2026-02-30")
    listing = listing.replace("2026.10.26", "2026.02.30")
    detail = case["detail_html"].replace("2026-10-26", "2026-02-30")
    detail = detail.replace("2026.10.26", "2026.02.30")
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            listing,
            list_url=config.list_url,
            profile=config.html_profile,
            detail_loader=Mock(return_value=detail),
        )


def test_supplementary_boards_are_enabled_without_replacing_original_channels() -> None:
    seoul = load_config(ROOT / "config/batch-seoul-ten.example.toml")
    assert {"yangcheon", "yangcheon_gosi", "gangbuk", "gangbuk_gosi"} <= set(
        seoul.enabled_sources,
    )
    busan = load_config(ROOT / "config/batch-seoul-busan-ten.example.toml")
    assert {"seocho", "seocho_katia", "busan", "busan_gosi"} <= set(busan.enabled_sources)
    assert busan.sources["seocho_katia"].municipality == "서초구 (교통영향평가협회)"
    for config in (seoul, busan):
        for slug in config.enabled_sources:
            assert config.sources[slug].fixture_path is None


def test_original_news_and_gyeongbuk_searches_have_no_fixed_historical_cutoff() -> None:
    configs = [
        ("config/batch-seoul-busan-ten.example.toml", "busan"),
        ("config/batch-jeonbuk-gyeongbuk-gyeongnam-thirty.example.toml", "gyeongbuk"),
    ]
    for path, slug in configs:
        query = parse_qs(urlparse(load_config(ROOT / path).sources[slug].list_url).query)
        assert not {"searchStrtDt", "searchEndDt", "srchBeginDt", "srchEndDt"} & query.keys()


FOUR_CASES = json.loads(
    (ROOT / "tests/fixtures/cafe_four_recovered_profiles.json").read_text(encoding="utf-8"),
)


@pytest.mark.parametrize("key", FOUR_CASES)
def test_missing_notice_fetches_with_search_pagination_and_cached_details(key: str) -> None:
    case = FOUR_CASES[key]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [case["slug"]]
    config = settings.sources[case["slug"]]
    profile = config.html_profile
    assert profile is not None
    client = Mock()

    def response(url: str, **kwargs: object) -> str:
        assert kwargs["verify_tls"] and kwargs["use_session"]
        if url == case["url"]:
            return str(case["detail_html"])
        query = parse_qs(urlparse(url).query)
        assert query[profile.search_param] == ["평가위원"]
        assert not {"searchStrtDt", "searchEndDt", "srchBeginDt", "srchEndDt"} & query.keys()
        if query[profile.page_param] == ["1"]:
            return str(case["list_html"])
        assert query[profile.page_param] == ["2"]
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        container.clear()
        return str(soup)

    client.get_text.side_effect = response
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    for _ in range(2):
        assert [
            (n.title, str(n.published_date), n.url)
            for n in source.fetch(date.fromisoformat(case["date"]))
        ] == [
            (case["title"], case["date"], case["url"]),
        ]
    assert client.get_text.call_count == 3
    assert sum(c.args[0] == case["url"] for c in client.get_text.call_args_list) == 1
    client.post_text.assert_not_called()


@pytest.mark.parametrize("key", FOUR_CASES)
def test_explicit_registration_date_cannot_fall_back_to_other_dates(key: str) -> None:
    case = FOUR_CASES[key]
    source = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    assert source.html_profile is not None
    # Keep a valid list date and a valid application date: neither repairs bad metadata.
    detail = case["detail_html"].replace(case["date"], "2026-02-30")
    detail += "<p>접수기간: 2026-10-23 ~ 2026-10-30</p>"
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            case["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value=detail),
        )


@pytest.mark.parametrize("key", ["seodaemun_gosi", "mapo_gosi", "gangnam_union6"])
def test_detail_error_page_does_not_become_a_notice(key: str) -> None:
    case = FOUR_CASES[key]
    source = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            case["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<p>일시적으로 조회할 수 없습니다.</p>"),
        )


@pytest.mark.parametrize("key", ["seodaemun_gosi", "mapo_gosi"])
def test_legacy_row_with_missing_click_handler_is_not_silently_skipped(key: str) -> None:
    case = FOUR_CASES[key]
    source = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    profile = source.html_profile
    assert profile is not None
    soup = BeautifulSoup(case["list_html"], "html5lib")
    link = soup.select_one(profile.link_selector)
    assert link is not None
    del link["onclick"]
    with pytest.raises(ValueError, match="onclick missing"):
        parse_profiled_html(str(soup), list_url=source.list_url, profile=profile)


def test_new_channels_are_enabled_alongside_original_channels() -> None:
    seoul = load_config(ROOT / "config/batch-seoul-ten.example.toml")
    busan = load_config(ROOT / "config/batch-seoul-busan-ten.example.toml")
    assert {"seodaemun", "seodaemun_gosi", "mapo", "mapo_gosi"} <= set(seoul.enabled_sources)
    assert {"gangnam", "gangnam_union6"} <= set(busan.enabled_sources)
    for config, slugs in [(seoul, ["seodaemun_gosi", "mapo_gosi"]), (busan, ["gangnam_union6"])]:
        for slug in slugs:
            assert not config.sources[slug].recruitment_only
            assert config.sources[slug].fixture_path is None


LATEST_CASES = json.loads(
    (ROOT / "tests/fixtures/cafe_20261028_profiles.json").read_text(encoding="utf-8"),
)


@pytest.mark.parametrize("slug", LATEST_CASES)
def test_recovered_boards_fetch_real_dates_paginate_and_cache(slug: str) -> None:
    case = LATEST_CASES[slug]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [slug]
    profile = settings.sources[slug].html_profile
    assert profile is not None
    client = Mock(spec=RequestsHttpClient)
    pages: list[int] = []

    def response(url: str, **kwargs: object) -> str:
        assert kwargs["verify_tls"] and kwargs["use_session"]
        if url == case["url"]:
            return str(case["detail_html"])
        query = parse_qs(urlparse(url).query)
        page = int(query.get(profile.page_param, ["1"])[0])
        assert page in {1, 2}
        pages.append(page)
        soup = BeautifulSoup(case["list_html"], "html5lib")
        if page == 2:
            container = soup.select_one(profile.container_selector)
            assert container is not None
            container.clear()
            if profile.page_number_selector:
                current = soup.select_one(profile.page_number_selector)
                assert current is not None
                current.string = "2"
        return str(soup)

    client.get_text.side_effect = response
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    source.throttle_seconds = 0
    target = date.fromisoformat(case["date"])
    for _ in range(2):
        notices = source.fetch(target)
        assert [(n.title, str(n.published_date), n.url) for n in notices] == [
            (case["title"], case["date"], case["url"]),
        ]
    assert source.fetch(target + timedelta(days=1)) == []
    assert pages == [1, 2]


@pytest.mark.parametrize("slug", LATEST_CASES)
def test_missing_registration_date_never_uses_application_period(slug: str) -> None:
    case = LATEST_CASES[slug]
    config = load_config(ROOT / case["config_path"]).sources[slug]
    assert config.html_profile is not None
    listing = BeautifulSoup(case["list_html"], "html5lib")
    node = listing.select_one(config.html_profile.date_selector)
    assert node is not None
    node.clear()
    detail = BeautifulSoup(case["detail_html"], "html5lib")
    if config.html_profile.detail_date_selector:
        node = detail.select_one(config.html_profile.detail_date_selector)
        assert node is not None
        node.clear()
    detail.append(BeautifulSoup("<p>접수기간: 2026-10-27 ~ 2026-11-06</p>", "html.parser"))
    with pytest.raises(
        ValueError,
        match="invalid title or registration date|registration-date element",
    ):
        parse_profiled_html(
            str(listing),
            list_url=config.list_url,
            profile=config.html_profile,
            detail_loader=Mock(return_value=str(detail)),
        )


@pytest.mark.parametrize("value", ["평가위원", "평가 위원", "평 가 위 원", "평가\n위원"])
def test_spaced_keywords_collect_without_rewriting_official_title(value: str) -> None:
    case = LATEST_CASES["daegu_market"]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = ["daegu_market"]
    client = Mock(spec=RequestsHttpClient)
    client.get_text.return_value = case["list_html"].replace("평가 위원", value)
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    source.throttle_seconds = 0
    source.page_cache[1] = case["list_html"].replace("평가 위원", value)
    source.page_cache[2] = '<div class="boardList"><ul class="articleList"></ul></div>'
    source.detail_cache[case["url"]] = case["detail_html"].replace("평가 위원", value)
    notices = source.fetch(date.fromisoformat(case["date"]))
    assert len(notices) == 1 and notices[0].url == case["url"]
    assert " ".join(value.split()) in notices[0].title
    client.get_text.assert_not_called()


def test_navigation_keywords_do_not_turn_unrelated_notice_into_recruitment() -> None:
    case = LATEST_CASES["daegu_market"]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = ["daegu_market"]
    client = Mock(spec=RequestsHttpClient)
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    source.page_cache[1] = case["list_html"].replace("평가 위원", "운영")
    source.page_cache[2] = '<div class="boardList"><ul class="articleList"></ul></div>'
    source.detail_cache[case["url"]] = (
        case["detail_html"].replace("평가 위원", "운영") + "<nav>평가 위원 모집</nav>"
    )
    assert source.fetch(date.fromisoformat(case["date"])) == []
    client.get_text.assert_not_called()


def test_supplemental_batch_is_enabled_and_does_not_pin_search_dates() -> None:
    settings = load_config(ROOT / "config/batch-cafe-20261028.example.toml")
    assert set(settings.enabled_sources) == set(settings.sources)
    for config in settings.sources.values():
        assert config.fixture_path is None
        query = parse_qs(urlparse(config.list_url).query)
        assert "searchStartDate" not in query and "searchEndDate" not in query
        assert config.request_strategy.verify_tls


def test_public_fixtures_omit_contacts_and_session_fields() -> None:
    for case in LATEST_CASES.values():
        for key in ["list_html", "detail_html"]:
            soup = BeautifulSoup(case[key], "html5lib")
            assert not soup.select("script,style,input,iframe")
            assert all(word not in soup.get_text() for word in ["연락처", "전화번호", "담당자"])
