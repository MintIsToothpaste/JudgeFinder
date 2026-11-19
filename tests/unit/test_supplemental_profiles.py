from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup
from profile_cases import PROFILE_BATCHES, load_source_subset, read_cases

from judgefinder.adapters.config import load_config
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.adapters.sources.generic_engine.wonkwang_contract import WonkwangContractSource
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
        if profile.request_method == "POST":
            data = kwargs["data"]
            assert isinstance(data, bytes)
            url += "?" + data.decode("ascii")
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
    client.post_text.side_effect = response
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
    settings = load_config(ROOT / "config/batch-cafe.example.toml")
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


def test_recovered_board_preserves_registration_paginates_and_caches(
    recovered_board_case: dict[str, str], recovered_board_http: list[str],
) -> None:
    case = recovered_board_case
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [case["slug"]]
    source = SourceRegistry(
        settings, RequestsHttpClient(), ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    for _ in range(2):
        window_end = date.fromisoformat(case.get("window_end", "2026-10-22"))
        notices = [notice for offset in range(7)
                   for notice in source.fetch(window_end - timedelta(days=6 - offset))]
        assert [(n.title, str(n.published_date), n.url) for n in notices] == [
            (case["title"], case["date"], case["url"]),
        ]
    assert len(recovered_board_http) == int(case.get("requests_per_collect", "3"))
    profile = settings.sources[case["slug"]].html_profile
    assert profile is not None
    needs_detail = bool(profile.detail_title_selector or profile.detail_date_selector)
    assert recovered_board_http.count(case["url"]) == int(needs_detail)


def test_recovered_board_rejects_invalid_metadata_despite_application_dates(
    recovered_board_case: dict[str, str],
) -> None:
    case = recovered_board_case
    source = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    profile = source.html_profile
    assert profile is not None
    listing = BeautifulSoup(case["list_html"], "html5lib")
    for node in listing.select(profile.date_selector) if profile.date_selector else []:
        if profile.listing_date_attribute:
            node[profile.listing_date_attribute] = "invalid"
        else:
            node.string = "invalid"
    detail = BeautifulSoup(case["detail_html"], "html5lib")
    if profile.detail_date_selector:
        node = detail.select_one(profile.detail_date_selector)
        assert node is not None
        if profile.detail_date_attribute:
            node[profile.detail_date_attribute] = "2026-02-30"
        else:
            # Preserve label descendants used by metadata selectors such as :has().
            for value in list(node.find_all(string=True)):
                if any(character.isdigit() for character in value):
                    value.replace_with(re.sub(
                        r"[0-9].*", "2026-02-30", str(value), flags=re.DOTALL,
                    ))
    detail_html = str(detail) + "<p>접수기간: 2026-10-21 ~ 2026-10-29</p>"
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            str(listing), list_url=source.list_url, profile=profile,
            detail_loader=Mock(return_value=detail_html),
        )


def test_recovered_board_error_document_is_not_accepted(
    recovered_board_case: dict[str, str],
) -> None:
    case = recovered_board_case
    source = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    profile = source.html_profile
    assert profile is not None
    needs_detail = bool(profile.detail_title_selector or profile.detail_date_selector)
    error = "title or registration-date element missing" if needs_detail else "container missing"
    with pytest.raises(ValueError, match=error):
        parse_profiled_html(
            case["list_html"] if needs_detail else "<h1>Page Not Found</h1>",
            list_url=source.list_url, profile=profile,
            detail_loader=Mock(return_value="<h1>Page Not Found</h1>"),
        )


def test_recovered_board_fixtures_are_sanitized(recovered_board_case: dict[str, str]) -> None:
    case = recovered_board_case
    for key in ("list_html", "detail_html"):
        soup = BeautifulSoup(case[key], "html5lib")
        assert not soup.select("script,style,input,iframe")
        assert not any(label in soup.get_text() for label in ("담당자", "연락처", "전화번호"))


def test_october_22_boards_are_enabled_without_historical_search_cutoffs() -> None:
    settings = load_source_subset(
        ROOT / "config/batch-cafe.example.toml",
        ["jemulpo_eminwon", "cheonan_uc", "gimje_education", "geoje_gohyeon", "gimhae_cultural"],
    )
    assert set(settings.enabled_sources) == {
        "jemulpo_eminwon", "cheonan_uc", "gimje_education", "geoje_gohyeon", "gimhae_cultural",
    }
    for source in settings.sources.values():
        assert source.fixture_path is None and not source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 100
    assert settings.sources["jemulpo_eminwon"].available_from == date(2026, 7, 1)
    assert settings.sources["gimje_education"].html_profile.two_digit_year_base == 2000
    source = load_config(ROOT / "config/batch-jeonnam-daejeon-ten.example.toml").sources["daejeon"]
    query = parse_qs(urlparse(source.list_url).query)
    assert "conifmstdt" not in query and "conifmenddt" not in query


