from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from judgefinder.domain.source_profiles import EngineType

TITLE_KEYS: tuple[str, ...] = (
    "title",
    "sj",
    "subject",
    "notAncmtSj",
    "nttSj",
    "bbscttSj",
)
URL_KEYS: tuple[str, ...] = (
    "url",
    "link",
    "detailUrl",
    "viewUrl",
    "nttUrl",
)
DATE_KEYS: tuple[str, ...] = (
    "date",
    "pubDate",
    "regDate",
    "regdate",
    "ntceDate",
    "notAncmtDe",
    "frstRegisterPnttm",
    "registerDate",
)
NttNo_KEYS: tuple[str, ...] = ("nttNo", "ntt_no", "nttno")
BbsNo_KEYS: tuple[str, ...] = ("bbsNo", "bbs_no", "bbsno")
NotAncmtNo_KEYS: tuple[str, ...] = ("notAncmtMgtNo", "not_ancmt_mgt_no")
NotAncmtType_KEYS: tuple[str, ...] = ("notAncmtSeCode", "not_ancmt_se_code")

NOTICE_URL_HINTS: tuple[str, ...] = (
    "selectbbsnttview.do",
    "selecteminwonview.do",
    "ofraction.do",
    "sapgosibizprocess.do",
    "view.do",
    "nttno=",
    "notancmtmgtno=",
)

DATE_FRAGMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}"),
    re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일"),
    re.compile(r"\b\d{8}\b"),
)

