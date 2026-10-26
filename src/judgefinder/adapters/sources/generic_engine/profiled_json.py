from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from judgefinder.adapters.sources.generic_engine.parser import (
    GenericNoticeCandidate,
    _extract_date_from_text,
)
from judgefinder.domain.source_profiles import JsonProfile


def _value(data: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(data, dict) or key not in data:
            raise ValueError(f"JSON field missing: {path}")
        data = data[key]
    return data


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError(f"JSON {label} must be a nonnegative integer")
    return int(value)


def parse_profiled_json(
    payload: str, *, list_url: str, profile: JsonProfile, expected_page: int = 1,
) -> list[GenericNoticeCandidate]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("JSON listing response is not valid JSON") from exc
    if profile.status_path and _value(data, profile.status_path) != profile.success_value:
        raise ValueError("JSON listing response reports failure")
    rows = _value(data, profile.rows_path)
    if not isinstance(rows, list):
        raise ValueError("JSON listing rows must be an array")
    if profile.page_path and _integer(_value(data, profile.page_path), "page") != expected_page:
        raise ValueError("JSON listing page does not match requested page")
    if profile.total_path:
        total = _integer(_value(data, profile.total_path), "total")
        expected_rows = min(profile.page_size, max(0, total - (expected_page - 1) *
                                                  profile.page_size))
        if len(rows) != expected_rows:
            raise ValueError("JSON listing row count contradicts reported total")
    candidates = []
    base = urlparse(list_url)
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"JSON row {index}: object required")
        title, raw_date, identifier = (
            row.get(profile.title_key), row.get(profile.date_key), row.get(profile.id_key),
        )
        if not isinstance(title, str) or not title.strip() or not isinstance(raw_date, str):
            raise ValueError(f"JSON row {index}: title or registration date missing")
        published = _extract_date_from_text(raw_date)
        if published is None or not re.fullmatch(r"[1-9][0-9]*", str(identifier)):
            raise ValueError(f"JSON row {index}: invalid date or numeric notice identifier")
        url = urljoin(list_url, profile.detail_url_template.replace("{id}", str(identifier)))
        parsed = urlparse(url)
        if (parsed.scheme not in {"http", "https"} or parsed.scheme != base.scheme
                or parsed.netloc != base.netloc or parsed.username or parsed.password):
            raise ValueError(f"JSON row {index}: detail URL must stay on configured origin")
        url = urlunparse(parsed._replace(fragment="", params=""))
        if url == urlunparse(base._replace(fragment="", params="")):
            raise ValueError(f"JSON row {index}: detail URL resolves to listing")
        title = " ".join(unescape(title).split())
        if not title:
            raise ValueError(f"JSON row {index}: title or registration date missing")
        candidates.append(GenericNoticeCandidate(
            title=title, published_date=published, url=url, searchable_text=title,
        ))
    return candidates
