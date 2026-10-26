from __future__ import annotations

import pytest

from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title


@pytest.mark.parametrize("title", [
    "목포항구축제 행사 대행 용역」제안서 평가위원(후보자) 등록 신청 공고",
    "2026 목포해상W쇼 행사대행 용역 제안서 평가위원(후보자) 등록 신청 공고",
    "목포권 기독교 근대역사관 전시설계 및 전시물 제작·설치 제안서 평가위원(후보자) 등록 신청 공고",
    "제안서 평가위원(예비위원) 등록 신청 안내",
    "제안서 평가위원 등록 신청 공고",
    "강릉시 2026년 지능형교통체계(ITS) 구축 사업자 제안서 평가위원 후보자 등록 신청 안내 공고",
    "제안서 평가위원 예비위원 등록 신청 안내",
    "제안서 평가위원(후보자) 등록 신청 안내 공고",
])
def test_candidate_registration_announcement_is_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize("title", [
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
])
def test_other_registration_titles_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT


@pytest.mark.parametrize("title", [
    "2026년 강진군 정보시스템 유지관리 제안서 평가위원 추천 의뢰",
    "제안서 평가위원(후보자) 추천 의뢰 공고",
    "제안서 평가위원(예비위원) 추천 요청 안내",
    "제안서 평가위원 추천 요청",
    "제안서 평가위원 추천요청(고창군 CCTV 통합관제센터 시스템 및 CCTV 유지보수)",
    "제안서 평가위원(후보자) 추천 요청 안내(시설 유지보수 용역)",
])
def test_explicit_evaluator_nomination_request_is_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize("title", [
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
])
def test_other_nomination_titles_are_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT
