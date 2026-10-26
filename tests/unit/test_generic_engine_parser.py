from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from judgefinder.adapters.sources.generic_engine.parser import parse_generic_engine_candidates
from judgefinder.domain.source_profiles import EngineType


def test_parse_generic_engine_hanam_gosi_list() -> None:
    payload = (Path(__file__).parents[1] / "fixtures/hanam_gosi_list.html").read_text(
        encoding="utf-8"
    )
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.hanam.go.kr/www/selectGosiList.do?key=171",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 3
    assert candidates[0].title == (
        "「하남 교산지구 자족용지 핵심 타깃기업 발굴 용역」 제안서 평가위원(후보자) 모집 공고"
    )
    assert candidates[0].url == (
        "https://www.hanam.go.kr/www/selectGosiData.do"
        "?key=171&not_ancmt_mgt_no=52650&not_ancmt_se_code=01,04"
    )
    assert candidates[0].published_date == date(2026, 9, 22)
    assert candidates[1].published_date == date(2026, 9, 23)
    assert candidates[2].published_date == date(2022, 12, 5)


@pytest.mark.parametrize(
    "href",
    [
        "/www/selectGosiList.do?not_ancmt_mgt_no=52650",
        "/www/selectGosiData.do",
        "/www/selectGosiData.do?not_ancmt_mgt_no=",
        "/www/selectGosiData.do?not_ancmt_mgt_no=invalid",
        "/www/selectGosiData.do?not_ancmt_mgt_no=-1",
        "/www/selectGosiData.do?not_ancmt_mgt_no=0",
        "/www/selectGosiData.do?not_ancmt_mgt_no=52650&not_ancmt_mgt_no=52651",
        "/www/selectGosiData.do.bak?not_ancmt_mgt_no=52650",
        "/www/download.do?not_ancmt_mgt_no=52650",
        "/www/other.do?next=selectGosiData.do&not_ancmt_mgt_no=52650",
    ],
)
def test_parse_generic_engine_rejects_invalid_gosi_detail_links(href: str) -> None:
    payload = f'<table><tr><td>2026-09-22</td><td><a href="{href}">Notice</a></td></tr></table>'
    assert parse_generic_engine_candidates(
        payload,
        list_url="https://www.hanam.go.kr/www/selectGosiList.do?key=171",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    ) == []


@pytest.mark.parametrize("registered", ["", "invalid", "20260230"])
def test_parse_gosi_does_not_replace_invalid_registration_date_with_posting_period(
    registered: str,
) -> None:
    payload = f"""
    <table>
      <thead><tr><th>제목</th><th>등록일</th><th>게재기간</th></tr></thead>
      <tbody><tr>
        <td><a href="./selectGosiData.do?not_ancmt_mgt_no=52650">Notice</a></td>
        <td>{registered}</td><td>2026-09-22 ~ 2026-10-08</td>
      </tr></tbody>
    </table>
    """
    assert parse_generic_engine_candidates(
        payload,
        list_url="https://www.hanam.go.kr/www/selectGosiList.do?key=171",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    ) == []


