from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from judgefinder.adapters.sources.municipal_rss.parser import DEFAULT_KEYWORDS
from judgefinder.adapters.sources.pocheon_eminwon.parser import extract_pocheon_eminwon_rows
from judgefinder.domain.entities import Notice, SourceType
from judgefinder.infrastructure.http.client import HttpClient

LOGGER = logging.getLogger(__name__)

DEFAULT_POCHEON_EMINWON_LIST_URL = (
    "https://www.pocheon.go.kr/www/selectEminwonList.do?key=12563&notAncmtSeCode=01"
)


@dataclass(slots=True)
class PocheonEminwonSource:
    slug: str
    municipality: str
    source_type: SourceType
    list_url: str
    timezone: ZoneInfo
    http_client: HttpClient
    fixture_path: Path | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 3
    max_pages: int = 200
    page_unit: int = 10
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    page_cache: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    request_headers: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    effective_list_url: str = field(default="", init=False, repr=False)
    search_keyword: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        self.effective_list_url = _resolve_pocheon_list_url(self.list_url)
        self.search_keyword = next((k.strip() for k in self.keywords if k.strip()), "")
        parsed_url = urlparse(self.effective_list_url)
        referer = f"{parsed_url.scheme}://{parsed_url.netloc}/" if parsed_url.netloc else ""
        self.request_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": referer,
        }

    def fetch(self, target_date: date) -> list[Notice]:
        fetched_at = datetime.now(tz=self.timezone)
        notices: list[Notice] = []
        seen_urls: set[str] = set()
        normalized_keywords = tuple(
            _normalize_text(keyword) for keyword in self.keywords if keyword.strip()
        )
        seen_target_page = False

        for page_index in range(1, self.max_pages + 1):
            page_html = self._load_page(page_index=page_index)
            rows = extract_pocheon_eminwon_rows(
                page_html, list_url=self.effective_list_url
            )
            if not rows:
                break

            page_dates = [row.published_date for row in rows]
            page_has_target = False

            for row in rows:
                if row.published_date != target_date:
                    continue
                page_has_target = True
                seen_target_page = True

                searchable = _normalize_text(row.searchable_text)
                if normalized_keywords and not _contains_keyword(
                    searchable, normalized_keywords
                ):
                    continue

                if row.url in seen_urls:
                    continue
                seen_urls.add(row.url)
                notices.append(
                    Notice(
                        id=None,
                        municipality=self.municipality,
                        title=row.title,
                        url=row.url,
                        published_date=row.published_date,
                        fetched_at=fetched_at,
                        source_type=self.source_type,
                    )
                )

            max_date = max(page_dates)
            if seen_target_page and not page_has_target and max_date < target_date:
                break
            if self.fixture_path is not None:
                break

        return notices

    def _load_page(self, *, page_index: int) -> str:
        if self.fixture_path is not None:
            return self.fixture_path.read_text(encoding="utf-8")

        cached = self.page_cache.get(page_index)
        if cached is not None:
            return cached

        request_url = self._build_request_url(page_index=page_index)
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                payload = self.http_client.get_text(
                    request_url,
                    timeout_seconds=self.timeout_seconds,
                    headers=self.request_headers,
                )
                self.page_cache[page_index] = payload
                return payload
            except Exception as exc:  # pragma: no cover - retry branch
                last_error = exc
                if attempt < self.max_retries:
                    LOGGER.warning(
                        "%s eminwon fetch failed (attempt %s/%s): %s",
                        self.slug,
                        attempt,
                        self.max_retries,
                        exc,
                    )

        if last_error is None:
            raise RuntimeError(f"{self.slug} eminwon fetch failed without an exception.")
        raise last_error

    def _build_request_url(self, *, page_index: int) -> str:
        parsed_url = urlparse(self.effective_list_url)
        query_params = parse_qs(parsed_url.query, keep_blank_values=True)
        query_params["pageUnit"] = [str(self.page_unit)]
        query_params["pageIndex"] = [str(page_index)]
        if self.search_keyword:
            query_params["searchCnd"] = ["notAncmtSj"]
            query_params["searchKrwd"] = [self.search_keyword]
        return urlunparse(parsed_url._replace(query=urlencode(query_params, doseq=True)))


def _resolve_pocheon_list_url(list_url: str) -> str:
    parsed_url = urlparse(list_url)
    if "selectEminwonList.do" in parsed_url.path:
        return list_url
    if "rssBbsNtt.do" in parsed_url.path:
        LOGGER.info(
            "Pocheon list_url points to legacy RSS. "
            "Using selectEminwon list instead: %s",
            DEFAULT_POCHEON_EMINWON_LIST_URL,
        )
        return DEFAULT_POCHEON_EMINWON_LIST_URL
    return list_url


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())
