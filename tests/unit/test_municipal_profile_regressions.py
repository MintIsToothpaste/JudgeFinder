from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from typing import Any
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup
from profile_cases import PROFILE_BATCHES

from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.mapo_search import normalize_search_response
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.notice_classification import (
    NoticeCategory,
    classify_notice_title,
)
from judgefinder.domain.source_profiles import HtmlProfile


@pytest.mark.parametrize("slug", PROFILE_BATCHES["busan_daegu_ten"].cases)
def test_invalid_listing_does_not_become_a_successful_empty_result(slug: str) -> None:
    batch = PROFILE_BATCHES["busan_daegu_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h2>Service unavailable</h2><table><tr><td>2026-10-03</td></tr></table>",
            list_url=source.list_url,
            profile=source.html_profile,
        )


def test_archive_profiles_do_not_keep_relative_dates_or_fixed_2018_year() -> None:
    batch = PROFILE_BATCHES["busan_daegu_ten"]
    assert len(batch.settings.enabled_sources) == len(batch.cases) == 10
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        query = parse_qs(urlparse(source.list_url).query, keep_blank_values=True)
        assert "yyyy" not in query and "recent_mm" not in query
        assert source.fixture_path is None
        assert source.recruitment_only and source.request_strategy.verify_tls
        if source.slug not in {"yeonje", "daegu", "daegu_seogu"}:
            assert query["list_gubun"] == ["A"]
    assert parse_qs(
        urlparse(batch.settings.sources["daegu_seogu"].list_url).query,
        keep_blank_values=True,
    )["endYn"] == [""]
    assert parse_qs(urlparse(batch.settings.sources["daegu"].list_url).query)["searchGosi_gbn"] == [
        "A"
    ]


def test_data_action_profiles_preserve_menu_context_and_notice_identifier() -> None:
    batch = PROFILE_BATCHES["busan_daegu_ten"]
    for slug, menu_key, menu_id in [
        ("yeonje", "mId", "0206030000"),
        ("daegu_seogu", "mid", "0601020100"),
    ]:
        profile = batch.settings.sources[slug].html_profile
        assert profile is not None and profile.link_attribute == "data-action"
        assert not profile.id_pattern
        query = parse_qs(urlparse(batch.cases[slug]["url"]).query)
        assert query[menu_key] == [menu_id] and int(query["notAncmtMgtNo"][0]) > 0


def test_suyeong_creation_date_and_full_detail_title_are_used() -> None:
    batch = PROFILE_BATCHES["busan_daegu_ten"]
    profile = batch.settings.sources["suyeong"].html_profile
    assert profile is not None
    assert "작성일" in profile.detail_date_selector
    assert "..." in batch.cases["suyeong"]["list_html"]
    assert "..." not in batch.cases["suyeong"]["title"]


def test_clickable_donggu_table_cell_and_daegu_form_are_declarative() -> None:
    batch = PROFILE_BATCHES["busan_daegu_ten"]
    profile = batch.settings.sources["daegu_donggu"].html_profile
    assert profile is not None and profile.link_selector == "td:nth-of-type(3)"
    assert (
        profile.link_attribute == "onclick"
        and "<a " not in batch.cases["daegu_donggu"]["list_html"]
    )
    query = parse_qs(urlparse(batch.cases["daegu"]["url"]).query)
    assert query["gosi_gbn"] == ["A"]
    assert query["menu_link"] == ["/front/daeguSidoGosi/daeguSidoGosiView.do"]


@pytest.mark.parametrize("slug", PROFILE_BATCHES["busan_ten"].cases)
def test_invalid_listing_is_not_a_successful_empty_search(slug: str) -> None:
    batch = PROFILE_BATCHES["busan_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h2>The request / response that are contrary to the Web firewall "
            "security policies have been blocked.</h2><table><tr><td>Detect time</td>"
            "<td>2026-10-03</td></tr></table>",
            list_url=source.list_url,
            profile=source.html_profile,
        )


def test_archive_routes_do_not_apply_portal_relative_date_cutoff() -> None:
    batch = PROFILE_BATCHES["busan_ten"]
    assert len(batch.settings.enabled_sources) == 10
    assert len({s.municipality for s in batch.settings.sources.values()}) == 10
    for source in batch.settings.sources.values():
        params = parse_qs(urlparse(source.list_url).query)
        assert params["list_gubun"] == ["A"]
        assert "nodate_recent_mm" not in params
        assert source.fixture_path is None
        assert source.recruitment_only and source.request_strategy.verify_tls


def test_native_post_search_and_clickable_table_cells_use_existing_profiles() -> None:
    batch = PROFILE_BATCHES["busan_ten"]
    donggu = batch.settings.sources["busan_donggu"].html_profile
    yeongdo = batch.settings.sources["yeongdo"].html_profile
    assert donggu is not None and donggu.request_method == "POST"
    assert yeongdo is not None and yeongdo.link_attribute == "onclick"
    assert yeongdo.link_selector == "td:nth-of-type(3)"
    assert "<a " not in batch.cases["yeongdo"]["list_html"]
    busanjin = batch.settings.sources["busanjin"]
    assert parse_qs(urlparse(busanjin.list_url).query)["epcCheck"] == ["Y"]


