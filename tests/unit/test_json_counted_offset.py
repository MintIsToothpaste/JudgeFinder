from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.source_profiles import EngineType, JsonProfile

PROFILE = JsonProfile(
    rows_path="items", title_key="title", date_key="date", id_key="id",
    detail_url_template="/detail?id={id}", total_path="total", page_size=1,
    page_param="page", offset_param="offset", offset_base=0,
)
URL = "https://city.example/list"


def test_counted_statusless_api_validates_each_field_and_terminal_page() -> None:
    payload = {"total": 1, "items": [
        {"title": "평가위원 모집 공고", "date": "2026-10-01", "id": 123},
    ]}
    assert len(parse_profiled_json(json.dumps(payload), list_url=URL, profile=PROFILE)) == 1
    assert parse_profiled_json(
        '{"total":1,"items":[]}', list_url=URL, profile=PROFILE, expected_page=2,
    ) == []


@pytest.mark.parametrize("raw,expected", [
    ("&apos;장비 구입&apos; 평가위원 모집", "'장비 구입' 평가위원 모집"),
    ("&quot;연구 용역&quot; 평가위원 모집", '"연구 용역" 평가위원 모집'),
    ("A&amp;B 평가위원 모집", "A&B 평가위원 모집"),
    ("&amp;quot; 평가위원 모집", "&quot; 평가위원 모집"),
    ("장비 <A> 평가위원 모집", "장비 <A> 평가위원 모집"),
])
def test_json_titles_decode_entities_once_without_stripping_literal_markup(
    raw: str, expected: str,
) -> None:
    payload = {"total": 1, "items": [{"title": raw, "date": "2026-10-01", "id": 123}]}
    actual = parse_profiled_json(json.dumps(payload), list_url=URL, profile=PROFILE)
    assert actual[0].title == expected


def test_json_entity_only_whitespace_title_is_invalid() -> None:
    payload = {"total": 1, "items": [{"title": "&nbsp;", "date": "2026-10-01", "id": 123}]}
    with pytest.raises(ValueError, match="title or registration date missing"):
        parse_profiled_json(json.dumps(payload), list_url=URL, profile=PROFILE)


@pytest.mark.parametrize("payload", [
    '{}', '<h1>Error</h1>', '{"total":1,"items":[]}', '{"total":0,"items":null}',
    '{"total":true,"items":[]}', '{"items":[]}', '{"total":0}',
])
def test_statusless_error_or_partial_response_is_not_success(payload: str) -> None:
    with pytest.raises(ValueError):
        parse_profiled_json(payload, list_url=URL, profile=PROFILE)


@pytest.mark.parametrize("options", [
    {"offset_base": True}, {"offset_base": 2}, {"offset_base": "0"},
    {"offset_param": "page"}, {"total_path": ""}, {"success_value": "OK"},
])
def test_invalid_counted_offset_configuration_is_rejected(options: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(PROFILE, **options)  # type: ignore[arg-type]


@pytest.mark.parametrize("base,expected", [(0, "1"), (1, "2")])
def test_json_offset_can_be_zero_or_one_based(base: int, expected: str) -> None:
    source = GenericEngineSource(
        slug="city", municipality="city", list_url=URL, source_type=SourceType.API,
        engine_type=EngineType.JSON_LIST_API, http_client=Mock(), timezone=ZoneInfo("Asia/Seoul"),
        json_profile=replace(PROFILE, offset_base=base),
    )
    query = parse_qs(urlparse(source._build_request_url(page_index=2)).query)
    assert query["offset"] == [expected] and query["page"] == ["2"]


def test_ignored_json_offset_is_failure_not_silent_truncation() -> None:
    http = Mock()
    http.get_text.return_value = json.dumps({"total": 2, "items": [
        {"title": "평가위원 모집", "date": "2026-10-01", "id": 123},
    ]})
    source = GenericEngineSource(
        slug="city", municipality="city", list_url=URL, source_type=SourceType.API,
        engine_type=EngineType.JSON_LIST_API, http_client=http, timezone=ZoneInfo("Asia/Seoul"),
        json_profile=PROFILE,
    )
    with pytest.raises(ValueError, match="pagination repeated"):
        source.fetch(date(2026, 10, 1))