def test_geoje_recovers_body_keyword_without_importing_navigation_text() -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/cafe_20261022_profiles.json").read_text(encoding="utf-8"),
    )
    case = cases["geoje_gohyeon"]
    source = load_config(ROOT / case["config_path"]).sources["geoje_gohyeon"]
    assert source.html_profile is not None
    assert "평가위원" not in case["title"]
    candidate = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )[0]
    assert "평가위원" in candidate.body_text
    assert candidate.title == case["title"]
    detail = BeautifulSoup(case["detail_html"], "html5lib")
    body = detail.select_one("#bo_v_con")
    assert body is not None
    body.string = "축제 행사 운영 안내"
    unrelated = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=source.html_profile,
        detail_loader=Mock(return_value=str(detail) + "<nav>평가위원 모집</nav>"),
    )[0]
    assert "평가위원" not in unrelated.searchable_text



def test_october_21_boards_and_jeju_have_no_fixed_search_dates() -> None:
    settings = load_source_subset(
        ROOT / "config/batch-cafe.example.toml",
        read_cases("cafe_20261021_profiles.json"),
    )
    assert set(settings.enabled_sources) == {
        "seoul_women", "incheon_seohae_culture", "jeonnam_tourism",
        "jeju_international_university",
    }
    for config in settings.sources.values():
        assert config.fixture_path is None and not config.recruitment_only
        assert config.request_strategy.verify_tls and config.max_pages == 100
    profile = settings.sources["jeonnam_tourism"].html_profile
    assert profile.page_path_template == "/plaza/notice/lists/{page}"
    assert profile.page_number_selector and not profile.page_param
    source = load_config(
        ROOT / "config/batch-gyeongnam-jeju-final-twenty.example.toml",
    ).sources["jeju"]
    query = parse_qs(urlparse(source.list_url).query)
    assert "conIfmStdt" not in query and "conIfmEnddt" not in query


def test_seohae_uses_registration_date_instead_of_date_in_title() -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/cafe_20261021_profiles.json").read_text(encoding="utf-8"),
    )
    case = cases["incheon_seohae_culture"]
    assert "2026-05-18" in case["title"]
    assert case["date"] == "2026-10-20"


HIBRAIN_CASES = json.loads(
    (ROOT / "tests/fixtures/hibrain_profiles.json").read_text(encoding="utf-8"),
)


@pytest.mark.parametrize("key", HIBRAIN_CASES)
def test_hibrain_terminal_pages_are_explicitly_empty(key: str) -> None:
    case = HIBRAIN_CASES[key]
    source = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    assert source.html_profile is not None
    assert parse_profiled_html(
        case["empty_html"], list_url=source.list_url, profile=source.html_profile,
        expected_page=2,
    ) == []


def test_hibrain_sources_and_nowon_original_board_remain_enabled() -> None:
    seoul = load_config(ROOT / "config/batch-seoul-ten.example.toml")
    assert {"nowon", "nowon_gosi"} <= set(seoul.enabled_sources)
    assert "q_bbsCode=1004" in seoul.sources["nowon"].list_url
    assert "q_bbsCode=1003" in seoul.sources["nowon_gosi"].list_url
    config_path = "config/batch-hibrain.example.toml"
    settings = load_source_subset(
        ROOT / config_path,
        (c["slug"] for c in HIBRAIN_CASES.values() if c["config_path"] == config_path),
    )
    assert len(settings.enabled_sources) == 30
    assert set(settings.enabled_sources) == {
        c["slug"] for c in HIBRAIN_CASES.values() if c["config_path"] == config_path
    }
    for config in [seoul.sources["nowon_gosi"], *settings.sources.values()]:
        assert config.fixture_path is None and not config.recruitment_only
        assert config.request_strategy.verify_tls and config.max_pages == 100
        assert "hibrain.net" not in config.list_url
        assert not any("date" in key.lower() for key in parse_qs(urlparse(config.list_url).query))
    assert settings.sources["khoa"].html_profile.id_format == "zero_padded_numeric"
    assert settings.sources["keiti"].html_profile.request_method == "POST"


