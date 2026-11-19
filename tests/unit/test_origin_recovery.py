from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.adapters.origin_discovery import HIBRAIN_LIST, HibrainOriginDiscovery
from judgefinder.adapters.origin_reader import ConfiguredOriginReader
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.source_profiles import EngineType, HtmlProfile
from judgefinder.infrastructure.http.client import HttpResponse

DAY = date(2026, 11, 3)
URL = "https://city.go.kr/view?board=A&id=12&mode=view"
DETAIL = (
    '<h1>제안서 평가위원(후보자) 모집 공고</h1><time>2026-11-03</time>'
    '<article>평가위원 공개 모집 안내<script>irrelevant</script></article>'
)


def source(client: Mock) -> GenericEngineSource:
    return GenericEngineSource(
        slug="city", municipality="도시", source_type=SourceType.HTML,
        list_url="https://city.go.kr/list?board=A", engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"), http_client=client, max_retries=1,
        html_profile=HtmlProfile(
            container_selector="table", row_selector="tr", link_selector="a",
            date_selector="td.date", detail_url_template="/view?board=A&id={id}&mode=view",
            id_pattern="id=([1-9][0-9]*)",
            detail_title_selector="h1", detail_date_selector="time", detail_body_selector="article",
        ),
    )


def test_official_identity_ignores_search_but_preserves_board_and_uses_https() -> None:
    reader = ConfiguredOriginReader([source(Mock())])
    route = reader.resolve(URL)
    assert reader.resolve("http://city.go.kr/view?id=12&board=A&page=9&search=x").identity_key == (
        route.identity_key
    )
    assert route.canonical_url == URL
    for url in (
        URL.replace("board=A", "board=B"), URL.replace("city.go.kr", "evil.go.kr"),
        URL + "&id=13", "https://city.go.kr/view?id=12", URL.replace("id=12", "id=0"),
        URL.replace("mode=view", "mode=delete"), "https://user@city.go.kr/view?board=A&id=12",
    ):
        with pytest.raises(ValueError):
            reader.resolve(url)
    s = source(Mock())
    assert s.html_profile is not None
    s.html_profile = replace(s.html_profile, detail_url_template="/view?board=B&id={id}&mode=view")
    other = ConfiguredOriginReader([s]).resolve(URL.replace("board=A", "board=B"))
    assert other.identity_key != route.identity_key


@pytest.mark.parametrize("body,final_url,status,reason", [
    (DETAIL, URL, 200, ""),
    (DETAIL.replace("2026-11-03", "missing"), URL, 200, "date invalid"),
    (DETAIL.replace("<article>", "<aside>").replace("</article>", "</aside>"), URL, 200,
     "body missing"),
    (DETAIL, "https://city.go.kr/", 200, "matches"),
    (DETAIL, URL, 403, "HTTP 403"),
    (DETAIL, URL.replace("https:", "http:"), 200, "configured scheme"),
    (DETAIL.replace("평가위원 공개 모집 안내", "게시물이 없습니다"), URL, 200, "missing notice"),
])
def test_reader_verifies_official_metadata_and_redirects(
    body: str, final_url: str, status: int, reason: str,
) -> None:
    client = Mock()
    client.get_response.return_value = HttpResponse(status, body, {}, final_url)
    reader = ConfiguredOriginReader([source(client)])
    if reason:
        with pytest.raises(ValueError, match=reason):
            reader.read(reader.resolve(URL))
    else:
        result = reader.read(reader.resolve(URL))
        assert result.notice.published_date == DAY
        assert result.body_text == "평가위원 공개 모집 안내"
        assert result.notice.url == URL


def listing(ids: list[int]) -> str:
    return '<ul id="articleList">' + "".join(
        f'<li class="row"><span class="td_title"><a href="/recruits/{i}?category=public">'
        '평가위원 모집 공고</a></span><span class="td_rdtm">26.11.03</span></li>'
        for i in ids
    ) + "</ul>"