JAVASCRIPT_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:nttNo|ntt_no|nttno)\D{0,5}(\d+)", re.IGNORECASE),
    re.compile(r"(?:bbsNo|bbs_no|bbsno)\D{0,5}(\d+)", re.IGNORECASE),
    re.compile(r"(?:notAncmtMgtNo|not_ancmt_mgt_no)\D{0,5}(\d+)", re.IGNORECASE),
)
BOARD_VIEW_PATTERN = re.compile(
    r"boardView\(\s*['\"]?\d+['\"]?\s*,\s*['\"]?(\d+)['\"]?\s*\)",
    re.IGNORECASE,
)
FN_SEARCH_DETAIL_PATTERN = re.compile(
    r"fn_search_detail\(\s*['\"]?(\d+)['\"]?\s*\)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class GenericNoticeCandidate:
    title: str
    url: str
    published_date: date
    searchable_text: str


def parse_generic_engine_candidates(
    payload: str,
    *,
    list_url: str,
    engine_type: EngineType,
) -> list[GenericNoticeCandidate]:
    if engine_type is EngineType.JSON_LIST_API or _looks_like_json_payload(payload):
        parsed = _parse_json_candidates(payload, list_url=list_url, engine_type=engine_type)
        if parsed:
            return _dedupe_candidates(parsed)
    return _dedupe_candidates(
        _parse_html_candidates(payload, list_url=list_url, engine_type=engine_type)
    )


def _parse_html_candidates(
    payload: str,
    *,
    list_url: str,
    engine_type: EngineType,
) -> list[GenericNoticeCandidate]:
    soup = BeautifulSoup(payload, "html.parser")
    candidates: list[GenericNoticeCandidate] = []

    for anchor in soup.select("a[href]"):
        href_value = anchor.get("href")
        if not isinstance(href_value, str) or not href_value.strip():
            continue
        url = _normalize_candidate_url(anchor, href_value.strip(), list_url=list_url)
        if not url:
            continue
        if not _is_probable_notice_url(url, engine_type=engine_type):
            continue

        title = _normalize_whitespace(anchor.get_text(" ", strip=True))
        if not title:
            continue

        context_text = _extract_context_text(anchor)
        published_date = _extract_date_from_text(context_text)
        if published_date is None:
            continue

        candidates.append(
            GenericNoticeCandidate(
                title=title,
                url=url,
                published_date=published_date,
                searchable_text=_normalize_whitespace(f"{title} {context_text}"),
            )
        )

    return candidates


def _parse_json_candidates(
    payload: str,
    *,
    list_url: str,
    engine_type: EngineType,
) -> list[GenericNoticeCandidate]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    candidates: list[GenericNoticeCandidate] = []
    for row in _iter_dicts(data):
        title = _first_string(row, TITLE_KEYS)
        if not title:
            continue
        published_date = _extract_date_from_mapping(row)
        if published_date is None:
            continue
        url = _extract_url_from_mapping(row, list_url=list_url)
        if not url:
            continue
        if not _is_probable_notice_url(url, engine_type=engine_type):
            continue

        searchable_text = _normalize_whitespace(
            " ".join(str(value) for value in row.values() if isinstance(value, (str, int, float)))
        )
        candidates.append(
            GenericNoticeCandidate(
                title=_normalize_whitespace(title),
                url=url,
                published_date=published_date,
                searchable_text=searchable_text,
            )
        )

    return candidates


def _normalize_candidate_url(anchor: Tag, href: str, *, list_url: str) -> str:
    onclick_raw = anchor.get("onclick")
    onclick = onclick_raw if isinstance(onclick_raw, str) else ""
    normalized_href = href.strip().lower()
    if normalized_href.startswith("javascript:") or (
        onclick and normalized_href in {"", "#", "javascript:;", "javascript:void(0);"}
    ):
        javascript_source = " ".join(
            part
            for part in (
                href,
                onclick,
            )
            if part
        )
        return _build_url_from_javascript(javascript_source, list_url=list_url)
    return urljoin(list_url, href)


def _build_url_from_javascript(source: str, *, list_url: str) -> str:
    ntt_no = _extract_identifier(source, JAVASCRIPT_ID_PATTERNS[0])
    bbs_no = _extract_identifier(source, JAVASCRIPT_ID_PATTERNS[1])
    not_ancmt_no = _extract_identifier(source, JAVASCRIPT_ID_PATTERNS[2])
    if not not_ancmt_no:
        not_ancmt_no = _extract_identifier(source, BOARD_VIEW_PATTERN)
    if not not_ancmt_no:
        not_ancmt_no = _extract_identifier(source, FN_SEARCH_DETAIL_PATTERN)

    parsed = urlparse(list_url)
    list_query = parse_qs(parsed.query, keep_blank_values=True)
    key = list_query.get("key", [""])[0]
    if ntt_no and bbs_no:
        query: dict[str, str] = {"bbsNo": bbs_no, "nttNo": ntt_no}
        if key:
            query["key"] = key
        return urlunparse(
            parsed._replace(
                path="/www/selectBbsNttView.do",
                query=urlencode(query),
                params="",
                fragment="",
            )
        )

    if not_ancmt_no and "/portal/saeol/gosilist.do" in parsed.path.lower():
        query = {"notAncmtMgtNo": not_ancmt_no}
        menu_id = list_query.get("mId", [""])[0]
        if menu_id:
            query["mId"] = menu_id
        return urlunparse(
            parsed._replace(
                path="/portal/saeol/gosiView.do",
                query=urlencode(query),
                params="",
                fragment="",
            )
        )

    if not_ancmt_no and "/prog/saeolgosi/" in parsed.path.lower():
        view_path = parsed.path
        if view_path.lower().endswith("/list.do"):
            view_path = view_path[:-len("/list.do")] + "/view.do"
        query = {"notAncmtMgtNo": not_ancmt_no}
        return urlunparse(
            parsed._replace(
                path=view_path,
                query=urlencode(query),
                params="",
                fragment="",
            )
        )

    if not_ancmt_no and key:
        notice_type = list_query.get("notAncmtSeCode", [""])[0]
        query = {"key": key, "notAncmtMgtNo": not_ancmt_no}
        if notice_type:
            query["notAncmtSeCode"] = notice_type
        return urlunparse(
            parsed._replace(
                path="/www/selectEminwonView.do",
                query=urlencode(query),
                params="",
                fragment="",
            )
        )
    return ""


def _extract_context_text(anchor: Tag) -> str:
    row = anchor.find_parent(["tr", "li", "article", "div"])
    if row is not None:
        return _normalize_whitespace(row.get_text(" ", strip=True))
    return _normalize_whitespace(anchor.get_text(" ", strip=True))


def _extract_identifier(value: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(value)
    if match is None:
        return ""
    return match.group(1)


def _extract_date_from_mapping(mapping: dict[str, object]) -> date | None:
    for key in DATE_KEYS:
        raw = mapping.get(key)
        if isinstance(raw, str):
            parsed = _extract_date_from_text(raw)
            if parsed is not None:
                return parsed
    for value in mapping.values():
        if isinstance(value, str):
            parsed = _extract_date_from_text(value)
            if parsed is not None:
                return parsed
    return None


def _extract_url_from_mapping(mapping: dict[str, object], *, list_url: str) -> str:
    direct_url = _first_string(mapping, URL_KEYS)
    if direct_url:
        return urljoin(list_url, direct_url)

    ntt_no = _first_string(mapping, NttNo_KEYS)
    bbs_no = _first_string(mapping, BbsNo_KEYS)
    if ntt_no and bbs_no:
        parsed = urlparse(list_url)
        list_query = parse_qs(parsed.query, keep_blank_values=True)
        key = list_query.get("key", [""])[0]
        query: dict[str, str] = {"bbsNo": bbs_no, "nttNo": ntt_no}
        if key:
            query["key"] = key
        return urlunparse(
            parsed._replace(
                path="/www/selectBbsNttView.do",
                query=urlencode(query),
                params="",
                fragment="",
            )
        )

    not_ancmt_no = _first_string(mapping, NotAncmtNo_KEYS)
    if not_ancmt_no:
        parsed = urlparse(list_url)
        list_query = parse_qs(parsed.query, keep_blank_values=True)
        key = list_query.get("key", [""])[0]
        if not key:
            return ""
        query = {"key": key, "notAncmtMgtNo": not_ancmt_no}
        notice_type = _first_string(mapping, NotAncmtType_KEYS)
        if notice_type:
            query["notAncmtSeCode"] = notice_type
        return urlunparse(
            parsed._replace(
                path="/www/selectEminwonView.do",
                query=urlencode(query),
                params="",
                fragment="",
            )
        )

    return ""


def _first_string(mapping: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _iter_dicts(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        mapping_rows = [value]
        for child in value.values():
            mapping_rows.extend(_iter_dicts(child))
        return mapping_rows
    if isinstance(value, list):
        list_rows: list[dict[str, object]] = []
        for child in value:
            list_rows.extend(_iter_dicts(child))
        return list_rows
    return []


def _extract_date_from_text(value: str) -> date | None:
    normalized = _normalize_whitespace(value)
    if not normalized:
        return None

    for pattern in DATE_FRAGMENT_PATTERNS:
        for match in pattern.findall(normalized):
            parsed = _parse_date_fragment(match)
            if parsed is not None:
                return parsed

    return _parse_date_fragment(normalized)


def _parse_date_fragment(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None

    format_candidates = (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y년 %m월 %d일",
    )
    for date_format in format_candidates:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    iso_match = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", text)
    if iso_match:
        return _build_date(
            year=int(iso_match.group(1)),
            month=int(iso_match.group(2)),
            day=int(iso_match.group(3)),
        )

    korean_match = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    if korean_match:
        return _build_date(
            year=int(korean_match.group(1)),
            month=int(korean_match.group(2)),
            day=int(korean_match.group(3)),
        )

    return None


def _build_date(*, year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _is_probable_notice_url(url: str, *, engine_type: EngineType) -> bool:
    lowered = url.lower()
    if any(marker in lowered for marker in NOTICE_URL_HINTS):
        return True
    if engine_type is EngineType.SAEOL_GOSI and "saeolgosi" in lowered:
        return True
    if engine_type is EngineType.CITYNET_SAPGOSI and "sapgosi" in lowered:
        return True
    return engine_type is EngineType.INTEGRATED_SEARCH_GOSI and "gosi" in lowered


def _looks_like_json_payload(payload: str) -> bool:
    stripped = payload.lstrip()
    if not stripped:
        return False
    return stripped[0] in {"{", "["}


def _dedupe_candidates(candidates: list[GenericNoticeCandidate]) -> list[GenericNoticeCandidate]:
    deduped: list[GenericNoticeCandidate] = []
    seen: set[tuple[str, date]] = set()
    for candidate in candidates:
        key = (candidate.url, candidate.published_date)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())