def test_changwon_expired_unlinked_notice_does_not_block_public_notice() -> None:
    case = HIBRAIN_CASES["changwon"]
    source = load_config(ROOT / case["config_path"]).sources["changwon"]
    profile = source.html_profile
    assert profile is not None
    soup = BeautifulSoup(case["list_html"], "html5lib")
    container = soup.select_one(profile.container_selector)
    assert container is not None
    row = BeautifulSoup(
        '<tr><td>491</td><td>공고</td><td class="tal">접수가 끝난 평가위원 모집</td>'
        '<td></td><td>2026-10-15</td><td>20261015 ~ 20261021</td></tr>',
        "html.parser",
    ).tr
    container.select_one("tbody").append(row)
    candidates = parse_profiled_html(
        str(soup), list_url=source.list_url, profile=profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert [candidate.url for candidate in candidates] == [case["url"]]


def test_ansan_uses_listing_date_when_detail_has_no_registration_date() -> None:
    batch = PROFILE_BATCHES["gyeonggi_cities_ten"]
    case = batch.cases["ansan"]
    source = batch.settings.sources["ansan"]
    profile = source.html_profile
    assert profile is not None and not profile.detail_date_selector
    assert "2026-10-01" not in case["detail_html"]
    candidates = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=profile,
        detail_loader=Mock(return_value=case["detail_html"] + "<p>접수 마감: 2026-10-09</p>"),
    )
    assert [str(c.published_date) for c in candidates] == ["2026-10-01"]