def test_discovery_isolates_detail_failure_and_extracts_only_related_originals() -> None:
    client = Mock()
    def response(url: str, **kwargs: object) -> HttpResponse:
        assert kwargs["verify_tls"]
        if url == HIBRAIN_LIST:
            return HttpResponse(200, listing([1, 2]), {}, url)
        if "/1?" in url:
            return HttpResponse(403, "denied", {}, url)
        return HttpResponse(200, '<a href="https://unrelated.net">body</a><table><tr>'
                            f'<th>관련 홈페이지</th><td><a href="{URL}">원문</a></td></tr>'
                            '</table>', {}, url)
    client.get_response.side_effect = response
    candidates = list(HibrainOriginDiscovery(client, throttle_seconds=0).discover(DAY, DAY))
    assert len(candidates) == 2
    assert candidates[0].origin_url == "" and "403" in candidates[0].discovery_error
    assert candidates[1].origin_url == URL
    assert "category=public" in candidates[1].discovery_url


def test_discovery_rejects_missing_list_and_incomplete_page_limit() -> None:
    client = Mock()
    client.get_response.return_value = HttpResponse(200, "Login", {}, HIBRAIN_LIST)
    with pytest.raises(ValueError, match="listing missing"):
        list(HibrainOriginDiscovery(client, throttle_seconds=0).discover(DAY, DAY))
    client.get_response.return_value = HttpResponse(
        200, '<ul id="articleList"></ul><a href="?page=2">다음</a>', {}, HIBRAIN_LIST,
    )
    with pytest.raises(ValueError, match="page limit"):
        list(HibrainOriginDiscovery(client, max_pages=1, throttle_seconds=0).discover(DAY, DAY))


def test_discovery_follows_numbered_page_links() -> None:
    client = Mock()
    def response(url: str, **kwargs: object) -> HttpResponse:
        if url == HIBRAIN_LIST:
            body = ('<ul id="articleList"></ul><ul class="pagination">'
                    '<li><a href="?page=2">2</a></li></ul>')
        else:
            assert "page=2" in url
            body = '<ul id="articleList"></ul>'
        return HttpResponse(200, body, {}, url)
    client.get_response.side_effect = response
    assert list(HibrainOriginDiscovery(client, throttle_seconds=0).discover(DAY, DAY)) == []
    assert client.get_response.call_count == 2


@pytest.mark.parametrize("settings", [
    'max_pages = 0', 'max_pages = true', 'throttle_seconds = nan', 'enabled = "yes"',
    'unknown = 1', 'candidate_file = ""',
])
def test_origin_config_rejects_invalid_settings(tmp_path: Path, settings: str) -> None:
    config = tmp_path / "settings.toml"
    config.write_text('timezone="Asia/Seoul"\ndb_path="db"\nenabled_sources=[]\n'
                      '[sources]\n[origin_recovery]\n' + settings, encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(config)


@pytest.mark.parametrize(
    ("id_format", "identifier", "accepted"),
    [
        ("numeric", "12", True), ("numeric", "0", False),
        ("hex32", "aB12" * 8, True), ("hex32", "aB12", False),
        ("zero_padded_numeric", "00012", True), ("zero_padded_numeric", "000", False),
        ("alphanumeric", "Ab12", True), ("alphanumeric", "Ab-12", False),
    ],
)
def test_listing_and_origin_reader_preserve_identifier_formats(
    id_format: str, identifier: str, accepted: bool,
) -> None:
    official = source(Mock())
    assert official.html_profile is not None
    official.html_profile = replace(
        official.html_profile, id_format=id_format, id_pattern=r"id=([^&]+)",
    )
    reader = ConfiguredOriginReader([official])
    url = URL.replace("id=12", f"id={identifier}")
    listing = (
        f'<table><tr><td><a href="{url}">평가위원 모집 공고</a></td>'
        f'<td class="date">{DAY}</td></tr></table>'
    )
    if accepted:
        notice = parse_profiled_html(
            listing, list_url=official.list_url, profile=official.html_profile,
            detail_loader=Mock(return_value=DETAIL),
        )[0]
        assert notice.url == reader.resolve(url).canonical_url == url
    else:
        with pytest.raises(ValueError, match="unsupported notice identifier"):
            parse_profiled_html(listing, list_url=official.list_url, profile=official.html_profile)
        with pytest.raises(ValueError, match="No enabled official detail profile"):
            reader.resolve(url)
