from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse, urlunparse

from judgefinder.adapters.attachments.hwpx import official_hwpx_texts
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_detail
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import Notice
from judgefinder.domain.notice_classification import (
    NoticeCategory,
    classify_committee_notice,
    committee_project_names,
)
from judgefinder.domain.origins import OriginDetails, OriginRoute
from judgefinder.domain.ports import NoticeSource
from judgefinder.domain.source_profiles import NOTICE_ID_PATTERNS as IDENTIFIERS

# These select navigation/search state, not a board's identity. Board IDs stay required.
NAVIGATION_KEYS = {
    "page", "cpage", "pageIndex", "pageNo", "searchCnt", "pageLine",
}
VIEW_KEYS = {"mode", "amode", "schM"}


class ConfiguredOriginReader:
    def __init__(self, sources: list[NoticeSource]) -> None:
        self.sources = {
            s.slug: s for s in sources
            if isinstance(s, GenericEngineSource) and s.html_profile is not None
            and s.html_profile.detail_url_template
        }

    def resolve(self, url: str) -> OriginRoute:
        matches = [route for s in self.sources.values() if (route := self._match(s, url))]
        if not matches:
            raise ValueError("No enabled official detail profile matches this URL")
        if len({r.identity_key for r in matches}) != 1:
            raise ValueError("Official URL matches multiple boards; manual review required")
        # Prefer a complete profile when two configured aliases describe the same board.
        def complete(route: OriginRoute) -> bool:
            profile = self.sources[route.source_slug].html_profile
            return bool(profile and profile.detail_body_selector)

        return max(matches, key=complete)

    def identity(self, municipality: str, url: str) -> str | None:
        try:
            route = self.resolve(url)
        except ValueError:
            return None
        return route.identity_key if route.municipality == municipality else None

    def _match(self, source: GenericEngineSource, url: str) -> OriginRoute | None:
        profile = source.html_profile
        assert profile is not None
        marker = "NOTICEIDENTIFIER"
        template = urljoin(source.list_url, profile.detail_url_template)
        target = urlparse(template.replace("{id}", marker))
        try:
            supplied = urlparse(url.strip())
            if supplied.username or supplied.password or any(c in url for c in "\r\n\\"):
                return None
            scheme_matches = supplied.scheme == target.scheme or (
                supplied.scheme == "http" and target.scheme == "https"
            )
            if not scheme_matches or (supplied.hostname, supplied.port) != (
                target.hostname, target.port,
            ) or supplied.scheme not in {"http", "https"}:
                return None
        except ValueError:
            return None
        path = re.sub(r";jsessionid=[^/;]*", "", supplied.path, flags=re.IGNORECASE)
        path = unquote(path)
        if ".." in path.split("/") or supplied.params and not supplied.params.lower().startswith(
            "jsessionid=",
        ):
            return None
        pattern = re.escape(unquote(target.path)).replace(marker, "(.+)")
        path_match = re.fullmatch(pattern, path)
        if path_match is None:
            return None
        query = parse_qs(supplied.query, keep_blank_values=True)
        required = parse_qs(target.query, keep_blank_values=True)
        identifier = path_match[1] if path_match.groups() else None
        for key, values in required.items():
            if values == [marker]:
                if len(query.get(key, [])) != 1:
                    return None
                identifier = query[key][0]
            elif key in VIEW_KEYS:
                if key in query and query[key] != values:
                    return None
            elif key not in NAVIGATION_KEYS and query.get(key) != values:
                return None
        if identifier is None or re.fullmatch(IDENTIFIERS[profile.id_format], identifier) is None:
            return None
        canonical = template.replace("{id}", identifier)
        parsed = urlparse(canonical)
        identity_url = urlunparse(parsed._replace(
            fragment="", params="", query=urlencode(sorted(
                (k, v) for k, values in parse_qs(parsed.query, keep_blank_values=True).items()
                if k not in NAVIGATION_KEYS for v in values
            )),
        ))
        identity = hashlib.sha256(json.dumps(
            [source.municipality, identity_url], ensure_ascii=False,
        ).encode()).hexdigest()
        return OriginRoute(source.slug, source.municipality, canonical, identifier, identity)

    def read(self, route: OriginRoute, *, committee_search: bool = False) -> OriginDetails:
        source = self.sources[route.source_slug]
        profile = source.html_profile
        assert profile is not None
        if not (profile.detail_title_selector and profile.detail_date_selector
                and profile.detail_body_selector):
            raise ValueError("Official detail title/date/body selectors must all be configured")
        response = None
        for attempt in range(source.max_retries):
            try:
                response = source.http_client.get_response(
                    route.canonical_url, timeout_seconds=source.timeout_seconds,
                    headers=source.request_headers, use_session=source.use_session,
                    verify_tls=source.verify_tls,
                )
                break
            except Exception:
                if attempt + 1 == source.max_retries:
                    raise
            finally:
                if source.throttle_seconds:
                    time.sleep(source.throttle_seconds)
        assert response is not None
        if not response.ok:
            raise ValueError(f"Official detail HTTP {response.status_code}")
        if urlparse(response.url).scheme != urlparse(route.canonical_url).scheme:
            raise ValueError("Official detail redirected away from its configured scheme")
        final_route = self.resolve(response.url)
        if final_route.identity_key != route.identity_key:
            raise ValueError("Official detail redirected to a different notice or board")
        candidate = parse_profiled_detail(
            response.text, url=route.canonical_url, profile=profile,
            allow_empty_body=committee_search,
        )
        if source.available_from and candidate.published_date < source.available_from:
            raise ValueError("Official notice predates the configured municipality")
        attachment = ""
        if (committee_search and committee_project_names(candidate.title, candidate.body_text)
                and classify_committee_notice(candidate.title, candidate.body_text)
                is NoticeCategory.UNKNOWN):
            for text in official_hwpx_texts(
                response.text, response.url, timeout_seconds=source.timeout_seconds,
                request_headers=source.request_headers,
            ):
                if classify_committee_notice(
                    candidate.title, candidate.body_text, text,
                ) is NoticeCategory.RECRUITMENT:
                    attachment = text
                    break
        return OriginDetails(Notice(
            id=None, municipality=route.municipality, title=candidate.title,
            url=route.canonical_url, published_date=candidate.published_date,
            fetched_at=datetime.now(source.timezone), source_type=source.source_type,
        ), candidate.body_text, attachment)
