from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from judgefinder.adapters.sources.generic_engine.gwanak import (
    gwanak_board_kind,
    gwanak_listing_row_count,
)
from judgefinder.adapters.sources.generic_engine.parser import (
    GenericNoticeCandidate,
    parse_generic_engine_candidates,
)
from judgefinder.adapters.sources.generic_engine.profiled_html import (
    parse_profiled_html,
    profiled_html_total_count,
)
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json
from judgefinder.adapters.sources.municipal_rss.parser import DEFAULT_KEYWORDS
from judgefinder.domain.entities import Notice, SourceType
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice
from judgefinder.domain.source_profiles import EngineType, HtmlProfile, JsonProfile
from judgefinder.infrastructure.http.client import FormHttpClient, HttpClient

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
    verify_tls: bool = True
    throttle_seconds: float = 0.0
    max_pages: int = 8
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    recruitment_only: bool = False
    html_profile: HtmlProfile | None = None
    available_from: date | None = None
    json_profile: JsonProfile | None = None
    profile: HtmlProfile | JsonProfile | None = field(default=None, init=False, repr=False)
    page_cache: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    detail_cache: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    profile_candidate_cache: dict[int, list[GenericNoticeCandidate]] = field(
        default_factory=dict, init=False, repr=False,
    )
    profile_total_count_cache: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    request_headers: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    page_param: str = field(default="", init=False, repr=False)
    search_keyword: str = field(default="", init=False, repr=False)
    earliest_requested_date: date | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.html_profile is not None and self.json_profile is not None:
            raise ValueError("A source cannot use both html_profile and json_profile")
        self.profile = self.html_profile or self.json_profile
        if type(self.max_pages) is not int or not 1 <= self.max_pages <= 1000:
            raise ValueError("max_pages must be an integer between 1 and 1000")
        parsed = urlparse(self.list_url)
        referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else ""
        self.request_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "application/json,text/html;q=0.9,*/*;q=0.8"
                if self.json_profile is not None or self.engine_type is EngineType.JSON_LIST_API
                else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
        }
        if self.include_referer and referer:
            self.request_headers["Referer"] = referer

        self.page_param = (
            self.profile.page_param if self.profile is not None
            else _resolve_page_param(self.list_url, engine_type=self.engine_type)
        )
        self.search_keyword = next(
            (keyword.strip() for keyword in self.keywords if keyword.strip()),
            "",
        )

    def fetch(self, target_date: date) -> list[Notice]:
        # Migrated archives must not be relabelled as a newly created municipality.
        if self.available_from is not None and target_date < self.available_from:
            return []
        if self.earliest_requested_date is None or target_date < self.earliest_requested_date:
            # A later request for older dates must resolve previously skipped details.
            self.earliest_requested_date = target_date
            if self.html_profile is not None and self.html_profile.date_selector and (
                self.html_profile.detail_date_selector or self.html_profile.detail_title_selector
                or self.html_profile.detail_body_selector
            ):
                self.profile_candidate_cache.clear()
        fetched_at = datetime.now(tz=self.timezone)
        normalized_keywords = tuple(
            _normalize_text(keyword) for keyword in self.keywords if keyword.strip()
        )

        notices: list[Notice] = []
        seen_urls: set[str] = set()
        seen_pages: set[frozenset[tuple[str, date]]] = set()
        seen_target_page = False

        for page_index in range(1, self.max_pages + 1):
            payload = self._load_page(page_index=page_index)
            if self.html_profile is not None:
                candidates = self.profile_candidate_cache.get(page_index)
                if candidates is None:
                    candidates = parse_profiled_html(
                        payload, list_url=self.list_url, profile=self.html_profile,
                        detail_loader=self._load_detail,
                        recruitment_only=self.recruitment_only,
                        detail_not_before=self.earliest_requested_date,
                        expected_page=page_index,
                    )
                    total_count = profiled_html_total_count(payload, profile=self.html_profile)
                    if total_count is not None:
                        self.profile_total_count_cache[page_index] = total_count
                    if self.fixture_path is None:
                        self.profile_candidate_cache[page_index] = candidates
                LOGGER.debug(
                    "%s page=%s profile_parsed=%s status=%s",
                    self.slug, page_index, len(candidates),
                    "parsed" if candidates else "empty_board",
                )
            elif self.json_profile is not None:
                candidates = self.profile_candidate_cache.get(page_index)
                if candidates is None:
                    candidates = parse_profiled_json(
                        payload, list_url=self.list_url, profile=self.json_profile,
                        expected_page=page_index,
                    )
                    if self.fixture_path is None:
                        self.profile_candidate_cache[page_index] = candidates
            else:
                candidates = parse_generic_engine_candidates(
                    payload, list_url=self.list_url, engine_type=self.engine_type,
                )
            if self.profile is None and gwanak_board_kind(self.list_url):
                row_count = gwanak_listing_row_count(payload)
                if row_count and not candidates:
                    raise ValueError(
                        f"{self.slug} page={page_index}: parsing failed: "
                        f"listing_rows={row_count}, parsed=0; not an empty search result"
                    )
                if len(candidates) < row_count:
                    LOGGER.warning(
                        "%s page=%s partial parsing: listing_rows=%s parsed=%s",
                        self.slug, page_index, row_count, len(candidates),
                    )
                LOGGER.debug(
                    "%s page=%s listing_rows=%s parsed=%s status=%s",
                    self.slug, page_index, row_count, len(candidates),
                    "empty_board" if not row_count else "parsed",
                )
            if not candidates:
                if self.profile is None and not gwanak_board_kind(self.list_url):
                    LOGGER.debug(
                        "%s page=%s no parseable candidates (not proof of no notices)",
                        self.slug, page_index,
                    )
                break

            # Some boards clamp out-of-range pages back to their first page.
            page_signature = frozenset(
                (candidate.url, candidate.published_date) for candidate in candidates
            )
            if page_signature in seen_pages:
                if self.json_profile is not None:
                    raise ValueError(
                        f"{self.slug}: JSON pagination repeated a nonempty page; "
                        "collection completeness is unverified"
                    )
                LOGGER.debug("%s page=%s repeated listing; stopping", self.slug, page_index)
                break
            seen_pages.add(page_signature)

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
                if self.recruitment_only:
                    category = classify_notice(candidate.title, candidate.body_text)
                    if category is not NoticeCategory.RECRUITMENT:
                        log = LOGGER.warning if category is NoticeCategory.UNKNOWN else LOGGER.debug
                        log(
                            "%s excluded category=%s title=%s url=%s",
                            self.slug, category.value, candidate.title, candidate.url,
                        )
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

            total_count = self.profile_total_count_cache.get(page_index)
            if self.html_profile is not None and total_count is not None and (
                page_index * self.html_profile.page_size >= total_count
            ):
                break
            max_date = max(page_dates)
            if max_date < target_date and not page_has_target and seen_target_page:
                break
            if max_date < target_date and not seen_target_page:
                break
            if self.fixture_path is not None:
                break
            if self.profile is not None and not self.page_param:
                break
        else:
            if self.profile is not None:
                raise ValueError(
                    f"{self.slug}: pagination limit ({self.max_pages}) reached; "
                    "collection completeness is unverified"
                )

        LOGGER.debug(
            "%s target_date=%s collected=%s recruitment_only=%s",
            self.slug, target_date, len(notices), self.recruitment_only,
        )
        return notices

    def _load_page(self, *, page_index: int) -> str:
        if self.fixture_path is not None:
            return self.fixture_path.read_text(encoding="utf-8")

        cached = self.page_cache.get(page_index)
        if cached is not None:
            return cached

        request_url = self._build_request_url(page_index=page_index)
        post = self.profile is not None and self.profile.request_method == "POST"
        payload = self._request_text(request_url, post=post)
        self.page_cache[page_index] = payload
        return payload

    def _load_detail(self, url: str) -> str:
        if url not in self.detail_cache:
            self.detail_cache[url] = self._request_text(url)
        return self.detail_cache[url]

    def _request_text(self, request_url: str, *, post: bool = False) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if post:
                    if not isinstance(self.http_client, FormHttpClient):
                        raise TypeError("HTTP client does not support board search POST forms")
                    parsed = urlparse(request_url)
                    payload = self.http_client.post_text(
                        urlunparse(parsed._replace(query="")),
                        data=parsed.query.encode("ascii"),
                        timeout_seconds=self.timeout_seconds,
                        headers={**self.request_headers,
                                 "Content-Type": "application/x-www-form-urlencoded"},
                        use_session=self.use_session, verify_tls=self.verify_tls,
                    )
                else:
                    payload = self.http_client.get_text(
                        request_url,
                        timeout_seconds=self.timeout_seconds,
                        headers=self.request_headers,
                        use_session=self.use_session,
                        verify_tls=self.verify_tls,
                    )
                if self.throttle_seconds > 0:
                    time.sleep(self.throttle_seconds)
                return payload
            except Exception as exc:  # pragma: no cover - retry branch
                last_error = exc
                if attempt < self.max_retries:
                    LOGGER.debug(
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
        if self.profile is not None:
            search_param = self.profile.search_param
            if search_param and self.search_keyword and not query_params.get(search_param, [""])[0]:
                query_params[search_param] = [self.search_keyword]
            if self.json_profile is not None and self.json_profile.offset_param:
                query_params[self.json_profile.offset_param] = [
                    str((page_index - 1) * self.json_profile.page_size
                        + self.json_profile.offset_base),
                ]
            if self.html_profile is not None and self.html_profile.offset_param:
                query_params[self.html_profile.offset_param] = [
                    str((page_index - 1) * self.html_profile.page_size),
                ]
        else:
            _apply_search_params(
                query_params, engine_type=self.engine_type,
                keyword=self.search_keyword, list_url=self.list_url,
            )
        encoding = self.profile.request_encoding if self.profile else "utf-8"
        return urlunparse(parsed._replace(
            query=urlencode(query_params, doseq=True, encoding=encoding),
        ))


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
        gwanak_kind = gwanak_board_kind(list_url)
        if gwanak_kind:
            if keyword and "searchKey" not in query_params:
                query_params["searchKey"] = [keyword]
            query_params.setdefault(
                "tgtTypeCd", ["NOT_ANCMT_SJ" if gwanak_kind == "gosi" else "SUB_CONT"],
            )
            return
        if keyword and not any(
            k in query_params for k in ("searchKrwd", "searchWrd", "searchKeyword", "searchKey")
        ):
            query_params["searchKrwd"] = [keyword]
        return

    if engine_type is EngineType.JSON_LIST_API and keyword and "q" not in query_params:
        query_params["q"] = [keyword]


def _resolve_page_param(list_url: str, *, engine_type: EngineType) -> str:
    parsed_url = urlparse(list_url)
    query_params = parse_qs(parsed_url.query, keep_blank_values=True)
    for candidate in (
        "pageIndex",
        "pageNo",
        "p",
        "page",
        "nowPage",
        "curPage",
        "startPage",
        "GotoPage",
    ):
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
    # Korean notice titles may split a search term across spaces or line breaks.
    compact_text = "".join(text.split())
    return any("".join(keyword.split()) in compact_text for keyword in keywords)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _is_portal_saeol_gosi_list(list_url: str) -> bool:
    path = urlparse(list_url).path.lower()
    return "/portal/saeol/gosilist.do" in path or "/portal/saeol/gosi/list.do" in path
