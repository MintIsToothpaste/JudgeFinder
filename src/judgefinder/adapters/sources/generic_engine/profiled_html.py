from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from datetime import date
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from judgefinder.adapters.sources.generic_engine.parser import (
    GenericNoticeCandidate,
    _extract_date_from_text,
)
from judgefinder.domain.notice_classification import NoticeCategory, classify_notice_title
from judgefinder.domain.source_profiles import HtmlProfile

EMPTY_TEXT = re.compile(
    r"(?:게시물|게시글|자료|데이터|데이타|검색\s*결과|등록된\s*글).*(?:없|존재하지\s*않)"
    r"|^\s*(?:결과가|등록된\s*(?:소식이|내용이)|등록/검색된\s*정보가|입력된\s*글이|검색내역이)\s*없습니다[.!]?\s*$",
)


def _registration_date(text: str, profile: HtmlProfile) -> date | None:
    if profile.two_digit_year_base is not None:
        # The board's explicitly configured century is independent of today's date.
        match = re.fullmatch(r"\s*([0-9]{2})[./-]([0-9]{1,2})[./-]([0-9]{1,2})[.]?\s*", text)
        if match:
            try:
                return date(
                    profile.two_digit_year_base + int(match[1]), int(match[2]), int(match[3]),
                )
            except ValueError:
                return None
    return _extract_date_from_text(text)


def _title_text(node: Tag, exclude_selector: str) -> str:
    if exclude_selector:
        # Exclude configured UI badges without changing the parsed document.
        node = deepcopy(node)
        for badge in node.select(exclude_selector):
            badge.decompose()
    return " ".join(node.get_text().split())


def profiled_html_total_count(payload: str, *, profile: HtmlProfile) -> int | None:
    if not profile.total_count_selector:
        return None
    nodes = BeautifulSoup(payload, "html5lib").select(profile.total_count_selector)
    if len(nodes) != 1:
        raise ValueError("HTML listing total-count element missing or ambiguous")
    text = " ".join(nodes[0].get_text(" ", strip=True).split())
    match = re.fullmatch(profile.total_count_pattern, text)
    if match is None or not re.fullmatch(r"[0-9]+", match[1]):
        raise ValueError("HTML listing total count must be a nonnegative integer")
    return int(match[1])


