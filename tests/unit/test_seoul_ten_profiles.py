from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.mapo_search import normalize_search_response
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title
from judgefinder.domain.source_profiles import HtmlProfile

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/seoul_ten_profiles.json").read_text(encoding="utf-8"))
SETTINGS = load_config(ROOT / "config/batch-seoul-ten.example.toml")


@pytest.mark.parametrize("slug", [slug for slug in CASES if slug != "mapo"])
def test_official_title_date_and_canonical_url(slug: str) -> None:
    case = CASES[slug]
    config = SETTINGS.sources[slug]
    assert config.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"], list_url=config.list_url, profile=config.html_profile,
        detail_loader=loader,
    )
    assert len(actual) == 1
    assert (actual[0].title, str(actual[0].published_date), actual[0].url) == (
        case["title"], case["date"], case["url"],
    )
    if case["detail_html"]:
        loader.assert_called_once_with(case["url"])
    else:
        loader.assert_not_called()


def test_detail_failures_do_not_fall_back_to_announcement_start_date() -> None:
    config = SETTINGS.sources["dongdaemun"]
    assert config.html_profile is not None
    for payload in ("접속 차단", "<th>등록일</th><td>2026-02-30</td>"):
        with pytest.raises(ValueError):
            parse_profiled_html(
                CASES["dongdaemun"]["list_html"], list_url=config.list_url,
                profile=config.html_profile, detail_loader=Mock(return_value=payload),
            )


def test_nowon_preserves_zero_menu_context_without_search_or_page_state() -> None:
    case = CASES["nowon"]
    config = SETTINGS.sources["nowon"]
    assert config.html_profile is not None
    for suffix in ("", "&amp;q_clCode=0&amp;q_searchVal=test&amp;q_currPage=7"):
        payload = case["list_html"].replace(
            "q_bbscttSn=20251020092118088'", f"q_bbscttSn=20251020092118088{suffix}'",
        )
        actual = parse_profiled_html(
            payload, list_url=config.list_url, profile=config.html_profile,
            detail_loader=Mock(return_value=case["detail_html"]),
        )
        assert actual[0].url == case["url"]
        assert parse_qs(urlparse(actual[0].url).query) == {
            "q_bbsCode": ["1004"], "q_bbscttSn": ["20251020092118088"], "q_clCode": ["0"],
        }


def test_nowon_bare_board_fragment_is_not_accepted_as_public_detail_page() -> None:
    case = CASES["nowon"]
    config = SETTINGS.sources["nowon"]
    assert config.html_profile is not None
    fragment = case["detail_html"].replace("<div id='content'>", "").replace("</div>", "")
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            case["list_html"], list_url=config.list_url, profile=config.html_profile,
            detail_loader=Mock(return_value=fragment),
        )


@pytest.mark.parametrize("field,value", [
    ("request_method", "DELETE"), ("request_encoding", "unknown"),
    ("link_attribute", "src"), ("link_attribute", "onclick"),
    ("date_selector", ""),
])
def test_profile_rejects_unsupported_options(field: str, value: str) -> None:
    profile = HtmlProfile(container_selector="table", row_selector="tr", date_selector="td")
    options: dict[str, Any] = {field: value}
    with pytest.raises(ValueError):
        replace(profile, **options)


@pytest.mark.parametrize("message", ["데이터가 존재하지 않습니다.", "게시글이 존재하지 않습니다."])
def test_real_empty_korean_message_and_missing_detail_loader(message: str) -> None:
    config = SETTINGS.sources["nowon"]
    assert config.html_profile is not None
    assert parse_profiled_html(
        f'<table class="table-list"><tbody><tr><td>{message}</td>'
        '</tr></tbody></table>', list_url=config.list_url, profile=config.html_profile,
    ) == []
    with pytest.raises(ValueError, match="detail loader"):
        parse_profiled_html(
            CASES["nowon"]["list_html"], list_url=config.list_url, profile=config.html_profile,
        )


