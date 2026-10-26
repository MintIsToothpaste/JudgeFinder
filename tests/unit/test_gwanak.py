from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.parser import (
    GenericNoticeCandidate,
    parse_generic_engine_candidates,
)
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title
from judgefinder.domain.source_profiles import EngineType
from judgefinder.infrastructure.http.client import RequestsHttpClient

FIXTURES = Path(__file__).parents[1] / "fixtures"
GOSI_URL = "https://www.gwanak.go.kr/site/gwanak/ex/bbsNew/List.do?typeCode=1&pageIndex=1"
NEWS_URL = "https://www.gwanak.go.kr/site/gwanak/ex/bbs/List.do?cbIdx=239&pageIndex=1"
DETAIL_URL = (
    "https://www.gwanak.go.kr/site/gwanak/ex/bbsNew/View.do?not_ancmt_mgt_no=41700&typeCode=1"
)
EMPTY_PAGE = """
<div id="boardDivId"><table class="list">
<thead><tr><th>제목</th></tr></thead>
<tbody><tr><td colspan="8">등록된 게시물이 없습니다.</td></tr></tbody>
</table></div>
"""


def payload(board: str = "gosi") -> str:
    return (FIXTURES / f"gwanak_{board}_list.html").read_text(encoding="utf-8")


def parse(html: str, url: str = GOSI_URL) -> list[GenericNoticeCandidate]:
    return parse_generic_engine_candidates(
        html, list_url=url, engine_type=EngineType.GENERIC_EGOV_BBS,
    )


def source(*, board: str = "gosi", recruitment_only: bool = True) -> GenericEngineSource:
    return GenericEngineSource(
        slug="gwanak", municipality="관악구", source_type=SourceType.HTML,
        list_url=GOSI_URL if board == "gosi" else NEWS_URL,
        engine_type=EngineType.GENERIC_EGOV_BBS, timezone=ZoneInfo("Asia/Seoul"),
        http_client=RequestsHttpClient(), recruitment_only=recruitment_only,
        fixture_path=FIXTURES / f"gwanak_{board}_list.html",
    )


def test_gosi_malformed_cells_use_registration_date() -> None:
    candidates = parse(payload())
    assert len(candidates) == 2
    assert candidates[0].url == DETAIL_URL
    assert candidates[0].published_date == date(2026, 8, 31)
    assert candidates[0].title.endswith("제안서 평가위원(후보자) 모집 공고")
    assert candidates[1].published_date == date(2026, 7, 23)


def test_news_detail_link_uses_four_arguments_and_written_date() -> None:
    candidates = parse(payload("news"), NEWS_URL)
    assert len(candidates) == 1
    assert candidates[0].url == (
        "https://www.gwanak.go.kr/site/gwanak/ex/bbs/View.do"
        "?cbIdx=239&bcIdx=204488&parentSeq=204488"
    )
    assert candidates[0].published_date == date(2026, 8, 31)


@pytest.mark.parametrize("call", [
    "doBbsFView('0')", "doBbsFView('-1')", "doBbsFView('abc')", "doBbsFView('１２')",
    "doBbsFView('41700','1')", "otherView('41700')", "doBbsFView('41700');evil()",
    "doBbsFView('41700\")", "doBbsFView('41700?typeCode=2')",
])
def test_rejects_unsupported_or_invalid_gosi_calls(call: str) -> None:
    html = payload().replace("doBbsFView('41700');return false;", call)
    assert all(item.url != DETAIL_URL for item in parse(html))


@pytest.mark.parametrize("url", [
    GOSI_URL.replace("www.gwanak.go.kr", "other.go.kr"),
    GOSI_URL.replace("www.gwanak.go.kr", "www.gwanak.go.kr.example.com"),
    GOSI_URL.replace("/site/gwanak/", "/site/other/"),
    GOSI_URL.replace("typeCode=1", "typeCode=2"),
    GOSI_URL + "&typeCode=2",
])
def test_gwanak_rule_is_limited_to_verified_board(url: str) -> None:
    assert parse(payload(), url) == []


@pytest.mark.parametrize("replacement", ["", "20260230", "not-a-date", "20260831 junk"])
def test_bad_registration_date_never_falls_back_to_announcement_date(replacement: str) -> None:
    candidates = parse(payload().replace("20260831", replacement))
    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 7, 23)


def test_missing_registration_header_does_not_fall_back() -> None:
    assert parse(payload().replace("등록일", "unknown")) == []


def test_nested_table_cells_do_not_shift_registration_column() -> None:
    html = payload().replace("</a>", "</a><table><tr><td>extra</td></tr></table>", 1)
    assert parse(html)[0].published_date == date(2026, 8, 31)


def test_news_board_id_must_match_list() -> None:
    assert parse(payload("news"), NEWS_URL.replace("239", "999")) == []


@pytest.mark.parametrize(("board", "condition"), [("gosi", "NOT_ANCMT_SJ"), ("news", "SUB_CONT")])
def test_gwanak_search_parameters(board: str, condition: str) -> None:
    query = parse_qs(urlparse(source(board=board)._build_request_url(page_index=2)).query)
    assert query["searchKey"] == ["평가위원"]
    assert query["tgtTypeCd"] == [condition]
    assert query["pageIndex"] == ["2"]
    assert "searchKrwd" not in query