def test_historical_full_title_does_not_include_nested_registration_paragraph() -> None:
    batch = PROFILE_BATCHES["busan_ten"]
    case = batch.cases["haeundae"]
    source = batch.settings.sources["haeundae"]
    assert source.html_profile is not None
    assert "등록일" in case["detail_html"]
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert actual[0].title == case["title"] and "등록일" not in actual[0].title


@pytest.mark.parametrize("slug", PROFILE_BATCHES["daegu_incheon_ten"].cases)
def test_real_listing_title_registration_date_and_canonical_url(slug: str) -> None:
    batch = PROFILE_BATCHES["daegu_incheon_ten"]
    case, source = batch.cases[slug], batch.settings.sources[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert classify_notice_title(actual[0].title).value == case["category"]
    if slug in [s for s, c in batch.cases.items() if c["detail_html"]]:
        loader.assert_called_once_with(case["url"])
    else:
        loader.assert_not_called()


@pytest.mark.parametrize(
    "slug", [s for s, c in PROFILE_BATCHES["daegu_incheon_ten"].cases.items() if c["detail_html"]]
)
def test_http_200_error_document_does_not_become_a_notice(slug: str) -> None:
    batch = PROFILE_BATCHES["daegu_incheon_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<title>New Document</title>"),
        )


def test_incheon_uses_actual_euc_kr_request_and_clickable_row_identifier() -> None:
    batch = PROFILE_BATCHES["daegu_incheon_ten"]
    registry = SourceRegistry(batch.settings, Mock(), ZoneInfo("Asia/Seoul"))
    source = next(s for s in registry.build_enabled_sources() if s.slug == "incheon")
    assert isinstance(source, GenericEngineSource)
    request_url = source._build_request_url(page_index=2)
    assert "conTitle=%C6%F2%B0%A1%C0%A7%BF%F8" in request_url
    query = parse_qs(urlparse(request_url).query)
    assert query["currPageNo"] == ["2"] and query["conGosiGbn"] == ["A"]
    profile = batch.settings.sources["incheon"].html_profile
    assert profile is not None and not profile.link_selector and profile.link_attribute == "onclick"
    assert "<nobr>" in batch.cases["incheon"]["detail_html"]


def test_dalseo_uses_registration_date_not_posting_period_or_truncated_title() -> None:
    batch = PROFILE_BATCHES["daegu_incheon_ten"]
    case = batch.cases["dalseo"]
    profile = batch.settings.sources["dalseo"].html_profile
    assert profile is not None
    assert "등록일" in case["detail_html"]
    assert "게재기간" not in profile.date_selector
    assert "..." not in case["title"]


