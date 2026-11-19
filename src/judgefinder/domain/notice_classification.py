from __future__ import annotations

import re
from enum import Enum


class NoticeCategory(str, Enum):
    RECRUITMENT = "recruitment"
    RESULT = "result"
    UNKNOWN = "unknown"


_COMMITTEE = r"(?:평가|심사|심의)위원(?:회(?:위원)?)?(?:\((?:후보자|예비위원)\)|후보자|예비위원)?"
_RECRUITMENT_ACTION = (
    r"(?:을|를)?(?:아래와같이|다음과같이)?(?:공개)?"
    r"(?:모집|공모|등록(?:신청)?(?:공고|안내)|추천(?:요청|의뢰)|재공고)"
)
_COMMITTEE_RECRUITMENT = re.compile(_COMMITTEE + _RECRUITMENT_ACTION)
_EVALUATOR_RECRUITMENT = re.compile(
    r"평가위원(?:\((?:후보자|예비위원)\)|후보자|예비위원)?" + _RECRUITMENT_ACTION,
)
_EVALUATOR_APPLICATION_FORM = re.compile(r"평가위원(?:\(후보자\)|후보자)?등록신청서")
_PROPOSAL_ROLE = re.compile(
    r"제안서(?:를|의|에대한)?(?:공정한|객관적인|공정하고객관적인)?"
    r"(?:(?:기술능력|기술|정량|정성)적?)?(?:평가|심사|심의)(?!결과|점수공개)",
)
_ATTACHMENT_ROLE = re.compile(_PROPOSAL_ROLE.pattern + r"|사업설명서[^.。]{0,40}평가업무")
_PROPOSAL_EVALUATION_CONTENT = re.compile(
    r"평가내용[:：]?제안서적합성평가|방법[:：]입찰참여자의제안내용을배점표에따라평가",
)
_PROJECT_NAME = re.compile(r"[「『《〈“]([^」』》〉”]+)[」』》〉”]")
_OPERATOR_COMMITTEE_PROJECT = re.compile(r"^(.+?민간위탁)[」』》〉”]?수탁기관선정심사위원회")
_PROJECT_SECURITY_OATH = re.compile(
    r"보안각서본인은[「『《〈“]([^」』》〉”]+)[」』》〉”].{0,100}?"
    r"심사관련정보\(제안서내용,평가결과",
)
_COMMITTEE_ROSTER = re.compile(
    _COMMITTEE + r"(?:회)?(?:선정)?(?:명단|구성현황)(?:공개|공고|안내|$)",
)


def committee_project_names(title: str, body_text: str = "") -> tuple[str, ...]:
    """Use a quoted project name only when it identifies this notice's title."""
    headline = "".join(title.split())
    names = _PROJECT_NAME.findall(title) + _PROJECT_NAME.findall(body_text)
    operator_project = _OPERATOR_COMMITTEE_PROJECT.match(headline)
    if operator_project:
        names.append(operator_project[1].lstrip("「『《〈“"))
    return tuple(
        name for value in names
        if len(name := "".join(value.split())) >= 6 and name in headline
    )


def classify_committee_notice(
    title: str, body_text: str = "", attachment_text: str = "",
) -> NoticeCategory:
    """Classify alternative committee names using the official recruitment and role."""
    headline, body, attachment = (
        "".join(text.split()) for text in (title, body_text, attachment_text)
    )
    if (is_notice_result_title(title) or _COMMITTEE_ROSTER.search(headline)
            or re.search(r"(?:심의|위촉)(?:\([^)]*\))?결과", headline)):
        return NoticeCategory.RESULT
    if re.search(r"취소|철회|(?:모집|공모|접수)마감(?:안내|공고|$)", headline):
        return NoticeCategory.UNKNOWN
    if classify_notice(title, body_text) is NoticeCategory.RECRUITMENT:
        return NoticeCategory.RECRUITMENT
    recruitment = (
        _COMMITTEE_RECRUITMENT.search(headline) or _COMMITTEE_RECRUITMENT.search(body)
        or (re.search(_COMMITTEE, headline)
            and "접수기간" in body and "접수방법" in body
            and ("모집인원" in body or "모집분야" in body))
    )
    if not recruitment:
        return NoticeCategory.UNKNOWN
    if _PROPOSAL_ROLE.search(headline) or _PROPOSAL_ROLE.search(body):
        return NoticeCategory.RECRUITMENT
    if attachment:
        projects = committee_project_names(title, body_text)
        if (_PROPOSAL_EVALUATION_CONTENT.search(attachment)
                and any(project in _PROJECT_NAME.findall(attachment) for project in projects)):
            return NoticeCategory.RECRUITMENT
        if any(project in projects for project in _PROJECT_SECURITY_OATH.findall(attachment)):
            return NoticeCategory.RECRUITMENT
        if any(
            _ATTACHMENT_ROLE.search(attachment, match.end(), match.end() + 100)
            for project in projects
            for match in re.finditer(re.escape(project), attachment)
        ):
            return NoticeCategory.RECRUITMENT
    return NoticeCategory.UNKNOWN


def is_notice_result_title(title: str) -> bool:
    compact = "".join(title.split())
    return "평가점수공개" in compact or bool(
        re.search(r"(?:평가(?:위원회)?|선정|모집|심사|개최)(?:\([^)]*\))?결과", compact)
    )


def classify_notice_title(title: str) -> NoticeCategory:
    compact = "".join(title.split()).replace("평가(선정심사)위원", "평가위원")
    if "평가위원" not in compact:
        return NoticeCategory.UNKNOWN
    if is_notice_result_title(title):
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
    if category is not NoticeCategory.UNKNOWN:
        return category
    compact_title = "".join(title.split())
    if any(marker in compact_title for marker in (
        "취소", "철회", "마감", "결과", "명단", "세부평가",
    )):
        return category
    compact = "".join(body_text.split())
    if re.search(r"(?:평가|선정)결과(?:를)?(?:공개|공고)|공고(?:를)?취소", compact):
        return category
    if "평가위원" not in compact_title:
        if (
            re.search(r"제안서선정위원(?:\(후보자\)|후보자)?(?:공개)?모집", compact_title)
            and _EVALUATOR_APPLICATION_FORM.search(compact)
        ):
            return NoticeCategory.RECRUITMENT
        if any(marker in compact_title for marker in ("제안서평가", "제안서평기위원")) and (
            _EVALUATOR_RECRUITMENT.search(compact)
            or (
                "제안서평가모집공고" in compact_title
                and _EVALUATOR_APPLICATION_FORM.search(compact)
            )
        ):
            return NoticeCategory.RECRUITMENT
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
