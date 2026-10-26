from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from judgefinder.adapters.sources.generic_engine.gwanak import (
    build_gwanak_detail_url,
    gwanak_board_kind,
    gwanak_registration_text,
)
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
    "eminwonannouncedetail.do",
    "bbsmsgdetail.do",
    "ofraction.do",
    "sapgosibizprocess.do",
    "view.do",
    "view.ulsan",
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
SEARCH_DETAIL_PATTERN = re.compile(
    r"searchDetail\(\s*['\"]?(\d+)['\"]?\s*\)",
    re.IGNORECASE,
)
EMBEDDED_URL_PATTERN = re.compile(r"""['"]((?:https?:)?//[^'"]+|/[^'"]+|emwp/[^'"]+)['"]""")
NOTICE_NUMBER_PATTERN = re.compile(r"제\s*\d{4}(?:-\d+)?호")
NOTICE_IDENTIFIER_PATTERN = re.compile(r"\b\d{4}-\d+\b")


@dataclass(slots=True)
class GenericNoticeCandidate:
    title: str
    url: str
    published_date: date
    searchable_text: str
    body_text: str = ""


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

        title = _extract_candidate_title(anchor)
        if not title:
            continue

        context_text = _extract_context_text(anchor)
        published_date = _extract_candidate_date(anchor, url=url, context_text=context_text)
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
    href = href.replace("¬_", "&not_")
    onclick_raw = anchor.get("onclick")
    onclick = onclick_raw if isinstance(onclick_raw, str) else ""
    if gwanak_board_kind(list_url) and href.lower().startswith(("#", "javascript:")):
        return build_gwanak_detail_url(anchor, list_url=list_url)
    data_action = _extract_candidate_action_url(anchor)
    if data_action:
        return _strip_url_path_params(urljoin(list_url, data_action))
    if href.lower().startswith("emwp/"):
        parsed = urlparse(list_url)
        site_root = f"{parsed.scheme}://{parsed.netloc}/"
        return _strip_url_path_params(urljoin(site_root, href))
    normalized_href = href.strip().lower()
    embedded_url = _extract_embedded_notice_url(
        " ".join(part for part in (href, onclick) if part), list_url,
    )
    if embedded_url:
        return embedded_url
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
        return _strip_url_path_params(
            _build_url_from_javascript(javascript_source, list_url=list_url),
        )
    return _strip_url_path_params(urljoin(list_url, href))


def _build_url_from_javascript(source: str, *, list_url: str) -> str:
    ntt_no = _extract_identifier(source, JAVASCRIPT_ID_PATTERNS[0])
    bbs_no = _extract_identifier(source, JAVASCRIPT_ID_PATTERNS[1])
    not_ancmt_no = _extract_identifier(source, JAVASCRIPT_ID_PATTERNS[2])
    if not not_ancmt_no:
        not_ancmt_no = _extract_identifier(source, BOARD_VIEW_PATTERN)
    if not not_ancmt_no:
        not_ancmt_no = _extract_identifier(source, FN_SEARCH_DETAIL_PATTERN)
    if not not_ancmt_no:
        not_ancmt_no = _extract_identifier(source, SEARCH_DETAIL_PATTERN)

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

    if not_ancmt_no and _is_portal_saeol_notice_list_path(parsed.path):
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

    if not_ancmt_no and _is_ofr_action_list_path(parsed.path):
        query = {
            name: values[0]
            for name, values in list_query.items()
            if values and name not in {"pageIndex", "not_ancmt_sj", "not_ancmt_cn", "dept_nm"}
        }
        query["not_ancmt_mgt_no"] = not_ancmt_no
        query["method"] = "selectOfrNotAncmt"
        query["methodnm"] = "selectOfrNotAncmtRegst"
        return urlunparse(
            parsed._replace(
                path="/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do",
                query=urlencode(query),
                params="",
                fragment="",
            )
        )
    return ""


def _extract_candidate_action_url(anchor: Tag) -> str:
    href_value = anchor.get("href")
    normalized_href = href_value.strip().lower() if isinstance(href_value, str) else ""
    if normalized_href not in {"", "#", "javascript:;", "javascript:void(0);"}:
        return ""

    for attribute_name in ("data-action", "data-href", "data-url"):
        value = anchor.get(attribute_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_embedded_notice_url(source: str, list_url: str) -> str:
    for raw_candidate in EMBEDDED_URL_PATTERN.findall(source):
        candidate = unescape(raw_candidate.strip()).replace("¬_", "&not_")
        if not candidate:
            continue
        if candidate.lower().startswith("emwp/"):
            parsed = urlparse(list_url)
            site_root = f"{parsed.scheme}://{parsed.netloc}/"
            normalized = urljoin(site_root, candidate)
        elif candidate.startswith("//"):
            normalized = f"{urlparse(list_url).scheme}:{candidate}"
        else:
            normalized = urljoin(list_url, candidate)
        normalized = _strip_url_path_params(normalized)
        if _is_select_gosi_detail_url(normalized):
            return normalized
        if any(marker in normalized.lower() for marker in NOTICE_URL_HINTS):
            return normalized
        if _has_detail_query_signature(normalized):
            return normalized
        if _has_content_id_signature(normalized):
            return normalized
        if _has_show_detail_path(normalized):
            return normalized
    return ""


def _strip_url_path_params(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.params:
        return url
    return urlunparse(parsed._replace(params=""))


def _extract_context_text(anchor: Tag) -> str:
    row = _find_context_container(anchor)
    if row is not None:
        return _normalize_whitespace(row.get_text(" ", strip=True))
    return _normalize_whitespace(anchor.get_text(" ", strip=True))


def _extract_candidate_date(anchor: Tag, *, url: str, context_text: str) -> date | None:
    if gwanak_board_kind(url, detail=True):
        return _extract_date_from_text(gwanak_registration_text(anchor, detail_url=url))
    if _is_select_gosi_detail_url(url):
        row = anchor.find_parent("tr")
        table = anchor.find_parent("table")
        if row is not None and table is not None:
            cells = row.find_all(["td", "th"], recursive=False)
            for index, header in enumerate(table.select("thead th")):
                if header.get_text(strip=True) == "등록일":
                    # Gosi rows also contain a posting period; it is not the registration date.
                    if index >= len(cells):
                        return None
                    return _extract_date_from_text(cells[index].get_text(" ", strip=True))
    return _extract_date_from_text(context_text)


def _extract_identifier(value: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(value)
    if match is None:
        return ""
    return match.group(1)


def _extract_candidate_title(anchor: Tag) -> str:
    anchor_text = _normalize_whitespace(anchor.get_text(" ", strip=True))
    if _is_descriptive_title(anchor_text):
        return anchor_text

    row = _find_context_container(anchor)
    if row is None:
        return anchor_text

    best_title = anchor_text
    best_score = _score_title_candidate(anchor_text, anchor_text=anchor_text)
    for cell in row.find_all(["td", "th"], recursive=False):
        cell_text = _normalize_whitespace(cell.get_text(" ", strip=True))
        score = _score_title_candidate(cell_text, anchor_text=anchor_text)
        if score > best_score:
            best_title = cell_text
            best_score = score

    return best_title


def _find_context_container(anchor: Tag) -> Tag | None:
    return anchor.find_parent(["tr", "li", "article", "div"])


def _score_title_candidate(value: str, *, anchor_text: str) -> int:
    text = value.strip()
    if not text or text == anchor_text:
        return -1
    if _extract_date_from_text(text) is not None:
        return -1
    if text.isdigit():
        return -1

    score = min(len(text), 80)
    if _is_department_name(text):
        score -= 25
    if NOTICE_NUMBER_PATTERN.search(text):
        score -= 25
    if NOTICE_IDENTIFIER_PATTERN.search(text):
        score -= 25
    return score


def _is_descriptive_title(value: str) -> bool:
    text = value.strip()
    if not text or text.isdigit():
        return False
    if _extract_date_from_text(text) is not None:
        return False
    return not _is_department_name(text)


def _is_department_name(value: str) -> bool:
    if len(value) > 20:
        return False
    return value.endswith(
        (
            "과",
            "국",
            "실",
            "팀",
            "소",
            "동",
            "면",
            "읍",
            "센터",
            "사업소",
            "담당관",
        )
    )


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
        return _strip_url_path_params(urljoin(list_url, direct_url))

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
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and re.fullmatch(
        r"/site/[^/]+/board/[^/]+/[1-9][0-9]*", parsed.path,
    ):
        return True
    if _is_select_gosi_detail_url(url):
        return True
    lowered = url.lower()
    if any(marker in lowered for marker in NOTICE_URL_HINTS):
        return True
    if _has_detail_query_signature(url):
        return True
    if _has_content_id_signature(url):
        return True
    if _has_show_detail_path(url):
        return True
    if engine_type is EngineType.SAEOL_GOSI and "saeolgosi" in lowered:
        return True
    if engine_type is EngineType.CITYNET_SAPGOSI and "sapgosi" in lowered:
        return True
    return engine_type is EngineType.INTEGRATED_SEARCH_GOSI and "gosi" in lowered


def _is_select_gosi_detail_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.path.rsplit("/", 1)[-1].lower() != "selectgosidata.do":
        return False
    notice_ids = parse_qs(parsed.query, keep_blank_values=True).get("not_ancmt_mgt_no", [])
    return len(notice_ids) == 1 and re.fullmatch(r"[1-9][0-9]*", notice_ids[0]) is not None


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


def _is_portal_saeol_notice_list_path(path: str) -> bool:
    lowered = path.lower()
    return "/portal/saeol/gosilist.do" in lowered or "/portal/saeol/gosi/list.do" in lowered


def _is_ofr_action_list_path(path: str) -> bool:
    lowered = path.lower()
    return "/emwp/gov/mogaha/ntis/web/ofr/action/ofraction.do" in lowered


def _has_detail_query_signature(url: str) -> bool:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    mode = query.get("mode", [""])[0].lower()
    notice_id = query.get("no", [""])[0]
    return mode in {"v", "view"} and bool(notice_id)


def _has_content_id_signature(url: str) -> bool:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if not any(query.get(key, [""])[0] for key in ("id", "i", "seq")):
        return False

    path = parsed.path.lower()
    return any(
        token in path
        for token in (
            "/news/",
            "/notice/",
            "/announcement/",
            "/recruitment/",
            "/legislation/",
            "/headline/",
            "/tender",
            "/work/",
            "/gunbo/",
        )
    )


def _has_show_detail_path(url: str) -> bool:
    return "/show/" in urlparse(url).path.lower()