def test_yeongjong_actual_empty_news_message_is_recognized() -> None:
    batch = PROFILE_BATCHES["daegu_incheon_ten"]
    source = batch.settings.sources["yeongjong"]
    assert source.html_profile is not None
    assert (
        parse_profiled_html(
            batch.cases["yeongjong"]["empty_list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
        )
        == []
    )


@pytest.mark.parametrize(
    "slug",
    [
        s
        for s in PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"].settings.enabled_sources
        if PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"].settings.sources[s].html_profile
    ],
)
def test_actual_full_title_registration_date_and_canonical_url(slug: str) -> None:
    batch = PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
        expected_page=1,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    loader.assert_called_once_with(case["url"])


def test_real_counted_json_without_status_and_zero_based_offset() -> None:
    batch = PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"]
    source, case = batch.settings.sources["gyeonggi"], batch.cases["gyeonggi"]
    profile = source.json_profile
    assert profile is not None
    assert profile.status_path == profile.success_value == ""
    assert profile.total_path == "total" and profile.offset_base == 0
    assert profile.request_method == "POST" and profile.search_param == "keyword"
    actual = parse_profiled_json(
        case["list_json"], list_url=source.list_url, profile=profile, expected_page=1
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert (
        parse_profiled_json(
            '{"total":1,"items":[]}', list_url=source.list_url, profile=profile, expected_page=2
        )
        == []
    )
    query = parse_qs(urlparse(source.list_url).query)
    assert query["keyfield"] == ["SUBJECT"]


def test_actual_api_escaped_titles_match_the_public_detail_display() -> None:
    batch = PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"]
    source = batch.settings.sources["gyeonggi"]
    assert source.json_profile is not None
    records = batch.cases["gyeonggi"]["escaped_title_rows"]
    assert len(records) == 5
    for record in records:
        payload = json.dumps({"total": 1, "items": [record["row"]]})
        actual = parse_profiled_json(
            payload, list_url=source.list_url, profile=replace(source.json_profile, page_size=1)
        )
        assert [(n.title, str(n.published_date), n.url) for n in actual] == [
            (record["title"], record["date"], record["url"]),
        ]


@pytest.mark.parametrize(
    "payload",
    [
        "<h1>Error</h1>",
        '{"error":"unavailable"}',
        '{"total":1,"items":[]}',
        '{"total":true,"items":[]}',
        '{"total":0,"items":{}}',
    ],
)
def test_counted_json_error_or_partial_response_fails_closed(payload: str) -> None:
    batch = PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"]
    source = batch.settings.sources["gyeonggi"]
    assert source.json_profile is not None
    with pytest.raises(ValueError):
        parse_profiled_json(payload, list_url=source.list_url, profile=source.json_profile)


def test_sejong_real_blank_dates_are_not_guessed_or_enabled() -> None:
    batch = PROFILE_BATCHES["daejeon_ulsan_sejong_gyeonggi_ten"]
    source, case = batch.settings.sources["sejong"], batch.cases["sejong"]
    assert "sejong" not in batch.settings.enabled_sources and case["held"]
    profile = source.html_profile
    assert profile is not None
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            case["list_html"],
            list_url=source.list_url,
            profile=profile,
            detail_loader=Mock(return_value=case["detail_html"]),
            expected_page=1,
        )
    soup = BeautifulSoup(case["detail_html"], "html.parser")
    date_node = soup.select_one(profile.detail_date_selector)
    assert date_node is not None and not date_node.get_text(strip=True)


def test_chuncheon_uses_the_displayed_date_not_creation_timestamp() -> None:
    batch = PROFILE_BATCHES["gyeonggi_gangwon_chungbuk_thirty"]
    case, profile = batch.cases["chuncheon"], batch.settings.sources["chuncheon"].json_profile
    assert profile is not None and profile.date_key == "pbsHopYmd"
    row = json.loads(case["list_json"])["noticeList"][0]
    assert row["frstRegTs"] == "2026-09-28"
    assert case["date"] == row[profile.date_key] == "2026-09-29"


@pytest.mark.parametrize(
    "slug",
    [
        slug
        for slug, case in PROFILE_BATCHES["gyeongnam_jeju_final"].cases.items()
        if not case.get("empty")
    ],
)
def test_actual_full_title_registration_date_and_stable_url(slug: str) -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    if source.json_profile:
        actual = parse_profiled_json(
            case["list_json"],
            list_url=source.list_url,
            profile=source.json_profile,
            expected_page=1,
        )
    else:
        loader = Mock(return_value=case["detail_html"])
        actual = parse_profiled_html(
            case["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=loader,
            expected_page=1,
            recruitment_only=True,
        )
        loader.assert_called_once_with(case["url"])
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]


@pytest.mark.parametrize(
    "slug",
    [
        slug
        for slug in [
            slug
            for slug, case in PROFILE_BATCHES["gyeongnam_jeju_final"].cases.items()
            if not case.get("empty")
        ]
        if PROFILE_BATCHES["gyeongnam_jeju_final"].settings.sources[slug].html_profile
    ],
)
def test_missing_detail_is_not_a_successful_zero(slug: str) -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            case["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<h1>Error</h1>"),
        )


@pytest.mark.parametrize(
    "slug",
    [
        *[
            slug
            for slug in [
                slug
                for slug, case in PROFILE_BATCHES["gyeongnam_jeju_final"].cases.items()
                if not case.get("empty")
            ]
            if PROFILE_BATCHES["gyeongnam_jeju_final"].settings.sources[slug].html_profile
        ],
        "haman-current",
    ],
)
def test_missing_container_is_not_a_successful_zero(slug: str) -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    source = batch.settings.sources[slug]
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h1>Forbidden</h1>",
            list_url=source.list_url,
            profile=source.html_profile,
            expected_page=1,
        )


@pytest.mark.parametrize(
    "slug",
    [
        slug
        for slug in [
            slug
            for slug in [
                slug
                for slug, case in PROFILE_BATCHES["gyeongnam_jeju_final"].cases.items()
                if not case.get("empty")
            ]
            if PROFILE_BATCHES["gyeongnam_jeju_final"].settings.sources[slug].html_profile
        ]
        if PROFILE_BATCHES["gyeongnam_jeju_final"]
        .settings.sources[slug]
        .html_profile.page_number_selector
    ],
)
def test_ignored_page_fails_before_details_are_loaded(slug: str) -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    source = batch.settings.sources[slug]
    loader = Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            expected_page=2,
            detail_loader=loader,
        )
    loader.assert_not_called()


def test_haman_current_empty_is_paired_with_verified_past_recruitment() -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    source = batch.settings.sources["haman-current"]
    assert (
        parse_profiled_html(
            batch.cases["haman-current"]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            expected_page=1,
        )
        == []
    )
    assert batch.settings.sources["haman"].municipality == source.municipality
    assert "모집" in batch.cases["haman"]["title"]


def test_haman_current_retains_the_boards_verified_detail_and_date_rules() -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    source, case = batch.settings.sources["haman-current"], batch.cases["haman"]
    assert source.html_profile == batch.settings.sources["haman"].html_profile
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        expected_page=1,
        detail_loader=Mock(return_value=case["detail_html"]),
        recruitment_only=True,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]


