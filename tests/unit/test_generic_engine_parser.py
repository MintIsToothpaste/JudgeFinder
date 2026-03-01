from __future__ import annotations

from datetime import date

from judgefinder.adapters.sources.generic_engine.parser import parse_generic_engine_candidates
from judgefinder.domain.source_profiles import EngineType


def test_parse_generic_engine_html_candidates() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026-02-22</td>
            <td>
              <a href="/www/selectBbsNttView.do?bbsNo=18&nttNo=1001">
                평가위원 모집 공고
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://city.go.kr/www/selectBbsNttList.do?bbsNo=18",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].title == "평가위원 모집 공고"
    assert candidates[0].url == "https://city.go.kr/www/selectBbsNttView.do?bbsNo=18&nttNo=1001"
    assert candidates[0].published_date == date(2026, 2, 22)


def test_parse_generic_engine_json_candidates() -> None:
    payload = """
    {
      "items": [
        {
          "title": "평가위원 후보자 모집",
          "nttNo": "396005",
          "bbsNo": "18",
          "regDate": "2026-02-22"
        }
      ]
    }
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.jecheon.go.kr/www/selectBbsNttList.do?key=5233&bbsNo=18",
        engine_type=EngineType.JSON_LIST_API,
    )

    assert len(candidates) == 1
    assert candidates[0].title == "평가위원 후보자 모집"
    assert (
        candidates[0].url
        == "https://www.jecheon.go.kr/www/selectBbsNttView.do?bbsNo=18&nttNo=396005&key=5233"
    )
    assert candidates[0].published_date == date(2026, 2, 22)


def test_parse_generic_engine_saeol_boardview_candidates() -> None:
    payload = """
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
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.anseong.go.kr/portal/saeol/gosiList.do?mId=0501040000",
        engine_type=EngineType.SAEOL_GOSI,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 2, 27)
    assert (
        candidates[0].url
        == "https://www.anseong.go.kr/portal/saeol/gosiView.do?notAncmtMgtNo=71148&mId=0501040000"
    )


def test_parse_generic_engine_saeol_fn_search_detail_candidates() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026-02-27</td>
            <td>
              <a href="#" onclick="fn_search_detail('46819'); return false;">
                제안서 평가위원 모집 공고
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.djjunggu.go.kr/prog/saeolGosi/GOSI/sub03_06/list.do",
        engine_type=EngineType.SAEOL_GOSI,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 2, 27)
    assert (
        candidates[0].url
        == "https://www.djjunggu.go.kr/prog/saeolGosi/GOSI/sub03_06/view.do?notAncmtMgtNo=46819"
    )