def test_explicit_search_settings_are_preserved() -> None:
    collector = source()
    collector.list_url += "&searchKey=custom&tgtTypeCd=NOT_ANCMT_CN"
    query = parse_qs(urlparse(collector._build_request_url(page_index=1)).query)
    assert query["searchKey"] == ["custom"]
    assert query["tgtTypeCd"] == ["NOT_ANCMT_CN"]
    assert "searchKrwd" not in query


def test_target_on_second_page_is_collected(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = source()
    collector.fixture_path = None
    first = payload().replace("20260831", "20260912").replace("20260723", "20260911")
    pages = [first, payload(), EMPTY_PAGE]
    calls: list[int] = []

    def load(self: GenericEngineSource, *, page_index: int) -> str:
        calls.append(page_index)
        return pages[page_index - 1]

    monkeypatch.setattr(GenericEngineSource, "_load_page", load)
    notices = collector.fetch(date(2026, 8, 31))
    assert [notice.url for notice in notices] == [DETAIL_URL]
    assert calls == [1, 2, 3]


@pytest.mark.parametrize(("title", "category"), [
    ("제안서 평가위원(후보자) 모집 공고", NoticeCategory.RECRUITMENT),
    ("평가위원 후보자 추가모집 및 기간 연장", NoticeCategory.RECRUITMENT),
    ("평가위원회 평가 결과 공개", NoticeCategory.RESULT),
    ("평가위원 후보자 모집 결과 안내", NoticeCategory.RESULT),
    ("평가위원 선정결과", NoticeCategory.RESULT),
    ("평가위원회 개최결과 알림", NoticeCategory.RESULT),
    ("평가위원 모집 취소", NoticeCategory.UNKNOWN),
    ("평가위원 모집 마감 안내", NoticeCategory.UNKNOWN),
    ("평가위원 안내", NoticeCategory.UNKNOWN),
    ("사업 참여기업 모집", NoticeCategory.UNKNOWN),
])
def test_title_classification(title: str, category: NoticeCategory) -> None:
    assert classify_notice_title(title) is category


def test_news_result_is_excluded_only_when_enabled(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        assert source(board="news").fetch(date(2026, 8, 31)) == []
    assert "excluded category=result" in caplog.text
    assert len(source(board="news", recruitment_only=False).fetch(date(2026, 8, 31))) == 1


def test_unknown_title_is_excluded_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    html = payload("news").replace("평가 결과 공개", "안내")
    monkeypatch.setattr(GenericEngineSource, "_load_page", lambda self, page_index: html)
    with caplog.at_level(logging.WARNING):
        assert source(board="news").fetch(date(2026, 8, 31)) == []
    assert "excluded category=unknown" in caplog.text


def test_present_rows_with_zero_candidates_raise_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = payload().replace("doBbsFView", "unsupportedView")
    monkeypatch.setattr(GenericEngineSource, "_load_page", lambda self, page_index: html)
    with pytest.raises(ValueError, match="listing_rows=2, parsed=0"):
        source().fetch(date(2026, 8, 31))


def test_partial_parsing_is_not_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    html = payload().replace("20260723", "invalid")
    monkeypatch.setattr(GenericEngineSource, "_load_page", lambda self, page_index: html)
    with caplog.at_level(logging.WARNING):
        assert len(source().fetch(date(2026, 8, 31))) == 1
    assert "partial parsing: listing_rows=2 parsed=1" in caplog.text


def test_real_empty_listing_is_distinguished(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(GenericEngineSource, "_load_page", lambda self, page_index: EMPTY_PAGE)
    with caplog.at_level(logging.DEBUG):
        assert source().fetch(date(2026, 8, 31)) == []
    assert "status=empty_board" in caplog.text
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


@pytest.mark.parametrize("html", [
    "<html>Access denied</html>", EMPTY_PAGE.replace("게시물이 없습니다", "변경된 구조"),
])
def test_unknown_response_is_not_treated_as_empty(
    html: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(GenericEngineSource, "_load_page", lambda self, page_index: html)
    with pytest.raises(ValueError, match="absence of notices is unverified"):
        source().fetch(date(2026, 8, 31))


@pytest.mark.parametrize("setting", ["true", "false", '"true"'])
def test_recruitment_setting_load_and_registry_wiring(tmp_path: Path, setting: str) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'timezone = "Asia/Seoul"\ndb_path = "test.db"\nenabled_sources = ["gwanak"]\n'
        '[sources.gwanak]\nmunicipality = "Gwanak"\nsource_type = "html"\n'
        f'list_url = "{GOSI_URL}"\nengine_type = "generic_egov_bbs"\n'
        f'recruitment_only = {setting}\n', encoding="utf-8",
    )
    if setting == '"true"':
        with pytest.raises(ValueError, match="recruitment_only"):
            load_config(config_path)
        return
    config = load_config(config_path)
    sources = SourceRegistry(config, RequestsHttpClient(), ZoneInfo("Asia/Seoul"))
    collector = sources.build_enabled_sources()[0]
    assert isinstance(collector, GenericEngineSource)
    assert collector.recruitment_only is (setting == "true")