def test_jinju_label_exclusion_and_reported_count_survive_config_loading() -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    source, case = batch.settings.sources["jinju"], batch.cases["jinju"]
    assert source.html_profile.total_count_selector == ".infomenu .right"
    assert source.html_profile.total_count_pattern.count("(") == 1
    assert not case["title"].startswith("제목 ")
    with pytest.raises(ValueError, match="row count contradicts"):
        parse_profiled_html(
            case["list_html"].replace("전체게시물:1개", "전체게시물:2개"),
            list_url=source.list_url,
            profile=source.html_profile,
            expected_page=1,
        )


def test_jeju_uses_verified_rows_not_inconsistent_total_field() -> None:
    batch = PROFILE_BATCHES["gyeongnam_jeju_final"]
    source, case = batch.settings.sources["jeju"], batch.cases["jeju"]
    assert source.json_profile.total_path == "query.rows"
    data = json.loads(case["list_json"])
    assert data["query"]["total"] == 0 and data["query"]["rows"] == 1
    with pytest.raises(ValueError, match="total|row"):
        parse_profiled_json(
            case["list_json"],
            list_url=source.list_url,
            profile=replace(source.json_profile, total_path="query.total"),
            expected_page=1,
        )


@pytest.mark.parametrize("slug", PROFILE_BATCHES["held_eighteen_recovered"].cases)
def test_actual_full_title_registration_date_and_url(slug: str) -> None:
    batch = PROFILE_BATCHES["held_eighteen_recovered"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
        expected_page=1,
        recruitment_only=True,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", PROFILE_BATCHES["held_eighteen_recovered"].cases)
def test_missing_detail_remains_a_failure(slug: str) -> None:
    batch = PROFILE_BATCHES["held_eighteen_recovered"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            case["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<h1>Blocked</h1>"),
        )


@pytest.mark.parametrize("slug", PROFILE_BATCHES["held_eighteen_recovered"].cases)
def test_page_mismatch_fails_before_requesting_details(slug: str) -> None:
    batch = PROFILE_BATCHES["held_eighteen_recovered"]
    source, loader = batch.settings.sources[slug], Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            expected_page=2,
            detail_loader=loader,
        )
    loader.assert_not_called()


def test_pyeongchang_does_not_use_posting_period_as_registration_date() -> None:
    batch = PROFILE_BATCHES["held_eighteen_recovered"]
    source, case = batch.settings.sources["pyeongchang"], batch.cases["pyeongchang"]
    assert source.html_profile.detail_origin == "https://www.pc.go.kr"
    assert not source.html_profile.detail_date_selector
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"] + "<p>게시기간 2000-01-01</p>"),
    )
    assert str(actual[0].published_date) == case["date"]
    with pytest.raises(ValueError, match="configured host"):
        parse_profiled_html(
            case["list_html"],
            list_url=source.list_url,
            profile=replace(source.html_profile, detail_origin=""),
        )


def test_namyangju_uses_explicit_registration_metadata_not_body_signature() -> None:
    batch = PROFILE_BATCHES["held_eighteen_recovered"]
    source, case = batch.settings.sources["namyangju"], batch.cases["namyangju"]
    assert "등록일" in source.html_profile.detail_date_selector
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"] + "<p>본문 작성 2000-01-01</p>"),
    )
    assert str(actual[0].published_date) == case["date"]


@pytest.mark.parametrize("slug", PROFILE_BATCHES["incheon_jeonnam_ten"].cases)
def test_actual_html_title_date_url_or_explicit_empty_search(slug: str) -> None:
    batch = PROFILE_BATCHES["incheon_jeonnam_ten"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case.get("detail_html", ""))
    actual = parse_profiled_html(
        case.get("list_html", case.get("empty_list_html")),
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
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


@pytest.mark.parametrize(
    "slug",
    [
        slug
        for slug, case in PROFILE_BATCHES["incheon_jeonnam_ten"].cases.items()
        if case.get("detail_html")
    ],
)
def test_http_200_error_document_cannot_replace_authoritative_detail(slug: str) -> None:
    batch = PROFILE_BATCHES["incheon_jeonnam_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<title>JSP compile error</title>"),
        )


def test_integrated_province_keeps_official_period_bounds_and_euc_kr_search() -> None:
    batch = PROFILE_BATCHES["incheon_jeonnam_ten"]
    sources = SourceRegistry(batch.settings, Mock(), ZoneInfo("Asia/Seoul")).build_enabled_sources()
    source = next(s for s in sources if s.slug == "jeonnam_gwangju")
    assert isinstance(source, GenericEngineSource)
    request = source._build_request_url(page_index=2)
    assert "conTitle=%C6%F2%B0%A1%C0%A7%BF%F8" in request
    query = parse_qs(urlparse(request).query)
    assert query["conIfmStdt"] == ["20260701"]
    assert query["conIfmEnddt"] == ["99991231"]
    assert query["currPageNo"] == ["2"]


def test_geomdan_uses_detail_date_instead_of_time_only_listing() -> None:
    batch = PROFILE_BATCHES["incheon_jeonnam_ten"]
    case = batch.cases["geomdan"]
    profile = batch.settings.sources["geomdan"].html_profile
    assert profile is not None
    assert "작성일" in case["detail_html"] and "년" in case["detail_html"]
    assert case["category"] != "recruitment"
    assert not profile.search_param