@pytest.mark.parametrize("message", [
    "등록된 내용이 없습니다.", "등록/검색된 정보가 없습니다.", "고시공고 결과가 없습니다.",
])
def test_public_empty_messages_do_not_hide_valid_links(message: str) -> None:
    case = HIBRAIN_CASES["seongnam_youth"]
    source = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    profile = source.html_profile
    assert profile is not None
    empty = case["empty_html"].replace("검색 결과가 없습니다.", message)
    assert parse_profiled_html(empty, list_url=source.list_url, profile=profile) == []
    listing = case["list_html"].replace(case["title"], message)
    candidates = parse_profiled_html(
        listing, list_url=source.list_url, profile=profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert [c.url for c in candidates] == [case["url"]]


def test_october_30_channels_remain_public_without_replacing_dobong_notices() -> None:
    seoul = load_config(ROOT / "config/batch-seoul-ten.example.toml")
    assert {"dobong", "dobong_gosi"} <= set(seoul.enabled_sources)
    config = load_source_subset(
        ROOT / "config/batch-cafe.example.toml",
        ["incheon_ccei", "anseong_industry"],
    )
    assert set(config.enabled_sources) == {"incheon_ccei", "anseong_industry"}
    for source in [seoul.sources["dobong_gosi"], *config.sources.values()]:
        assert source.fixture_path is None and not source.recruitment_only
        assert source.request_strategy.verify_tls and source.request_strategy.session
    assert config.sources["anseong_industry"].html_profile.id_format == "alphanumeric"


def test_asbiz_registration_date_does_not_use_earlier_body_signature() -> None:
    case = json.loads(
        (ROOT / "tests/fixtures/cafe_20261030_profiles.json").read_text(encoding="utf-8"),
    )["anseong_industry"]
    config = load_config(ROOT / case["config_path"]).sources["anseong_industry"]
    assert "2026년 10월 27일" in case["detail_html"]
    notices = parse_profiled_html(
        case["list_html"], list_url=config.list_url, profile=config.html_profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert [(n.title, str(n.published_date), n.url) for n in notices] == [
        (case["title"], "2026-10-28", case["url"]),
    ]


def test_suwon_current_empty_search_has_a_valid_pager_outside_the_table() -> None:
    config = load_config(
        ROOT / "config/batch-daejeon-ulsan-sejong-gyeonggi-ten.example.toml",
    ).sources["suwon"]
    html = (
        '<table class="p-table"><tbody></tbody></table>'
        '<div class="p-empty">등록된 게시물이 없습니다.</div>'
        '<div class="p-pagination"><strong class="p-page__link active">1</strong></div>'
    )
    assert parse_profiled_html(
        html, list_url=config.list_url, profile=config.html_profile, expected_page=1,
    ) == []
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            html, list_url=config.list_url, profile=config.html_profile, expected_page=2,
        )


def test_muan_public_portal_empty_search_does_not_accept_firewall_documents() -> None:
    config = load_config(ROOT / "config/batch-jeonnam-counties-ten.example.toml").sources["muan"]
    assert urlparse(config.list_url).hostname == "www.muan.go.kr"
    assert parse_qs(urlparse(config.list_url).query)["search_type"] == ["title"]
    html = (
        '<table class="board_t1"><tbody><tr>'
        '<td class="list_empty" colspan="5">검색내역이 없습니다.</td>'
        '</tr></tbody></table>'
    )
    assert parse_profiled_html(
        html, list_url=config.list_url, profile=config.html_profile,
    ) == []
    with pytest.raises(ValueError, match="listing container missing"):
        parse_profiled_html(
            "<h1>Web firewall security policies: blocked.</h1>",
            list_url=config.list_url, profile=config.html_profile,
        )


def test_hibrain_route_additions_use_public_boards_without_pinned_notice_ids() -> None:
    path = "config/batch-hibrain.example.toml"
    settings = load_config(ROOT / path)
    cases = json.loads(
        (ROOT / "tests/fixtures/hibrain_routes_profiles.json").read_text(encoding="utf-8"),
    )
    additions = {slug: c for slug, c in cases.items() if c["config_path"] == path}
    assert len(additions) == 30
    assert set(settings.enabled_sources) == {
        "andong_related", "kigas_notices", "kila_news", "railway_notices",
        "wonkwang_contract", "woo_jin_metro_ui", *additions,
        *(c["slug"] for c in HIBRAIN_CASES.values() if c["config_path"] == path),
    }
    for slug in additions:
        source = settings.sources[slug]
        recruitment_only = slug == "gimhae_bio_industry"
        assert source.fixture_path is None and source.request_strategy.verify_tls
        assert source.recruitment_only == recruitment_only
        assert source.max_pages == (10 if recruitment_only else 100)
        assert "hibrain.net" not in source.list_url
        assert not {
            "articleSeq", "list_no", "msg_seq", "wr_id", "boardNo", "bbsData",
            "idx", "bbsSn", "board_seq", "not_ancmt_mgt_no",
        } & parse_qs(urlparse(source.list_url).query).keys()
    assert {slug for slug in settings.enabled_sources
            if settings.sources[slug].request_strategy.transport == "windows_curl"} == {
        "sscmc_notice",
    }
    # 부산TP 목록은 만료일을 표시하므로 등록일의 대체값으로 사용하지 않는다.
    profile = settings.sources["busan_tp_notice"].html_profile
    assert profile is not None and not profile.date_selector
    assert "작성일" in profile.detail_date_selector
    for slug in ("gyeongbuk_rise", "gyeongnam_tourism"):
        profile = settings.sources[slug].html_profile
        assert profile is not None and profile.total_count_selector


def test_rise_terminal_page_can_have_zero_pager_and_no_notice_container() -> None:
    source = load_config(ROOT / "config/batch-hibrain.example.toml").sources[
        "gyeongbuk_rise"
    ]
    html = (
        '<div class="noticeBox"><div class="ntCont">'
        '<div class="pageCount"><span class="allPost">6</span>'
        '<span class="paging">0</span></div>'
        '<div style="text-align: center;"><p>게시글이 없습니다.</p></div>'
        '</div></div>'
    )
    assert parse_profiled_html(
        html, list_url=source.list_url, profile=source.html_profile, expected_page=2,
    ) == []


def test_muan_current_empty_listing_does_not_synthesize_an_archived_notice() -> None:
    source = load_config(ROOT / "config/batch-jeonnam-counties-ten.example.toml").sources[
        "muan"
    ]
    detail = Mock()
    html = (
        '<table class="board_t1"><tbody><tr>'
        '<td class="list_empty" colspan="5">검색내역이 없습니다.</td>'
        '</tr></tbody></table>'
    )
    assert parse_profiled_html(
        html, list_url=source.list_url, profile=source.html_profile, detail_loader=detail,
    ) == []
    detail.assert_not_called()


def test_added_repost_boards_preserve_original_channels_and_search_contracts() -> None:
    settings = load_config(ROOT / "config/batch-hibrain.example.toml")
    assert {"dtmsa_bid", "esk_recruit"} <= set(settings.enabled_sources)
    profile = settings.sources["dtmsa_bid"].html_profile
    assert profile is not None and profile.request_method == "POST"
    assert profile.search_param == "searchword"
    assert parse_qs(urlparse(settings.sources["dtmsa_bid"].list_url).query) == {
        "searchKey": ["ARTICLE_TITLE"],
    }
    assert settings.sources["esk_recruit"].municipality == "대한인간공학회"
    for config_path, slug in (
        ("config/batch-cafe.example.toml", "daegu_market"),
        ("config/batch-cafe.example.toml", "daegu_market_announcement"),
    ):
        original = load_config(ROOT / config_path)
        assert slug in original.enabled_sources
    assert "kigas_notices" in settings.enabled_sources


def test_esk_blank_terminal_cell_cannot_hide_a_real_notice_link() -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/hibrain_routes_profiles.json").read_text(encoding="utf-8"),
    )
    case = cases["esk_recruit"]
    source = load_config(ROOT / case["config_path"]).sources["esk_recruit"]
    assert parse_profiled_html(
        case["empty_html"], list_url=source.list_url, profile=source.html_profile,
        expected_page=2,
    ) == []
    html = BeautifulSoup(case["empty_html"], "html5lib")
    cell = html.select_one("td.empty_table")
    assert cell is not None
    cell.append(BeautifulSoup(
        '<a href="/recruit/999">평가위원 모집</a>', "html5lib",
    ).a)
    # A linked row with broken metadata must fail rather than become an empty result.
    with pytest.raises(ValueError, match="notice link missing"):
        parse_profiled_html(
            str(html), list_url=source.list_url, profile=source.html_profile, expected_page=2,
        )


