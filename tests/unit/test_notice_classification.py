from __future__ import annotations

from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.domain.notice_classification import (
    NoticeCategory,
    classify_notice,
    classify_notice_title,
)
from judgefinder.domain.source_profiles import HtmlProfile

TITLE = "완주군 수소산업 중장기 마스터플랜 수립 용역 평가위원 공고"


BODY = "모집기간: 2026. 4. 9 ~ 2026. 4. 17. 모집인원: 예비평가위원 27명 신청방법: 방문"


PROFILE = HtmlProfile(
    container_selector="table",
    row_selector="tbody tr",
    date_selector="td.date",
    detail_title_selector="h1",
    detail_body_selector=".notice-body",
)


LISTING = (
    '<table><tbody><tr><td><a href="/1">평가위원 공고</a></td>'
    '<td class="date">2026-04-09</td></tr></tbody></table>'
)


DETAIL = f'<h1>{TITLE}</h1><div class="notice-body">{BODY}</div>'


@pytest.mark.parametrize(
    "title,body",
    [
        (TITLE, BODY),
        (
            "긴급구조시스템 제안서 평가위원(후보자) 추천",
            "모집인원 : 21명(제안서 평가위원의 3배수) 접수기간 : 2026. 4. 24. 접수방법 : 공문",
        ),
    ],
)
def test_explicit_application_body_rescues_ambiguous_title(title: str, body: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.UNKNOWN
    assert classify_notice(title, body) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    "title",
    [
        "평가위원 모집 취소공고",
        "평가위원 추천 철회",
        "평가위원 모집 마감",
        "평가위원 명단 공고",
        "평가위원 결과 공고",
        "평가위원별 세부평가 공고",
        "입찰 참가 업체 공고",
    ],
)
def test_body_does_not_override_nonrecruitment_title(title: str) -> None:
    assert classify_notice(title, BODY) is not NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    "body",
    [
        "",
        "평가위원 모집인원: 27명",
        BODY.replace("모집기간", "사업기간"),
        BODY.replace("모집인원", "입찰인원"),
        BODY.replace("신청방법", "선정방법"),
        BODY.replace("27명", "미정"),
        BODY.replace("2026. 4. 9", "미정"),
        BODY.replace("평가위원", "사업자"),
        BODY + " 평가결과를 공개합니다.",
        BODY + " 공고를 취소합니다.",
    ],
)
def test_incomplete_or_contradictory_body_is_not_recruitment(body: str) -> None:
    assert classify_notice(TITLE, body) is NoticeCategory.UNKNOWN


def test_body_processing_is_opt_in_and_scoped_to_notice_content() -> None:
    loader = Mock(return_value=DETAIL + "<footer>평가결과를 공개합니다.</footer>")
    candidate = parse_profiled_html(
        LISTING, list_url="https://example.go.kr/list", profile=PROFILE, detail_loader=loader
    )[0]
    assert classify_notice(candidate.title, candidate.body_text) is NoticeCategory.RECRUITMENT
    assert "평가결과" not in candidate.body_text
    assert candidate.title == TITLE and candidate.published_date == date(2026, 4, 9)
    disabled = parse_profiled_html(
        LISTING,
        list_url="https://example.go.kr/list",
        profile=replace(PROFILE, detail_body_selector=""),
        detail_loader=loader,
    )[0]
    assert not disabled.body_text
    assert classify_notice(disabled.title, disabled.body_text) is NoticeCategory.UNKNOWN


def test_configured_body_missing_fails_closed() -> None:
    with pytest.raises(ValueError, match="configured notice body missing"):
        parse_profiled_html(
            LISTING,
            list_url="https://example.go.kr/list",
            profile=PROFILE,
            detail_loader=Mock(return_value=f"<h1>{TITLE}</h1>"),
        )


def test_unneeded_body_does_not_change_established_title_classification() -> None:
    candidate = parse_profiled_html(
        LISTING,
        list_url="https://example.go.kr/list",
        profile=PROFILE,
        detail_loader=Mock(return_value="<h1>평가위원 모집 공고</h1>"),
    )[0]
    assert not candidate.body_text
    assert classify_notice(candidate.title) is NoticeCategory.RECRUITMENT


def test_before_window_does_not_require_body_request() -> None:
    loader = Mock()
    candidate = parse_profiled_html(
        LISTING,
        list_url="https://example.go.kr/list",
        profile=PROFILE,
        detail_loader=loader,
        detail_not_before=date(2026, 5, 1),
    )[0]
    loader.assert_not_called()
    assert not candidate.body_text


