from __future__ import annotations

from datetime import date
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.source_profiles import EngineType, HtmlProfile, JsonProfile


@pytest.mark.parametrize("profiled", [False, True])
def test_html_sources_request_html_instead_of_negotiating_json(profiled: bool) -> None:
    client = Mock()

    def response(url: str, **kwargs: object) -> str:
        headers = kwargs["headers"]
        assert isinstance(headers, dict)
        assert headers["Accept"].split(",")[0] == "text/html"
        if "pageIndex=1" in url:
            return (
                "<table><tr><td>2026-10-05</td><td>"
                "<a href='/www/selectBbsNttView.do?bbsNo=18&amp;nttNo=7001'>evaluator</a>"
                "</td></tr></table>"
            )
        return "<table></table>"

    client.get_text.side_effect = response
    source = GenericEngineSource(
        slug="city", municipality="City", source_type=SourceType.HTML,
        list_url="https://city.go.kr/list", engine_type=EngineType.GENERIC_EGOV_BBS,
        timezone=ZoneInfo("Asia/Seoul"), http_client=client, keywords=("evaluator",),
        html_profile=HtmlProfile(
            container_selector="table", row_selector="tbody tr",
            date_selector="td:first-child", link_selector="a",
        ) if profiled else None,
    )
    assert len(source.fetch(date(2026, 10, 5))) == 1


@pytest.mark.parametrize("profiled", [False, True])
def test_json_apis_keep_json_as_the_preferred_representation(profiled: bool) -> None:
    source = GenericEngineSource(
        slug="api", municipality="City", source_type=SourceType.API,
        list_url="https://city.go.kr/api", engine_type=EngineType.JSON_LIST_API,
        timezone=ZoneInfo("Asia/Seoul"), http_client=Mock(),
        json_profile=JsonProfile(
            rows_path="rows", title_key="title", date_key="date", id_key="id",
            detail_url_template="/view?id={id}", total_path="total",
        ) if profiled else None,
    )
    assert source.request_headers["Accept"].split(",")[0] == "application/json"