def test_october_31_boards_extend_existing_channels_without_pinned_dates() -> None:
    settings = load_source_subset(
        ROOT / "config/batch-cafe.example.toml",
        read_cases("cafe_20261031_profiles.json"),
    )
    assert set(settings.enabled_sources) == {
        "yongsan_gosi", "ebs_notice", "jecheon_cultural",
        "gwangju_bukgu_facilities", "ulsan_volunteer", "kfce_notice", "silla_heritage",
    }
    assert "yongsan" in load_config(
        ROOT / "config/batch-seoul-five.example.toml",
    ).enabled_sources
    for slug in settings.enabled_sources:
        source = settings.sources[slug]
        assert not source.recruitment_only
        assert source.request_strategy.verify_tls
        assert source.fixture_path is None
        assert not {"sdate", "edate", "bgnDts", "endDts", "idx", "nttId", "postId", "aseq"} & (
            parse_qs(urlparse(source.list_url).query).keys()
        )


    assert settings.sources["kfce_notice"].html_profile.search_param == "sv"
    assert parse_qs(urlparse(settings.sources["kfce_notice"].list_url).query)["sk"] == [
        "article_title",
    ]
    assert urlparse(settings.sources["silla_heritage"].list_url).scheme == "http"
    for source in SourceRegistry(
        settings, RequestsHttpClient(), ZoneInfo(settings.timezone),
    ).build_enabled_sources():
        if source.slug in {"kfce_notice", "silla_heritage"}:
            assert isinstance(source, GenericEngineSource)
            assert source.request_headers["User-Agent"].startswith("Mozilla/5.0")


@pytest.mark.parametrize("metadata,valid", [
    ("작성일 26-10-30 15:05", True),
    ("작성일 26-10-30 00:00:59", True),
    ("작성일 26-10-30 24:00", False),
    ("작성일 26-10-30 15:60", False),
    ("작성일 26-02-30 15:05", False),
    ("접수기간 26-10-30 15:05", False),
    ("작성일 26-10-30 ~ 26-11-04", False),
])
def test_explicit_two_digit_registration_metadata_with_time(
    metadata: str, valid: bool,
) -> None:
    case = json.loads(
        (ROOT / "tests/fixtures/cafe_20261031_profiles.json").read_text(encoding="utf-8"),
    )["jecheon_cultural"]
    config = load_config(ROOT / case["config_path"]).sources["jecheon_cultural"]
    profile = config.html_profile
    assert profile is not None
    detail = BeautifulSoup(case["detail_html"], "html5lib")
    node = detail.select_one(profile.detail_date_selector)
    assert node is not None
    node.string = metadata
    loader = Mock(return_value=str(detail))
    if valid:
        notices = parse_profiled_html(
            case["list_html"], list_url=config.list_url, profile=profile,
            detail_loader=loader,
        )
        assert [notice.published_date for notice in notices] == [date(2026, 10, 30)]
    else:
        with pytest.raises(ValueError, match="invalid title or registration date"):
            parse_profiled_html(
                case["list_html"], list_url=config.list_url, profile=profile,
                detail_loader=loader,
            )