def test_euc_kr_post_search_and_cached_detail_get() -> None:
    client = Mock()
    client.post_text.return_value = CASES["seodaemun"]["list_html"]
    client.get_text.return_value = CASES["yangcheon"]["detail_html"]
    sources = {s.slug: s for s in SourceRegistry(
        SETTINGS, client, ZoneInfo("Asia/Seoul"),
    ).build_enabled_sources()}
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
        CASES["yangcheon"]["detail_html"] if "View.do" in url
        else CASES["yangcheon"]["list_html"]
    )
    assert len(source.fetch(date(2026, 7, 3))) == 1
    assert len(source.fetch(date(2026, 7, 3))) == 1
    assert sum("View.do" in c.args[0] for c in client.get_text.call_args_list) == 1


def test_last_page_empty_message_does_not_discard_already_collected_notices() -> None:
    case = CASES["gwangjin"]
    client = Mock()

    def response(url: str, **_: object) -> str:
        if "view.do" in url:
            return str(case["detail_html"])
        if parse_qs(urlparse(url).query)["pageIndex"] == ["1"]:
            return str(case["list_html"])
        return (
            '<div class="table m"><table><tbody><tr><td class="nodata" colspan="7">'
            '게시글이 존재하지 않습니다.</td></tr></tbody></table></div>'
        )

    client.get_text.side_effect = response
    source = next(s for s in SourceRegistry(
        SETTINGS, client, ZoneInfo("Asia/Seoul"),
    ).build_enabled_sources() if s.slug == "gwangjin")
    assert isinstance(source, GenericEngineSource)
    source.throttle_seconds = 0
    for _ in range(2):
        assert [n.url for n in source.fetch(date.fromisoformat(case["date"]))] == [case["url"]]
    assert client.get_text.call_count == 3


@pytest.mark.parametrize("title", [
    "홍제역 역세권활성화사업 분야별 용역 제안서평가위원(후보자) 모집 취소 공고",
    "제안서평가위원회[2025-2026 동대문구 눈썰매장] 결과 공고",
    "2026~27년 U-양천 통합관제센터 및 CCTV 유지보수 평가위원별 점수공개",
    "2026년 상반기 마포구 성별영향평가위원회 서면심의 결과",
    "2025년 하반기 마포구 성별영향평가위원회 서면심의 결과",
])
def test_excluded_live_notices_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT


def test_mapo_post_search_paginates_and_filters_results() -> None:
    case = CASES["mapo"]
    positive = {"_source": {
        "ba_title": case["title"], "ba_regdate": case["date"] + "T11:35:39Z",
        "link_url": urlparse(case["url"]).path + "?cp=1",
    }}
    negative = {"_source": {
        "ba_title": "제안서 평가위원회 결과 공개", "ba_regdate": case["date"],
        "link_url": "/site/main/board/notice/999999",
    }}
    client = Mock()
    client.post_text.side_effect = [
        json.dumps({"responses": [{"hits": {"hits": [positive, negative]}}]}),
        json.dumps({"responses": [{"hits": {"hits": []}}]}),
    ]
    source = next(s for s in SourceRegistry(
        SETTINGS, client, ZoneInfo("Asia/Seoul"),
    ).build_enabled_sources() if s.slug == "mapo")
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


@pytest.mark.parametrize("payload", [
    "<html>denied</html>", "{}", '{"responses": []}',
    '{"responses": [{"error": "backend unavailable"}]}',
    '{"responses": [{"timed_out": true, "hits": {"hits": []}}]}',
    '{"responses": [{"_shards": {"failed": 1}, "hits": {"hits": []}}]}',
    '{"responses": [{"hits": {"hits": [{"_source": {}}]}}]}',
])
def test_mapo_invalid_response_is_not_reported_as_zero(payload: str) -> None:
    with pytest.raises(ValueError):
        normalize_search_response(payload, list_url=SETTINGS.sources["mapo"].list_url)


@pytest.mark.parametrize("link,published", [
    ("https://other.example/site/main/board/notice/1", "2026-05-11"),
    ("/site/main/board/notice/list", "2026-05-11"),
    ("/site/main/board/notice/123", "2026-02-30"),
])
def test_mapo_rejects_invalid_identity_and_dates(link: str, published: str) -> None:
    payload = json.dumps({"responses": [{"hits": {"hits": [{"_source": {
        "ba_title": "평가위원 모집", "ba_regdate": published, "link_url": link,
    }}]}}]})
    with pytest.raises(ValueError):
        normalize_search_response(payload, list_url=SETTINGS.sources["mapo"].list_url)