def test_ganghwa_actual_final_empty_page_is_not_a_failed_collection() -> None:
    batch = PROFILE_BATCHES["incheon_jeonnam_ten"]
    source = batch.settings.sources["ganghwa"]
    assert source.html_profile is not None
    assert (
        parse_profiled_html(
            batch.cases["ganghwa"]["last_empty_list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
        )
        == []
    )
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            '<p class="nocontens">조회 권한이 없습니다.</p>',
            list_url=source.list_url,
            profile=source.html_profile,
        )


@pytest.mark.parametrize("slug", PROFILE_BATCHES["jeonnam_counties_ten"].cases)
def test_actual_full_title_date_url_or_explicit_empty_listing(slug: str) -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case.get("detail_html", ""))
    actual = parse_profiled_html(
        case.get("list_html", case.get("empty_list_html")),
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
        expected_page=1,
        recruitment_only=case.get("listing_only", False),
    )
    if "empty_list_html" in case:
        assert actual == []
        loader.assert_not_called()
    else:
        assert [(n.title, str(n.published_date), n.url) for n in actual] == [
            (case["title"], case["date"], case["url"]),
        ]
        if case.get("listing_only"):
            loader.assert_not_called()
            assert case["category"] == "result"
        else:
            loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", PROFILE_BATCHES["jeonnam_counties_ten"].cases)
def test_missing_listing_is_not_a_successful_zero_result(slug: str) -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing (container missing|page does not match)"):
        parse_profiled_html(
            "<h1>FORBIDDEN</h1>",
            list_url=source.list_url,
            profile=source.html_profile,
            expected_page=1,
        )


@pytest.mark.parametrize("slug", ["gokseong", "goheung", "yeongam"])
def test_legacy_td_links_and_td_headers_need_no_anchor_or_javascript(slug: str) -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    profile = batch.settings.sources[slug].html_profile
    assert profile is not None
    soup = BeautifulSoup(batch.cases[slug]["list_html"], "html5lib")
    link = soup.select_one(profile.link_selector)
    assert link is not None and link.name == "td" and not link.find("a")
    assert not soup.find("th")
    header = soup.select_one("tbody > tr")
    assert header is not None and "등록일" in header.get_text() and "제목" in header.get_text()


@pytest.mark.parametrize("slug", ["gokseong", "goheung", "yeongam"])
def test_non_numeric_legacy_identifier_cannot_be_executed(slug: str) -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    soup = BeautifulSoup(batch.cases[slug]["list_html"], "html5lib")
    link = soup.select_one(source.html_profile.link_selector)
    assert link is not None
    link["onclick"] = "searchDetail('not-a-number');alert('unexpected')"
    loader = Mock()
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_profiled_html(
            str(soup), list_url=source.list_url, profile=source.html_profile, detail_loader=loader
        )
    loader.assert_not_called()


@pytest.mark.parametrize("slug", ["gurye", "haenam"])
def test_wrong_current_page_is_rejected_before_fetching_details(slug: str) -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None and source.html_profile.page_number_selector
    loader = Mock()
    with pytest.raises(ValueError, match="HTML listing page does not match requested page"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=loader,
            expected_page=2,
        )
    loader.assert_not_called()


def test_archives_supply_recruitment_not_false_success_from_current_results() -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    assert "empty_list_html" in batch.cases["jangheung_current"]
    assert batch.cases["gangjin_current"]["listing_only"]
    for slug in ["jangheung", "gangjin"]:
        assert batch.cases[slug]["category"] == "recruitment"
        assert date.fromisoformat(batch.cases[slug]["date"]) >= date(2025, 10, 5)


def test_actual_nomination_request_uses_the_same_html_profile() -> None:
    batch = PROFILE_BATCHES["jeonnam_counties_ten"]
    source, case = batch.settings.sources["gangjin"], batch.nomination["gangjin"]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
        recruitment_only=True,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert case["category"] == "recruitment"
    loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", PROFILE_BATCHES["jeonnam_daejeon_ten"].cases)
