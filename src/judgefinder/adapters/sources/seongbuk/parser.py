from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from judgefinder.domain.entities import Notice, SourceType

LOGGER = logging.getLogger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = (
    "제안서 평가위원",
    "평가위원(후보자)",
    "평가위원 후보자",
)


def parse_seongbuk_notices(
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
        LOGGER.warning("Failed to parse Seongbuk RSS payload.")
        return []

    normalized_keywords = tuple(_normalize_text(keyword) for keyword in keywords)
    notices: list[Notice] = []

    for item in root.findall(".//item"):
        title = _extract_text(item, "title")
        link = _extract_text(item, "link")
        regdate_text = _extract_text(item, "regdate")
        description = _extract_text(item, "description")
        content_encoded = _extract_text(item, "{http://purl.org/rss/1.0/modules/content/}encoded")

        published_date = _parse_regdate(regdate_text)
        if published_date is None or published_date != target_date:
            continue
        if not title or not link:
            continue

        searchable_text = _normalize_text(" ".join((title, description, content_encoded)))
        if not _contains_keyword(searchable_text, normalized_keywords):
            continue

        notices.append(
            Notice(
                id=None,
                municipality=municipality,
                title=title,
                url=urljoin(list_url, link),
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


def _parse_regdate(value: str) -> date | None:
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
    )
    for date_format in format_candidates:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    normalized_prefix = text[:10].replace(".", "-").replace("/", "-")
    try:
        return date.fromisoformat(normalized_prefix)
    except ValueError:
        LOGGER.debug("Skipping Seongbuk item with invalid regdate: %s", text)
        return None
