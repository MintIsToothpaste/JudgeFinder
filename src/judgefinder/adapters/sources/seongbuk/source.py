from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from judgefinder.adapters.sources.seongbuk.parser import parse_seongbuk_notices
from judgefinder.domain.entities import Notice, SourceType
from judgefinder.infrastructure.http.client import HttpClient

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SeongbukSource:
    slug: str
    municipality: str
    source_type: SourceType
    list_url: str
    timezone: ZoneInfo
    http_client: HttpClient
    fixture_path: Path | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 3
    max_pages: int = 30
    page_cache: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    request_headers: dict[str, str] = field(
        default_factory=lambda: {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            "Referer": "https://www.sb.go.kr/",
        }
    )

    def fetch(self, target_date: date) -> list[Notice]:
        fetched_at = datetime.now(tz=self.timezone)
        notices: list[Notice] = []
        seen_urls: set[str] = set()

        for page_no in range(1, self.max_pages + 1):
            rss_xml = self._load_rss(page_no=page_no)
            page_notices = parse_seongbuk_notices(
                rss_xml,
                municipality=self.municipality,
                list_url=self.list_url,
                target_date=target_date,
                fetched_at=fetched_at,
                source_type=self.source_type,
            )
            for notice in page_notices:
                if notice.url in seen_urls:
                    continue
                seen_urls.add(notice.url)
                notices.append(notice)

            if not _has_items(rss_xml):
                break

            if self.fixture_path is not None:
                break

        return notices

    def _load_rss(self, page_no: int) -> str:
        if self.fixture_path is not None:
            return self.fixture_path.read_text(encoding="utf-8")

        cached = self.page_cache.get(page_no)
        if cached is not None:
            return cached

        request_url = self._build_request_url(page_no=page_no)
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                payload = self.http_client.get_text(
                    request_url,
                    timeout_seconds=self.timeout_seconds,
                    headers=self.request_headers,
                )
                self.page_cache[page_no] = payload
                return payload
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    LOGGER.warning(
                        "Seongbuk RSS fetch failed (attempt %s/%s): %s",
                        attempt,
                        self.max_retries,
                        exc,
                    )

        if last_error is None:
            raise RuntimeError("Seongbuk RSS fetch failed without an exception.")
        raise last_error

    def _build_request_url(self, page_no: int) -> str:
        parsed_url = urlparse(self.list_url)
        query_params = parse_qs(parsed_url.query, keep_blank_values=True)
        query_params["pageNo"] = [str(page_no)]
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed_url._replace(query=new_query))


def _has_items(rss_xml: str) -> bool:
    try:
        root = ET.fromstring(rss_xml)
    except ET.ParseError:
        return False
    return bool(root.findall(".//item"))
