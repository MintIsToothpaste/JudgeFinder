from __future__ import annotations

import base64
import json
import re
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup

from judgefinder.adapters.config import load_config
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.openworks_board import OpenworksBoardSource
from judgefinder.adapters.sources.generic_engine.parser import _extract_date_from_text
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.source_profiles import HtmlProfile
from judgefinder.infrastructure.http.client import RequestsHttpClient

ROOT = Path(__file__).parents[2]


ADDITIONAL_EXAMPLE = ROOT / "config/batch-cafe-additional-institutions.example.toml"


ADDITIONAL_FIXTURE = json.loads(
    (ROOT / "tests/fixtures/cafe_additional_institutions.json").read_text(encoding="utf-8"),
)


ADDITIONAL_CASES = ADDITIONAL_FIXTURE["sources"]


@pytest.mark.parametrize("slug", ADDITIONAL_CASES)
def test_public_boards_collect_window_and_cache_requests(slug: str) -> None:
    settings = load_config(ADDITIONAL_EXAMPLE)
    settings.enabled_sources = [slug]
    config, case = settings.sources[slug], ADDITIONAL_CASES[slug]
    profile = config.html_profile
    assert profile is not None
    client = Mock()

    def response(url: str, **_: object) -> str:
        if url in case["details"]:
            return str(case["details"][url])
        query = parse_qs(urlparse(url).query)
        assert query[profile.search_param] == ["평가위원"]
        if slug == "hwaseong_talent":
            assert base64.b64decode(query["search_Text"][0]).decode() == "평가위원"
        if slug.startswith("busan_bepa_"):
            assert query["periodState"] == ["all"]
        return str(case["pages"][query[profile.page_param][0]])

    client.get_text.side_effect = response
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    end = date.fromisoformat(ADDITIONAL_FIXTURE["window_end"])
    start = end - timedelta(days=ADDITIONAL_FIXTURE["window_days"] - 1)
    for _ in range(2):
        notices = [
            n
            for offset in range(ADDITIONAL_FIXTURE["window_days"])
            for n in source.fetch(start + timedelta(days=offset))
        ]
        assert sorted((n.title, str(n.published_date), n.url) for n in notices) == sorted(
            (n["title"], n["date"], n["url"]) for n in case["notices"]
        )
    assert client.get_text.call_count == len(case["pages"]) + len(case["details"])


def test_seven_institutions_have_live_profiles_and_broad_keyword_collection() -> None:
    config = load_config(ADDITIONAL_EXAMPLE)
    assert set(config.enabled_sources) == set(ADDITIONAL_CASES)
    assert len({s.municipality for s in config.sources.values()}) == 7
    assert len(ADDITIONAL_FIXTURE["targets"]) == 9
    for source in config.sources.values():
        assert source.fixture_path is None and source.html_profile is not None
        assert not source.recruitment_only
        assert source.request_strategy.verify_tls
    # Results stay available for manual review, as requested for maximum recall.
    assert any("평가점수 공개" in n["title"] for n in ADDITIONAL_CASES["daejeon_junggu"]["notices"])


@pytest.mark.parametrize("slug", ["uiseong", "busan_bistep", "busan_technopark"])
def test_complete_detail_titles_replace_truncated_or_duplicated_list_titles(slug: str) -> None:
    profile = load_config(ADDITIONAL_EXAMPLE).sources[slug].html_profile
    assert profile is not None
    case = ADDITIONAL_CASES[slug]
    soup = BeautifulSoup(case["pages"]["1"], "html5lib")
    title = soup.select_one(profile.container_selector).select_one(profile.link_selector)
    assert title is not None
    if slug == "uiseong":
        assert "평가위원" not in title.get_text()
    elif slug == "busan_bistep":
        assert "..." in title.get_text()
    else:
        assert len(title.select("span")) == 2
    config = load_config(ADDITIONAL_EXAMPLE).sources[slug]
    actual = parse_profiled_html(
        case["pages"]["1"],
        list_url=config.list_url,
        profile=profile,
        detail_loader=lambda url: case["details"][url],
        detail_not_before=date(2026, 10, 21),
    )
    for expected in case["notices"]:
        assert next(n.title for n in actual if n.url == expected["url"]) == expected["title"]


