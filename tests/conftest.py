from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup

from judgefinder.adapters.config import load_config
from judgefinder.infrastructure.http.client import RequestsHttpClient

ROOT = Path(__file__).parents[1]
RECOVERED_BOARDS = {
    slug: case
    for filename in (
        "cafe_20261022_profiles.json", "cafe_20261021_profiles.json",
        "cafe_20261029_profiles.json",
    )
    for slug, case in json.loads(
        (ROOT / "tests/fixtures" / filename).read_text(encoding="utf-8"),
    ).items()
}


@pytest.fixture(params=sorted(RECOVERED_BOARDS))
def recovered_board_case(request: pytest.FixtureRequest) -> dict[str, str]:
    slug = str(request.param)
    return {"slug": slug, **RECOVERED_BOARDS[slug]}


@pytest.fixture
def recovered_board_http(
    recovered_board_case: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Share captured board responses between parser/source and CLI tests."""
    case = recovered_board_case
    config = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    profile = config.html_profile
    assert profile is not None
    calls: list[str] = []

    def response(self: RequestsHttpClient, url: str, **kwargs: object) -> str:
        assert kwargs["verify_tls"] and kwargs["use_session"]
        calls.append(url)
        if url == case["url"]:
            return case["detail_html"]
        query = parse_qs(urlparse(url).query)
        if profile.search_param:
            assert query[profile.search_param] == ["평가위원"]
        page = (
            int(urlparse(url).path.rsplit("/", 1)[1])
            if profile.page_path_template else int(query[profile.page_param][0])
        )
        assert page in {1, 2}
        if page == 1:
            return case["list_html"]
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        for row in container.select(profile.row_selector):
            row.decompose()
        if profile.page_number_selector:
            current = soup.select_one(profile.page_number_selector)
            assert current is not None
            current.string = "2"
        return str(soup)

    monkeypatch.setattr(RequestsHttpClient, "get_text", response)
    return calls