@pytest.mark.parametrize(
    "title",
    [
        "「2026년 전주시 산림교육(유아숲체험원・숲해설)운영사업」제안서 평가위원(후보자)재공고",
        "제안서 평가위원 ( 후보자 ) 재공고",
        "제안서 평가위원(예비위원) 재공고",
    ],
)
def test_explicit_candidate_reannouncement_is_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    "title",
    [
        "제안서 평가위원(후보자) 재공고 취소",
        "취소된 제안서 평가위원(후보자) 재공고",
        "철회된 제안서 평가위원(후보자) 재공고",
        "마감된 제안서 평가위원(후보자) 재공고",
        "제안서 평가위원(후보자) 재공고 마감",
        "평가위원(후보자) 평가 결과 재공고",
        "평가위원(후보자) 평가점수 공개 재공고",
        "평가 결과 공고 - 평가위원(후보자) 재공고",
        "평가위원회 구성 재공고",
        "평가위원(후보자) 명단 재공고",
        "사업자(후보자) 재공고",
        "평가위원(후보자) 재공고 시스템 구축",
    ],
)
def test_unrelated_result_or_cancelled_reannouncement_is_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    "title",
    [
        "목포항구축제 행사 대행 용역」제안서 평가위원(후보자) 등록 신청 공고",
        "2026 목포해상W쇼 행사대행 용역 제안서 평가위원(후보자) 등록 신청 공고",
        "목포권 기독교 근대역사관 전시설계 및 전시물 제작·설치 "
        "제안서 평가위원(후보자) 등록 신청 공고",
        "제안서 평가위원(예비위원) 등록 신청 안내",
        "제안서 평가위원 등록 신청 공고",
        "강릉시 2026년 지능형교통체계(ITS) 구축 사업자 제안서 평가위원 후보자 등록 신청 안내 공고",
        "제안서 평가위원 예비위원 등록 신청 안내",
        "제안서 평가위원(후보자) 등록 신청 안내 공고",
    ],
)
def test_candidate_registration_announcement_is_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    "title",
    [
        "제안서 평가위원(후보자) 등록 신청 결과 공고",
        "제안서 평가위원(후보자) 등록 신청 공고 취소",
        "제안서 평가위원(후보자) 등록 신청 마감 안내",
        "제안서 평가위원(후보자) 등록 신청 철회 공고",
        "제안서 평가위원(후보자) 등록 신청 현황 공개",
        "제안서 평가위원 등록 신청 시스템 구축 공고",
        "사업자 등록 신청 공고",
        "평가위원(후보자) 등록 신청 공고 평가점수 공개",
        "평가위원 후보자 등록 신청 안내 공고 취소",
        "평가위원 후보자 등록 신청 안내 공고 모집마감",
        "평가위원 후보자 등록 신청 안내 공고 결과 공개",
    ],
)
def test_other_registration_titles_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    "title",
    [
        "2026년 강진군 정보시스템 유지관리 제안서 평가위원 추천 의뢰",
        "제안서 평가위원(후보자) 추천 의뢰 공고",
        "제안서 평가위원(예비위원) 추천 요청 안내",
        "제안서 평가위원 추천 요청",
        "제안서 평가위원 추천요청(고창군 CCTV 통합관제센터 시스템 및 CCTV 유지보수)",
        "제안서 평가위원(후보자) 추천 요청 안내(시설 유지보수 용역)",
    ],
)
def test_explicit_evaluator_nomination_request_is_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    "title",
    [
        "제안서 평가위원 추천 의뢰 결과 공고",
        "제안서 평가위원 추천 요청 취소",
        "취소된 제안서 평가위원 추천 의뢰",
        "제안서 평가위원 추천 의뢰 마감",
        "제안서 평가위원 추천 의뢰 철회",
        "제안서 평가위원 추천 명단 공개",
        "제안서 평가위원 추천 의뢰 시스템 구축 공고",
        "평가위원 추천 방식 변경 안내",
        "업체 추천 의뢰",
        "제안서 평가위원 추천 요청(결과 공개)",
        "제안서 평가위원 추천 요청(추천 명단)",
        "제안서 평가위원 추천 요청(접수 현황)",
        "제안서 평가위원 추천 요청(시설 유지보수 용역) 취소",
    ],
)
def test_other_nomination_titles_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT
