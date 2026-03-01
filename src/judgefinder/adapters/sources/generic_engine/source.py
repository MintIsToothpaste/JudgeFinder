from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from judgefinder.adapters.sources.generic_engine.parser import parse_generic_engine_candidates
from judgefinder.adapters.sources.municipal_rss.parser import DEFAULT_KEYWORDS
from judgefinder.domain.entities import Notice, SourceType
from judgefinder.domain.source_profiles import EngineType
from judgefinder.infrastructure.http.client import HttpClient

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class GenericEngineSource:
    slug: str
    municipality: str
    source_type: SourceType
    list_url: str
    engine_type: EngineType
    timezone: ZoneInfo
    http_client: HttpClient
    fixture_path: Path | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 3
    use_session: bool = False
    include_referer: bool = False
    throttle_seconds: float = 0.0
    max_pages: int = 8
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    page_cache: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    request_headers: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    page_param: str = field(default="", init=False, repr=False)
    search_keyword: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        parsed = urlparse(self.list_url)
        referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else ""
        self.request_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "application/json,text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
        }
        if self.include_referer and referer:
            self.request_headers["Referer"] = referer

        self.page_param = _resolve_page_param(self.list_url, engine_type=self.engine_type)
        self.search_keyword = next(
            (keyword.strip() for keyword in self.keywords if keyword.strip()),
            "",
        )

    def fetch(self, target_date: date) -> list[Notice]:
        fetched_at = datetime.now(tz=self.timezone)
        normalized_keywords = tuple(
            _normalize_text(keyword) for keyword in self.keywords if keyword.strip()
        )

        notices: list[Notice] = []
        seen_urls: set[str] = set()
        seen_target_page = False

        for page_index in range(1, self.max_pages + 1):
            payload = self._load_page(page_index=page_index)
            candidates = parse_generic_engine_candidates(
                payload,
                list_url=self.list_url,
                engine_type=self.engine_type,
            )
            if not candidates:
                break

            page_dates = [candidate.published_date for candidate in candidates]
            page_has_target = False
            for candidate in candidates:
                if candidate.published_date != target_date:
                    continue

                page_has_target = True
                seen_target_page = True
                searchable = _normalize_text(candidate.searchable_text)
                if normalized_keywords and not _contains_keyword(searchable, normalized_keywords):
                    continue
                if candidate.url in seen_urls:
                    continue

                seen_urls.add(candidate.url)
                notices.append(
                    Notice(
                        id=None,
                        municipality=self.municipality,
                        title=candidate.title,
                        url=candidate.url,
                        published_date=candidate.published_date,
                        fetched_at=fetched_at,
                        source_type=self.source_type,
                    )
                )

            max_date = max(page_dates)
            if max_date < target_date and not page_has_target and seen_target_page:
                break
            if max_date < target_date and not seen_target_page:
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
                    use_session=self.use_session,
                )
                self.page_cache[page_index] = payload
                if self.throttle_seconds > 0:
                    time.sleep(self.throttle_seconds)
                return payload
            except Exception as exc:  # pragma: no cover - retry branch
                last_error = exc
                if attempt < self.max_retries:
                    LOGGER.warning(
                        "%s generic engine fetch failed (attempt %s/%s): %s",
                        self.slug,
                        attempt,
                        self.max_retries,
                        exc,
                    )

        if last_error is None:
            raise RuntimeError(f"{self.slug} generic engine fetch failed without exception.")
        raise last_error

    def _build_request_url(self, *, page_index: int) -> str:
        parsed = urlparse(self.list_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        if self.page_param:
            query_params[self.page_param] = [str(page_index)]
        _apply_search_params(
            query_params,
            engine_type=self.engine_type,
            keyword=self.search_keyword,
            list_url=self.list_url,
        )
        return urlunparse(parsed._replace(query=urlencode(query_params, doseq=True)))


def _apply_search_params(
    query_params: dict[str, list[str]],
    *,
    engine_type: EngineType,
    keyword: str,
    list_url: str,
) -> None:
    if engine_type is EngineType.SAEOL_GOSI:
        if _is_portal_saeol_gosi_list(list_url):
            if keyword and "searchTxt" not in query_params:
                query_params["searchTxt"] = [keyword]
            if "searchType" not in query_params:
                query_params["searchType"] = ["NOT_ANCMT_SJ"]
            return

        if keyword and "searchKeyword" not in query_params:
            query_params["searchKeyword"] = [keyword]
        if "searchCondition" not in query_params:
            query_params["searchCondition"] = ["sj"]
        return

    if engine_type is EngineType.EMINWON_OFR:
        if keyword and "not_ancmt_sj" not in query_params:
            query_params["not_ancmt_sj"] = [keyword]
        if "method" not in query_params:
            query_params["method"] = ["selectOfrNotAncmt"]
        if "ofr_pageSize" not in query_params:
            query_params["ofr_pageSize"] = ["30"]
        return

    if engine_type is EngineType.CITYNET_SAPGOSI:
        if "command" not in query_params:
            query_params["command"] = ["searchList"]
        if keyword and "searchKeyword" not in query_params:
            query_params["searchKeyword"] = [keyword]
        return

    if engine_type is EngineType.INTEGRATED_SEARCH_GOSI:
        if keyword and "sstring" not in query_params:
            query_params["sstring"] = [keyword]
        if "type" not in query_params:
            query_params["type"] = ["GOSI"]
        return

    if engine_type is EngineType.GENERIC_EGOV_BBS:
        if keyword and not any(
            k in query_params for k in ("searchKrwd", "searchWrd", "searchKeyword")
        ):
            query_params["searchKrwd"] = [keyword]
        return

    if engine_type is EngineType.JSON_LIST_API and keyword and "q" not in query_params:
        query_params["q"] = [keyword]


def _resolve_page_param(list_url: str, *, engine_type: EngineType) -> str:
    parsed_url = urlparse(list_url)
    query_params = parse_qs(parsed_url.query, keep_blank_values=True)
    for candidate in ("pageIndex", "pageNo", "page", "nowPage"):
        if candidate in query_params:
            return candidate

    if engine_type is EngineType.SAEOL_GOSI and _is_portal_saeol_gosi_list(list_url):
        return "page"

    if engine_type in {
        EngineType.SAEOL_GOSI,
        EngineType.EMINWON_OFR,
        EngineType.CITYNET_SAPGOSI,
        EngineType.GENERIC_EGOV_BBS,
    }:
        return "pageIndex"
    return "page"


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _is_portal_saeol_gosi_list(list_url: str) -> bool:
    path = urlparse(list_url).path.lower()
    return "/portal/saeol/gosilist.do" in path