def test_parse_gosi_detail_links_without_table_headers() -> None:
    payload = """
    <table><tr><td>2026-09-22</td>
      <td><a href="./selectGosiData.do?not_ancmt_mgt_no=52650">Notice</a></td>
    </tr></table>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.hanam.go.kr/www/selectGosiList.do?key=171",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )
    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 9, 22)


@pytest.mark.parametrize(
    "attributes",
    [
        'href="#" data-action="/www/selectGosiData.do?not_ancmt_mgt_no=52650"',
        'href="#" onclick="open(\'/www/selectGosiData.do?not_ancmt_mgt_no=52650\')"',
    ],
)
def test_parse_gosi_detail_action_links(attributes: str) -> None:
    payload = (
        '<table><tr><td>2026-09-22</td>'
        f'<td><a {attributes}>Notice</a></td></tr></table>'
    )
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.hanam.go.kr/www/selectGosiList.do?key=171",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )
    assert len(candidates) == 1
    assert candidates[0].url == (
        "https://www.hanam.go.kr/www/selectGosiData.do?not_ancmt_mgt_no=52650"
    )


def test_parse_gosi_json_links_preserves_explicit_registration_date() -> None:
    payload = json.dumps({"items": [{
        "title": "Notice",
        "url": "/www/selectGosiData.do?not_ancmt_mgt_no=52650",
        "regDate": "20260923",
        "postingPeriod": "2026-09-22 ~ 2026-10-08",
    }]})
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.hanam.go.kr/www/selectGosiList.do?key=171",
        engine_type=EngineType.JSON_LIST_API,
    )
    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 9, 23)


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


def test_parse_generic_engine_supports_data_action_notice_links() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>20260313</td>
            <td>
              <a
                href="#"
                data-action="/portal/saeol/gosi/view.do?notAncmtMgtNo=41717&mId=0301040000"
                onclick="req.post(this); return false;"
              >
                Proposal evaluation result notice
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.yc.go.kr/portal/saeol/gosi/list.do?mId=0301040000",
        engine_type=EngineType.SAEOL_GOSI,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://www.yc.go.kr/portal/saeol/gosi/view.do?notAncmtMgtNo=41717&mId=0301040000"
    )


def test_parse_generic_engine_supports_view_ulsan_notice_links() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026-03-13</td>
            <td>
              <a href="/board/view.ulsan?boardId=BBS_0000057&startPage=1&dataSid=720254">
                Notice on rice seedling support
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.junggu.ulsan.kr/board/list.ulsan?boardId=BBS_0000057&startPage=1",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://www.junggu.ulsan.kr/board/view.ulsan?boardId=BBS_0000057&startPage=1&dataSid=720254"
    )


def test_parse_generic_engine_supports_bbs_msg_detail_notice_links() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026.03.13</td>
            <td>
              <a href="/main/bbs/bbsMsgDetail.do?msg_seq=13476&bcd=announce">
                District notice
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.icdonggu.go.kr/main/information/news/announce.jsp",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://www.icdonggu.go.kr/main/bbs/bbsMsgDetail.do?msg_seq=13476&bcd=announce"
    )


def test_parse_generic_engine_supports_eminwon_announce_detail_links() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>[Any District Notice]</td>
            <td>
              <a href="/main/eminwon/eminwonAnnounceDetail.do?mgt_no=70083">
                Care service provider recruitment notice
              </a>
            </td>
            <td>2026-03-13</td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.namdong.go.kr/main/news/announce.jsp",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://www.namdong.go.kr/main/eminwon/eminwonAnnounceDetail.do?mgt_no=70083"
    )


def test_parse_generic_engine_supports_ofr_search_detail_links() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026-03-13</td>
            <td>
              <a href="#" onclick="javaScript:searchDetail('43729')">
                Buk-gu notice
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url=(
            "https://eminwon.bukgu.ulsan.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
            "?jndinm=OfrNotAncmtEJB&context=NTIS&homepage_pbs_yn=Y&subCheck=Y"
            "&ofr_pageSize=10&not_ancmt_se_code=01,03,04&title=%EA%B3%A0%EC%8B%9C%EA%B3%B5%EA%B3%A0"
            "&countYn=Y&nodate_recent_mm=12&epcCheck=Y&method=selectListOfrNotAncmt"
            "&methodnm=selectListOfrNotAncmtHomepage"
        ),
        engine_type=EngineType.EMINWON_OFR,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://eminwon.bukgu.ulsan.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
        "?jndinm=OfrNotAncmtEJB&context=NTIS&homepage_pbs_yn=Y&subCheck=Y&ofr_pageSize=10"
        "&not_ancmt_se_code=01%2C03%2C04&title=%EA%B3%A0%EC%8B%9C%EA%B3%B5%EA%B3%A0"
        "&countYn=Y&nodate_recent_mm=12&epcCheck=Y&method=selectOfrNotAncmt"
        "&methodnm=selectOfrNotAncmtRegst&not_ancmt_mgt_no=43729"
    )


def test_parse_generic_engine_resolves_emwp_relative_links_from_site_root() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026-03-13</td>
            <td>
              <a href="emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do?not_ancmt_mgt_no=27478">
                Dong-gu notice
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url=(
            "https://eminwon.donggu.ulsan.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
            "?jndinm=OfrNotAncmtEJB&method=selectListOfrNotAncmt"
        ),
        engine_type=EngineType.EMINWON_OFR,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://eminwon.donggu.ulsan.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do?not_ancmt_mgt_no=27478"
    )


def test_parse_generic_engine_supports_mode_v_detail_links() -> None:
    payload = """
    <html>
      <body>
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
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.yd21.go.kr/kr/html/sub02/020103.html?GotoPage=1",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://www.yd21.go.kr/kr/html/sub02/020103.html?mode=V&no=2ef66d4431ac1e9f2fcf6d188a06976c&GotoPage=1"
    )