def test_technopark_registration_date_is_independent_of_application_period() -> None:
    config = load_config(ADDITIONAL_EXAMPLE).sources["busan_technopark"]
    case = ADDITIONAL_CASES["busan_technopark"]
    profile = config.html_profile
    assert profile is not None
    soup = BeautifulSoup(case["pages"]["1"], "html5lib")
    for cell in soup.select("td.period"):
        cell.string = "2099.01.01 ~ 2099.12.31"
    notices = parse_profiled_html(
        str(soup),
        list_url=config.list_url,
        profile=profile,
        detail_loader=lambda url: case["details"][url],
        detail_not_before=date(2026, 10, 21),
    )
    assert next(n.published_date for n in notices if "9582608" in n.url) == date(2026, 10, 26)


@pytest.mark.parametrize("target", ADDITIONAL_FIXTURE["targets"], ids=lambda n: n["url"])
def test_invalid_registration_dates_do_not_turn_into_collected_notices(
    target: dict[str, str],
) -> None:
    config = load_config(ADDITIONAL_EXAMPLE).sources[target["slug"]]
    profile, case = config.html_profile, ADDITIONAL_CASES[target["slug"]]
    assert profile is not None
    listing = BeautifulSoup(case["pages"]["1"], "html5lib")
    row = next(
        row
        for row in listing.select(profile.container_selector)[0].select(
            profile.row_selector,
        )
        if (
            match := re.search(
                profile.id_pattern,
                row.select_one(profile.link_selector)[profile.link_attribute],
            )
        )
        and match[1] == target["notice_id"]
    )
    container = listing.select_one(profile.container_selector)
    for other in list(container.select(profile.row_selector)):
        if other is not row:
            other.decompose()
    row.select_one(profile.date_selector).string = "2026-02-30"
    detail = BeautifulSoup(case["details"].get(target["url"], ""), "html5lib")
    if profile.detail_date_selector:
        detail.select_one(profile.detail_date_selector).string = "2026-02-30"
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            str(listing),
            list_url=config.list_url,
            profile=profile,
            detail_loader=lambda _: str(detail),
        )


PUBLIC_EXAMPLE = ROOT / "config/batch-public-institutions-seven.example.toml"


PUBLIC_FIXTURE = json.loads(
    (ROOT / "tests/fixtures/public_institutions_seven.json").read_text(encoding="utf-8"),
)


PUBLIC_CASES = PUBLIC_FIXTURE["sources"]


@pytest.mark.parametrize("slug", PUBLIC_CASES)
def test_public_institution_window_search_pagination_and_cache(slug: str) -> None:
    settings = load_config(PUBLIC_EXAMPLE)
    settings.enabled_sources = [slug]
    config, case = settings.sources[slug], PUBLIC_CASES[slug]
    profile = config.html_profile or config.json_profile
    assert profile is not None
    client = Mock()

    def response(url: str, **kwargs: object) -> str:
        if url in case["details"]:
            return str(case["details"][url])
        query = parse_qs(urlparse(url).query)
        if "data" in kwargs:
            assert slug == "gangwon_ccei"
            query = parse_qs(kwargs["data"].decode("ascii"))
            assert query["kind"] == ["my"] and query["pagePerContents"] == ["8"]
        assert query[profile.search_param] == ["평가위원"]
        if slug == "gyeongnam_technopark_ktp":
            assert query["agencyCd"] == ["TP_GN"]
        return str(case["pages"][query[profile.page_param][0]])

    client.get_text.side_effect = response
    client.post_text = Mock(side_effect=response)
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    end = date.fromisoformat(PUBLIC_FIXTURE["window_end"])
    start = end - timedelta(days=PUBLIC_FIXTURE["window_days"] - 1)
    for _ in range(2):
        notices = [
            n
            for offset in range(PUBLIC_FIXTURE["window_days"])
            for n in source.fetch(start + timedelta(days=offset))
        ]
        assert sorted((n.title, str(n.published_date), n.url) for n in notices) == sorted(
            (n["title"], n["date"], n["url"]) for n in case["notices"]
        )
    assert client.get_text.call_count + client.post_text.call_count == (
        len(case["pages"]) + len(case["details"])
    )


