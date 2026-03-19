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
        verify_tls: bool = True,
    ) -> str:
        _ = timeout_seconds
        _ = verify_tls
        self.calls.append((url, use_session, headers))
        if "pageIndex=1" in url:
            return """
            <html>
              <table>
                <tr>
                  <td>2026-02-22</td>
                  <td><a href="/www/selectBbsNttView.do?bbsNo=18&nttNo=7001">?됯??꾩썝 紐⑥쭛</a></td>
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
        verify_tls: bool = True,
    ) -> HttpResponse:
        _ = url
        _ = timeout_seconds
        _ = headers
        _ = use_session
        _ = verify_tls
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
        verify_tls: bool = True,
    ) -> str:
        _ = timeout_seconds
        _ = verify_tls
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
                        Evaluator recruitment notice
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
        verify_tls: bool = True,
    ) -> HttpResponse:
        _ = timeout_seconds
        _ = headers
        _ = use_session
        _ = verify_tls
        return HttpResponse(status_code=200, text="", headers={}, url=url)


class FakeCurPageClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, Mapping[str, str] | None]] = []

    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        _ = timeout_seconds
        _ = verify_tls
        self.calls.append((url, use_session, headers))
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if query.get("curPage") == ["1"]:
            return """
            <html>
              <table>
                <tr>
                  <td>2026-03-13</td>
                  <td><a href="/nbgosi/view?sno=100">Busan notice</a></td>
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
        verify_tls: bool = True,
    ) -> HttpResponse:
        _ = timeout_seconds
        _ = headers
        _ = use_session
        _ = verify_tls
        return HttpResponse(status_code=200, text="", headers={}, url=url)


class FakeStartPageClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, Mapping[str, str] | None]] = []

    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        _ = timeout_seconds
        _ = verify_tls
        self.calls.append((url, use_session, headers))
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if query.get("startPage") == ["1"]:
            return """
            <html>
              <table>
                <tr>
                  <td>2026-03-13</td>
                  <td>
                    <a href="/board/view.ulsan?boardId=BBS_0000057&startPage=1&dataSid=720254">
                      Ulsan Jung-gu notice
                    </a>
                  </td>
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
        verify_tls: bool = True,
    ) -> HttpResponse:
        _ = timeout_seconds
        _ = headers
        _ = use_session
        _ = verify_tls
        return HttpResponse(status_code=200, text="", headers={}, url=url)


class FakeGotoPageClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, Mapping[str, str] | None]] = []

    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        _ = timeout_seconds
        _ = verify_tls
        self.calls.append((url, use_session, headers))
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if query.get("GotoPage") == ["1"]:
            return """
            <html>
              <table>
                <tr>
                  <td>2026-03-13</td>
                  <td>
                    <a href="?mode=V&no=2ef66d4431ac1e9f2fcf6d188a06976c&GotoPage=1">
                      Yeongdong notice
                    </a>
                  </td>
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
        verify_tls: bool = True,
    ) -> HttpResponse:
        _ = timeout_seconds
        _ = headers
        _ = use_session
        _ = verify_tls
        return HttpResponse(status_code=200, text="", headers={}, url=url)


class FakePPageClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, Mapping[str, str] | None]] = []

    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        _ = timeout_seconds
        _ = verify_tls
        self.calls.append((url, use_session, headers))
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if query.get("p") == ["1"]:
            return """
            <html>
              <table>
                <tr>
                  <td>2026-03-13</td>
                  <td><a href="?id=30755&dn=">Yecheon announcement</a></td>
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
        verify_tls: bool = True,
    ) -> HttpResponse:
        _ = timeout_seconds
        _ = headers
        _ = use_session
        _ = verify_tls
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
        keywords=("?됯??꾩썝",),
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
    keyword = "evaluator"
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


def test_generic_engine_source_supports_portal_saeol_list_query_shape() -> None:
    keyword = "\ud3c9\uac00\uc704\uc6d0"
    http_client = FakeHttpClient()
    source = GenericEngineSource(
        slug="yeongcheon",
        municipality="Yeongcheon",
        source_type=SourceType.HTML,
        list_url="https://www.yc.go.kr/portal/saeol/gosi/list.do?mId=0301040000",
        engine_type=EngineType.SAEOL_GOSI,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=http_client,
        keywords=(keyword,),
        max_pages=1,
    )

    _ = source.fetch(date(2026, 2, 22))

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


def test_generic_engine_source_uses_cur_page_when_list_url_defines_it() -> None:
    http_client = FakeCurPageClient()
    source = GenericEngineSource(
        slug="busan",
        municipality="Busan",
        source_type=SourceType.HTML,
        list_url="https://www.busan.go.kr/nbgosi?curPage=1",
        engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=http_client,
        keywords=("?됯??꾩썝",),
        max_pages=1,
    )

    _ = source.fetch(date(2026, 3, 13))

    first_url = http_client.calls[0][0]
    first_query = parse_qs(urlparse(first_url).query, keep_blank_values=True)
    assert first_query.get("curPage") == ["1"]
    assert "pageIndex" not in first_query
    assert first_query.get("searchKrwd") == ["?됯??꾩썝"]

def test_generic_engine_source_uses_start_page_when_list_url_defines_it() -> None:
    http_client = FakeStartPageClient()
    source = GenericEngineSource(
        slug="uljunggu",
        municipality="Ulsan Jung-gu",
        source_type=SourceType.HTML,
        list_url=(
            "https://www.junggu.ulsan.kr/board/list.ulsan"
            "?boardId=BBS_0000057&menuCd=DOM_000000102003001000&startPage=1"
        ),
        engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=http_client,
        keywords=("?됯??꾩썝",),
        max_pages=1,
    )

    _ = source.fetch(date(2026, 3, 13))

    first_url = http_client.calls[0][0]
    first_query = parse_qs(urlparse(first_url).query, keep_blank_values=True)
    assert first_query.get("startPage") == ["1"]
    assert "pageIndex" not in first_query
    assert first_query.get("searchKrwd") == ["?됯??꾩썝"]


def test_generic_engine_source_uses_goto_page_when_list_url_defines_it() -> None:
    http_client = FakeGotoPageClient()
    source = GenericEngineSource(
        slug="yd21",
        municipality="Yeongdong",
        source_type=SourceType.HTML,
        list_url="https://www.yd21.go.kr/kr/html/sub02/020103.html?GotoPage=1",
        engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=http_client,
        keywords=("?됯??꾩썝",),
        max_pages=1,
    )

    _ = source.fetch(date(2026, 3, 13))

    first_url = http_client.calls[0][0]
    first_query = parse_qs(urlparse(first_url).query, keep_blank_values=True)
    assert first_query.get("GotoPage") == ["1"]
    assert "pageIndex" not in first_query
    assert first_query.get("searchKrwd") == ["?됯??꾩썝"]


def test_generic_engine_source_uses_p_when_list_url_defines_it() -> None:
    http_client = FakePPageClient()
    source = GenericEngineSource(
        slug="ycg",
        municipality="Yecheon",
        source_type=SourceType.HTML,
        list_url="https://www.ycg.kr/open.content/ko/administrative/news/announcement/?p=1",
        engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"),
        http_client=http_client,
        keywords=("?됯??꾩썝",),
        max_pages=1,
    )

    _ = source.fetch(date(2026, 3, 13))

    first_url = http_client.calls[0][0]
    first_query = parse_qs(urlparse(first_url).query, keep_blank_values=True)
    assert first_query.get("p") == ["1"]
    assert "pageIndex" not in first_query
    assert first_query.get("searchKrwd") == ["?됯??꾩썝"]