def test_parse_generic_engine_uses_row_title_when_anchor_text_is_numeric() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td><a href="#" onclick="javaScript:searchDetail('36786')">1132</a></td>
            <td>Yangyang Notice No. 2026-324</td>
            <td>Land survey public notice</td>
            <td>Civil Affairs Division</td>
            <td>2026-03-13</td>
            <td>19</td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url=(
            "https://eminwon.yangyang.go.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
            "?jndinm=OfrNotAncmtEJB&context=NTIS&homepage_pbs_yn=Y&subCheck=Y"
            "&ofr_pageSize=10&not_ancmt_se_code=01,04,05,06"
            "&title=%EA%B3%A0%EC%8B%9C%EA%B3%B5%EA%B3%A0&countYn=Y"
            "&method=selectListOfrNotAncmt&methodnm=selectListOfrNotAncmtHomepage"
        ),
        engine_type=EngineType.EMINWON_OFR,
    )

    assert len(candidates) == 1
    assert candidates[0].title == "Land survey public notice"
    assert candidates[0].published_date == date(2026, 3, 13)


def test_parse_generic_engine_supports_content_id_detail_links() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026.03.13</td>
            <td><a href="?id=30755&dn=">Yecheon announcement</a></td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.ycg.kr/open.content/ko/administrative/news/announcement/?p=1",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://www.ycg.kr/open.content/ko/administrative/news/announcement/?id=30755&dn="
    )


def test_parse_generic_engine_supports_show_detail_paths() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026-03-13</td>
            <td>
              <a href="/home/www/open_information/yeongam_news/announcement/announcement_01/show/39047?page=1&search=&not_ancmt_sj=">
                Yeongam announcement
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url=(
            "https://www.yeongam.go.kr/home/www/open_information/yeongam_news/"
            "announcement/announcement_01/yeongam.go?page=1"
        ),
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://www.yeongam.go.kr/home/www/open_information/yeongam_news/announcement/announcement_01/show/39047?page=1&search=&not_ancmt_sj="
    )


def test_parse_generic_engine_supports_popup_center_detail_links() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026-03-13</td>
            <td>
              <a
                href="#popup"
                onclick="popupCenter('http://eminwon.brcn.go.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do?subCheck=N&amp;jndinm=OfrNotAncmtEJB&amp;context=NTIS&amp;method=selectOfrNotAncmt&amp;methodnm=selectOfrNotAncmtRegst&amp;not_ancmt_se_code=01,02,04&amp;not_ancmt_mgt_no=55063', 'popwin'); return false;"
              >
                Boryeong city notice
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://www.brcn.go.kr/prog/eminwon/kor/BB/sub04_03_01/list.do?pageIndex=1",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "http://eminwon.brcn.go.kr/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do?subCheck=N&jndinm=OfrNotAncmtEJB&context=NTIS&method=selectOfrNotAncmt&methodnm=selectOfrNotAncmtRegst&not_ancmt_se_code=01,02,04&not_ancmt_mgt_no=55063"
    )


def test_parse_generic_engine_strips_session_path_params_from_detail_links() -> None:
    payload = """
    <html>
      <body>
        <table>
          <tr>
            <td>2026-03-13</td>
            <td>
              <a href="./selectBbsNttView.do;JSESSIONID=ABC123?key=478&amp;bbsNo=87&amp;nttNo=200210&amp;pageIndex=1">
                Donghae notice
              </a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    candidates = parse_generic_engine_candidates(
        payload,
        list_url="https://dh.go.kr/www/selectBbsNttList.do?bbsNo=87&key=478&pageIndex=1",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )

    assert len(candidates) == 1
    assert candidates[0].published_date == date(2026, 3, 13)
    assert (
        candidates[0].url
        == "https://dh.go.kr/www/selectBbsNttView.do?key=478&bbsNo=87&nttNo=200210&pageIndex=1"
    )
