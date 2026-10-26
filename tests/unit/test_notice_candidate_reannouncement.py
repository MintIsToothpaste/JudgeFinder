from __future__ import annotations

import pytest

from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title


@pytest.mark.parametrize("title", [
    "「2026년 전주시 산림교육(유아숲체험원・숲해설)운영사업」제안서 평가위원(후보자)재공고",
    "제안서 평가위원 ( 후보자 ) 재공고",
    "제안서 평가위원(예비위원) 재공고",
])
def test_explicit_candidate_reannouncement_is_recruitment(title: str) -> None:
    assert classify_notice_title(title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize("title", [
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
])
def test_unrelated_result_or_cancelled_reannouncement_is_not_recruitment(title: str) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT
