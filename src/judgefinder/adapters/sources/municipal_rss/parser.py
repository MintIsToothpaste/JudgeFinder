from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from datetime import date, datetime
from ipaddress import ip_address
from urllib.parse import ParseResult, parse_qs, urlencode, urljoin, urlparse, urlunparse
from xml.etree import ElementTree as ET

from judgefinder.domain.entities import Notice, SourceType

LOGGER = logging.getLogger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = ("\ud3c9\uac00\uc704\uc6d0",)
DATE_TAGS: tuple[str, ...] = ("regdate", "pubDate", "pubdate", "date")


def parse_municipal_rss_notices(
    rss_xml: str,
    *,
    municipality: str,
    list_url: str,
    target_date: date,
    fetched_at: datetime,
    source_type: SourceType,
    keywords: Iterable[str] = DEFAULT_KEYWORDS,
) -> list[Notice]:
    try:
        root = ET.fromstring(rss_xml)
    except ET.ParseError:
        LOGGER.warning("Failed to parse municipal RSS payload.")
        return []

    normalized_keywords = tuple(
        _normalize_text(keyword) for keyword in keywords if keyword.strip()
    )
    notices: list[Notice] = []

    for item in root.findall(".//item"):
        title = _extract_text(item, "title")
        link = _extract_text(item, "link")
        description = _extract_text(item, "description")
        content_encoded = _extract_text(
            item, "{http://purl.org/rss/1.0/modules/content/}encoded"
        )
        published_date = _extract_item_date(item)

        if published_date is None or published_date != target_date:
            continue
        if not title or not link:
            continue

        searchable_text = _normalize_text(" ".join((title, description, content_encoded)))
        if normalized_keywords and not _contains_keyword(searchable_text, normalized_keywords):
            continue

        notices.append(
            Notice(
                id=None,
                municipality=municipality,
                title=title,
                url=_normalize_notice_url(list_url=list_url, link=link),
                published_date=published_date,
                fetched_at=fetched_at,
                source_type=source_type,
            )
        )

    return notices


def _extract_text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _extract_item_date(item: ET.Element) -> date | None:
    for tag in DATE_TAGS:
        parsed = _parse_date_text(_extract_text(item, tag))
        if parsed is not None:
            return parsed

    # Some feeds mix namespaces/casing, so inspect children directly.
    for child in list(item):
        tag_name = child.tag.rsplit("}", 1)[-1].lower()
        if tag_name not in {"regdate", "pubdate", "date"}:
            continue
        parsed = _parse_date_text((child.text or "").strip())
        if parsed is not None:
            return parsed

    return None


def _parse_date_text(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None

    format_candidates = (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%Y%m%d%H%M",
        "%Y%m%d%H%M%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",
    )
    for date_format in format_candidates:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    iso_match = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", text)
    if iso_match:
        return _build_date_safely(
            year=int(iso_match.group(1)),
            month=int(iso_match.group(2)),
            day=int(iso_match.group(3)),
            raw=text,
        )

    korean_match = re.search(r"(\d{1,2})\s+(\d{1,2})\D+\s+(\d{4})", text)
    if korean_match:
        return _build_date_safely(
            year=int(korean_match.group(3)),
            month=int(korean_match.group(2)),
            day=int(korean_match.group(1)),
            raw=text,
        )

    numbers = [int(match) for match in re.findall(r"\d+", text)]
    if len(numbers) >= 3:
        if 1000 <= numbers[0] <= 2999:
            return _build_date_safely(
                year=numbers[0],
                month=numbers[1],
                day=numbers[2],
                raw=text,
            )
        if 1000 <= numbers[2] <= 2999:
            return _build_date_safely(
                year=numbers[2],
                month=numbers[1],
                day=numbers[0],
                raw=text,
            )

    LOGGER.debug("Skipping RSS item with invalid date text: %s", text)
    return None


def _build_date_safely(*, year: int, month: int, day: int, raw: str) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        LOGGER.debug("Skipping RSS item with unparseable date components: %s", raw)
        return None


def _normalize_notice_url(*, list_url: str, link: str) -> str:
    absolute_url = urljoin(list_url, link)
    parsed = urlparse(absolute_url)

    mobile_desktop_url = _rewrite_mobile_notice_url(list_url=list_url, parsed=parsed)
    if mobile_desktop_url is not None:
        return mobile_desktop_url

    host = parsed.hostname
    if host is None:
        return absolute_url

    try:
        ip_address(host)
    except ValueError:
        return absolute_url

    list_parsed = urlparse(list_url)
    if not list_parsed.netloc:
        return absolute_url
    return urlunparse(parsed._replace(scheme=list_parsed.scheme, netloc=list_parsed.netloc))


def _rewrite_mobile_notice_url(*, list_url: str, parsed: ParseResult) -> str | None:
    if parsed.path != "/mobile/selectBbsNttView.do":
        return None
    if parsed.hostname not in {"okjc.net", "www.okjc.net", "jecheon.go.kr", "www.jecheon.go.kr"}:
        return None

    query_params = parse_qs(parsed.query, keep_blank_values=True)
    bbs_no = query_params.get("bbsNo", [""])[0]
    ntt_no = query_params.get("nttNo", [""])[0]
    if not bbs_no or not ntt_no:
        return None

    list_parsed = urlparse(list_url)
    if not list_parsed.netloc:
        return None

    rewritten_query: dict[str, str] = {"bbsNo": bbs_no, "nttNo": ntt_no}
    # Jecheon desktop board requires key=5233 for bbsNo=18 detail pages.
    if list_parsed.hostname in {"jecheon.go.kr", "www.jecheon.go.kr"} and bbs_no == "18":
        rewritten_query = {"key": "5233", "bbsNo": bbs_no, "nttNo": ntt_no}

    return urlunparse(
        parsed._replace(
            scheme=list_parsed.scheme or "https",
            netloc=list_parsed.netloc,
            path="/www/selectBbsNttView.do",
            query=urlencode(rewritten_query),
            params="",
            fragment="",
        )
    )
