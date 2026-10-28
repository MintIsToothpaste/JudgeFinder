from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup, Comment
from profile_cases import PROFILE_BATCHES


def test_settings_do_not_enable_unverified_sources_or_fixtures() -> None:
    batch = PROFILE_BATCHES["chungbuk_chungnam_jeonbuk_thirty"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 28
    assert {"dangjin", "geumsan"}.isdisjoint(batch.settings.enabled_sources)
    assert len({s.municipality for s in batch.settings.sources.values()}) == 28
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 80
        assert urlparse(source.list_url).scheme == "https"
        if "eminwon" in urlparse(source.list_url).hostname:
            assert parse_qs(urlparse(source.list_url).query)["list_gubun"] == ["A"]
    for slug in [slug for slug, source in batch.settings.sources.items() if source.html_profile]:
        expected_format = "hex32" if slug in {"jeonju", "namwon"} else "numeric"
        assert batch.settings.sources[slug].html_profile.id_format == expected_format
    profile = batch.settings.sources["jeonbuk"].html_profile
    assert profile.date_selector and not profile.detail_date_selector
    assert batch.settings.sources["taean"].html_profile.detail_url_template.endswith(
        "subCheck=N&not_ancmt_mgt_no={id}",
    )


@pytest.mark.parametrize(
    "cases",
    [
        PROFILE_BATCHES["chungbuk_chungnam_jeonbuk_thirty"].cases,
        PROFILE_BATCHES["chungbuk_chungnam_jeonbuk_thirty"].recovered,
    ],
    ids=["batch", "recovered"],
)
def test_fixture_raw_html_does_not_include_contact_values(
    cases: dict[str, dict[str, str]],
) -> None:
    for case in cases.values():
        for key in ("list_html", "detail_html"):
            assert not re.search(
                r"[\w.+-]+@[\w.-]+|\b0\d{1,2}[- ]\d{3,4}[- ]\d{4}\b",
                case.get(key, ""),
            )


def test_profiles_are_isolated_and_new_districts_have_a_start_date() -> None:
    batch = PROFILE_BATCHES["daegu_incheon_ten"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 10
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages >= 40
    assert batch.settings.sources["jemulpo"].available_from == date(2026, 7, 1)
    assert batch.settings.sources["yeongjong"].available_from == date(2026, 7, 1)
    for slug in ["jemulpo", "yeongjong", "michuhol"]:
        profile = batch.settings.sources[slug].html_profile
        assert profile is not None and not profile.search_param
        assert batch.cases[slug]["category"] != "recruitment"


def test_official_archive_scope_and_security_settings() -> None:
    batch = PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"]
    assert len(batch.cases) == len(batch.settings.sources) == 10
    assert len(batch.settings.enabled_sources) == 9
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
        assert source.request_strategy.session and source.request_strategy.referer
    for slug in ["daedeok", "ulsan_junggu", "ulsan_namgu", "ulsan_donggu", "ulsan_bukgu"]:
        assert parse_qs(urlparse(batch.settings.sources[slug].list_url).query)["list_gubun"] == [
            "A"
        ]
    query = parse_qs(urlparse(batch.settings.sources["ulju"].list_url).query)
    assert query["seCode"] == ["04"] and query["searchType"] == ["tit"]
    assert parse_qs(urlparse(batch.settings.sources["suwon"].list_url).query)["q_searchKey"] == [
        "SJ"
    ]


def test_real_response_fixtures_exclude_hidden_fields_scripts_and_contacts() -> None:
    batch = PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"]
    for case in batch.cases.values():
        for key in ("list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert not any(
                label in soup.get_text() for label in ("담당자", "연락처", "전화번호", "문의전화")
            )
    wire = json.loads(batch.cases["gyeonggi"]["list_json"])
    assert set(wire) == {"total", "items"}
    assert set(wire["items"][0]) == {"B_IDX", "WRITE_DATE2", "SUBJECT"}


def test_official_live_profiles_are_isolated_and_explicit() -> None:
    batch = PROFILE_BATCHES["gyeonggi_cities_next_ten"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 10
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
        assert urlparse(source.list_url).scheme == "https"
    for slug in ("guri", "gunpo", "uiwang", "yongin"):
        assert parse_qs(urlparse(batch.settings.sources[slug].list_url).query)["list_gubun"] == [
            "A"
        ]
    osan = batch.settings.sources["osan"]
    assert parse_qs(urlparse(osan.list_url).query)["pbsDivision"] == ["all"]
    yongin, paju = (
        batch.settings.sources["yongin"].html_profile,
        batch.settings.sources["paju"].html_profile,
    )
    assert yongin is not None and paju is not None
    assert yongin.request_method == "POST" and yongin.request_encoding == "utf-8"
    assert parse_qs(urlparse(batch.settings.sources["yongin"].list_url).query)["epcCheck"] == ["Y"]
    assert paju.title_exclude_selector == ".category-label,.ico-new"
    assert batch.cases["namyangju"]["date"] == "2026-03-18"
    assert all(not c["listing_only"] for c in batch.cases.values())


def test_gyeonggi_cities_ten_official_live_profiles_are_isolated_and_explicit() -> None:
    batch = PROFILE_BATCHES["gyeonggi_cities_ten"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 10
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
        assert urlparse(source.list_url).scheme == "https"
    for slug in ("seongnam", "anyang", "goyang"):
        assert parse_qs(urlparse(batch.settings.sources[slug].list_url).query)["list_gubun"] == [
            "A"
        ]
    uijeongbu = batch.settings.sources["uijeongbu"].html_profile
    bucheon = batch.settings.sources["bucheon"].html_profile
    assert uijeongbu is not None and bucheon is not None
    assert uijeongbu.search_param == "searchTxt"
    assert parse_qs(urlparse(batch.settings.sources["uijeongbu"].list_url).query)["searchType"] == [
        "not_ancmt_sj"
    ]
    assert bucheon.detail_date_selector == ("th:-soup-contains-own('게재(공고)일자') + td")
    assert batch.cases["bucheon"]["date"] == "2026-09-28"
    assert batch.cases["pyeongtaek"]["listing_only"]


def test_gyeonggi_gangwon_chungbuk_thirty_settings_are_explicit() -> None:
    batch = PROFILE_BATCHES["gyeonggi_gangwon_chungbuk_thirty"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 28
    assert {"sokcho", "pyeongchang"}.isdisjoint(batch.settings.enabled_sources)
    assert len({s.municipality for s in batch.settings.sources.values()}) == 28
    for source in batch.settings.sources.values():
        assert source.fixture_path is None
        assert source.recruitment_only == (source.slug != "wonju")
        assert source.request_strategy.verify_tls and source.max_pages == 80
        assert urlparse(source.list_url).scheme == "https"
        if "eminwon" in urlparse(source.list_url).hostname:
            assert parse_qs(urlparse(source.list_url).query)["list_gubun"] == ["A"]
    assert batch.settings.sources["yeongdong"].html_profile.id_format == "hex32"
    for slug in [slug for slug, source in batch.settings.sources.items() if source.html_profile]:
        if slug != "yeongdong":
            assert batch.settings.sources[slug].html_profile.id_format == "numeric"
    for slug in ("donghae", "wonju"):
        profile = batch.settings.sources[slug].html_profile
        assert profile.date_selector and not profile.detail_date_selector


def test_only_verified_public_sources_are_enabled() -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 22
    assert len([slug for slug, case in batch.cases.items() if not case.get("empty")]) == 21
    assert len({s.municipality for s in batch.settings.sources.values()}) == 20
    assert "jejusi" not in batch.settings.enabled_sources
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 80
        assert urlparse(source.list_url).scheme == "https"


def test_fixtures_exclude_contact_metadata_and_remote_scripts() -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    for case in batch.cases.values():
        for key in ("list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html5lib")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert not re.search(r"[\w.+-]+@[\w.-]+|\b0\d{1,2}-\d{3,4}-\d{4}\b", soup.get_text())
            assert not any(x in soup.get_text() for x in ("담당자", "연락처", "전화번호"))


def test_only_recovered_sources_are_enabled_and_tls_is_preserved() -> None:
    batch = PROFILE_BATCHES["held_eighteen_recovered"]
    assert (
        set(batch.settings.enabled_sources)
        == set(batch.cases)
        == {
            "pyeongchang",
            "sangju",
            "andong",
            "namyangju",
        }
    )
    assert "isLinkage=Y" in batch.settings.sources["andong"].html_profile.detail_url_template
    assert "list_gubun=A" in batch.settings.sources["sangju"].list_url
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 80


def test_fixtures_do_not_contain_contact_details_or_scripts() -> None:
    batch = PROFILE_BATCHES["held_eighteen_recovered"]
    for case in batch.cases.values():
        for key in ("list_html", "detail_html"):
            soup = BeautifulSoup(case[key], "html5lib")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert not re.search(r"[\w.+-]+@[\w.-]+|\b0\d{1,2}-\d{3,4}-\d{4}\b", soup.get_text())
            assert not any(x in soup.get_text() for x in ("담당자", "연락처", "전화번호"))


def test_isolated_profiles_cover_ten_municipalities_and_both_mokpo_boards() -> None:
    batch = PROFILE_BATCHES["incheon_jeonnam_ten"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 12
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
    for slug in ["seohae", "geomdan", "geomdan_news", "jeonnam_gwangju"]:
        assert batch.settings.sources[slug].available_from == date(2026, 7, 1)
    for slug in ["yeonsu", "namdong", "bupyeong", "gyeyang"]:
        query = parse_qs(urlparse(batch.settings.sources[slug].list_url).query)
        assert query["list_gubun"] == ["A"]
    assert "old_public_notice" in batch.settings.sources["mokpo"].list_url
    assert "old_public_notice" not in batch.settings.sources["mokpo_current"].list_url
    assert "등록 신청" in batch.cases["mokpo"]["title"]
    assert batch.cases["mokpo"]["category"] == "recruitment"


def test_jeonbuk_gyeongbuk_gyeongnam_thirty_settings_are_explicit() -> None:
    batch = PROFILE_BATCHES["jeonbuk_gyeongbuk_gyeongnam_thirty"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 25
    assert {"andong", "sangju", "uiseong", "yecheon", "changwon"}.isdisjoint(
        batch.settings.enabled_sources,
    )
    assert len({s.municipality for s in batch.settings.sources.values()}) == 25
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 80
        assert urlparse(source.list_url).scheme == "https"
        if "eminwon" in urlparse(source.list_url).hostname:
            assert parse_qs(urlparse(source.list_url).query)["list_gubun"] == ["A"]
    for slug in [slug for slug, source in batch.settings.sources.items() if source.html_profile]:
        assert batch.settings.sources[slug].html_profile.id_format == "numeric"
    assert batch.settings.sources["gumi"].html_profile.detail_body_selector == ".view_cont"
    assert batch.settings.sources["yeongyang"].html_profile.detail_title_selector == (
        ".view_title > p.title"
    )
    assert "cmd=258" in batch.settings.sources["seongju"].html_profile.detail_url_template


def test_official_archive_and_search_parameters_cover_ten_municipalities() -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 12
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.source_type == "html" and source.html_profile is not None
        assert source.request_strategy.verify_tls and source.max_pages == 40
    for slug in [*["gokseong", "goheung", "yeongam", "muan"], "boseong", "hwasun", "gurye"]:
        assert parse_qs(urlparse(batch.settings.sources[slug].list_url).query)["list_gubun"] == [
            "A"
        ]
    haenam = batch.settings.sources["haenam"]
    assert parse_qs(urlparse(haenam.list_url).query)["searchType"] == ["notSj"]
    assert haenam.html_profile is not None and haenam.html_profile.page_param == "nowPageNum"
    jangheung = parse_qs(urlparse(batch.settings.sources["jangheung"].list_url).query)
    assert jangheung["category_1"] == ["지난 고시공고"]
    assert jangheung["start_date"] == ["2025-10-05"]
    current = parse_qs(urlparse(batch.settings.sources["jangheung_current"].list_url).query)
    assert "category_1" not in current
    assert "/old_gosi_new" in batch.settings.sources["gangjin"].list_url
    assert "/notice/gosi" in batch.settings.sources["gangjin_current"].list_url


def test_real_response_fixtures_exclude_scripts_comments_hidden_fields_and_contacts() -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    for case in [*batch.cases.values(), *batch.nomination.values()]:
        for key in ("list_html", "empty_list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script, style, input, iframe")
            assert not soup.find_all(string=lambda node: isinstance(node, Comment))
            assert "담당자" not in soup.get_text() and "연락처" not in soup.get_text()


def test_official_city_only_archive_and_search_scope() -> None:
    batch = PROFILE_BATCHES["jeonnam_daejeon_ten"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 10
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
    for slug in ["hampyeong", "daejeon_donggu", "yuseong"]:
        query = parse_qs(urlparse(batch.settings.sources[slug].list_url).query)
        assert query.get("listGubun", query.get("list_gubun")) == ["A"]
    city = batch.settings.sources["daejeon"]
    assert urlparse(city.list_url).path == "/drh/drhGosiList.do"
    query = parse_qs(urlparse(city.list_url).query)
    assert query["gosigbn"] == ["A"] and query["menuSeq"] == ["1908"]
    assert query["conifmstdt"] == ["2025-10-05"] and query["conifmenddt"] == ["2026-10-04"]


def test_jeonnam_daejeon_fixtures_are_sanitized() -> None:
    batch = PROFILE_BATCHES["jeonnam_daejeon_ten"]
    for case in batch.cases.values():
        for key in ("list_html", "detail_html", "empty_list_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda node: isinstance(node, Comment))
            assert "담당자" not in soup.get_text() and "연락처" not in soup.get_text()


def test_official_pagination_and_archive_profiles_cover_ten_municipalities() -> None:
    batch = PROFILE_BATCHES["jeonnam_gwangju_ten"]
    assert len(batch.cases) == len(batch.settings.enabled_sources) == 13
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 40
    profile = batch.settings.sources["suncheon"].html_profile
    assert profile is not None and profile.page_param == "pageIndex"
    assert profile.page_number_selector
    for slug in ["yeosu", "naju", "gwangju_seogu"]:
        assert f"{slug}_current" in batch.settings.enabled_sources
    assert batch.settings.sources["damyang"].json_profile is not None


def test_real_response_fixtures_exclude_scripts_comments_and_hidden_inputs() -> None:
    batch = PROFILE_BATCHES["jeonnam_gwangju_ten"]
    for case in batch.cases.values():
        for key in ("list_html", "empty_list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script, style, input, iframe")
            assert not soup.find_all(string=lambda node: isinstance(node, Comment))
