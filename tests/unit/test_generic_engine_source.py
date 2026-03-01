from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.source_profiles import EngineType
from judgefinder.infrastructure.http.client import HttpResponse


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, Mapping[str, str] | None]] = []

    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
    ) -> str:
        _ = timeout_seconds
        self.calls.append((url, use_session, headers))
        if "pageIndex=1" in url:
            return """
            <html>
              <table>
                <tr>
                  <td>2026-02-22</td>
                  <td><a href="/www/selectBbsNttView.do?bbsNo=18&nttNo=7001">평가위원 모집</a></td>
                </tr>
              </table>
            </html>
            """
        return "<html><body>empty</body></html>"

    def get_response(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
    ) -> HttpResponse:
        _ = url
        _ = timeout_seconds
        _ = headers
        _ = use_session
        return HttpResponse(status_code=200, text="", headers={}, url=url)


class FakeAnseongSaeolClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, Mapping[str, str] | None]] = []

    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
    ) -> str:
        _ = timeout_seconds
        self.calls.append((url, use_session, headers))
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        page = query.get("page", [""])[0]
        if page == "1":
            return """
            <html>
              <body>
                <table>
                  <tr>
                    <td>2026.02.27</td>
                    <td>
                      <a href="#" onclick="javascript:boardView('1', '71148');return false;">
                        안성시 먹거리통합지원센터 전문 운영관리 용역 제안서 평가위원 공개 모집 공고
                      </a>
                    </td>
                  </tr>
                </table>
              </body>
            </html>
            """
        return "<html><body>empty</body></html>"

    def get_response(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
    ) -> HttpResponse:
        _ = timeout_seconds
        _ = headers
        _ = use_session
        return HttpResponse(status_code=200, text="", headers={}, url=url)


def test_generic_engine_source_fetches_target_date_with_request_strategy() -> None:
    http_client = FakeHttpClient()
    source = GenericEngineSource(
        slug="city",
        municipality="City",
        source_type=SourceType.HTML,
        list_url="https://city.go.kr/www/selectBbsNttList.do?bbsNo=18",
        engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=http_client,
        keywords=("평가위원",),
        max_pages=2,
        use_session=True,
        include_referer=True,
    )

    notices = source.fetch(date(2026, 2, 22))

    assert len(notices) == 1
    assert notices[0].url == "https://city.go.kr/www/selectBbsNttView.do?bbsNo=18&nttNo=7001"
    assert "pageIndex=1" in http_client.calls[0][0]
    assert "searchKrwd" in http_client.calls[0][0]
    assert http_client.calls[0][1] is True
    assert http_client.calls[0][2] is not None
    assert "Referer" in http_client.calls[0][2]


def test_generic_engine_source_supports_anseong_saeol_query_shape() -> None:
    keyword = "\ud3c9\uac00\uc704\uc6d0"
    http_client = FakeAnseongSaeolClient()
    source = GenericEngineSource(
        slug="anseong",
        municipality="Anseong",
        source_type=SourceType.HTML,
        list_url="https://www.anseong.go.kr/portal/saeol/gosiList.do?mId=0501040000",
        engine_type=EngineType.SAEOL_GOSI,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=http_client,
        keywords=(keyword,),
        max_pages=2,
    )

    notices = source.fetch(date(2026, 2, 27))

    assert len(notices) == 1
    assert (
        notices[0].url
        == "https://www.anseong.go.kr/portal/saeol/gosiView.do?notAncmtMgtNo=71148&mId=0501040000"
    )

    first_url = http_client.calls[0][0]
    first_query = parse_qs(urlparse(first_url).query, keep_blank_values=True)
    assert first_query.get("page") == ["1"]
    assert first_query.get("searchType") == ["NOT_ANCMT_SJ"]
    assert first_query.get("searchTxt") == [keyword]


def test_generic_engine_source_keeps_default_saeol_query_shape() -> None:
    keyword = "\ud3c9\uac00\uc704\uc6d0"
    http_client = FakeHttpClient()
    source = GenericEngineSource(
        slug="djjunggu",
        municipality="Daejeon Jung-gu",
        source_type=SourceType.HTML,
        list_url="https://www.djjunggu.go.kr/prog/saeolGosi/GOSI/sub03_06/list.do",
        engine_type=EngineType.SAEOL_GOSI,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=http_client,
        keywords=(keyword,),
        max_pages=1,
    )

    _ = source.fetch(date(2026, 2, 22))

    first_url = http_client.calls[0][0]
    first_query = parse_qs(urlparse(first_url).query, keep_blank_values=True)
    assert first_query.get("pageIndex") == ["1"]
    assert first_query.get("searchKeyword") == [keyword]
    assert first_query.get("searchCondition") == ["sj"]
