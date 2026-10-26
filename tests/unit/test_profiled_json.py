from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.source_profiles import JsonProfile

PROFILE = JsonProfile(
    rows_path="data.rows", title_key="title", date_key="date", id_key="id",
    detail_url_template="/notice?id={id}", status_path="status", success_value="OK",
    total_path="total", page_path="page", page_param="page", offset_param="offset",
)
URL = "https://city.example/list?size=10"


def payload() -> dict[str, object]:
    return {"status": "OK", "total": 1, "page": 1, "data": {"rows": [
        {"title": "평가위원(후보자) 모집 공고", "date": "2026.09.22", "id": "123"},
    ]}}


def test_explicit_fields_supply_full_title_registration_date_and_safe_url() -> None:
    actual = parse_profiled_json(json.dumps(payload()), list_url=URL, profile=PROFILE)
    assert [(n.title, n.published_date, n.url) for n in actual] == [
        ("평가위원(후보자) 모집 공고", date(2026, 9, 22), "https://city.example/notice?id=123"),
    ]


@pytest.mark.parametrize("value", ["<h1>FORBIDDEN</h1>", "{", "null", "[]", "{}"])
def test_http_200_errors_are_not_empty_search_results(value: str) -> None:
    with pytest.raises(ValueError):
        parse_profiled_json(value, list_url=URL, profile=PROFILE)


@pytest.mark.parametrize("key,value", [
    ("status", "FAIL"), ("status", 0), ("total", True), ("total", -1),
    ("total", "unknown"), ("total", 0), ("total", 2), ("page", 2), ("page", True),
    ("data", {"rows": None}), ("data", {}), ("data", {"rows": [None]}),
    ("data", {"rows": []}),
])
def test_failed_status_missing_fields_and_contradictory_counts_fail_closed(
    key: str, value: object,
) -> None:
    data = payload()
    data[key] = value
    with pytest.raises(ValueError):
        parse_profiled_json(json.dumps(data), list_url=URL, profile=PROFILE)


@pytest.mark.parametrize("key,value", [
    ("title", ""), ("title", None), ("date", "12:34"), ("date", 20260922),
    ("date", "2026-02-30"), ("id", 0), ("id", True), ("id", "1&admin=true"),
    ("id", "javascript:alert(1)"),
])
def test_invalid_row_is_not_silently_discarded(key: str, value: object) -> None:
    row: dict[str, object] = {"title": "평가위원 모집", "date": "2026-09-22", "id": 1}
    row[key] = value
    data = payload()
    data["data"] = {"rows": [row]}
    with pytest.raises(ValueError):
        parse_profiled_json(json.dumps(data), list_url=URL, profile=PROFILE)


@pytest.mark.parametrize("template", [
    "https://outside.example/{id}", "http://city.example/{id}",
    "https://name:password@city.example/{id}", "javascript:{id}",
])
def test_detail_urls_cannot_escape_configured_origin(template: str) -> None:
    with pytest.raises(ValueError, match="origin"):
        parse_profiled_json(
            json.dumps(payload()), list_url=URL,
            profile=replace(PROFILE, detail_url_template=template),
        )


def test_verified_zero_and_past_last_page_are_allowed() -> None:
    data = payload()
    data.update(total=0, data={"rows": []})
    assert parse_profiled_json(json.dumps(data), list_url=URL, profile=PROFILE) == []
    data.update(total=1, page=2)
    assert parse_profiled_json(
        json.dumps(data), list_url=URL, profile=PROFILE, expected_page=2,
    ) == []


@pytest.mark.parametrize("changes", [
    {"rows_path": "data..rows"}, {"status_path": ""}, {"detail_url_template": "/detail"},
    {"detail_url_template": "/{id}/{other}"}, {"page_size": True}, {"page_size": 0},
    {"page_param": ""}, {"request_method": "DELETE"}, {"request_encoding": "bad"},
])
def test_invalid_profiles_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(PROFILE, **changes)  # type: ignore[arg-type]


def test_config_and_registry_preserve_real_api_offset_pagination() -> None:
    root = Path(__file__).parents[2]
    settings = load_config(root / "config/batch-jeonnam-gwangju-ten.example.toml")
    source = next(s for s in SourceRegistry(settings, Mock(), ZoneInfo("Asia/Seoul"))
        .build_enabled_sources() if s.slug == "damyang")
    assert isinstance(source, GenericEngineSource) and source.json_profile is not None
    query = parse_qs(urlparse(source._build_request_url(page_index=2)).query)
    assert query["CUR_PAGE_IDX"] == ["2"] and query["BEGIN_ROW_IDX"] == ["11"]
    assert query["ROW_CNT"] == ["10"] and query["searchVal"] == ["평가위원"]
    assert query["searchKey"] == ["B_Subject"] and query["listGubun"] == ["A"]


@pytest.mark.parametrize("profile_text", [
    'json_profile = "invalid"',
    '[json_profile]\nrows_path = "data.rows"',
    '[json_profile]\nunknown = "value"',
])
def test_invalid_json_config_is_rejected(tmp_path: Path, profile_text: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'timezone="Asia/Seoul"\ndb_path="notices.db"\nenabled_sources=["city"]\n'
        '[sources.city]\nmunicipality="city"\nsource_type="api"\n'
        'list_url="https://city.example/list"\n'
        + profile_text.replace("[json_profile]", "[sources.city.json_profile]"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_config(path)