def test_public_channels_preserve_provenance_and_maximum_recall() -> None:
    config = load_config(PUBLIC_EXAMPLE)
    assert set(config.enabled_sources) == set(PUBLIC_CASES)
    assert len(PUBLIC_FIXTURE["targets"]) == 7
    for source in config.sources.values():
        assert source.fixture_path is None and not source.recruitment_only
        assert source.request_strategy.verify_tls
    assert "국가유산청" in config.sources["national_heritage"].municipality
    assert "수탁기관" in config.sources["gyeongnam_future_education"].municipality
    ktp = config.sources["gyeongnam_technopark_ktp"]
    assert "한국테크노파크진흥회" in ktp.municipality
    assert ktp.html_profile.detail_origin == "https://www.gntp.or.kr"
    assert any("(마감)" in n["title"] for n in PUBLIC_CASES["gangwon_ccei"]["notices"])


@pytest.mark.parametrize("slug", ["national_heritage", "chungnam_state_university"])
def test_article_identity_is_independent_of_search_page_and_session(slug: str) -> None:
    config = load_config(PUBLIC_EXAMPLE).sources[slug]
    profile, case = config.html_profile, PUBLIC_CASES[slug]
    target = next(n for n in PUBLIC_FIXTURE["targets"] if n["slug"] == slug)
    assert profile is not None
    for page in (1, 17):
        listing = case["pages"]["1"].replace("pageIndex=1", f"pageIndex={page}")
        listing = listing.replace("page=1", f"page={page}")
        listing = listing.replace("fixture-session", f"different-session-{page}")
        candidates = parse_profiled_html(
            listing,
            list_url=config.list_url,
            profile=profile,
            detail_loader=lambda url: case["details"][url],
        )
        assert target["url"] in {c.url for c in candidates}
        assert all("session" not in c.url and "page=" not in c.url for c in candidates)
    if slug == "national_heritage":
        assert parse_qs(urlparse(target["url"]).query)["id"] == ["21733"]
        assert parse_qs(urlparse(target["url"]).query)["no"] == ["28393"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026. 10. 23. 오후 6:05", date(2026, 10, 23)),
        ("등록일: 2024. 2. 29.", date(2024, 2, 29)),
        ("2026 / 10 / 23", date(2026, 10, 23)),
        ("2026. 2. 30.", None),
        ("2026. 2. 29.", None),
        ("2026. 13. 1.", None),
        ("26. 10. 23.", None),
    ],
)
def test_explicit_spaced_registration_dates_still_validate_calendar(
    text: str,
    expected: date | None,
) -> None:
    assert _extract_date_from_text(text) == expected


@pytest.mark.parametrize("value", ["page,", "page&token", " page", False])
def test_query_exclusions_accept_only_explicit_parameter_names(value: object) -> None:
    with pytest.raises(ValueError, match="detail_query_exclude"):
        HtmlProfile(
            container_selector="table",
            row_selector="tr",
            date_selector="td.date",
            detail_query_exclude=value,
        )


def test_query_normalization_keeps_legacy_urls_and_rejects_external_origins() -> None:
    html = '<table><tr><td><a href="{url}">평가위원 모집</a></td>'
    html += '<td class="date">2026-10-23</td></tr></table>'
    base = "https://example.org/list"
    profile = HtmlProfile(
        container_selector="table",
        row_selector="tr",
        date_selector="td.date",
    )
    url = "/article?id=12&page=3"
    assert (
        parse_profiled_html(
            html.format(url=url),
            list_url=base,
            profile=profile,
        )[0].url
        == "https://example.org/article?id=12&page=3"
    )
    profile.detail_query_exclude = "page"
    assert (
        parse_profiled_html(
            html.format(url=url),
            list_url=base,
            profile=profile,
        )[0].url
        == "https://example.org/article?id=12"
    )
    with pytest.raises(ValueError, match="configured host"):
        parse_profiled_html(
            html.format(url="https://external.example/article?id=12&page=3"),
            list_url=base,
            profile=profile,
        )


