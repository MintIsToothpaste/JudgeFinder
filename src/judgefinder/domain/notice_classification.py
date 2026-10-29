from __future__ import annotations

import re
from enum import Enum


class NoticeCategory(str, Enum):
    RECRUITMENT = "recruitment"
    RESULT = "result"
    UNKNOWN = "unknown"


def classify_notice_title(title: str) -> NoticeCategory:
    compact = "".join(title.split())
    if "평가위원" not in compact:
        return NoticeCategory.UNKNOWN
    if re.search(r"(?:평가(?:위원회)?|선정|모집|심사|개최)(?:\([^)]*\))?결과", compact):
        return NoticeCategory.RESULT
    if "평가점수공개" in compact:
        return NoticeCategory.RESULT
    # Candidate registration announcements are recruitment even without "모집".
    registration = re.search(
        r"평가위원(?:\((?:후보자|예비위원)\)|후보자|예비위원)?"
        r"등록(?:신청)?(?:공고|안내(?:공고)?)$", compact,
    )
    # Explicit requests for evaluator nominations also accept candidate registrations.
    nomination = re.search(
        r"평가위원(?:\((?:후보자|예비위원)\))?추천(?:의뢰|요청)(?:공고|안내)?"
        r"(?:\((?![^()]*(?:결과|명단|현황))[^()]+\))?$", compact,
    )
    reannouncement = re.search(r"평가위원\((?:후보자|예비위원)\)재공고$", compact)
    open_call = re.search(r"평가위원(?:\(후보자\)|후보자)?공모(?:공고|알림|안내)?$", compact)
    if ("모집" in compact or registration or nomination or reannouncement or open_call) and not any(
        marker in compact for marker in ("취소", "철회", "마감")
    ):
        return NoticeCategory.RECRUITMENT
    return NoticeCategory.UNKNOWN


def classify_notice(title: str, body_text: str = "") -> NoticeCategory:
    category = classify_notice_title(title)
    if category is not NoticeCategory.UNKNOWN or "평가위원" not in "".join(title.split()):
        return category
    compact_title = "".join(title.split())
    if any(marker in compact_title for marker in (
        "취소", "철회", "마감", "결과", "명단", "세부평가",
    )):
        return category
    compact = "".join(body_text.split())
    if re.search(r"(?:평가|선정)결과(?:를)?(?:공개|공고)|공고(?:를)?취소", compact):
        return category
    # Only an explicitly scoped body with all application signals can rescue a title.
    if (
        "평가위원" in compact
        and re.search(r"(?:모집|접수)기간[:：]?\d{4}[./-]\d{1,2}", compact)
        and re.search(r"모집인원[:：]?(?:(?:예비|제안서)?평가위원)?\d+명", compact)
        and re.search(r"(?:신청|접수)방법[:：]", compact)
    ):
        return NoticeCategory.RECRUITMENT
    return category