def parse_profiled_html(
    payload: str, *, list_url: str, profile: HtmlProfile,
    detail_loader: Callable[[str], str] | None = None,
    recruitment_only: bool = False,
    detail_not_before: date | None = None,
    expected_page: int | None = None,
) -> list[GenericNoticeCandidate]:
    # HTML5 attribute rules preserve bare query keys such as &notAncmtMgtNo.
    # html.parser incorrectly decodes their &not prefix into a NOT SIGN.
    soup = BeautifulSoup(payload, "html5lib")
    container = soup.select_one(profile.container_selector)
    if container is None:
        raise ValueError("HTML listing container missing; absence of notices is unverified")
    rows = container.select(profile.row_selector)
    total_count = profiled_html_total_count(payload, profile=profile)
    # Some boards reset or remove the pager on an explicit empty terminal page.
    # A missing/mismatched pager with real rows must still fail closed.
    if rows and all(
        EMPTY_TEXT.search(row.get_text(" ", strip=True))
        and row.name not in {"a", "button"} and not row.find(["a", "button"])
        and (row.select_one(profile.link_selector) is None if profile.link_selector
             else not row.has_attr(profile.link_attribute))
        for row in rows
    ):
        if total_count is not None and expected_page is not None and (
            (expected_page - 1) * profile.page_size < total_count
        ):
            raise ValueError("HTML empty listing contradicts reported total")
        return []
    if profile.page_number_selector and expected_page is not None:
        current = soup.select_one(profile.page_number_selector)
        text = current.get_text(strip=True) if current else ""
        if not text.isdigit() or int(text) != expected_page:
            raise ValueError("HTML listing page does not match requested page")
    if total_count is not None and expected_page is not None:
        expected_rows = min(profile.page_size, max(
            0, total_count - (expected_page - 1) * profile.page_size,
        ))
        if len(rows) != expected_rows:
            raise ValueError("HTML listing row count contradicts reported total")
    candidates: list[GenericNoticeCandidate] = []
    for index, row in enumerate(rows, start=1):
        date_node = row.select_one(profile.date_selector) if profile.date_selector else None
        listing_date_text = ""
        if date_node is not None:
            value = (
                date_node.get(profile.listing_date_attribute, "")
                if profile.listing_date_attribute else date_node.get_text(" ", strip=True)
            )
            listing_date_text = value if isinstance(value, str) else ""
        listing_date = _registration_date(listing_date_text, profile)
        before_window = (
            detail_not_before is not None and listing_date is not None
            and listing_date < detail_not_before
        )
        anchor = row.select_one(profile.link_selector) if profile.link_selector else row
        if anchor is None:
            if EMPTY_TEXT.search(row.get_text(" ", strip=True)):
                continue
            raise ValueError(f"HTML row {index}: notice link missing")
        href = anchor.get(profile.link_attribute)
        if not isinstance(href, str):
            raise ValueError(f"HTML row {index}: {profile.link_attribute} missing")
        if profile.id_pattern:
            # Explicit formats preserve strict validation without evaluating JavaScript.
            match = re.search(profile.id_pattern, href)
            identifier_pattern = (
                r"[a-fA-F0-9]{32}" if profile.id_format == "hex32"
                else r"0*[1-9][0-9]*" if profile.id_format == "zero_padded_numeric"
                else r"[1-9][0-9]*"
            )
            if match is None or re.fullmatch(identifier_pattern, match.group(1)) is None:
                # Expired legacy identifiers cannot block the requested date window.
                if before_window:
                    continue
                raise ValueError(f"HTML row {index}: unsupported notice identifier")
            href = profile.detail_url_template.replace("{id}", match.group(1))
        url = urljoin(list_url, href)
        parsed = urlparse(url)
        base = urlparse(list_url)
        # A separate public detail host must be explicitly pinned in the profile.
        origin = urlparse(profile.detail_origin) if profile.detail_origin else base
        if parsed.scheme not in {"http", "https"} or parsed.netloc != origin.netloc:
            raise ValueError(f"HTML row {index}: notice URL must stay on the configured host")
        if parsed.scheme != origin.scheme or parsed.username or parsed.password:
            raise ValueError(f"HTML row {index}: invalid notice URL origin")
        query = parsed.query
        if profile.detail_query_exclude:
            excluded = set(profile.detail_query_exclude.split(","))
            query = urlencode([
                (key, value) for key, value in parse_qsl(query, keep_blank_values=True)
                if key not in excluded
            ])
        url = urlunparse(parsed._replace(fragment="", params="", query=query))
        if url == urlunparse(base._replace(fragment="", params="")):
            raise ValueError(f"HTML row {index}: detail URL resolves to listing")
        title_node = row.select_one(profile.title_selector) if profile.title_selector else anchor
        # A clearly excluded result with a listing date needs no detail request.
        # Missing details for recruitment/ambiguous titles must still fail closed.
        listing_result = (
            recruitment_only and date_node is not None and title_node is not None
            and classify_notice_title(
                _title_text(title_node, profile.title_exclude_selector),
            ) is NoticeCategory.RESULT
        )
        detail = None
        if (profile.detail_date_selector or profile.detail_title_selector
            or profile.detail_body_selector) and not (
            listing_result or before_window
        ):
            if detail_loader is None:
                raise ValueError("HTML profile requires a detail loader")
            detail = BeautifulSoup(detail_loader(url), "html5lib")
            if profile.detail_date_selector:
                date_node = detail.select_one(profile.detail_date_selector)
            if profile.detail_title_selector:
                title_node = detail.select_one(profile.detail_title_selector)
        if title_node is None or date_node is None:
            raise ValueError(f"HTML row {index}: title or registration-date element missing")
        # Search highlighting can split a word across inline tags.
        title = _title_text(title_node, profile.title_exclude_selector)
        published_date = listing_date
        if detail is not None and profile.detail_date_selector:
            value = (
                date_node.get(profile.detail_date_attribute, "")
                if profile.detail_date_attribute else date_node.get_text(" ", strip=True)
            )
            published_date = _registration_date(value if isinstance(value, str) else "", profile)
        if not title or published_date is None:
            raise ValueError(f"HTML row {index}: invalid title or registration date")
        body_text = ""
        if (detail is not None and profile.detail_body_selector
            and classify_notice_title(title) is NoticeCategory.UNKNOWN):
            body_node = detail.select_one(profile.detail_body_selector)
            if body_node is None:
                raise ValueError(f"HTML row {index}: configured notice body missing")
            body_node = deepcopy(body_node)
            for tag in body_node.select("script,style,nav,header,footer"):
                tag.decompose()
            body_text = " ".join(body_node.get_text(" ", strip=True).split())
        candidates.append(GenericNoticeCandidate(
            title=title, url=url, published_date=published_date,
            searchable_text=f"{title} {body_text}".strip(),
            body_text=body_text,
        ))
    return candidates