def test_ccei_rejects_invalid_dates_and_incomplete_json_pages() -> None:
    config = load_config(PUBLIC_EXAMPLE).sources["gangwon_ccei"]
    profile = config.json_profile
    assert profile is not None
    data = json.loads(PUBLIC_CASES[config.slug]["pages"]["1"])
    data["result"]["list"][0]["REG_DATE"] = "2026.02.30"
    with pytest.raises(ValueError, match="invalid date"):
        parse_profiled_json(json.dumps(data), list_url=config.list_url, profile=profile)
    data["result"]["list"].pop()
    with pytest.raises(ValueError, match="row count"):
        parse_profiled_json(json.dumps(data), list_url=config.list_url, profile=profile)


RECOVERY_CASES = json.loads(
    (ROOT / "tests/fixtures/cafe_20261023_profiles.json").read_text(encoding="utf-8"),
)


@pytest.mark.parametrize("slug", RECOVERY_CASES)
def test_recovered_profile_fetches_paginates_and_caches(slug: str) -> None:
    case = RECOVERY_CASES[slug]
    settings = load_config(ROOT / case["config_path"])
    settings.enabled_sources = [slug]
    config = settings.sources[slug]
    profile = config.html_profile
    assert profile is not None
    client = Mock(spec=RequestsHttpClient)
    calls: list[str] = []

    def response(url: str, **kwargs: object) -> str:
        assert kwargs["verify_tls"] and kwargs["use_session"]
        if url == case["url"]:
            return str(case["detail_html"])
        query = parse_qs(urlparse(url).query)
        if "data" in kwargs:
            data = kwargs["data"]
            assert isinstance(data, bytes)
            query = parse_qs(data.decode("ascii"))
        calls.append(url)
        page = int(query.get(profile.page_param, ["1"])[0])
        assert page in {1, 2}
        if slug == "gyeongnam_education":
            if page == 1:
                assert url == config.list_url
            else:
                assert query["csrfToken"] == ["test-public-form-token"]
                assert query["q_rowPerPage"] == ["10"]
        if slug == "seoul_education":
            assert query["q_rowPerPage"] == ["10"]
        if slug == "wonju":
            assert query["searchKrwd"] == ["평가"]
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        if page == 2:
            container.clear()
        if profile.page_number_selector:
            pager = soup.new_tag("div", attrs={"class": "p-pagination"})
            current = soup.new_tag("span", attrs={"class": "active"})
            current.string = str(page)
            pager.append(current)
            soup.append(pager)
        soup.append(
            BeautifulSoup(
                '<input name="csrfToken" value="test-public-form-token">',
                "html.parser",
            )
        )
        return str(soup)

    client.get_text.side_effect = response
    client.post_text.side_effect = response
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    assert isinstance(source, OpenworksBoardSource) == (slug == "gyeongnam_education")
    source.throttle_seconds = 0
    for _ in range(2):
        notices = source.fetch(date.fromisoformat(case["date"]))
        assert [(n.title, str(n.published_date), n.url) for n in notices] == [
            (case["title"], case["date"], case["url"]),
        ]
    assert len(calls) == 2
    assert all("csrfToken" not in n.url for n in notices)


@pytest.mark.parametrize(
    "slug",
    [
        key
        for key, case in RECOVERY_CASES.items()
        if load_config(ROOT / case["config_path"]).sources[key].html_profile.detail_date_selector
    ],
)
def test_invalid_detail_registration_date_never_uses_application_date(slug: str) -> None:
    case = RECOVERY_CASES[slug]
    config = load_config(ROOT / case["config_path"]).sources[slug]
    assert config.html_profile is not None
    detail = case["detail_html"].replace(case["date"], "2026-02-30")
    detail += "<p>접수기간: 2026-10-22 ~ 2026-10-30</p>"
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            case["list_html"],
            list_url=config.list_url,
            profile=config.html_profile,
            detail_loader=Mock(return_value=detail),
        )


