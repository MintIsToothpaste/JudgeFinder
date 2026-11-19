from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title
from judgefinder.domain.origins import COMMITTEE_SEARCH_SUFFIX, OriginCandidate
from judgefinder.domain.ports import NoticeSource
from judgefinder.infrastructure.http.client import HttpClient

HIBRAIN_LIST = (
    "https://www.hibrain.net/research/researches/34/recruitments/425/recruits"
    "?listType=ING&sortType=AD&displayType=TIT&limit=100&siteid=1"
)


def _hibrain_date(text: str) -> date:
    value = text.strip().rstrip(".")
    if not re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{2}", value):
        raise ValueError("Hibrain registration/update date is missing or invalid")
    return date.fromisoformat("20" + value.replace(".", "-"))


class HibrainOriginDiscovery:
    label = HIBRAIN_LIST

    def __init__(self, client: HttpClient, *, max_pages: int = 3,
                 timeout_seconds: float = 20, throttle_seconds: float = 0.3) -> None:
        self.client = client
        self.max_pages = max_pages
        self.timeout_seconds = timeout_seconds
        self.throttle_seconds = throttle_seconds

    def _load(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "www.hibrain.net":
            raise ValueError("Hibrain navigation must stay on its configured HTTPS host")
        response = self.client.get_response(
            url, timeout_seconds=self.timeout_seconds, use_session=True, verify_tls=True,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
        )
        if self.throttle_seconds:
            time.sleep(self.throttle_seconds)
        if not response.ok:
            raise ValueError(f"Hibrain discovery HTTP {response.status_code}; no bypass attempted")
        final = urlparse(response.url)
        if final.scheme != "https" or final.hostname != "www.hibrain.net":
            raise ValueError("Hibrain discovery redirected away from its host")
        return response.text

    def discover(self, start: date, end: date) -> Iterable[OriginCandidate]:
        url = HIBRAIN_LIST
        seen: set[str] = set()
        for _ in range(self.max_pages):
            soup = BeautifulSoup(self._load(url), "html5lib")
            listing = soup.select_one("#articleList")
            if listing is None:
                raise ValueError("Hibrain listing missing; absence of candidates is unverified")
            rows = listing.select("li.row")
            dates = []
            for row in rows:
                link, stamp = row.select_one(".td_title a[href]"), row.select_one(".td_rdtm")
                if link is None or stamp is None:
                    raise ValueError("Hibrain listing title or update date missing")
                day = _hibrain_date(stamp.get_text(strip=True))
                dates.append(day)
                detail_url = urljoin(url, str(link["href"]))
                if detail_url in seen:
                    raise ValueError("Hibrain listing pagination repeated a notice")
                seen.add(detail_url)
                title = " ".join(link.get_text().split())
                if not start <= day <= end or "평가위원" not in "".join(title.split()):
                    continue
                if classify_notice_title(title) is NoticeCategory.RESULT:
                    continue
                try:
                    detail = BeautifulSoup(self._load(detail_url), "html5lib")
                except Exception as exc:
                    yield OriginCandidate(detail_url, "", day, f"Detail discovery failed: {exc}")
                    continue
                related = [tr for tr in detail.select("tr")
                           if "관련 홈페이지" in tr.get_text(" ", strip=True)]
                origins = list(dict.fromkeys(
                    urljoin(detail_url, str(a["href"]))
                    for tr in related for a in tr.select("a[href]")
                ))
                if not origins:
                    yield OriginCandidate(detail_url, "", day)
                for origin in origins:
                    yield OriginCandidate(detail_url, origin, day)
            if dates != sorted(dates, reverse=True):
                raise ValueError("Hibrain listing update dates are not descending")
            if dates and min(dates) < start:
                return
            current_page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
            next_link = next((a for a in soup.select(".pagination a[href]") if
                              parse_qs(urlparse(str(a["href"])).query).get("page") ==
                              [str(current_page + 1)]), None)
            if next_link is None:
                next_link = soup.find("a", string=lambda s: s and s.strip() == "다음")
            if next_link is None:
                return
            url = urljoin(url, str(next_link["href"]))
        raise ValueError("Hibrain discovery page limit reached; completeness is unverified")


class CommitteeOriginDiscovery:
    SEARCH_TERMS = ("심의위원", "심사위원")

    def __init__(self, source: GenericEngineSource, term: str) -> None:
        self.source = source
        self.term = term
        self.label = source.list_url + COMMITTEE_SEARCH_SUFFIX

    @classmethod
    def for_source(cls, source: NoticeSource) -> Iterable[CommitteeOriginDiscovery]:
        if type(source) is not GenericEngineSource or source.fixture_path is not None:
            return
        profile = source.html_profile
        if profile is None or not (
            profile.search_param and profile.date_selector and profile.detail_url_template
            and profile.detail_title_selector and profile.detail_date_selector
            and profile.detail_body_selector and source.search_keyword == "평가위원"
        ):
            return

        parsed = urlparse(source.list_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        current = query.get(profile.search_param, [""])
        if len(current) != 1 or current[0] not in ("", "평가위원", *cls.SEARCH_TERMS):
            return
        # Discover IDs using the listing date. Verify each detail separately so one
        # inaccessible notice can be held without losing the rest of the page.
        listing = replace(
            profile, detail_title_selector="", detail_date_selector="",
            detail_date_attribute="", detail_body_selector="",
        )
        for term in cls.SEARCH_TERMS:
            query[profile.search_param] = [term]
            url = urlunparse(parsed._replace(query=urlencode(query, doseq=True), fragment=""))
            search = replace(
                source, list_url=url, html_profile=listing, keywords=(), recruitment_only=False,
            )
            if current == [term]:
                search.page_cache = source.page_cache
            yield cls(search, term)

    def discover(self, start: date, end: date) -> Iterable[OriginCandidate]:
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            for notice in self.source.fetch(day):
                # Boards can include pinned posts that do not match the query.
                # A visibly truncated title still needs the official detail checked.
                if (self.term in "".join(notice.title.split())
                        or notice.title.endswith(("...", "…"))):
                    yield OriginCandidate(self.label, notice.url, day)


class FileOriginDiscovery:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.label = str(path)

    def discover(self, start: date, end: date) -> Iterable[OriginCandidate]:
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, list):
            raise ValueError("Origin candidate file must contain a JSON array")
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each origin candidate must be an object")
            discovery, origin, stamp = (
                item.get("discovery_url"), item.get("origin_url"), item.get("discovered_date"),
            )
            if (not isinstance(discovery, str) or not isinstance(origin, str)
                    or not isinstance(stamp, str)):
                raise ValueError("Candidate requires discovery_url, origin_url, discovered_date")
            day = date.fromisoformat(stamp)
            if start <= day <= end:
                yield OriginCandidate(discovery, origin, day)