def test_actual_complete_title_registration_date_and_canonical_url(slug: str) -> None:
    batch = PROFILE_BATCHES["jeonnam_daejeon_ten"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
        expected_page=1,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert case["category"] == "recruitment"
    loader.assert_called_once_with(case["url"])


def test_real_button_attribute_and_zero_based_offset_are_configurable() -> None:
    batch = PROFILE_BATCHES["jeonnam_daejeon_ten"]
    seogu, yeonggwang = (
        batch.settings.sources["daejeon_seogu"],
        batch.settings.sources["yeonggwang"],
    )
    assert seogu.html_profile is not None and yeonggwang.html_profile is not None
    assert seogu.html_profile.link_attribute == "data-key-no"
    soup = BeautifulSoup(batch.cases["daejeon_seogu"]["list_html"], "html5lib")
    link = soup.select_one(seogu.html_profile.link_selector)
    assert link is not None and link.name == "td" and not link.find("a")
    assert link["data-key-no"] == "51899"
    assert yeonggwang.html_profile.offset_param == "offset"
    assert yeonggwang.html_profile.page_size == 10


def test_actual_empty_terminal_page_does_not_require_current_page_marker() -> None:
    batch = PROFILE_BATCHES["jeonnam_daejeon_ten"]
    source = batch.settings.sources["daejeon"]
    assert source.html_profile is not None
    loader = Mock()
    assert (
        parse_profiled_html(
            batch.cases["daejeon"]["empty_list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=loader,
            expected_page=3,
        )
        == []
    )
    loader.assert_not_called()


@pytest.mark.parametrize("slug", PROFILE_BATCHES["jeonnam_gwangju_ten"].cases)
def test_actual_title_date_url_or_explicit_empty_listing(slug: str) -> None:
    batch = PROFILE_BATCHES["jeonnam_gwangju_ten"]
    source, case = batch.settings.sources[slug], batch.cases[slug]
    loader = Mock(return_value=case.get("detail_html", ""))
    if source.json_profile:
        actual = parse_profiled_json(
            case["list_json"],
            list_url=source.list_url,
            profile=source.json_profile,
        )
    else:
        assert source.html_profile is not None
        actual = parse_profiled_html(
            case.get("list_html", case.get("empty_list_html")),
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=loader,
            expected_page=1,
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


@pytest.mark.parametrize(
    "slug",
    [
        slug
        for slug, case in PROFILE_BATCHES["jeonnam_gwangju_ten"].cases.items()
        if "list_json" not in case
    ],
)
def test_missing_listing_cannot_be_mistaken_for_zero_notices(slug: str) -> None:
    batch = PROFILE_BATCHES["jeonnam_gwangju_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h1>FORBIDDEN</h1>",
            list_url=source.list_url,
            profile=source.html_profile,
        )


def test_north_district_registration_date_is_not_the_shared_class_first_value() -> None:
    batch = PROFILE_BATCHES["jeonnam_gwangju_ten"]
    case = batch.cases["gwangju_bukgu"]
    soup = BeautifulSoup(case["detail_html"], "html.parser")
    assert "게재제호" in soup.select_one("dt.field02").get_text()  # type: ignore[union-attr]
    assert not soup.select_one("dt.field02 + dd").get_text(strip=True)  # type: ignore[union-attr]
    profile = batch.settings.sources["gwangju_bukgu"].html_profile
    assert profile is not None
    assert "등록일" in profile.detail_date_selector
    assert date.fromisoformat(case["date"]) > date(2025, 10, 4)


@pytest.mark.parametrize("slug", PROFILE_BATCHES["seoul_busan_ten"].cases)
def test_detail_error_page_is_not_silently_accepted(slug: str) -> None:
    batch = PROFILE_BATCHES["seoul_busan_ten"]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<p>점검 중</p>"),
        )


def test_truncated_songpa_listing_is_enriched_before_recruitment_filtering() -> None:
    batch = PROFILE_BATCHES["seoul_busan_ten"]
    source = batch.settings.sources["songpa"]
    profile = source.html_profile
    assert profile is not None
    case = batch.cases["songpa"]
    listing_only = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=replace(
            profile,
            detail_title_selector="",
            detail_date_selector="",
            date_selector="td:nth-of-type(5)",
        ),
    )
    assert listing_only[0].title.endswith("...")
    assert classify_notice_title(listing_only[0].title) is not NoticeCategory.RECRUITMENT
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert "공개모집 수정 공고" in actual[0].title


def test_registration_date_is_not_announcement_period_start() -> None:
    batch = PROFILE_BATCHES["seoul_busan_ten"]
    source = batch.settings.sources["geumcheon"]
    assert source.html_profile is not None
    case = batch.cases["geumcheon"]
    assert "2026-09-09 ~ 2026-09-11" in case["list_html"]
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert str(actual[0].published_date) == "2026-09-08"


@pytest.mark.parametrize("message", ["결과가 없습니다.", "결과가 없습니다"])
def test_gangnam_last_page_is_a_verified_empty_list(message: str) -> None:
    batch = PROFILE_BATCHES["seoul_busan_ten"]
    source = batch.settings.sources["gangnam"]
    assert source.html_profile is not None
    assert (
        parse_profiled_html(
            '<table class="table-hover"><tbody><tr><td colspan="100%">'
            f'<div class="empty-list"><div class="center">{message}</div></div>'
            "</td></tr></tbody></table>",
            list_url=source.list_url,
            profile=source.html_profile,
        )
        == []
    )


def test_unavailable_search_result_is_not_a_verified_empty_list() -> None:
    batch = PROFILE_BATCHES["seoul_busan_ten"]
    source = batch.settings.sources["gangnam"]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="notice link missing"):
        parse_profiled_html(
            '<table class="table-hover"><tbody><tr><td>결과를 불러올 수 없습니다.</td>'
            "</tr></tbody></table>",
            list_url=source.list_url,
            profile=source.html_profile,
        )


def test_busan_http_200_deleted_notice_is_not_valid_detail() -> None:
    batch = PROFILE_BATCHES["seoul_busan_ten"]
    source = batch.settings.sources["busan"]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            batch.cases["busan"]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(
                return_value=(
                    "<html><head><title>통합 공지사항 : 부산광역시</title>"
                    "<script>alert('삭제된 게시물 입니다.');location.href='/nbnews/';</script>"
                    "</head></html>"
                )
            ),
        )