def test_wonju_typo_uses_scoped_body_without_accepting_unrelated_evaluations() -> None:
    case = RECOVERY_CASES["wonju"]
    settings = load_config(ROOT / case["config_path"])
    config = settings.sources["wonju"]
    assert not config.recruitment_only and config.html_profile is not None
    candidates = parse_profiled_html(
        case["list_html"],
        list_url=config.list_url,
        profile=config.html_profile,
        detail_loader=Mock(return_value=case["detail_html"]),
    )
    assert "평가위원" not in candidates[0].title
    assert "평가위원" in candidates[0].searchable_text
    # An environmental evaluation does not acquire keywords from page navigation.
    detail = case["detail_html"].replace(case["title"], "환경영향평가 항목 결정 공고")
    detail = detail.replace("평가위원(후보자) 공개 모집", "주민 의견 제출")
    detail += "<nav>평가위원 모집 게시판</nav>"
    unrelated = parse_profiled_html(
        case["list_html"],
        list_url=config.list_url,
        profile=config.html_profile,
        detail_loader=Mock(return_value=detail),
    )
    assert "평가위원" not in unrelated[0].searchable_text


@pytest.mark.parametrize(
    "previous",
    [
        "",
        '<input name="csrfToken" value="">',
        '<input name="csrfToken" value="a"><input name="csrfToken" value="b">',
    ],
)
def test_openworks_missing_or_ambiguous_token_does_not_send_paging_request(previous: str) -> None:
    settings = load_config(ROOT / "config/batch-cafe-20261023.example.toml")
    settings.enabled_sources = ["gyeongnam_education"]
    client = Mock()
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    source.page_cache[1] = previous
    with pytest.raises(ValueError, match="token missing or ambiguous"):
        source._load_page(page_index=2)
    client.get_text.assert_not_called()


def test_openworks_uses_each_previous_page_token_and_requires_session() -> None:
    settings = load_config(ROOT / "config/batch-cafe-20261023.example.toml")
    settings.enabled_sources = ["gyeongnam_education"]
    client = Mock()
    source = SourceRegistry(
        settings,
        client,
        ZoneInfo(settings.timezone),
    ).build_enabled_sources()[0]
    source.throttle_seconds = 0
    client.get_text.side_effect = [
        '<input name="csrfToken" value="one">',
        '<input name="csrfToken" value="two">',
        "<table></table>",
    ]
    for page in [1, 2, 3]:
        source._load_page(page_index=page)
    assert parse_qs(urlparse(client.get_text.call_args_list[1].args[0]).query)["csrfToken"] == [
        "one",
    ]
    assert parse_qs(urlparse(client.get_text.call_args_list[2].args[0]).query)["csrfToken"] == [
        "two",
    ]
    source.page_cache.clear()
    with pytest.raises(ValueError, match="preceding page"):
        source._load_page(page_index=2)
    source.use_session = False
    with pytest.raises(ValueError, match="requires a session"):
        source._load_page(page_index=1)


def test_jemulpo_time_only_list_row_uses_explicit_detail_date() -> None:
    settings = load_config(ROOT / "config/batch-daegu-incheon-ten.example.toml")
    config = settings.sources["jemulpo"]
    assert config.html_profile is not None
    cases = json.loads(
        (ROOT / "tests/fixtures/daegu_incheon_ten_profiles.json").read_text(encoding="utf-8"),
    )
    case = cases["jemulpo"]
    soup = BeautifulSoup(case["list_html"], "html5lib")
    node = soup.select_one(config.html_profile.date_selector)
    assert node is not None
    node.string = "17:10:31"
    detail = "<dl><dt>작성일</dt><dd>2026년 10월 26일(월) 17:10:31</dd></dl>"
    notices = parse_profiled_html(
        str(soup),
        list_url=config.list_url,
        profile=config.html_profile,
        detail_loader=Mock(return_value=detail),
    )
    assert notices[0].published_date == date(2026, 10, 26)
    with pytest.raises(ValueError, match="registration-date element missing"):
        parse_profiled_html(
            str(soup),
            list_url=config.list_url,
            profile=config.html_profile,
            detail_loader=Mock(return_value="<p>접수기간: 2026-10-26 ~ 2026-10-30</p>"),
        )


def test_new_fixtures_omit_contacts_scripts_and_real_session_fields() -> None:
    for case in RECOVERY_CASES.values():
        for key in ["list_html", "detail_html"]:
            soup = BeautifulSoup(case[key], "html5lib")
            assert not soup.select("script,style,input,iframe")
            assert all(word not in soup.get_text() for word in ["담당자", "연락처", "전화번호"])