@pytest.mark.parametrize("date_order,reverse_rows,error", [
    ("descending", False, ""),
    ("", False, "historical page unavailable"),
    ("descending", True, "registration dates are not descending"),
])
def test_ordered_board_keeps_current_notice_when_older_page_is_broken(
    date_order: str, reverse_rows: bool, error: str,
) -> None:
    case = json.loads(
        (ROOT / "tests/fixtures/cafe_20261031_profiles.json").read_text(encoding="utf-8"),
    )["jecheon_cultural"]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = ["jecheon_cultural"]
    profile = settings.sources["jecheon_cultural"].html_profile
    assert profile is not None
    profile.date_order = date_order
    listing = BeautifulSoup(case["list_html"], "html5lib")
    row = listing.select_one(profile.row_selector)
    assert row is not None
    # Parse a standalone table row in its required table context.
    older_row = BeautifulSoup(
        "<table><tbody>" + str(row).replace("686", "675") + "</tbody></table>", "html5lib",
    ).select_one("tr")
    assert older_row is not None
    if reverse_rows:
        row.insert_before(older_row)
    else:
        row.insert_after(older_row)
    old_url = case["url"].replace("686", "675")
    old_detail = case["detail_html"].replace("26-10-30", "26-10-02")
    client = Mock()

    def response(url: str, **_: object) -> str:
        if url == case["url"]:
            return str(case["detail_html"])
        if url == old_url:
            return str(old_detail)
        if parse_qs(urlparse(url).query)["page"] == ["1"]:
            return str(listing)
        raise ValueError("historical page unavailable")

    client.get_text.side_effect = response
    source = SourceRegistry(
        settings, client, ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    if error:
        with pytest.raises(ValueError, match=error):
            source.fetch(date(2026, 10, 30))
    else:
        notices = source.fetch(date(2026, 10, 30))
        assert [notice.url for notice in notices] == [case["url"]]
        assert not any("page=2" in call.args[0] for call in client.get_text.call_args_list)



def test_second_hibrain_boards_use_public_searches_and_keep_existing_channels() -> None:
    settings = load_config(ROOT / "config/batch-hibrain.example.toml")
    slugs = {
        "daegu_sports", "jeonbuk_education", "gri_bid", "gwangju_cultural",
        "incheon_smartcity", "eumseong_notice", "sancheong_recruit", "jejusi_notice",
    }
    assert slugs <= set(settings.enabled_sources)
    assert settings.sources["gri_bid"].html_profile.link_attribute == "onclick"
    assert "공고일자" in settings.sources["gri_bid"].html_profile.detail_date_selector
    assert not settings.sources["gwangju_cultural"].html_profile.date_order
    assert not settings.sources["incheon_smartcity"].html_profile.date_order
    for config_path, slug in (
        ("config/batch-chungbuk-chungnam-jeonbuk-thirty.example.toml", "eumseong"),
        ("config/batch-gyeongnam-jeju-final-twenty.example.toml", "sancheong"),
        ("config/batch-gyeongnam-jeju-final-twenty.example.toml", "jeju"),
    ):
        assert slug in load_config(ROOT / config_path).enabled_sources
    sources = SourceRegistry(
        settings, RequestsHttpClient(), ZoneInfo(settings.timezone),
    ).build_enabled_sources()
    jejusi = next(source for source in sources if source.slug == "jejusi_notice")
    assert isinstance(jejusi, GenericEngineSource)
    query = parse_qs(urlparse(jejusi._build_request_url(page_index=2)).query)
    assert query["searchText"] == ["평가"]
    assert query["currentPageNo"] == ["2"]
    sports = next(source for source in sources if source.slug == "daegu_sports")
    assert isinstance(sports, GenericEngineSource)
    query = parse_qs(urlparse(sports._build_request_url(page_index=2)).query)
    assert query["start"] == ["10"] and query["keyword"] == ["평가위원"]


def test_bdi_starts_with_first_page_and_finds_notice_on_second_page() -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/hibrain_routes_profiles.json").read_text(encoding="utf-8"),
    )
    case = cases["bdi_notice"]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = ["bdi_notice"]
    client = Mock()
    calls: list[str] = []

    def respond(url: str, **kwargs: object) -> str:
        assert kwargs["use_session"] and kwargs["verify_tls"]
        calls.append(url)
        if url == case["url"]:
            return str(case["detail_html"])
        if url == case["preceding_url"]:
            return str(case["preceding_detail_html"])
        page = int(urlparse(url).path.rsplit("/", 1)[1])
        assert page in {1, 2, 3}
        if page == 1:
            return str(case["preceding_list_html"])
        if page == 2:
            return str(case["list_html"])
        soup = BeautifulSoup(case["list_html"], "html5lib")
        soup.select_one("#tablelist tbody").clear()
        return str(soup)

    client.get_text.side_effect = respond
    source = SourceRegistry(
        settings, client, ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    for _ in range(2):
        notices = source.fetch(date.fromisoformat(case["date"]))
        assert [(n.title, str(n.published_date), n.url) for n in notices] == [
            (case["title"], case["date"], case["url"]),
        ]
    assert calls == [
        "https://www.bdi.re.kr/www/board/1/1", case["preceding_url"],
        "https://www.bdi.re.kr/www/board/1/2", case["url"],
        "https://www.bdi.re.kr/www/board/1/3",
    ]
    client.post_text.assert_not_called()

@pytest.mark.parametrize("evaluator_body", [True, False])
def test_suwon_committee_recovery_requires_evaluator_keywords_in_scoped_body(
    evaluator_body: bool,
) -> None:
    case = json.loads(
        (ROOT / "tests/fixtures/cafe_20261103_profiles.json").read_text(encoding="utf-8"),
    )["suwon_committee"]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = ["suwon_committee"]
    detail = BeautifulSoup(case["detail_html"], "html5lib")
    if not evaluator_body:
        body = detail.select_one("td.p-table__content")
        assert body is not None
        body.string = "민간위탁기관선정심의위원회 위원 후보자를 모집합니다."
    # Unrelated navigation cannot turn a non-evaluator committee into a match.
    payload = str(detail) + "<aside>다른 게시판 평가위원 모집</aside>"
    client = Mock()

    def response(url: str, **_: object) -> str:
        if url == case["url"]:
            return payload
        query = parse_qs(urlparse(url).query)
        assert query["q_searchVal"] == ["심의위원"]
        return (case["list_html"] if query["q_currPage"] == ["1"] else (
            '<table class="p-table"><tbody></tbody></table>'
            '<div class="p-pagination"><strong class="p-page__link active">2</strong></div>'
        ))

    client.get_text.side_effect = response
    source = SourceRegistry(
        settings, client, ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    notices = source.fetch(date(2026, 11, 2))
    assert [notice.url for notice in notices] == ([case["url"]] if evaluator_body else [])
    if notices:
        assert notices[0].title == case["title"]
        assert "평가위원" not in notices[0].title


def test_november_4_routes_activate_existing_collectors_and_preserve_board_boundaries() -> None:
    settings = load_source_subset(
        ROOT / "config/batch-cafe.example.toml",
        [*read_cases("cafe_20261104_profiles.json"), "hanam", "jecheon"],
    )
    assert set(settings.enabled_sources) == {
        "gogung_bid", "gyeonggi_sports_bid", "sokcho_cultural", "pohang_tp_notice",
        "hanam", "jecheon",
    }
    base = load_config(ROOT / "config/config.example.toml")
    for slug in ("hanam", "jecheon"):
        assert settings.sources[slug] == base.sources[slug]
        assert slug not in base.enabled_sources
    previous = load_config(ROOT / "config/batch-cafe.example.toml")
    old = parse_qs(urlparse(previous.sources["pohang_technopark"].list_url).query)
    new = parse_qs(urlparse(settings.sources["pohang_tp_notice"].list_url).query)
    assert old["manage_idx"] == ["15"] and new["manage_idx"] == ["2"]
    for source in settings.sources.values():
        assert source.fixture_path is None and source.request_strategy.verify_tls
        assert not {"srchBeginDt", "srchEndDt", "q_startDt", "q_endDt", "conIfmEnddt"} & (
            set(parse_qs(urlparse(source.list_url).query))
        )


def test_wonkwang_public_post_extracts_official_date_and_caches_without_url_tokens(
    wonkwang_contract_case: dict[str, str], wonkwang_contract_http: list[str],
) -> None:
    case = wonkwang_contract_case
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [case["slug"]]
    source = SourceRegistry(settings, RequestsHttpClient(), ZoneInfo(settings.timezone))
    collector = source.build_enabled_sources()[0]
    assert isinstance(collector, WonkwangContractSource)
    collector.throttle_seconds = 0
    for _ in range(2):
        notices = collector.fetch(date.fromisoformat(case["date"]))
        assert [(n.title, str(n.published_date), n.url) for n in notices] == [
            (case["title"], case["date"], case["url"]),
        ]
    assert len(wonkwang_contract_http) == 3
    assert not any(k in notices[0].url for k in ("g_secure", "g_ipaddr", "g_accountyear"))
    assert not notices[0].title.startswith("work")


@pytest.mark.parametrize("failure", ["token", "page", "total", "identity", "date"])
def test_wonkwang_rejects_incomplete_forms_and_unverified_detail(
    wonkwang_contract_case: dict[str, str], wonkwang_contract_http: list[str], failure: str,
) -> None:
    case = wonkwang_contract_case
    if failure == "token":
        case["seed_html"] = case["seed_html"].replace('name="g_secure"', 'name="unrelated"')
    elif failure == "page":
        case["list_html"] = case["list_html"].replace('name="page" value="1"',
                                                    'name="page" value="2"')
    elif failure == "total":
        case["list_html"] = case["list_html"].replace('name="tpage" value="1"',
                                                    'name="tpage" value="invalid"')
    elif failure == "identity":
        identifier = parse_qs(urlparse(case["url"]).query)["notice_no"][0]
        case["detail_html"] = case["detail_html"].replace(identifier, "b" * 32)
    else:
        case["detail_html"] = case["detail_html"].replace("2026.10.30", "2026.02.30")
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [case["slug"]]
    collector = SourceRegistry(
        settings, RequestsHttpClient(), ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    collector.throttle_seconds = 0
    with pytest.raises(ValueError):
        collector.fetch(date.fromisoformat(case["date"]))


def test_wonkwang_tracks_rotating_context_and_server_page_count(
    wonkwang_contract_case: dict[str, str], wonkwang_contract_http: list[str],
) -> None:
    case = wonkwang_contract_case
    case["list_html"] = case["list_html"].replace('name="tpage" value="1"',
                                                'name="tpage" value="2"')
    empty = BeautifulSoup(case["list_html"], "html5lib")
    empty.select_one('.cards').decompose()
    empty.select_one('input[name="page"]')["value"] = "2"
    empty.select_one('.page > .on').string = "2"
    case["empty_html"] = str(empty)
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [case["slug"]]
    collector = SourceRegistry(
        settings, RequestsHttpClient(), ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    collector.throttle_seconds = 0
    assert len(collector.fetch(date.fromisoformat(case["date"]))) == 1
    assert len(wonkwang_contract_http) == 4


def test_wonkwang_uses_the_boards_selected_year_instead_of_a_fixed_year(
    wonkwang_contract_case: dict[str, str], wonkwang_contract_http: list[str],
) -> None:
    case = wonkwang_contract_case
    for name in ("seed_html", "list_html", "detail_html", "date"):
        case[name] = case[name].replace("2026", "2027")
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [case["slug"]]
    collector = SourceRegistry(
        settings, RequestsHttpClient(), ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    collector.throttle_seconds = 0
    assert collector.fetch(date.fromisoformat(case["date"]))[0].published_date.year == 2027


def test_november_5_selection_keyword_is_scoped_to_the_supplemental_board() -> None:
    settings = load_source_subset(
        ROOT / "config/batch-cafe.example.toml",
        read_cases("cafe_20261105_profiles.json"),
    )
    assert set(settings.enabled_sources) == set(settings.sources)
    assert len(settings.enabled_sources) == 12
    special = settings.sources["hwaseong_selection"]
    assert special.keywords == ("사업계획서 선정심의위원",)
    previous = load_config(ROOT / "config/batch-gyeonggi-gangwon-chungbuk-thirty.example.toml")
    assert previous.sources["hwaseong"].keywords == ("평가위원",)
    assert previous.sources["hwaseong"].recruitment_only
    for slug, source in settings.sources.items():
        assert source.fixture_path is None and source.request_strategy.verify_tls
        if slug != "hwaseong_selection":
            assert source.keywords == ("평가위원",)
        query = parse_qs(urlparse(source.list_url).query)
        assert not {"searchStrtDt", "searchEndDt", "srchBeginDt", "srchEndDt"} & query.keys()
    old = load_config(ROOT / "config/batch-jeonbuk-gyeongbuk-gyeongnam-thirty.example.toml")
    assert "boardMngNo=71" in old.sources["gyeongbuk"].list_url
    assert "boardMngNo=8" in settings.sources["gyeongbuk_announcements"].list_url
    assert urlparse(old.sources["goryeong"].list_url).hostname == "www.goryeong.go.kr"
    assert urlparse(settings.sources["goryeong_eminwon"].list_url).hostname == (
        "eminwon.goryeong.go.kr"
    )


def test_accessibility_page_label_keeps_selected_page_validation() -> None:
    case = json.loads(
        (ROOT / "tests/fixtures/cafe_20261105_profiles.json").read_text(encoding="utf-8"),
    )["kotsa_notice"]
    source = load_config(ROOT / case["config_path"]).sources["kotsa_notice"]
    profile = source.html_profile
    assert profile is not None
    soup = BeautifulSoup(case["list_html"], "html5lib")
    pager = soup.select_one(profile.page_number_selector)
    assert pager is not None
    assert pager.select_one(".hidden") is not None
    candidates = parse_profiled_html(
        str(soup), list_url=source.list_url, profile=profile,
        detail_loader=Mock(return_value=case["detail_html"]), expected_page=1,
    )
    assert [candidate.url for candidate in candidates] == [case["url"]]
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            str(soup), list_url=source.list_url, profile=profile,
            detail_loader=Mock(return_value=case["detail_html"]), expected_page=2,
        )