def test_public_archive_form_parameters_and_javascript_link_variants() -> None:
    batch = PROFILE_BATCHES["seoul_busan_ten"]
    for slug in ("guro", "geumcheon", "dongjak", "seocho", "songpa", "gangdong"):
        source = batch.settings.sources[slug]
        assert parse_qs(urlparse(source.list_url).query)["list_gubun"] == ["A"]
        assert source.fixture_path is None
    gangdong = batch.settings.sources["gangdong"]
    assert parse_qs(urlparse(gangdong.list_url).query)["epcCheck"] == ["Y"]
    assert gangdong.html_profile is not None
    assert gangdong.html_profile.link_attribute == "href"
    soup = BeautifulSoup(batch.cases["gangdong"]["list_html"], "html5lib")
    anchor = soup.select_one("td.title a")
    assert anchor is not None and anchor["href"] == "javascript:searchDetail(58540)"


@pytest.mark.parametrize(
    "slug", [slug for slug in PROFILE_BATCHES["seoul_ten"].cases if slug != "mapo"]
)
def test_official_title_date_and_canonical_url(slug: str) -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    case = batch.cases[slug]
    config = batch.settings.sources[slug]
    assert config.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"],
        list_url=config.list_url,
        profile=config.html_profile,
        detail_loader=loader,
    )
    assert len(actual) == 1
    assert (actual[0].title, str(actual[0].published_date), actual[0].url) == (
        case["title"],
        case["date"],
        case["url"],
    )
    if case["detail_html"]:
        loader.assert_called_once_with(case["url"])
    else:
        loader.assert_not_called()


def test_detail_failures_do_not_fall_back_to_announcement_start_date() -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    config = batch.settings.sources["dongdaemun"]
    assert config.html_profile is not None
    for payload in ("접속 차단", "<th>등록일</th><td>2026-02-30</td>"):
        with pytest.raises(ValueError):
            parse_profiled_html(
                batch.cases["dongdaemun"]["list_html"],
                list_url=config.list_url,
                profile=config.html_profile,
                detail_loader=Mock(return_value=payload),
            )


def test_nowon_preserves_zero_menu_context_without_search_or_page_state() -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    case = batch.cases["nowon"]
    config = batch.settings.sources["nowon"]
    assert config.html_profile is not None
    for suffix in ("", "&amp;q_clCode=0&amp;q_searchVal=test&amp;q_currPage=7"):
        payload = case["list_html"].replace(
            "q_bbscttSn=20251020092118088'",
            f"q_bbscttSn=20251020092118088{suffix}'",
        )
        actual = parse_profiled_html(
            payload,
            list_url=config.list_url,
            profile=config.html_profile,
            detail_loader=Mock(return_value=case["detail_html"]),
        )
        assert actual[0].url == case["url"]
        assert parse_qs(urlparse(actual[0].url).query) == {
            "q_bbsCode": ["1004"],
            "q_bbscttSn": ["20251020092118088"],
            "q_clCode": ["0"],
        }


def test_nowon_bare_board_fragment_is_not_accepted_as_public_detail_page() -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    case = batch.cases["nowon"]
    config = batch.settings.sources["nowon"]
    assert config.html_profile is not None
    fragment = case["detail_html"].replace("<div id='content'>", "").replace("</div>", "")
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            case["list_html"],
            list_url=config.list_url,
            profile=config.html_profile,
            detail_loader=Mock(return_value=fragment),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_method", "DELETE"),
        ("request_encoding", "unknown"),
        ("link_attribute", "src"),
        ("link_attribute", "onclick"),
        ("date_selector", ""),
    ],
)
def test_profile_rejects_unsupported_options(field: str, value: str) -> None:
    profile = HtmlProfile(container_selector="table", row_selector="tr", date_selector="td")
    options: dict[str, Any] = {field: value}
    with pytest.raises(ValueError):
        replace(profile, **options)


@pytest.mark.parametrize("message", ["데이터가 존재하지 않습니다.", "게시글이 존재하지 않습니다."])
def test_real_empty_korean_message_and_missing_detail_loader(message: str) -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    config = batch.settings.sources["nowon"]
    assert config.html_profile is not None
    assert (
        parse_profiled_html(
            f'<table class="table-list"><tbody><tr><td>{message}</td></tr></tbody></table>',
            list_url=config.list_url,
            profile=config.html_profile,
        )
        == []
    )
    with pytest.raises(ValueError, match="detail loader"):
        parse_profiled_html(
            batch.cases["nowon"]["list_html"],
            list_url=config.list_url,
            profile=config.html_profile,
        )


def test_euc_kr_post_search_and_cached_detail_get() -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    client = Mock()
    client.post_text = Mock(return_value=batch.cases["seodaemun"]["list_html"])
    client.get_text.return_value = batch.cases["yangcheon"]["detail_html"]
    sources = {
        s.slug: s
        for s in SourceRegistry(
            batch.settings,
            client,
            ZoneInfo("Asia/Seoul"),
        ).build_enabled_sources()
    }
    source = sources["seodaemun"]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    assert len(source.fetch(date(2026, 9, 14))) == 1
    call = client.post_text.call_args
    assert call.args[0] == "https://www.sdm.go.kr/news/notice/notice.do"
    body = parse_qs(call.kwargs["data"].decode("ascii"), encoding="euc-kr")
    assert body["keyword"] == ["평가위원"]
    assert body["cp"] == ["2"]
    assert body["sdmBoardConfSeq"] == ["82"]
    assert call.kwargs["verify_tls"] is True
    client.get_text.assert_not_called()
    source = sources["yangcheon"]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    client.get_text.side_effect = lambda url, **_: (
        batch.cases["yangcheon"]["detail_html"]
        if "View.do" in url
        else batch.cases["yangcheon"]["list_html"]
    )
    assert len(source.fetch(date(2026, 7, 3))) == 1
    assert len(source.fetch(date(2026, 7, 3))) == 1
    assert sum("View.do" in c.args[0] for c in client.get_text.call_args_list) == 1


def test_last_page_empty_message_does_not_discard_already_collected_notices() -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    case = batch.cases["gwangjin"]
    client = Mock()

    def response(url: str, **_: object) -> str:
        if "view.do" in url:
            return str(case["detail_html"])
        if parse_qs(urlparse(url).query)["pageIndex"] == ["1"]:
            return str(case["list_html"])
        return (
            '<div class="table m"><table><tbody><tr><td class="nodata" colspan="7">'
            "게시글이 존재하지 않습니다.</td></tr></tbody></table></div>"
        )

    client.get_text.side_effect = response
    source = next(
        s
        for s in SourceRegistry(
            batch.settings,
            client,
            ZoneInfo("Asia/Seoul"),
        ).build_enabled_sources()
        if s.slug == "gwangjin"
    )
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    for _ in range(2):
        assert [n.url for n in source.fetch(date.fromisoformat(case["date"]))] == [case["url"]]
    assert client.get_text.call_count == 3


def test_mapo_post_search_paginates_and_filters_results() -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    case = batch.cases["mapo"]
    positive = {
        "_source": {
            "ba_title": case["title"],
            "ba_regdate": case["date"] + "T11:35:39Z",
            "link_url": urlparse(case["url"]).path + "?cp=1",
        }
    }
    negative = {
        "_source": {
            "ba_title": "제안서 평가위원회 결과 공개",
            "ba_regdate": case["date"],
            "link_url": "/site/main/board/notice/999999",
        }
    }
    client = Mock()
    client.post_text = Mock(
        side_effect=[
            json.dumps({"responses": [{"hits": {"hits": [positive, negative]}}]}),
            json.dumps({"responses": [{"hits": {"hits": []}}]}),
        ]
    )
    source = next(
        s
        for s in SourceRegistry(
            batch.settings,
            client,
            ZoneInfo("Asia/Seoul"),
        ).build_enabled_sources()
        if s.slug == "mapo"
    )
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    actual = source.fetch(date.fromisoformat(case["date"]))
    assert [(n.title, n.url) for n in actual] == [(case["title"], case["url"])]
    again = source.fetch(date.fromisoformat(case["date"]))
    assert [(n.title, n.url) for n in again] == [(case["title"], case["url"])]
    assert client.post_text.call_count == 2
    for index, call in enumerate(client.post_text.call_args_list):
        params = parse_qs(call.kwargs["data"].decode())
        assert params["requestMethod"] == ["GET"]
        query = json.loads(params["objData"][0].splitlines()[1])
        assert query["from"] == index * 10
        assert query["query"]["multi_match"]["operator"] == "and"


@pytest.mark.parametrize(
    "payload",
    [
        "<html>denied</html>",
        "{}",
        '{"responses": []}',
        '{"responses": [{"error": "backend unavailable"}]}',
        '{"responses": [{"timed_out": true, "hits": {"hits": []}}]}',
        '{"responses": [{"_shards": {"failed": 1}, "hits": {"hits": []}}]}',
        '{"responses": [{"hits": {"hits": [{"_source": {}}]}}]}',
    ],
)
def test_mapo_invalid_response_is_not_reported_as_zero(payload: str) -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    with pytest.raises(ValueError):
        normalize_search_response(payload, list_url=batch.settings.sources["mapo"].list_url)


@pytest.mark.parametrize(
    "link,published",
    [
        ("https://other.example/site/main/board/notice/1", "2026-05-11"),
        ("/site/main/board/notice/list", "2026-05-11"),
        ("/site/main/board/notice/123", "2026-02-30"),
    ],
)
def test_mapo_rejects_invalid_identity_and_dates(link: str, published: str) -> None:
    batch = PROFILE_BATCHES["seoul_ten"]
    payload = json.dumps(
        {
            "responses": [
                {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "ba_title": "평가위원 모집",
                                    "ba_regdate": published,
                                    "link_url": link,
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )
    with pytest.raises(ValueError):
        normalize_search_response(payload, list_url=batch.settings.sources["mapo"].list_url)
